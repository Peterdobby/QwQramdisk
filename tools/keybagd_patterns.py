"""Analyze the iOS 9.3 keybagd layout; emit a reviewable candidate, not approval.

New source hashes must still be reviewed and registered before device use.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from .offsetfinder import (MachOArm64, NOP, branch_target, encode_b,
                           find_all, is_bl, read_word, unique)


def _imports(data, finder):
    """Resolve arm64 symbol stubs using Mach-O indirect-symbol metadata."""
    if len(data) < 32 or data[:8] != bytes.fromhex("cffaedfe0c000001"):
        raise ValueError("expected an arm64 Mach-O")
    count, command_bytes = struct.unpack_from("<II", data, 16)
    end, off = 32 + command_bytes, 32
    if end > len(data) or count > 1024:
        raise ValueError("invalid Mach-O load commands")
    symbols = indirect = None
    stubs = []
    for _ in range(count):
        if off + 8 > end:
            raise ValueError("truncated load command")
        cmd, size = struct.unpack_from("<II", data, off)
        if size < 8 or off + size > end:
            raise ValueError("invalid load command size")
        if cmd == 2 and size >= 24:
            symbols = struct.unpack_from("<IIII", data, off + 8)
        if cmd == 0xb and size >= 80:
            indirect = struct.unpack_from("<II", data, off + 56)
        if cmd == 0x19 and size >= 72:
            sections = struct.unpack_from("<I", data, off + 64)[0]
            if 72 + sections * 80 > size:
                raise ValueError("truncated section table")
            for i in range(sections):
                section = off + 72 + i * 80
                address, length = struct.unpack_from("<QQ", data, section + 32)
                flags, first, stride = struct.unpack_from("<III", data, section + 64)
                if flags & 0xff == 8:
                    stubs.append((address, length, first, stride))
        off += size
    if not symbols or not indirect:
        raise ValueError("missing imported-symbol metadata")
    symoff, nsyms, stroff, strsize = symbols
    indoff, nindirect = indirect
    if (symoff + nsyms * 16 > len(data) or stroff + strsize > len(data)
            or indoff + nindirect * 4 > len(data)):
        raise ValueError("invalid symbol table bounds")
    result = {}
    for address, length, first, stride in stubs:
        if not stride or length % stride or first + length // stride > nindirect:
            raise ValueError("invalid stub table")
        for index in range(length // stride):
            symbol = struct.unpack_from("<I", data, indoff + 4 * (first + index))[0]
            if symbol & 0xc0000000:
                continue
            if symbol >= nsyms:
                raise ValueError("invalid indirect symbol index")
            nameoff = struct.unpack_from("<I", data, symoff + symbol * 16)[0]
            nul = data.find(b"\0", stroff + nameoff, stroff + strsize)
            if nameoff >= strsize or nul < 0:
                raise ValueError("invalid imported symbol name")
            name = data[stroff + nameoff:nul].decode("ascii")
            result.setdefault(name, []).append(finder.va_to_offset(address + index * stride))
    return result


def analyze(data, build):
    if not re.fullmatch(r"13[A-Z][0-9]+", build):
        raise ValueError("invalid iOS 9 build label")
    finder = MachOArm64(data)
    imports = _imports(data, finder)
    reboot = unique(imports.get("_reboot", []), "reboot import")
    exit_stub = unique(imports.get("_exit", []), "exit import")

    def reference(text):
        return unique((ref for ref, _, _ in finder.string_refs(text)), text.decode())

    def called(off):
        word = read_word(data, off)
        if not is_bl(word):
            raise ValueError(f"expected call at 0x{off:x}")
        return finder.va_to_offset(branch_target(word, finder.offset_to_va(off)))

    auto_boot = reference(b"auto-boot")
    fatality = reference(b"fatality")
    if not 0 < auto_boot - fatality < 0x80:
        raise ValueError("auto-boot write is outside the expected fatal handler")
    writes = (auto_boot - 4, auto_boot + 16)
    if called(writes[0]) != called(writes[1]):
        raise ValueError("fatal NVRAM calls do not use the same writer")
    reboot_calls = [off for off in range(auto_boot + 20, auto_boot + 0x100, 4)
                    if is_bl(read_word(data, off)) and called(off) == reboot]
    reboot_call = unique(reboot_calls, "fatal reboot call")
    if (read_word(data, reboot_call - 4) != 0x52800000
            or read_word(data, reboot_call + 4) != 0x528008e0
            or called(reboot_call + 8) != exit_stub):
        raise ValueError("fatal reboot/exit control flow changed")

    init = reference(b"****** IN MKB_INIT ****\n")
    early = reference(b"****** STARTING EARLYBOOT SETUP ****\n") - 4
    done = reference(b"****** DONE MKB_INIT ****\n")
    if read_word(data, early) != 0xf94002c3:
        raise ValueError("earlyboot block no longer starts with the expected stdout load")
    compare = bytes.fromhex("0800bc52085e80721f00086b")
    branches = [off + 12 for off in find_all(data, compare)
                if init < off < init + 0x100 and off % 4 == 0]
    load_branch = unique(branches, "system-handle comparison")
    word = read_word(data, load_branch)
    if (word & 0xff00001f != 0x54000001
            or finder.va_to_offset(branch_target(word, finder.offset_to_va(load_branch))) != early
            or not is_bl(read_word(data, load_branch - 16))):
        raise ValueError("systembag load-skip branch changed")
    exits = [off for off in range(done + 4, done + 0x40, 4)
             if read_word(data, off) == 0x52800000
             and is_bl(read_word(data, off + 4)) and called(off + 4) == exit_stub]
    clean_exit = unique(exits, "successful init exit")
    if not init < load_branch < early < done < clean_exit:
        raise ValueError("unexpected init control-flow ordering")
    patches = []
    for off, after, note in [
        (writes[0], NOP, "disable fatal NVRAM diagnostic write"),
        (writes[1], NOP, "disable fatal auto-boot write"),
        (reboot_call, NOP, "disable fatal reboot"),
        (load_branch, NOP, "always load Data systembag"),
        (early, encode_b(finder.offset_to_va(early), finder.offset_to_va(clean_exit)),
         "exit init before earlyboot and user-session setup"),
    ]:
        patches.append({"offset": off, "before": data[off:off + 4].hex(),
                        "after": after.hex(), "note": note})
    count = data.count(b"/private/var")
    if not count:
        raise ValueError("no Data path anchors")
    result = bytearray(data.replace(b"/private/var", b"/mnt2//././."))
    for patch in patches:
        off = patch["offset"]
        if result[off:off + 4] != bytes.fromhex(patch["before"]):
            raise ValueError("path relocation overlaps an instruction patch")
        result[off:off + 4] = bytes.fromhex(patch["after"])
    return {"build": build, "size": len(data), "paths": count,
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "result_sha256": hashlib.sha256(result).hexdigest(), "patches": patches,
            "analysis": "iOS 9.3 layout candidate; requires review and device validation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--build", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = analyze(args.source.read_bytes(), args.build)
    document = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.write_text(document)
    print(document, end="")


if __name__ == "__main__":
    main()

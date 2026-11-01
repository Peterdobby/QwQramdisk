"""Rebuild and ad-hoc sign the iOS 9 helpers on macOS before packaging.

The normal create command consumes these prepared assets without signing.
Upstream AMFI reference: j1ans/QwQramdisk commit 018b3cacab01.
"""
import os
import hashlib
import subprocess
import tarfile
import tempfile
from pathlib import Path
from .keybagd_registry import generate_header

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.uname().sysname != "Darwin":
        raise SystemExit("Preparing signed helpers requires macOS and Xcode")
    generate_header(ROOT / "ramdisk/keybagd-profiles.json",
                    ROOT / "ramdisk/keybagd-profiles.h")
    with tempfile.TemporaryDirectory(prefix="qwq-helpers-") as directory:
        temporary = Path(directory)
        patcher = temporary / "patch-keybagd-ios9"
        resources = {
            "find-ios9": "./usr/bin/find",
            "grep-ios9": "./usr/bin/grep",
            "chmod-ios9": "./bin/chmod",
            "cp-ios9": "./bin/cp",
            "chown-ios9": "./usr/sbin/chown",
            "sleep-ios9": "./bin/sleep",
            "scp-ios9": "./usr/bin/scp",
            "sftp-server-ios9": "./usr/libexec/sftp-server",
        }
        subprocess.run([
            "xcrun", "--sdk", "iphoneos", "clang", "-target", "arm64-apple-ios9.0",
            "-O2", "-Wno-deprecated-declarations",
            str(ROOT / "ramdisk/patch-keybagd-ios9.c"), "-o", str(patcher),
        ], check=True)
        # The newer bundled ls imports clock_gettime (iOS 10+) and cannot
        # run on 13D15. Build the older Apple/BSD implementation for iOS 9.
        ls = temporary / "ls-ios9"
        ls_root = ROOT / "vendor/src/file_cmds-220.7"
        subprocess.run([
            "xcrun", "--sdk", "iphoneos", "clang", "-target", "arm64-apple-ios9.0",
            "-O2", "-Wno-deprecated-non-prototype", "-I", str(ls_root / "compat"),
            *(str(ls_root / "ls" / name) for name in ("ls.c", "cmp.c", "print.c", "util.c")),
            str(ls_root / "compat/humanize_number.c"), "-o", str(ls),
        ], check=True)
        with tarfile.open(ROOT / "vendor/resources/iram.tar") as archive:
            for name, member in resources.items():
                with archive.extractfile(member) as source:
                    (temporary / name).write_bytes(source.read())
        storage = temporary / "ensure-asp-writable-ios9"
        subprocess.run([
            "xcrun", "--sdk", "iphoneos", "clang", "-target", "arm64-apple-ios9.0",
            "-O2", "-Wall", "-Wextra",
            str(ROOT / "ramdisk/ensure-asp-writable-ios9.c"),
            "-framework", "CoreFoundation", "-framework", "IOKit", "-o", str(storage),
        ], check=True)
        helpers = [patcher, ls, storage, *(temporary / name for name in resources)]
        for source in helpers:
            # A SHA-1 CodeDirectory is compatible with the tested 13D15 loader.
            entitlements = (["--entitlements", str(ROOT / "ramdisk/asp-storage-entitlements.plist")]
                            if source == storage else [])
            subprocess.run(["codesign", "--force", "--sign", "-",
                            "--digest-algorithm=sha1", *entitlements, str(source)], check=True)
            subprocess.run(["codesign", "--verify", str(source)], check=True)
        for source in helpers:
            target = ROOT / "ramdisk" / source.name
            target.write_bytes(source.read_bytes())
            target.chmod(0o755)
            print("Prepared signed helper:", target)
        checksums = []
        for source in sorted(helpers):
            target = ROOT / "ramdisk" / source.name
            checksums.append(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  "
                             f"ramdisk/{source.name}\n")
        (ROOT / "ramdisk/SHA256SUMS").write_text("".join(checksums))


if __name__ == "__main__":
    main()

"""Edit the requested MobileGestalt cache flag through a booted ramdisk."""
from datetime import datetime
import plistlib
import shlex
import tempfile
from pathlib import Path, PurePosixPath

from .activation import (_chown_id, _preflight, list_tree, scp_pull,
                         sftp_push_tree, ssh_run)

PLIST_REMOTE = "/mnt2/mobile/Library/Caches/com.apple.MobileGestalt.plist"
ACTIVATION_KEY = "a6vjpkzcrjrsxmnifsm0dg"


def patched_plist(original):
    """Preserve the plist format and all values except the requested flag."""
    try:
        document = plistlib.loads(original)
    except (ValueError, TypeError) as exc:
        raise ValueError("MobileGestalt cache is not a valid plist") from exc
    if not isinstance(document, dict):
        raise ValueError("MobileGestalt plist root must be a dictionary")
    extra = document.get("CacheExtra", {})
    if not isinstance(extra, dict):
        raise ValueError("CacheExtra must be a dictionary; refusing to replace it")
    if extra.get(ACTIVATION_KEY) is True:
        return original, False
    extra[ACTIVATION_KEY] = True
    document["CacheExtra"] = extra
    fmt = plistlib.FMT_BINARY if original.startswith(b"bplist00") else plistlib.FMT_XML
    return plistlib.dumps(document, fmt=fmt, sort_keys=False), True


def _read(kit_root, port, remote, directory):
    rows = list_tree(kit_root, port, remote)
    if len(rows) != 1 or rows[0][0] != "" or rows[0][-1]:
        raise RuntimeError(f"expected a regular plist file: {remote}")
    _, mode, uid, gid, size, _ = rows[0]
    directory.mkdir(parents=True, exist_ok=True)
    scp_pull(kit_root, port, remote, directory, recursive=False)
    local = directory / PurePosixPath(remote).name
    local.chmod(local.stat().st_mode | 0o400)
    data = local.read_bytes()
    if len(data) != size:
        raise RuntimeError(f"downloaded plist size does not match {remote}")
    return data, (mode, uid, gid)


def patch_activation(kit_root, port=2236):
    _preflight(kit_root, port, "patching the MobileGestalt cache")
    target = PLIST_REMOTE
    quoted = shlex.quote(target)
    exists = ssh_run(kit_root, port,
                     f'if [ -f {quoted} ] && [ ! -L {quoted} ]; then '
                     'printf yes; else printf no; fi').strip()
    if exists != "yes":
        raise RuntimeError(f"MobileGestalt cache is missing or is a symlink: {target}")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    backup = target + ".bak-" + stamp
    temporary = target + ".qwq-" + stamp
    report = {"path": target, "key": ACTIVATION_KEY, "value": True,
              "changed": False, "backup": None}
    with tempfile.TemporaryDirectory(prefix="qwq-mobilegestalt-") as directory:
        local = Path(directory)
        original, metadata = _read(kit_root, port, target, local / "original")
        patched, changed = patched_plist(original)
        if not changed:
            return report
        mode, uid, gid = metadata
        upload = local / "upload"
        upload.mkdir()
        (upload / PurePosixPath(temporary).name).write_bytes(patched)
        try:
            sftp_push_tree(kit_root, port, upload, str(PurePosixPath(target).parent),
                           [], [PurePosixPath(temporary).name])
            ssh_run(kit_root, port,
                    f'set -e; chown {_chown_id(uid)}:{_chown_id(gid)} {shlex.quote(temporary)}; '
                    f'chmod {mode:o} {shlex.quote(temporary)}')
            staged, staged_metadata = _read(kit_root, port, temporary, local / "staged")
            if staged != patched or staged_metadata != metadata:
                raise RuntimeError("staged MobileGestalt plist verification failed")
            ssh_run(kit_root, port,
                    f'set -e; test ! -e {shlex.quote(backup)}; '
                    f'cp -p {quoted} {shlex.quote(backup)}')
            saved, saved_metadata = _read(kit_root, port, backup, local / "backup")
            if saved != original or saved_metadata != metadata:
                raise RuntimeError("MobileGestalt cache changed while editing; original not overwritten")
            ssh_run(kit_root, port, f'mv -f {shlex.quote(temporary)} {quoted}')
            landed, landed_metadata = _read(kit_root, port, target, local / "verify")
            if landed != patched or landed_metadata != metadata:
                raise RuntimeError(f"MobileGestalt verification failed; original backup: {backup}")
            report.update(changed=True, backup=backup)
            return report
        finally:
            try:
                ssh_run(kit_root, port, f'rm -f {shlex.quote(temporary)}')
            except RuntimeError:
                # A disconnected transport must not hide the original error.
                # After a verified rename, this temporary path no longer exists.
                pass

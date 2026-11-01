"""Offline acceptance checks for iOS 9 ramdisk artifacts.

Run from the project root: python3 -m tools.verify_ios9 --profile n66m-13F69
This never connects to or modifies a device.
"""
import argparse
import json
import tempfile
from pathlib import Path

from .boot import verify
from .build import cached_components, verify_hfs_file
from .common import kit_bin, run, sha256
from .ios9_pattern import bootargs_for_profile
from .profiles import get_profile
from .profiles import PROFILES


ROOT = Path(__file__).resolve().parents[1]


def check(profile, cache, output, kit):
    manifest = verify(output)
    if manifest["profile"] != profile:
        raise ValueError("output manifest belongs to a different profile")
    firmware, _, _ = cached_components(cache, profile)
    if any(manifest["firmware"].get(k) != firmware[k]
           for k in ("identifier", "version", "buildid")):
        raise ValueError("output firmware identity does not match cache")
    img4, hfsplus = kit_bin(kit, "img4"), kit_bin(kit, "hfsplus")
    with tempfile.TemporaryDirectory(prefix="qwq-ios921-") as temporary:
        scratch = Path(temporary)
        # Inspect the wrapped image that will actually be sent over USB.
        image = scratch / "ramdisk.dmg"
        run([img4, "-i", output / "RestoreRamdisk.img4", "-o", image])
        if sha256(image) != sha256(output / "ramdisk.dmg"):
            raise ValueError("wrapped ramdisk differs from working filesystem")
        marker = scratch / "profile.txt"
        marker.write_text(profile + "\n")
        storage_marker = scratch / "storage-mode.txt"
        storage_marker.write_text(get_profile(profile).get("ios9_storage_mode", "stock") + "\n")
        files = {
            "usr/local/libexec/ensure-asp-writable-ios9": ROOT / "ramdisk/ensure-asp-writable-ios9",
            "private/var/tmp/ios9-storage-mode.txt": storage_marker,
            "bin/sleep": ROOT / "ramdisk/sleep-ios9",
            "usr/bin/find": ROOT / "ramdisk/find-ios9",
            "usr/bin/grep": ROOT / "ramdisk/grep-ios9",
            "bin/chmod": ROOT / "ramdisk/chmod-ios9",
            "bin/cp": ROOT / "ramdisk/cp-ios9",
            "usr/sbin/chown": ROOT / "ramdisk/chown-ios9",
            "bin/ls": ROOT / "ramdisk/ls-ios9",
            "bin/mount": ROOT / "ramdisk/mount-ios9",
            "usr/bin/scp": ROOT / "ramdisk/scp-ios9",
            "usr/libexec/sftp-server": ROOT / "ramdisk/sftp-server-ios9",
            "private/var/tmp/ios9-profile.txt": marker,
            "usr/local/bin/mount-mnt2": ROOT / "ramdisk/mount-mnt2",
            "usr/local/bin/mount-ios9-stage": ROOT / "ramdisk/mount-ios9-stage",
            "usr/local/bin/finish-ios9-keybagd": ROOT / "ramdisk/finish-ios9-keybagd",
            "usr/local/libexec/patch-keybagd-ios9": ROOT / "ramdisk/patch-keybagd-ios9",
            "private/var/tmp/com.apple.mobile.keybagd-ios9.plist":
                ROOT / "ramdisk/com.apple.mobile.keybagd-ios9.plist",
        }
        for source, target in (("sh", "bin/sh"), ("bash", "bin/bash"),
                               ("launchctl", "bin/launchctl"),
                               ("dropbear", "usr/local/bin/dropbear"),
                               ("restored_external", "usr/local/bin/restored_external")):
            files[target] = kit / "resources/ios9-sshrd" / source
        for target, source in files.items():
            verify_hfs_file(hfsplus, image, target, source, scratch / "extracted")
        stages = {}
        for stage in ("iBSS", "iBEC"):
            patch = json.loads((output / (stage + ".patch.json")).read_text())
            raw = output / "raw" / (stage + ".raw")
            if sha256(raw) != patch["output_sha256"]:
                raise ValueError(f"{stage} patched payload digest mismatch")
            payload = scratch / (stage + ".raw")
            run([img4, "-i", output / (stage + ".im4p"), "-o", payload])
            if sha256(payload) != sha256(raw):
                raise ValueError(f"{stage} wrapped payload mismatch")
            if stage == "iBEC" and bootargs_for_profile(profile) not in payload.read_bytes():
                raise ValueError("iBEC is missing the current ramdisk boot arguments")
            stages[stage] = len(patch["patches"])
    return {
        "profile": profile,
        "status": "offline-verified; device testing required",
        "firmware_components": "BuildManifest identity and SHA-1 passed",
        "artifacts": manifest["artifacts"],
        "wrapped_bootchain_patch_counts": stages,
        "boot_arguments": bootargs_for_profile(profile).rstrip(b"\0").decode("ascii"),
        "wrapped_ramdisk_files_verified": sorted(files),
        "device_boot": "not tested", "ssh": "not tested", "mnt2_rw": "not tested",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True,
                        choices=tuple(name for name, p in PROFILES.items() if p["version"].startswith("9.")))
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--kit", type=Path, default=ROOT / "vendor")
    parser.add_argument("--report", type=Path, help="save a JSON acceptance report")
    args = parser.parse_args()
    report = check(args.profile, args.cache or ROOT / "cache" / args.profile,
                   args.output or ROOT / "output" / args.profile, args.kit)
    document = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(document)
    print(document, end="")


if __name__ == "__main__":
    main()

import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.keybagd_patterns import analyze
from tools.keybagd_registry import generate_header
from tools.offsetfinder import adr_target, branch_target, read_word

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(os.environ.get("QWQ_KEYBAGD_SAMPLE", ROOT / "cache/n66m-13F69/keybagd.system"))
EARLY_SAMPLE = Path(os.environ.get("QWQ_KEYBAGD_EARLY_SAMPLE", ROOT / "cache/n71m-13A452/keybagd.system"))
IOS91_SAMPLE = Path(os.environ.get("QWQ_KEYBAGD_IOS91_SAMPLE", ROOT / "cache/n71m-13B143/keybagd.system"))


@unittest.skipUnless(EARLY_SAMPLE.is_file(), "local 9.0.2 diagnostic sample not available")
class EarlyLoggingChecks(unittest.TestCase):
    def test_ios91_uses_identical_code_and_imports(self):
        source = IOS91_SAMPLE
        if not source.is_file():
            self.skipTest("local iOS 9.1 diagnostic sample not available")
        early, ios91 = EARLY_SAMPLE.read_bytes(), source.read_bytes()
        # Reviewed Mach-O code, stub, string and data sections are identical.
        self.assertEqual(early[0x3340:0x17568], ios91[0x3340:0x17568])
        self._check_success_log(source)

    def test_success_log_changes_leave_error_guards_intact(self):
        self._check_success_log(EARLY_SAMPLE)

    def _check_success_log(self, sample):
        import hashlib
        source = sample.read_bytes()
        registry = json.loads((ROOT / "ramdisk/keybagd-profiles.json").read_text())
        profile = next(p for p in registry["profiles"]
                       if p["source_sha256"] == hashlib.sha256(source).hexdigest())
        self.assertEqual(len(profile["patches"]), 6)
        output = bytearray(source.replace(b"/private/var", b"/mnt2//././."))
        for p in profile["patches"]:
            offset = p["offset"]
            self.assertEqual(output[offset:offset + 4].hex(), p["before"])
            output[offset:offset + 4] = bytes.fromhex(p["after"])
        self.assertEqual(output[0x4c94:0x4c98], source[0x4c94:0x4c98])
        self.assertEqual(output[0x4cac:0x4cb0], source[0x4cac:0x4cb0])
        string = adr_target(read_word(output, 0x4cb0), 0x4cb0)
        marker = b"System Keybag loaded\0"
        self.assertEqual(output[string:string + len(marker)], marker)
        self.assertEqual(branch_target(read_word(output, 0x4cc0), 0x4cc0), 0x10a68)
        self.assertEqual(hashlib.sha256(output).hexdigest(), profile["result_sha256"])


@unittest.skipUnless(SAMPLE.is_file(), "local 13F69 sample not available")
class PatternChecks(unittest.TestCase):
    def test_detected_plan_matches_reviewed_registry(self):
        candidate = analyze(SAMPLE.read_bytes(), "13F69")
        registry = json.loads((ROOT / "ramdisk/keybagd-profiles.json").read_text())
        reviewed = next(p for p in registry["profiles"] if p["build"] == "13F69")
        for field in ("size", "paths", "source_sha256", "result_sha256"):
            self.assertEqual(candidate[field], reviewed[field])
        strip_notes = lambda rows: [{k: row[k] for k in ("offset", "before", "after")}
                                   for row in rows]
        self.assertEqual(strip_notes(candidate["patches"]), reviewed["patches"])

    def test_changed_systembag_branch_is_rejected(self):
        data = bytearray(SAMPLE.read_bytes())
        data[0x1b36c:0x1b370] = bytes.fromhex("1f2003d5")
        with self.assertRaisesRegex(ValueError, "systembag load-skip branch"):
            analyze(bytes(data), "13F69")

    def test_changed_reboot_import_is_rejected(self):
        data = SAMPLE.read_bytes().replace(b"_reboot\0", b"_xexoot\0")
        with self.assertRaisesRegex(ValueError, "reboot import"):
            analyze(data, "13F69")


class RegistryChecks(unittest.TestCase):
    def test_duplicate_source_hash_is_rejected(self):
        registry = json.loads((ROOT / "ramdisk/keybagd-profiles.json").read_text())
        registry["profiles"].append(dict(registry["profiles"][0]))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "registry.json"
            source.write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError, "duplicate keybagd source hash"):
                generate_header(source, Path(directory) / "profiles.h")

    def test_out_of_bounds_patch_is_rejected(self):
        registry = json.loads((ROOT / "ramdisk/keybagd-profiles.json").read_text())
        registry["profiles"][0]["patches"][0]["offset"] = 0x10000000
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "registry.json"
            source.write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError, "patch offset"):
                generate_header(source, Path(directory) / "profiles.h")


if __name__ == "__main__":
    unittest.main()

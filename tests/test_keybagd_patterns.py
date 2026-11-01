import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.keybagd_patterns import analyze
from tools.keybagd_registry import generate_header

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(os.environ.get("QWQ_KEYBAGD_SAMPLE", ROOT / "cache/n66m-13F69/keybagd.system"))


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

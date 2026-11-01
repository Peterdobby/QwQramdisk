import plistlib
import unittest
import shlex
from unittest.mock import patch

from tools import activation_patch as module
from tools.activation_patch import ACTIVATION_KEY, patched_plist


class MobileGestaltPatchTests(unittest.TestCase):
    def test_preserves_other_values_and_format(self):
        for fmt in (plistlib.FMT_BINARY, plistlib.FMT_XML):
            with self.subTest(fmt=fmt):
                original = {"CacheExtra": {"other": b"unchanged", ACTIVATION_KEY: False},
                            "unrelated": ["value", 42]}
                raw = plistlib.dumps(original, fmt=fmt)
                result, changed = patched_plist(raw)
                expected = {"CacheExtra": {"other": b"unchanged", ACTIVATION_KEY: True},
                            "unrelated": ["value", 42]}
                self.assertTrue(changed)
                self.assertEqual(plistlib.loads(result), expected)
                self.assertIs(plistlib.loads(result)["CacheExtra"][ACTIVATION_KEY], True)
                self.assertEqual(result.startswith(b"bplist00"), fmt == plistlib.FMT_BINARY)

    def test_integer_one_becomes_boolean(self):
        result, changed = patched_plist(plistlib.dumps({"CacheExtra": {ACTIVATION_KEY: 1}}))
        self.assertTrue(changed)
        self.assertIs(plistlib.loads(result)["CacheExtra"][ACTIVATION_KEY], True)

    def test_true_is_idempotent(self):
        raw = plistlib.dumps({"CacheExtra": {ACTIVATION_KEY: True}})
        self.assertEqual(patched_plist(raw), (raw, False))

    def test_missing_cacheextra_is_created(self):
        result, changed = patched_plist(plistlib.dumps({"other": "kept"}))
        self.assertTrue(changed)
        self.assertEqual(plistlib.loads(result),
                         {"other": "kept", "CacheExtra": {ACTIVATION_KEY: True}})

    def test_invalid_structure_is_rejected(self):
        for raw in (b"", plistlib.dumps([]), plistlib.dumps({"CacheExtra": []})):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                patched_plist(raw)


class PatchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.path = module.PLIST_REMOTE
        self.original = plistlib.dumps({"CacheExtra": {"keep": 123}},
                                        fmt=plistlib.FMT_BINARY)
        self.metadata = (0o640, 501, 501)
        self.remote = {self.path: (self.original, self.metadata)}
        self.scripts = []

    def read(self, kit, port, path, directory):
        return self.remote[path]

    def upload(self, kit, port, local, remote_dir, dirs, files):
        for name in files:
            self.remote[remote_dir + "/" + name] = ((local / name).read_bytes(), self.metadata)

    def ssh(self, kit, port, script):
        self.scripts.append(script)
        words = shlex.split(script)
        if script.startswith("if [ -f"):
            return "yes"
        if "cp -p" in script:
            self.remote[words[-1]] = self.remote[words[-2]]
        elif script.startswith("mv -f"):
            self.remote[words[-1]] = self.remote.pop(words[-2])
        elif script.startswith("rm -f"):
            self.remote.pop(words[-1], None)
        return ""

    def test_backup_write_verify_and_repeat(self):
        with patch.object(module, "_preflight"), \
                patch.object(module, "_read", side_effect=self.read), \
                patch.object(module, "sftp_push_tree", side_effect=self.upload), \
                patch.object(module, "ssh_run", side_effect=self.ssh):
            report = module.patch_activation("unused")
            repeated = module.patch_activation("unused")
        data, metadata = self.remote[self.path]
        self.assertIs(plistlib.loads(data)["CacheExtra"][ACTIVATION_KEY], True)
        self.assertEqual(plistlib.loads(data)["CacheExtra"]["keep"], 123)
        self.assertEqual(metadata, self.metadata)
        self.assertEqual(self.remote[report["backup"]], (self.original, self.metadata))
        self.assertFalse(repeated["changed"])
        self.assertIn("chown 501:501", "\n".join(self.scripts))
        self.assertIn("chmod 640", "\n".join(self.scripts))

    def test_upload_failure_never_replaces_original(self):
        with patch.object(module, "_preflight"), \
                patch.object(module, "_read", side_effect=self.read), \
                patch.object(module, "sftp_push_tree", side_effect=RuntimeError("upload failed")), \
                patch.object(module, "ssh_run", side_effect=self.ssh):
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                module.patch_activation("unused")
        self.assertEqual(self.remote, {self.path: (self.original, self.metadata)})
        self.assertFalse(any(script.startswith("mv -f") for script in self.scripts))

    def test_cleanup_failure_preserves_original_error(self):
        def disconnected_cleanup(kit, port, script):
            if script.startswith("rm -f"):
                raise RuntimeError("disconnected during cleanup")
            return self.ssh(kit, port, script)
        with patch.object(module, "_preflight"), \
                patch.object(module, "_read", side_effect=self.read), \
                patch.object(module, "sftp_push_tree", side_effect=RuntimeError("upload failed")), \
                patch.object(module, "ssh_run", side_effect=disconnected_cleanup):
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                module.patch_activation("unused")


if __name__ == "__main__":
    unittest.main()

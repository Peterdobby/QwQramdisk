import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import activation as a


class ActivationExtraTests(unittest.TestCase):
    def _archive(self, path, extra=True):
        with tarfile.open(path, "w") as tf:
            for name in ("Lockdown", "Lockdown/activation_records"):
                member = tarfile.TarInfo(name)
                member.type, member.mode = tarfile.DIRTYPE, 0o700
                tf.addfile(member)
            files = [("Lockdown/activation_records/activation_record.plist", b"record", 0)]
            if extra:
                files.append(("Extras/" + a.COMM_CENTER_NOBACKUP, b"radio", 25))
            for name, data, uid in files:
                member = tarfile.TarInfo(name)
                member.size, member.mode = len(data), 0o600
                member.uid = member.gid = uid
                tf.addfile(member, io.BytesIO(data))

    def test_legacy_dump_adds_wireless_file(self):
        record = [("activation_records/activation_record.plist", 0o600, 501, 501, 6, False)]
        radio = [("", 0o600, 25, 25, 5, False)]
        with patch.object(a, "_pick_legacy_source", return_value=(a.MAD_REMOTE, record)), \
                patch.object(a, "ssh_run", return_value="yes"), \
                patch.object(a, "list_tree", return_value=radio):
            sources = a._dump_sources("unused", 2236, "9.2.1")
        self.assertIn(("/mnt2/" + a.COMM_CENTER_NOBACKUP,
                       "Extras/" + a.COMM_CENTER_NOBACKUP, radio), sources)

    def test_legacy_restore_handles_new_and_old_archives(self):
        for extra in (True, False):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "activation.tar"
                self._archive(archive, extra)
                def listing(kit, port, remote):
                    if remote == a.LOCKDOWN_REMOTE:
                        return [("activation_records/activation_record.plist", 0o600, 0, 0, 6, False)]
                    self.assertEqual(remote, "/mnt2/" + a.COMM_CENTER_NOBACKUP)
                    return [("", 0o600, 25, 25, 5, False)]
                with patch.object(a, "_preflight"), \
                        patch.object(a, "device_version", return_value=("9.2.1", "13D15")), \
                        patch.object(a, "ssh_run", return_value="yes") as ssh, \
                        patch.object(a, "sftp_push_tree") as upload, \
                        patch.object(a, "list_tree", side_effect=listing):
                    _, info = a.restore_activation("unused", 2236, archive)
                script = "\n".join(call.args[2] for call in ssh.call_args_list)
                self.assertEqual(info["restored"], 2 if extra else 1)
                if extra:
                    remote = "/mnt2/" + a.COMM_CENTER_NOBACKUP
                    self.assertIn(f'cp -p "{remote}"', script)
                    self.assertIn(f'chown 25:25 "{remote}"', script)
                    self.assertIn(f'chmod 600 "{remote}"', script)
                    self.assertIn(f'/Extras/{a.COMM_CENTER_NOBACKUP}" "{remote}"', script)
                    self.assertEqual(len(info["backups"]), 2)
                    self.assertEqual(upload.call_count, 2)
                else:
                    self.assertNotIn(a.COMM_CENTER_NOBACKUP, script)
                    self.assertEqual(upload.call_count, 1)

    def test_system_container_restore_maps_wireless_file(self):
        root = a.SYSTEM_CONTAINERS_REMOTE + "/00000000-0000-0000-0000-000000000000"
        names = [a.KIT_LOCKDOWN + "/activation_records/activation_record.plist",
                 a.KIT_LOCKDOWN + "/data_ark.plist", "private/var/" + a.COMM_CENTER_NOBACKUP]
        files = []
        for name in names:
            m = tarfile.TarInfo(name)
            m.mode, m.size = 0o600, 5
            m.uid = m.gid = 25 if name == names[-1] else 0
            files.append(m)
        def listing(kit, port, remote):
            if remote == root + "/Library/activation_records":
                return [("activation_record.plist", 0o600, 0, 0, 5, False)]
            uid = 25 if remote == "/mnt2/" + a.COMM_CENTER_NOBACKUP else 0
            return [("", 0o600, uid, uid, 5, False)]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(a, "_system_container", return_value=root), \
                patch.object(a, "sftp_push_tree"), \
                patch.object(a, "list_tree", side_effect=listing), \
                patch.object(a, "ssh_run", return_value="yes") as ssh:
            backups = a._restore_system_container("unused", 2236, Path(directory),
                                                   files, [], "test", True)
        script = "\n".join(call.args[2] for call in ssh.call_args_list)
        remote = "/mnt2/" + a.COMM_CENTER_NOBACKUP
        self.assertIn(f'/private/var/{a.COMM_CENTER_NOBACKUP}" "{remote}"', script)
        self.assertIn(f'chown 25:25 "{remote}"', script)
        self.assertIn(remote + ".bak-test", backups)

    def test_unknown_extra_is_rejected_before_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "activation.tar"
            self._archive(archive, extra=False)
            with tarfile.open(archive, "a") as tf:
                tf.addfile(tarfile.TarInfo("Extras/wireless/unrelated.plist"), io.BytesIO())
            with patch.object(a, "_preflight"), \
                    patch.object(a, "device_version", return_value=("9.2.1", "13D15")), \
                    patch.object(a, "sftp_push_tree") as upload:
                with self.assertRaisesRegex(RuntimeError, "unexpected activation tar"):
                    a.restore_activation("unused", 2236, archive)
                upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()

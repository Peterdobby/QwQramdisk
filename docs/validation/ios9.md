# iOS 9 validation — 2026-11-01

| Device/profile | Firmware | Offline image checks | Device validation |
|---|---|---|---|
| iPhone 6s Plus, TSMC A9 / n66m-13D15 | 9.2.1 / 13D15 | Passed | Running ramdisk session: SSH, keybagd init/service, systembag read, Data write/read/delete, SCP/SFTP transfer |
| iPhone 6s Plus, TSMC A9 / n66m-13F69 | 9.3.2 / 13F69 | Passed | Running ramdisk session: SSH, keybagd init/service, systembag read, Data write/read/delete, SFTP transfer |
| iPhone 6s Plus, Samsung A9 / n66-13D15 | 9.2.1 / 13D15 | Passed | Not tested |

Final helpers were transferred and exercised in already-running ramdisk sessions.
**Full DFU-to-SSH cold boot of the final packaged images remains pending.**
The profile status `device-tested-live-ssh-rw` describes these session tests.
It does not assert coverage of other boards or other iOS 9 binaries.

## Checks performed

- Firmware identity, component SHA-1 and IMG4 artifact SHA-256 checks.
- Extracted wrapped iBSS/iBEC payloads and injected HFS files compared to inputs.
- 13D15: nine relocated paths and six checked instruction changes; final output hash verified.
- 13F69: 22 relocated paths and five checked instruction changes; final output hash verified.
- System mounted read-only; Data mounted journaled read/write.
- keybagd output confirmed `System Keybag loaded`; launchd service PID observed.
- Existing systembag read plus create/read/compare/delete probe in Data tmp passed.
- Signed SFTP upload/download of 65536 bytes matched exactly, then the probe was removed.
- 13D15 tools: find, ls, grep, chmod, sleep and mount exercised; cp/chown used in an isolated restore fixture.
- 13D15 activation dump, including optional wireless plist, compared with device bytes and metadata.
- Restore tested against an isolated temporary device directory; real activation and wireless files were not overwritten by the test.
- `patch-activation`: offline plist and simulated transport tests only; real cache modification not tested.

The machine-readable [summary](ios9-summary.json) contains firmware hashes and
check results. Firmware images, keybagd samples, activation records, backups,
ECIDs and local filesystem paths are excluded from this repository.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
shasum -a 256 -c ramdisk/SHA256SUMS
./qwqramdisk create 9.2.1 --profile n66m-13D15 --offline
./qwqramdisk create 9.3.2 --profile n66m-13F69 --offline
python3 -m tools.verify_ios9 --profile n66m-13D15
python3 -m tools.verify_ios9 --profile n66m-13F69
```

Three analyzer tests require a locally obtained 13F69 sample and otherwise skip.
Supply its path as `QWQ_KEYBAGD_SAMPLE` or place it at
`cache/n66m-13F69/keybagd.system`. Unknown hashes are rejected by runtime
preflight. A pattern-analysis candidate requires review before registration.

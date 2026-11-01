# iOS 9 validation — 2026-11-01

| Device/profile | Firmware | Offline image checks | Device validation |
|---|---|---|---|
| iPhone 6s Plus, TSMC A9 / n66m-13D15 | 9.2.1 / 13D15 | Passed | Running ramdisk session: SSH, keybagd init/service, systembag read, Data write/read/delete, SCP/SFTP transfer |
| iPhone 6s Plus, TSMC A9 / n66m-13F69 | 9.3.2 / 13F69 | Passed | Running ramdisk session: SSH, keybagd init/service, systembag read, Data write/read/delete, SFTP transfer |
| iPhone 6s, TSMC A9 / n71m-13A452 | 9.0.2 / 13A452 | Passed | Reviewed diagnostics: DFU-to-SSH boot; live logging fix confirmed keybagd init/service, systembag read, Data write/read/delete. Final six-patch image cold boot pending regression |
| iPhone 6s, TSMC A9 / n71m-13B143 | 9.1 / 13B143 | Passed | Initial diagnostics confirm DFU-to-SSH and read-only System; tester reports updated full mount package working. Raw final mount log not archived |
| iPhone 6s Plus, Samsung A9 / n66-13D15 | 9.2.1 / 13D15 | Passed | Not tested |

For 9.0.2, 9.2.1 and 9.3.2, final helpers were exercised in running ramdisk
sessions; full cold boot of their final images remains pending regression.
The profile status `device-tested-live-ssh-rw` describes those session tests.
The 9.1 status `device-reported-ssh-rw` records tester confirmation separately
from validation backed by archived raw logs.
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
./qwqramdisk create 9.0.2 --profile n71m-13A452 --offline
./qwqramdisk create 9.1 --profile n71m-13B143 --offline
./qwqramdisk create 9.2.1 --profile n66m-13D15 --offline
./qwqramdisk create 9.3.2 --profile n66m-13F69 --offline
python3 -m tools.verify_ios9 --profile n71m-13A452
python3 -m tools.verify_ios9 --profile n71m-13B143
python3 -m tools.verify_ios9 --profile n66m-13D15
python3 -m tools.verify_ios9 --profile n66m-13F69
```

Three analyzer tests require a locally obtained 13F69 sample and otherwise skip.
Supply its path as `QWQ_KEYBAGD_SAMPLE` or place it at
`cache/n66m-13F69/keybagd.system`. Unknown hashes are rejected by runtime
preflight. A pattern-analysis candidate requires review before registration.

## Early-layout samples and additional feedback

13A452 shares the exact 13A405 binary. Both use nine path relocations and six
instruction changes, including two success-log fixes that preserve the failure
guards. 13B143 has identical executable sections but a different whole-file
hash, registered separately with the same six patches. Both patched output
hashes were checked using the C patcher and the offline image verifier.

The two early-layout tests also require locally obtained firmware samples.
Set `QWQ_KEYBAGD_EARLY_SAMPLE` and `QWQ_KEYBAGD_IOS91_SAMPLE`, or use
`cache/n71m-13A452/keybagd.system` and `cache/n71m-13B143/keybagd.system`.
Samples remain local and are not distributed in this repository.

9.3.5 was additionally reported working without a new profile entry. Its board
and logs were not provided; no board-specific validation status is inferred.
9.3.3/9.3.4 and cross-board compatibility still require device testing.

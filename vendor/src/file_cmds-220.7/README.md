# iOS 9 compatible ls

`ls/` is copied from Apple's `file_cmds-220.7` tag, retaining each file's
copyright and BSD license notice:
https://github.com/apple-oss-distributions/file_cmds/tree/file_cmds-220.7/ls

`compat/humanize_number.c` is copied from FreeBSD releng/10.2, retaining its
BSD license notice:
https://github.com/freebsd/freebsd-src/blob/releng/10.2/lib/libutil/humanize_number.c

The small compatibility headers select standard UNIX behavior and supply the
humanize_number declarations missing from the iPhoneOS SDK. The source files
are unmodified. Built without COLORLS, targeting arm64 / iOS 9.0; no ncurses
library or iOS 10 clock_gettime symbol is required. Rebuild and sign using
`python3 -m tools.prepare_ios9_helpers` from the project root.

The installed device's /bin/ls was arm32, so it is not used by this port.

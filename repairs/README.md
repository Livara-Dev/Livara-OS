# Compiler dependency repair

[Download the small source repair ZIP](https://github.com/Livara-Dev/Livara-OS/raw/refs/heads/main/repairs/livara-compiler-403-repair.zip) and its [SHA-256 checksum](livara-compiler-403-repair.zip.sha256).

Extract every file over the existing source folder containing `Build-Livara.bat`, replace matching files, retain the same source folder and Docker cache volumes, then rerun the BAT. Do not prune Docker or delete compiler caches. The patch represents source commit `bd53d15bfdc0fac4ea60a2d73c5931c228681108`; the current main branch already includes it.

This ZIP contains source fixes for the Mozilla compiler HTTP 403 failure, not an ISO or compiled browser. See [recovery details and exact qualification limits](../docs/browser-toolchain-recovery.md). A permanently blocked network still needs working access to the listed official Mozilla hosts; the early check now catches it before hours of editor/source preparation.

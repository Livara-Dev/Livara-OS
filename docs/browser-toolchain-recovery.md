# Mozilla compiler 403 recovery

The Windows build log supplied on 23 October 2026 stopped while `mach bootstrap` fetched `public/chain-of-trust.json` for compiler task `EjVk13JnRzGtJTrpJjppFQ`. The response was HTTP 403. Source import and patching had completed; full browser compilation had not started. A successful recipe check did not qualify this download path.

The corrected build checks access to Mozilla compiler metadata and its archive before editor compilation in the Windows/full-ISO entry points. The browser builder downloads and SHA-256 verifies the compiler into its existing persistent Mozilla cache before cloning, extracting or patching browser source. A pinned copy of the official chain-of-trust record is also verified and cached. For this one pinned task, Mozilla's downloader reads that verified local record; its original artifact SHA-256 verification remains active. Other tasks keep their original download and error handling. No TLS checks are disabled and no third-party compiler mirror is used.

A permanently inaccessible server now stops the early network check with a useful error. Retrying cannot guarantee access through a blocking network. Keep existing Docker volumes and compiler caches. Updating source cannot change the network policy of Docker Desktop, a VPN, firewall or ISP.

## Verified evidence

The actual 453,558,736-byte official archive was downloaded and matched SHA-256 `115862b87b97049ee92b6eaf19837ded48ce4092fae6e7634ac059eb24008bfe`. Its Clang binary executed and reported 22.1.8. The actual Firefox 158.0.1 `ArtifactRecord` class was exercised with the patch while network requests deliberately raised HTTP 403: the pinned task succeeded without a request, altered local provenance was rejected, and an unrelated task retained its HTTP error. The cached archive name also matched Mozilla's URL-derived cache naming. See [the bounded qualification report](browser-toolchain-qualification.json).

Six regression checks cover cache reuse without network, corrupt metadata, corrupt downloads, bounded persistent-403 handling, guarded/idempotent integration and early-check ordering. The complete Linux controller-image check passed 222 Python tests (one expected skip), 15 editor Node tests and the desktop contract checks; its real network preflight also passed. These results qualify this dependency recovery only. They do not establish a completed browser build, browser GUI test or bootable ISO.

## Apply the repair

Use the latest source from `https://github.com/Livara-Dev/Livara-OS`, or extract the supplied compiler repair ZIP over the existing source folder. Keep the same source folder and Docker cache volumes, then run `Build-Livara.bat` again. The repair ZIP contains the affected source files and checks, not a compiled browser or ISO. A failed early check means the listed Mozilla hosts remain inaccessible from that Docker environment; do not repeat a long build until access works.

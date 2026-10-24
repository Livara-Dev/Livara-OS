# Validation and release qualification

The [published x86-64 preview](https://github.com/Livara-Dev/Livara-OS/releases/tag/v0.1.0-preview.15.1) was built from source commit `093dd528b10e03e51915acf128cba67768ec1d85`. [Run 39989050633](https://github.com/Livara-Dev/Livara-OS/actions/runs/39989050633) completed ISO assembly, BIOS testing, UEFI testing and release publication successfully on 23 October 2026. The [machine-readable record](iso-qualification.json) contains the ISO hash, asset digests, exact source revision and original boot results.

## Actual ISO checks

Both firmware modes booted the same ISO under QEMU TCG with two virtual CPUs and 4 GiB RAM. Both ran the complete live self-test, including:

- Livara system identity, x86-64 kernel, local hardening observations and native Nmap.
- Evidence-case creation, sealing and hash verification.
- GNOME Shell, Livara Center, active Livara Glass, wallpaper and dock defaults.
- ClamAV, YARA and Hashdeep version checks.
- Active AppArmor and the loaded Podman namespace-permission profile.
- Offline Kali image import as the ordinary live user, Kali release identification and execution of Nmap 7.991 inside the rootless toolbox.

The BIOS harness completed in 549 seconds and UEFI in 577 seconds, including the live integration test and retained captures. These are software-emulated test durations, not measurements of physical desktop startup. Original desktop and quick-settings PNGs, serial logs and JSON results are retained in the Actions proof artifact. [Published original captures](https://github.com/Livara-Dev/Livara-OS/tree/build-proof/proof/39989050633/.build).

Image construction checked the installed boot image against all five NVIDIA 580 open kernel-module ABIs. It also checked the open-module license, strict desktop schemas and the branding audit. The source-package launcher diversions passed real DEB unpack, vendor upgrade and removal tests; see [package ownership](package-ownership-qualification.json) and [kernel package regression](kernel-package-qualification.json).

## Compiled applications

Livara Code 1.143.1 completed its actual source compilation and sandboxed native CLI/window checks in [run 39940915546](https://github.com/Livara-Dev/Livara-OS/actions/runs/39940915546).

The browser's Gecko engine compiled in [run 39940428897](https://github.com/Livara-Dev/Livara-OS/actions/runs/39940428897). Maintained Livara JavaScript resources were then corrected without changing the compiled native engine. [Run 39964210008](https://github.com/Livara-Dev/Livara-OS/actions/runs/39964210008) passed real native browser checks for chrome, window controls, appearance, dashboard initialization, Persian note persistence and focus controls. See [the original runtime report](browser-runtime-qualification.json).

The ISO consumes those qualified artifacts. The pinned official Tor Browser archive is separately checked against its official OpenPGP signature and hash before installation. No live Tor circuit was qualified.

Earlier component records retain their original revision-specific scope: [window controls](window-controls-qualification.json), [window effects](window-effects-qualification.json), [Settings](settings-redesign-qualification.json), [Studio](studio-redesign-qualification.json), [app icons](app-icons-qualification.json) and [Essentials](essentials-qualification.json). Passing the ISO smoke test does not establish every application workflow.

## Reproduce and limits

The committed font binaries were serialized with the tools pinned in
`build/requirements-check.txt`. Use the same compiler and HarfBuzz table
repacker for source checks; installing FontTools alone can produce equivalent
font behavior with different GPOS/GSUB bytes and fail the roundtrip tests.
Keep distribution PyGObject available while using the pinned tools:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r build/requirements-check.txt
. .venv/bin/activate
make check
```

`make check` runs source/backend tests, Node tests, compilation and shell checks. `make deb` builds the desktop package. `python3 scripts/package-source.py --check` audits source delivery. `Build-Livara.bat -Check` exercises the source/package path in Docker. These smaller checks do not compile the full engines or build an ISO. The full builder needs substantial resources; see [Windows instructions](windows-build.md).

The complete Kali catalog remains an on-demand option; its full runtime was not qualified. Physical RTX/Core Ultra hardware, graphics workloads, suspend/resume, encrypted disk installation, reboot, snapshot restore and phone pairing need separate testing. Native Windows execution remains unqualified. The current GRUB chain is unsigned, so this preview requires Secure Boot disabled. The live session is ephemeral; the repository README documents its account and persistence behavior.

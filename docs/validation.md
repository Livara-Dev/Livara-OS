# Validation of the source-builder revision

This delivery is a source ZIP with a Windows BAT/PowerShell ISO builder. **No new ISO was built or booted.** Full browser-engine compilation, native Windows execution and physical GPU support remain unqualified. Source checks do not establish a working, boot-tested distribution.

## Application forks

**Livara Code:** the actual pinned open-source workbench was downloaded, hash-verified, transformed and compiled with its Electron desktop application and built-in extensions. The compile completed without TypeScript or build errors. This replaces the retired native GTK editor. The source transformation preserves required copyright/license notices and technical extension API identifiers. Seven Python source-fork tests and twelve Node command tests cover its transformation and real filesystem/crypto behavior. Real non-root, sandboxed Electron workflow checks passed for the welcome hub, private notes, UUID insertion/save, Persian text, focus controls and the Livara terminal. Startup compatibility guards and refreshed webview CSP hashes were tested by applying equivalent changes to the compiled application; the entire final source revision was not recompiled afterward. The final source guards passed transformation, TypeScript syntax and regression checks. See `forks/code/qualification.json`; these captures predate the later window-control styling.

**Livara Browser:** the exact pinned upstream checkout and Livara transformation were checked. The Firefox158.0.1 source archive's SHA-512 was verified, and all **263** upstream patches applied to **283** original Mozilla source-file fixtures. Chrome/dashboard syntax, content security policy, private-window storage and launch-mode separation are covered by tests. **The complete Gecko engine was not compiled or launched here.** The build recipe and source patches are supplied for the local full build; see `forks/browser/validation.json`.

**Official Tor mode:** the actual official Tor Browser15.0.26 archive passed SHA-256, detached OpenPGP signature, primary/signing-key-chain, all246 member, and AMD64 ELF checks. The pinned archive is byte-identical to the official download. A real root-owned extraction also preserved all220 regular-file contents while making the shared baseline readable. Inspection confirmed its locked fingerprinting preference, bundled-only fonts and original NoScript. Eleven offline tests cover signature/tamper checks, original-file validation, private copy/update/profile preservation, unsafe arguments, storage symlinks and onion checksums. **No live Tor connection or circuit was tested.** See `forks/tor/qualification.json` and [Tor mode](tor-mode.md).

## Desktop, fonts and packaging

- Native window controls passed **26 real GTK4/Adwaita assertions**, including live size/color/symbol/side changes, physical RTL placement, true green-button fullscreen, actual F11 and Shift-click, maximize/restore, minimize, close-request guards and disposal. Measured buttons match 10×10, 14×14 and22×22 pixels. GTK3 and GTK4 providers parsed without CSS errors. Reopening can be needed when returning to stock styling after GTK preloaded an earlier managed user stylesheet; other live preferences were checked. See `window-controls-qualification.json`.
- Code's eight window-control preferences passed three additional Node tests, strict standalone DOM TypeScript checking, and actual Electron/window-manager interaction for fullscreen/F11, live preferences, maximize/restore, Shift-click, keyboard control, minimize and close. The complete emitted current contribution/controller was integrated into the source-built application; the whole workbench build was not repeated. Browser controls passed source/VM tests and pinned patch validation; the full browser remains uncompiled.
- Nine window-effects tests execute the production JavaScript state machine with native-window-manager fixtures: exact-once completion, cancellation/disable, actor restoration, native bookkeeping, API failures, reduced motion and skipped windows. A real Ubuntu 24.04 GJS process checked signal-handler lookup/block/unblock, GI-method replacement/restoration and SpiderMonkey parsing. An actual nested GNOME 46 compositor also passed real Zoom/Lift/Fade map/destroy transitions, exact-once native completion, reduced motion and extension-disable restoration. The software-rendered test session used a test-only animation override to exercise timed transitions; production keeps normal compositor eligibility. See [window effects](window-effects.md).
- The redesigned Settings catalog was audited read-only against actual GNOME 46 schemas: all 94 schema/key/type mappings and 224 declared values passed after correcting one Mutter workspace-key spelling. Twenty-five targeted tests pass. Native GTK checks cover search, fonts, wallpaper selection, named looks, Undo, scoped resets and a real fullscreen preview window. All eight sections rendered after layout in an 800×600 window request (790×590 client area). See `settings-redesign-qualification.json`; the optional `scripts/settings-ui-smoke.py` reproduces the native flow with private in-memory settings. [Customization](customization.md) explains unavailable settings, preset scope and hardware-dependent effects.
- Studio's redesign passed 30 backend tests and nine actual GTK workflows: honest Overview totals, background tool results, session-only drafts, search/no-results, Notebook save/archive/restore, Focus controls and persistent appearance changes. See `studio-redesign-qualification.json` and [feature inventory](studio-features.md).
- Native GTK4/libadwaita interaction under Ubuntu 24.04/Xvfb exercised Center, Settings, Task Manager, Studio and Graphics. Monitor used real system observations; Studio exercised Notes and a completed focus session. The Chat app's offline/profile/error handling was checked. These checks do not qualify a newly booted desktop.
- All six Livara fonts were rebuilt from editable UFO/TTX sources. Nine font tests include actual HarfBuzz Persian contextual joining, Lam-Alef, ZWNJ boundaries and mark positioning. Isolated fontconfig readback selected Livara Sans for English, Livara Persian for Persian and Livara Mono for code. The full requested Noto package set and FontForge resolved through Ubuntu APT.
- Real GSettings readback checked the Terminal profile and desktop customization. Branding fixtures checked image rendering, canvas bounds, icon cache rebuilding, stale asset detection and prompt handling. No hardware FPS, thermal, battery or game benchmark was run. Apple's proprietary Liquid Glass renderer is not implemented.
- Ubuntu APT simulation resolved the HWE kernel, matching precompiled NVIDIA 580 open modules and userspace, selecting no DKMS compilation package. Graphics tests include RTX generation fixtures and actual container observations. **No physical RTX 20/30/40/50 card was tested.** See [graphics](graphics.md).
- The Windows controller uses isolated Linux named volumes, normalizes Windows line endings and file modes, and exports root-owned Debian contents. PowerShell7.4 on Linux parsed the wrapper. **Windows/PowerShell5.1 and Docker Desktop were not run on a Windows host.** The final controller check builds the Debian integration package without compiling browser engines, downloading Kali or assembling an ISO.
- Source packaging audits an explicit allowlist, required sources/licenses, Windows-portable paths, fixed ZIP metadata and BAT CRLF. It excludes ISO, Debian packages, engine bundles, Kali payloads, secrets and build caches. The delivered checksum covers the complete source ZIP.

The earlier complete Windows controller ran 174 Python tests (one expected skip because the pinned upstream checkout is absent), 15 Node tests, Python compilation, shell syntax checks and Debian integration packaging. Final controller results and native Code GUI results are recorded in `validation-results.json`. Application screenshots are real Xvfb renders and nested GNOME captures, not screenshots of a newly booted Livara image. The retired editor/default-browser prototype screenshots are not part of this delivery.

## Reproduce

On Linux with the documented check dependencies:

```sh
make check
make deb
python3 scripts/package-source.py --check
make source
```

On Windows with Docker Desktop's Linux amd64 engine running:

```bat
Build-Livara.bat -Check
```

The check path does not create a root filesystem, Kali image or ISO. The full `Build-Livara.bat` compiles both application forks, prepares official Tor Browser and creates those products locally. It needs substantial memory, disk, downloads and time; see [Windows build instructions](windows-build.md).

## Qualification after building

Verify the emitted ISO checksum and test a BIOS VM first. UEFI graphics, Secure Boot, physical RTX cards, hybrid laptops, external monitors, suspend/resume, Vulkan/OpenGL and CUDA workloads need qualification on real hardware. This live preview has no installer or persistence wizard and an unsigned boot chain; see the README before use.

The complete Kali catalog is an on-demand `kali-linux-everything` option, with core tools bundled for offline first setup in a full build. The complete catalog was not downloaded or runtime-qualified for this source revision. Hardware-dependent and privileged tools need a suitable workflow beyond the rootless container.

## App icon customization revision

The October 23 icon-manager revision passed 14 backend tests and five native GTK workflows covering the chooser, background apply, Gio icon readback, original-icon restoration, filters, PNG/JPEG/WebP/ICO/SVG decoding and 800×600 layout. The pinned Linux controller image rebuilt the fonts with its installed FontTools before running 188 Python tests (one expected upstream-checkout skip), 15 Node tests, compilation, shell syntax checks and Debian integration packaging. The new modules and application shell match the exported package byte-for-byte; all package data members are root-owned and SVG/WebP dependencies are explicit. See `app-icons-qualification.json`. Native Windows and a new ISO boot remain untested. Earlier compositor, fork, gallery and controller records retain their original revision-specific scope.

## Essentials qualification

The current source includes 17 feature areas with native GTK pages, a keyboard command palette, GNOME desktop adapters and a branded Calamares configuration. Eighteen backend tests, native UI workflows, actual GPaste service readback, complete APT dependency simulation and available Calamares module schemas were checked. The new desktop Shell behaviors have contract tests; their operation in a new real GNOME session is not yet qualified. The installer welcome screen refused missing target partitions as expected. No disk installation, reboot, snapshot restore, phone pairing or physical hardware check was performed. See [the complete record](essentials-qualification.json).

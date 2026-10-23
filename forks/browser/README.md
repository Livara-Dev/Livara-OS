# Livara Browser source fork

This is a source fork of Zen Browser and its Firefox/Gecko engine. The kit contains source patches, browser chrome/dashboard source resources, branding, fonts, Tor runtime and a full native build recipe. It does not download and re-skin an upstream browser executable. A compiled browser is not included in this source delivery.

The pin is [Zen 1.23.4b](https://github.com/zen-browser/desktop/tree/541ee55196395ee8082862b83c84c90ab41d9f6d), commit `541ee55196395ee8082862b83c84c90ab41d9f6d`, Firefox **158.0.1**, Surfer **1.14.9**, Node **22**, Rust **1.95.0**. `upstream.json` pins the Mozilla source archive's SHA-512 from the release's `SHA512SUMS`. Upstream MPL-covered files retain MPL-2.0 notices, copyright, legal pages and technical identifiers. New Livara browser chrome uses GPL-3.0-or-later as stated in its source; applicable per-file licenses govern, and both sets of notices remain in the combined browser.

`prepare.py` verifies the exact Git revision, applies `patches/`, copies `overlay/`, derives all active branding images from Livara's browser artwork, embeds Livara Sans and the Vazirmatn-derived Livara Persian, and rebrands visible Fluent text while preserving message IDs and comments. Both font licenses/attribution are packaged; the Persian fonts retain Arabic/Persian shaping tables. Its source manifest records the revision and asset/patch hashes. Browser JavaScript/CSS and dashboard source resources are packaged into `browser.jar` during the local native build, rather than injected through a userChrome profile.

Run from the project root on x86_64 Linux with Docker:

```sh
./scripts/build-browser.sh --check             # Offline source/recipe checks
LIVARA_BUILD_JOBS=4 ./scripts/build-browser.sh  # Full native compilation
```

The Windows OS builder invokes the same Docker recipe. Output: `dist/forks/livara-browser-linux-x64.tar.xz`, rooted at `livara-browser/`, native binary `livara-browser`. The OS installs it under `/opt/livara-browser`; the system launcher is `share/livara/browser/livara-browser`. There is no stock-browser or WebKit fallback.

The actual pipeline performs `npm ci`, downloads/verifies Mozilla source, generates upstream preferences/search dumps, imports Zen/Livara patches, bootstraps Mozilla's native toolchain, runs `npm run build`, then `mach package`. It disables the upstream binary updater; maintainers must update the pinned sources and rebuild to supply engine/security updates. It neither contacts Zen's update service nor claims a deployed Livara update service.

Allow **100 GiB free disk and 16 GiB RAM** for the complete OS build; more helps parallel builds. Upstream documents 30 GB free for the browser alone; this script requires 30 GiB. Browser compilation can take hours. Docker BuildKit caches retain source/toolchains/objects between attempts. `LIVARA_BUILD_JOBS` controls parallelism; optional `LIVARA_BUILD_CA` supplies a transient BuildKit CA secret. Proxy variables are forwarded by name. No build CA or credentials enter the browser artifact. Downloads require internet access.

Livara adds glass appearance controls, dark/light/system theme, four accents, chrome text sizing, tab density/radius/motion controls, tab search, sidebar/toolbar actions, reader controls and explicit Tor mode. The local dashboard provides DuckDuckGo search, a clock, removable shortcuts, notes, focus timer and quiet view, without remote assets or background requests. Private-window dashboard data stays in memory. The full Gecko/Zen engine retains browser extensions, bookmarks, workspaces, downloads and split views.

Browser-specific traffic lights have configurable style, physical side, size, symbols, colors and green-button action. The default green action is fullscreen; Shift-click maximizes/restores. The browser retains its existing F11 shortcut and its guarded close/minimize actions. Standard style restores the stock controls. These resources are part of the local source build; their action/preference tests run in a JavaScript VM, and full Gecko runtime qualification remains outstanding. See [window controls](../../docs/window-controls.md).

Use the desktop Tor Mode action, appearance panel or `livara-browser --tor [http://YOUR-V3-ADDRESS.onion/]`. This opens the separately verified **official Tor Browser**, with its original engine, security profile, fonts, anti-fingerprinting defenses, NoScript, bridges and circuit isolation. It is not a proxy profile inside Livara Browser. The normal Livara engine never enables Tor mode and always refuses onion URLs. Its appearance controls and bundled fonts are not applied to Tor Browser.

The official bundle is downloaded and signature-verified by the local OS build. An immutable base is installed under `/opt/tor-browser`; its launcher maintains a private user copy so the original official updater can operate. No profile overrides, custom fonts, userChrome themes, weakened TLS settings or sandbox bypasses are added. See `forks/tor/` for the upstream pin, verification key and bundle recipe. Official Tor Browser branding remains visible by request.

Validation includes the pinned Git checkout/patch application, Mozilla archive digest, resource syntax/CSP, launcher mode separation, and official Tor Browser launcher/signature fixtures. All 263 upstream Zen patches applied successfully to 283 original Mozilla patched-file fixtures from the verified Firefox archive (`validation.json`). Full Gecko compilation and a real Tor network session were **not completed** in the authoring environment, which had about 12 GiB free disk. The packager requires a compiled ELF binary, Gecko library and Livara-reported native version before accepting an artifact. Source checks do not produce an ISO.

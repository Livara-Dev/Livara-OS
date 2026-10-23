# Official Tor Browser mode

The Tor button in Livara Browser, or `livara-browser --tor [https://address]`, opens a separate, unmodified **official Tor Browser**. With no address, Tor Browser opens its own default page. HTTP and HTTPS addresses are accepted, including valid current v3 `.onion` addresses. Custom profile, proxy, debugging and sandbox arguments are rejected.

Tor Browser keeps its official name, interface, NoScript extension, security levels, fingerprinting protection, bridges, connection settings and updater. Livara does not install its browser skin, extensions, fonts, preferences or Zen profile into Tor Browser. The normal Livara Browser continues to block `.onion` navigation and does not become a Tor proxy browser.

## Pinned release and authenticity

The baseline is **Tor Browser 15.0.26 for Linux x86_64**, resolved on October 22, 2026 from the Tor Project's current [platform download metadata](https://aus1.torproject.org/torbrowser/update_3/release/download-linux-x86_64.json). The release tag is `tbb-15.0.26-build1`.

The [official verification documentation](https://support.torproject.org/tor-browser/getting-started/verifying-tor-browser/) publishes the Tor Browser Developers primary fingerprint:

```text
EF6E 286D DA85 EA2A 4BA7 DE68 4E2C 6E87 9329 8290
```

The refreshed public key is included as `forks/tor/tor-browser-developers.asc`. The actual downloaded release has a valid detached signature made on **October 21, 2026**, by signing subkey `022DA248432D2A0E0F54E65E316C1FACD62D07D9`, authenticated under that primary key. Its archive SHA-256 is:

```text
327ac7443724b9eb6d3697506391b110ee159739bdc14bd731caa6fc16ffbf74
```

`forks/tor/upstream.json` pins the official HTTPS download, version, checksum, detached signature, public key and provenance files. `forks/tor/files.json` records every original file, directory, mode, size and content hash. `forks/tor/qualification.json` records this checkout's actual artifact verification. The source kit contains these small provenance files and the preparation recipe; the browser bundle is downloaded during the full build.

## Build and install

Run on Linux with Python 3, `gpg` and `gpgv`:

```sh
python3 scripts/prepare-tor-browser.py --check
python3 scripts/prepare-tor-browser.py dist/forks
```

`--check` is offline and downloads nothing. The complete step downloads the pinned official bundle, verifies its SHA-256 and detached signature against an isolated keyring, checks the primary/subkey chain, validates all 246 original members, and checks that `Browser/firefox.real` is an AMD64 ELF64 executable. It produces:

```text
dist/forks/livara-tor-browser-linux-x64.tar.xz
dist/forks/livara-tor-browser-verification.json
```

The `.tar.xz` is byte-for-byte identical to the official archive. It is not repacked, rebranded or patched. `--archive PATH` can verify an already downloaded bundle. The downloader retains HTTPS verification and configured proxy settings. An optional `LIVARA_BUILD_CA` adds a controller CA bundle to standard TLS trust without putting it in the artifact.

The installer places the unchanged browser files in `/opt/tor-browser`. Shared root-owned files receive read access, and existing executable files retain execution access, so desktop users can make their own copies. File bytes stay unchanged. The two runtime metadata files are installed separately:

```text
forks/tor/upstream.json -> /usr/share/livara/browser/tor-upstream.json
forks/tor/files.json    -> /usr/share/livara/browser/tor-files.json
```

## Private user copy and updates

On first launch, the wrapper verifies every installed baseline file against the signed file manifest. It then copies the complete official tree into:

```text
~/.local/share/livara/tor-browser/15.0.26/tor-browser/
```

The parent storage and version directories have mode `0700`. Copying happens under a lock, with a temporary directory, post-copy content verification and atomic promotion. The origin record is outside the official browser tree. The wrapper runs the original `Browser/start-tor-browser` from its own Browser directory, without added browser flags or preference files.

Later launches preserve the user copy, official updates, profiles, bookmarks, bridges and connection settings. The official updater can modify this private copy. The wrapper does not replace it with the older immutable baseline. A future source-kit baseline version uses a separate version directory; existing user data is retained. These directories consume disk until the user removes an unused copy after preserving any wanted data.

Root launch is refused. The wrapper does not pass `--no-sandbox` or set sandbox-disabling environment variables; inherited `MOZ_DISABLE_*` and obsolete Livara proxy variables are removed. Tor Browser manages its own Tor process and connection UI. There is no separate Livara SOCKS proxy process in this mode.

## Fonts and the Ubuntu 24.04 sandbox

The verified official `Browser/fonts/fonts.conf` explicitly says that bundled fonts are the only available system fonts and warns against edits. It lists only `<dir prefix="cwd">fonts</dir>` and does not include `/etc/fonts` configuration. Inspection of the signed `Browser/browser/omni.ja`, in `defaults/preferences/000-tor-browser.js`, confirmed these original defaults:

```js
pref("privacy.resistFingerprinting", true, locked);
pref("gfx.bundled-fonts.activate", 1);
```

The bundled NoScript XPI is retained unchanged in both original extension locations. Livara's desktop font aliases and browser styling are not copied into the official browser tree. The runtime verifies the baseline font files along with all other members before creating a user copy. Official startup and native browser font handling remain unchanged.

Ubuntu 24.04 restricts unprivileged user namespaces. The image installs `/etc/apparmor.d/livara-tor-browser` with narrowly attached `userns` permission for the installed and private-copy executable paths. `Browser/firefox` is an official shell wrapper; the native executable is `Browser/firefox.real`, so both paths are covered:

```text
abi <abi/4.0>,
include <tunables/global>
profile livara-tor-browser /opt/tor-browser/Browser/firefox{,.real} flags=(unconfined) {
  userns,
  include if exists <local/livara-tor-browser>
}
profile livara-tor-browser-private @{HOME}/.local/share/livara/tor-browser/*/tor-browser/Browser/firefox{,.real} flags=(unconfined) {
  userns,
  include if exists <local/livara-tor-browser-private>
}
```

This grants the executable paths access to user namespaces; Gecko's content sandbox remains enabled. It does not globally disable AppArmor's user-namespace restriction.

## Qualification limits

The actual official archive, OpenPGP signature, SHA-256, all original member hashes, native architecture, original bundled-font configuration and locked fingerprinting default were checked in this session. Offline tests cover private-copy preservation, official update/profile retention, changed-file rejection, unsafe arguments, root refusal, storage symlinks and v3 onion checksums. The unchanged browser was also launched as a regular user with its sandbox enabled in an offline test container; its genuine initial connection screen is included in the gallery. Connect was not selected, and no Tor circuit is implied by that capture.

Live Tor circuit connectivity and a rebuilt Livara ISO boot with this integration have not been qualified. The official Tor Browser session uses its own networking and protections; other Livara applications keep their usual networking. Unmodified official software does not establish a universal anonymity guarantee for the operating system, user activity or destination services.

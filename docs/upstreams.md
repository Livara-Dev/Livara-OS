# Upstream sources

Ubuntu and Kali are distributions assembled from many independently licensed projects. Their complete sources are not a single GitHub repository to combine. Livara builds an Ubuntu desktop with a separate Kali userspace using official package and image sources.

| Project | Official source or documentation | Livara use |
| --- | --- | --- |
| Ubuntu | [Launchpad](https://launchpad.net/ubuntu), [release lifecycle](https://ubuntu.com/about/release-cycle) | Noble userspace, package repository, desktop, and kernel packages |
| Kali Linux | [Kali GitLab](https://gitlab.com/kalilinux), [official container guide](https://www.kali.org/docs/containers/using-kali-podman-images/) | Kali rolling image and tool packages inside Podman |
| Kali package sources | [APT repository documentation](https://www.kali.org/docs/general-use/kali-apt-sources/) | Kept inside the Kali image |
| GNOME Shell | [GNOME GitLab](https://gitlab.gnome.org/GNOME/gnome-shell) | Ubuntu desktop shell |
| GTK | [GTK documentation](https://docs.gtk.org/gtk4/) | Native Livara application UI |
| libadwaita | [libadwaita documentation](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/) | Native application window, action rows, and notifications |
| Podman | [Official source](https://github.com/containers/podman) | Rootless Kali execution |
| Linux | [Official source mirror](https://github.com/torvalds/linux) | Kernel supplied by Ubuntu packages |

The customized applications, fonts and separate Tor application have their own source pins and licenses:

| Component | Official provenance and upstream license | Livara source record and use |
| --- | --- | --- |
| Code - OSS | [Microsoft source at the pinned commit](https://github.com/microsoft/vscode/tree/2d0b7506a36c1d6db9a466440131a8e01eab2289), [MIT license](https://github.com/microsoft/vscode/blob/2d0b7506a36c1d6db9a466440131a8e01eab2289/LICENSE.txt) | [Code pin](../forks/code/upstream.json): version **1.143.0**, commit `2d0b7506a36c1d6db9a466440131a8e01eab2289`. Livara Code is compiled from this source with Livara changes. The manifest also pins the source checksum, Node and Electron versions. It is not the proprietary Microsoft-branded binary; extensions use Open VSX. |
| Zen Browser | [Pinned source](https://github.com/zen-browser/desktop/tree/541ee55196395ee8082862b83c84c90ab41d9f6d), [MPL-2.0 license](https://github.com/zen-browser/desktop/blob/541ee55196395ee8082862b83c84c90ab41d9f6d/LICENSE) | [Browser pin](../forks/browser/upstream.json): **1.23.4b**, commit `541ee55196395ee8082862b83c84c90ab41d9f6d`. Livara applies source patches, replaces application branding, adds browser chrome/dashboard source resources, then builds the native browser locally. Legal attribution and compatibility identifiers remain. |
| Firefox / Gecko | [Official source archive](https://archive.mozilla.org/pub/firefox/releases/158.0.1/source/firefox-158.0.1.source.tar.xz), [release checksums](https://archive.mozilla.org/pub/firefox/releases/158.0.1/SHA512SUMS), [Mozilla source](https://github.com/mozilla-firefox/firefox/tree/FIREFOX_158_0_1_RELEASE), [MPL-2.0](https://www.mozilla.org/en-US/MPL/2.0/) | Firefox **158.0.1** supplies the engine beneath the normal Livara Browser fork. Its archive SHA-512 is pinned in the [browser manifest](../forks/browser/upstream.json); Gecko also includes components with their own notices. [Validation record](../forks/browser/validation.json): 263 Zen patches applied to 283 original Mozilla patched-file fixtures. This is source-patch validation, not a completed Gecko compilation or browser runtime test. |
| Official Tor Browser | [Official release directory](https://dist.torproject.org/torbrowser/15.0.26/), [Tor Browser source](https://gitlab.torproject.org/tpo/applications/tor-browser), [build source](https://gitlab.torproject.org/tpo/applications/tor-browser-build), [signature-verification instructions](https://support.torproject.org/tor-browser/getting-started/verifying-tor-browser/) | [Tor pin](../forks/tor/upstream.json): **15.0.26**, Linux x86_64, source tag `tbb-15.0.26-build1`. The local build verifies the detached OpenPGP signature and SHA-256, then installs the unchanged official bundle as a separate application. Original component licenses remain in `Browser/TorBrowser/Docs/Licenses/`; this bundle does not have one license that replaces them all. [File manifest](../forks/tor/files.json) and [qualification](../forks/tor/qualification.json) record actual bundle checks. |
| Vazirmatn | [Official source at the pinned commit](https://github.com/rastikerdar/vazirmatn/tree/83629f877e8f084cc07b47030b5d3a0ff06c76ec), [SIL OFL-1.1 license](https://github.com/rastikerdar/vazirmatn/blob/83629f877e8f084cc07b47030b5d3a0ff06c76ec/OFL.txt) | [Font pin](../fonts/vendor/vazirmatn/upstream.json): **v33.003**, commit `83629f877e8f084cc07b47030b5d3a0ff06c76ec`. Livara Persian is a renamed derivative retaining Persian/Arabic OpenType shaping. Original licensed sources, [copyright/license](../fonts/vendor/vazirmatn/OFL.txt) and attribution are included. |
| Original Livara Sans / Mono | [Font design and editable sources](../fonts/README.md), [SIL OFL-1.1](../fonts/OFL.txt) | Original Livara designs with Regular and SemiBold faces. These are separate from the attributed Vazirmatn derivative. Normal Livara applications use the multilingual font stack; official Tor Browser keeps its own bundled fonts. |

Upstream project names in source notices and this provenance record identify the original authors. Livara product branding does not remove license notices or establish endorsement by those projects. Original MPL-covered browser files retain MPL-2.0 notices; new Livara browser chrome follows GPL-3.0-or-later where stated, and new Code-fork contributions use MIT. Applicable per-file licenses and third-party notices remain authoritative, with both sets of notices retained in the combined browser. Microsoft and Mozilla trademarks are not granted by their open-source licenses. The official Tor Browser retains its official name and appearance by request; Livara does not apply its normal browser patches, fonts or profile to that application. See [browser build notes](../forks/browser/README.md), [Code build notes](../forks/code/README.md) and [Tor integration](tor-mode.md).

The lightweight ZIP ships Livara changes, build recipes, notices and pin/verification metadata. It does not include the full Code - OSS/Firefox source trees or prebuilt application bundles. The local builder downloads the pinned sources and signed Tor bundle. No claim of bit-for-bit reproducible builds follows from these source pins: toolchain/container downloads and distribution package repositories have separate versioning.

The original Livara sources are in this source kit. Base image pins used for the first preview:

```text
ubuntu:24.04
sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac

docker.io/kalilinux/kali-rolling:latest
sha256:4be87f78671419c13dcf4f207ead1cfc0de178ea281b3f69c0f49b69ba4e79b1
```

Package repositories are not frozen snapshots. A rebuilt image may resolve newer packages even with the same OCI base pin. Publish each build's package inventory and checksums alongside an image. Preserve third-party notices and provide corresponding source where a component's redistribution license requires it. Firmware packages may have different redistribution terms from the original Livara software.


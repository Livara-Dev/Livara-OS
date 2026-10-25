# Architecture

Livara uses a stable Ubuntu host and an independently packaged Kali userspace.

```text
Livara Center / Settings / Monitor / Studio / Chat (GTK4 + libadwaita)
Livara Code (Electron workbench) / Livara Browser (Gecko chrome)
Official Tor Browser (unchanged, separately verified engine)
       │
       ├── Shield / Verify / Cases / system observations
       ├── Personalize → user GNOME preferences + Livara Glass shell extension
       ├── Ubuntu native tools and desktop applications
       └── rootless Podman → Kali core / category profiles / everything
                                  │
                              /work directory

Ubuntu 24.04 LTS userspace + GNOME + Ubuntu HWE kernel
Casper live boot → compressed root filesystem + ephemeral writable overlay
GRUB BIOS / UEFI → kernel + Casper initramfs
```

The live root filesystem is assembled from signed Ubuntu APT packages in an Ubuntu OCI base and compressed with Zstandard. Casper creates the live user and writable overlay at boot. `grub-mkrescue` creates the bootable image from `build/grub.cfg`. A standalone `livara-desktop` package contains the original application, settings, artwork, and toolbox definition.

The desktop keeps Ubuntu's GNOME session, dock, settings, accessibility infrastructure, and package manager. Livara defaults to a purple Yaru theme and floating bottom dock. Its original GNOME 46 extension adds translucent shell surfaces and background blur through `Shell.BlurEffect`, with sharp foreground text and icons. A separate finite-transition engine animates ordinary window opening and closing. Native applications use customizable traffic-light controls. Settings exposes 94 validated preferences in eight searchable sections, four bundled looks, private user presets and live previews. Missing desktop schemas disable their corresponding controls. The supplied logo is integrated into the application icon, four wallpapers, and a Plymouth script theme.

The Kali container starts from the official `kalilinux/kali-rolling` image. Tool dependencies resolve inside Kali's package repository. The host's Ubuntu libraries and APT sources are untouched. Profile additions use explicit Kali metapackages rather than a mutable host installer downloaded at runtime. The full profile requests `kali-linux-everything` with recommended packages; category profiles request Kali's corresponding tool metapackages. The core profile remains a small explicit package list, bundled when the user builds an ISO. Full and category builds require network access and have not all been runtime-qualified.

Rootless execution uses `--userns=keep-id`, drops all Linux capabilities, enables `no-new-privileges`, limits processes and memory, and makes the image read-only. Kali's packaged file capabilities are removed during image creation so capability-bounded execution can launch its tools. Tools needing packet-level privileges will need a separate, deliberately configured workflow. The bind mount shares one user-selected directory; the rest of the home directory is not mounted. This is useful operational separation, not a promise that containers safely execute arbitrary untrusted binaries.

The live session has passwordless sudo, an automatic login, and screen locking disabled. Those are ephemeral preview behaviors. The `.deb` does not install those settings. No offensive tool services are started automatically. UFW's inbound-deny policy and Ubuntu automatic update timers are enabled in the image; Shield reports actual observable state and leaves inaccessible settings as unknown.

SHA-256 operations stream file contents in chunks. Case names use a narrow character set and cannot traverse paths. Sealing refuses symlinks and special files. Manifest verification compares the entire current inventory and reports additions, deletions, and byte changes. The manifest is unsigned and can be replaced by someone who can write the case, so a trusted external copy remains necessary.

The GUI runs expensive hashing and security checks outside the GTK event loop. External commands receive explicit argument arrays. A fixed terminal wrapper forwards arguments using `"$@"`; user input is never interpolated into shell source.

For boot verification, the third GRUB menu entry includes `livara.selftest`. A systemd service then checks the live mount, distribution identity, native tools, case integrity, the GNOME session, and the bundled rootless Kali image. Normal boot does not run these tests.

Future work before a general-purpose installed release includes an installer, persistent user setup, signed boot chain, update repository, reproducible package snapshots, hardware qualification, accessibility testing, and a supported upgrade policy.


## Native application suite

The desktop package installs dedicated Livara launchers and SVG/PNG identity assets. Compatibility desktop IDs route the shell’s Settings action and legacy browser, terminal, and monitor launchers to Livara. Hardware/device panels still execute GNOME Control Center directly. No Livara app impersonates its D-Bus service. Browser is built from the pinned Zen/Gecko source with Livara chrome and branding. Code is built from pinned MIT editor source with a compiled Livara contribution and bundled extension. Chat uses a separate persistent WebKit website profile. These apps open only on request.

Settings and Center share an original Python GTK application shell; Settings has a dedicated sectioned interface and canonical preference catalog. Monitor samples Linux procfs with identity-checked pidfd process controls. Studio’s 30 local tools use bounded input/scan work and background execution. Its Notebook, favorites, recent tool identifiers and appearance preferences use private filesystem storage; tool inputs/results are not automatically written to history. Code keeps the upstream document/extension architecture and workspace trust, with additional bounded Livara utilities. The retired GTK editor is not installed or used as a fallback. Application-specific behavior and limits are documented with their source.

## Liquid appearance and rendering

The GNOME 46 extension builds a separate live compositor scene behind each
eligible shell surface. Allocated wallpaper and visible current-workspace
window actors are cloned in stacking order, softened with Shell.BlurEffect in
ACTOR mode, then sampled by a Shell.GLSLEffect fragment shader. Rounded-distance
normals bend UV coordinates at the bevel, with bounded RGB dispersion, interior
magnification, a Fresnel rim and pointer-oriented highlights. Text/icons remain
in their original foreground actors and never enter the shader texture.

Up to eight live lenses share a six-million device-pixel render-target budget;
there are at most 64 visible sources and 256 candidate actors. Oversized or
unsupported surfaces retain the existing compositor blur and cached static rim,
with a maximum 512-pixel texture edge. Clear CSS is applied only after a live
backplate binds successfully. Window motion/content updates use Clutter.Clone
and compositor damage, without CPU screenshots or a frame timer. Hidden,
minimized and other-workspace windows leave the live scene. Hidden surfaces,
Overview, lock/greeter sessions and high-contrast themes release live lenses.
Reduced motion stops pointer lighting and Livara transitions.

Native GTK application cards remain readable CSS surfaces; they do not sample
the desktop behind their windows. This is Livara's original Linux optical
renderer, with actual sampled-pixel refraction on the named shell surfaces;
Apple's proprietary implementation and pixel-identical iOS behavior are not
claimed. [Renderer test and screenshots](liquid-glass.md).

Browser chrome and its offline dashboard use the same lens/plate separation in dark and light appearances. Their glass-off and increased-contrast paths use opaque surfaces. Code's lens is scoped to workbench chrome; editors retain the selected theme's opaque canvas and extension views retain VS Code color tokens. Browser popup windows keep styled native titlebar controls when there is no visible navigation toolbar to host the custom controls.

Disabling glass releases live scenes, shader and blur effects. Reduced-motion preferences turn off Livara transitions. Pre-rendered wallpapers avoid startup SVG filters. No cross-device FPS, memory, battery, or thermal benchmark has been established. GPU driver/kernel integration is described separately in graphics.md and needs hardware qualification.

## Windows source builder

Build-Livara.bat starts a PowerShell controller. Docker Desktop runs a Linux build controller with named source, build, and output volumes. The source copy excludes credentials, caches, previous outputs, and Git metadata; Linux script endings are normalized. Docker export/save and filesystem extraction remain Linux binary pipelines. Child containers share named volumes rather than treating a controller path as a Windows host bind path. Completed ISO/package/checksum files alone are copied back to Windows. The -Check path runs source checks and Debian packaging without building the live rootfs, Kali image, or ISO.

The source ZIP is assembled from an explicit allowlist; it contains no ISO, Debian package, Kali image, Docker cache, or previous build tree. This delivery is source only. A current-source image still needs boot and hardware qualification after it is built locally.

## Fork and Tor build boundary

The two customized application archives are built from content-pinned sources before rootfs assembly. The Code pipeline verifies source and Node checksums, compiles the desktop workbench and native modules, and bundles the Livara extension. The Browser pipeline verifies Mozilla source and the Zen revision, imports the patch series, adds compiled chrome resources, and builds through mach. Local recipe checks do not substitute for full application compilation. Both outputs use generic Linux x86-64 code.

The third application input is the unmodified official Tor Browser distribution. A separate preparation step checks its pinned hash and detached signature against the Tor Browser Developers key. Tor mode launches its own user-writable copy and separate profile, preserving the official security controls, bundled fonts, bridges, and signed updater. The ordinary Livara browser never acts as a Tor Browser substitute.

The image installer validates archive paths/internal links and ELF64 x86-64 machine identity before installing trusted build outputs under /opt. Electron’s sandbox helper receives the expected root ownership/mode; scoped AppArmor user-namespace profiles allow the engines’ content sandboxes without a global namespace-policy change. No product launcher disables the browser sandbox.

The desktop package contains app wrappers, native utilities, fonts and editable sources. The separately built Code/Browser/official-Tor engines are installed by live-rootfs assembly; installing only this desktop package on an existing machine does not install those engines.

## Multilingual type

Livara Sans/Mono are original editable Latin designs. Livara Persian derives from attributed Vazirmatn sources and retains Arabic/Persian OpenType shaping. The source kit keeps canonical UFO/TTX sources and licensed upstream SFD masters. The build recompiles edited sources before packaging. Fontconfig selects Livara faces and Noto script fallback; broad Noto coverage is downloaded as Ubuntu packages during the image build. The official Tor Browser is kept outside the customized app-font stack.

# Update Livara without downloading another ISO

Desktop update **0.1.4 — Browser reliability and automatic boot** restores the
browser's missing Zen language resources, fixes desktop icon matching, keeps
confirmed appearance preferences across browser restarts, and fits restored
windows to the current monitor work area. Normal installed boots start the main
OS automatically with a hidden GRUB menu. Press Esc during the short startup
interval to reveal recovery/other boot choices. See [runtime proof](browser-reliability.md).

Download **Livara-Halo-0.1.4-Update.zip** from the release and extract it into a
new folder. It contains both packages, checksums and the installer together.
Alternatively, download every individual file listed below, not just the script.
The installer prints progress and identifies missing downloads.

The desktop update upgrades an existing installed Livara system using a small
`livara-desktop` DEB and a separate `livara-code` application DEB. The small
package replaces Livara apps, icons, desktop schemas, the Shell extension and
maintained Browser UI and localization resources. The Code package retains the already source-compiled, runtime-tested Halo
editor and window-control fixes; this release repairs Browser resources and installed boot defaults. It does not
rebuild or download the kernel, boot image, Gecko or the whole ISO.

Download the DEB, `SHA256SUMS`, `update-manifest.json`, and
`Install-Livara-Update.sh` from the official
[desktop update release](https://github.com/Livara-Dev/Livara-OS/releases/tag/desktop-v0.1.4)
into one directory. If Code is installed, also download
`livara-code_0.1.4_amd64.deb` into that directory. The installer requires the
matching Code package when the app is already installed, preventing an update
that leaves compiled controller fixes behind. Close Browser and Code, then run:

```sh
bash Install-Livara-Update.sh
```

The installer verifies the files and uses APT to upgrade the existing package and
resolve any missing Ubuntu dependencies. Log out and back in to load the updated
Shell extension, and reopen Livara apps. No ISO replacement or reboot is needed.
Personal preferences, browser profiles, Code settings, home files and
administrator conffile edits are preserved. The login helper refreshes only
Livara's managed GTK CSS blocks using the user's saved control preferences.

An installed OS retains package upgrades. The current live ISO has no persistent
package storage: changes disappear at reboot. Keep the small update package on
a persistent disk and apply it again in a later live session, or install Livara
to retain upgrades. An update cannot make the read-only live ISO persistent.

## App resources and recovery

The package refreshes only the named Livara UI JS/CSS and pinned Zen English localization files inside the matching
Browser's `omni.ja` archives and adds a managed Code workbench CSS block. The
source pin/build identity must match, and Browser's executable hash must match
its build manifest. Code's stylesheet integrity checksum is updated rather than
disabling its integrity checker. Native engines/executables and user profiles
remain unchanged by the small desktop package. The separate Code DEB replaces
the application under `/opt/livara-code`, including its compiled TypeScript and
bundled Electron runtime, after CLI and real native window/control tests. It
owns no desktop launchers and does not touch profiles/extensions in the home
directory. Once the matching compiled package is installed, the resource helper
leaves its package-owned files unchanged.

All installed application resources are validated before writing. Original files
are saved under `/var/lib/livara/app-resource-backups`, and `latest.json` records
paths and before/after SHA-256 hashes. A failed write rolls back changes already
applied during that run. Unknown/custom app builds are preserved with a warning;
the desktop package itself can still upgrade. After investigating the warning,
retry with `sudo livara-refresh-app-resources`. Recovery is an administrator
operation: close apps and restore only the original files whose paths and hashes
are listed in that report, or reinstall the matching original application bundle.

Ubuntu kernel, NVIDIA, Mesa and security fixes continue through Ubuntu's signed
APT sources. Tor Browser retains its own official updater and is untouched.
There is no new background update server or unsigned APT repository.

## Release verification and maintainers

Only download from the project's official HTTPS GitHub release. Checksums detect
corruption; a checksum distributed alongside a file is not publisher
authentication. The tag-triggered workflow records GitHub artifact provenance.
With GitHub CLI, verify the package's provenance before installation:

```sh
gh attestation verify livara-desktop_0.1.4_all.deb --repo Livara-Dev/Livara-OS
gh attestation verify livara-code_0.1.4_amd64.deb --repo Livara-Dev/Livara-OS
sha256sum --check SHA256SUMS
```

Build locally with `python3 scripts/package-desktop-update.py`; outputs are in
`dist/update/`. Build and runtime-test Code with the existing `build-code.sh` and
`code-runtime-smoke.py` workflow, then run `python3 scripts/package-code-update.py
dist/forks/livara-code-linux-x64.tar.xz`. The Code packager checks the pinned build
identity and requires compiled-controller/style source hashes to match the
current fixes. Merge the tested Code package into the release with
`python3 scripts/package-desktop-update.py --code-package
dist/update-code/livara-code_0.1.4_amd64.deb`.

The manifest records the source commit and whether source files
were modified. A local working-tree package is a development artifact, not a
published release. The `desktop-vVERSION` tag workflow runs source tests, checks
a real previous-to-new DEB unpack upgrade and launcher ownership, attests the
packages, and publishes only after the matching Code artifact checks also succeed. An
unchanged Code recipe may reuse a successful same-repository compiled candidate;
the validator verifies the prior job and every relevant source input. The previous equivalent Code build took about
12 minutes to compile; allow additional time for dependencies and runtime checks.
It does not invoke Browser or ISO builds. Publication requires a successful
Actions run; a local package alone
does not establish that users can download the update.

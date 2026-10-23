# Livara Essentials

Open **Settings → Feature hub** or **Livara Essentials**. The native GTK app uses AMOLED black, purple accents, rounded cards, keyboard navigation, custom window controls and a live theme preview. Motion follows the system's animation preference. These features are included in the source builder; the downloadable source is not a preinstalled operating system.

## Design

**Theme Studio** previews and applies an accent, corner radius, border width and surface opacity. Named themes are private validated JSON and can be imported/exported, including visual desktop preferences, fonts, desktop glass, cursor and global icon/sound themes. Per-app icon replacements are managed separately. Managed GTK 3/4 CSS blocks preserve unrelated user CSS. Restore app styling removes only Livara's block. Native Livara windows update immediately; other GTK apps may require reopening. An app with a separate renderer must use its own theme. This is not Apple's proprietary optical renderer. Fonts, desktop glass, cursor themes, sounds and per-app icons have their own working controls linked from the page.

**Profiles** apply real desktop preferences. Gaming suppresses notification banners, prevents idle blanking and disables shell glass; Work enables dynamic workspaces and a fixed dock; Security Lab uses six fixed workspaces and disables recent-file recording; Battery Saver disables animation/glass/clock seconds and sets a five-minute idle delay. Supported power modes use the system power-profiles daemon; unsupported or unauthorized modes are reported. Undo restores the previous desktop values and, when available, the previous power profile.

**Layouts** save visual preferences and the positions, monitor and workspace of up to 100 open windows. They restore matching app IDs and window ordinals, with monitor bounds adjusted to the current displays. Missing apps are counted, not launched. No window contents, titles or commands are stored. Requires the enabled Livara GNOME extension. Desktop widgets are not part of this implementation.

## Productivity

**Command palette:** Super+Alt+Space. Search desktop apps, Livara features, Studio tools, recent local files when file history is enabled, and up to 800 immediate files in Documents/Downloads/Desktop. This bounded search does not index the entire disk. App launch uses desktop metadata; commands are fixed argument arrays, never shell expressions. Enter opens the selected result; Up/Down select; Escape closes. Shortcut avoids the Super+Space input-language binding.

**Window zones:** draw one to nine rectangles. Super+Alt+1…9 moves the focused normal window into the corresponding zone on its current display. Transient dialogs are excluded. Save updates real extension settings; two-column reset and undo are provided.

**Clipboard:** GPaste text/image history is opt-in, limited by default to 100 entries and 64MB. Super+Alt+V opens history. Livara pauses tracking while locked and in unknown or excluded focused apps. Configure exclusions using desktop IDs. These are convenience filters, not an isolation guarantee: other clipboard applications and sharing plugins are independent, focus transitions may expose copied content, and history is local plaintext. Do not store secrets in history. Clear history from GPaste's UI. The upstream GPaste shell extension is not automatically enabled.

**Quick Look:** in Files, select an image, PDF, supported media or code/text file and press Space. The actual viewer is GNOME Sushi; format support depends on installed decoders. Space/Escape closes.

**Recorder:** OBS Studio supports screen/window capture, microphone mixing, scenes and available hardware encoders. Use the Wayland portal to choose the capture. For manual redaction, add an opaque Color Source above a scene and place it over a private region, or crop the source. Inspect a test recording. There is no automatic secret detection.

**Connect:** KDE Connect supplies phone pairing, file transfers, notification sync, remote input and optional clipboard sharing. Approve pairing on both devices and enable only desired plugins. The phone needs KDE Connect and network reachability. No pairing, firewall rule or remote-control session is silently created. An optional UFW application profile `Livara Connect` declares TCP/UDP ports 1714–1764; scope any enabled rule to a trusted LAN.

## Security

**Permission dashboard:** enumerate installed Flatpak apps, inspect manifest permissions and user overrides, allow/deny network, home-directory access and microphone/audio, or reset one app's user overrides. Restart the app after changes. Audio is the PulseAudio socket, including playback and microphone. These controls do not sandbox native packages, separate camera permissions or remove permissions granted by another mechanism. The system privacy/applications panels remain available for supported portal permissions.

**Security Lab:** creates a real private case with evidence, reports, notes, a scope document and a working directory. The toolbox opens the existing rootless Kali container with that working directory mounted. The container shares the host's network and is not a virtual machine. Core tools are included by the ISO builder; the complete catalog remains an explicit download.

## System

**Hardware assistant:** runs bounded read-only firmware, driver, Secure Boot, session and storage checks. Graphics setup, Additional Drivers and Displays open their real system tools. Driver/firmware installation requires the tools' normal administrator authentication. No physical Intel Core Ultra or RTX series qualification is inferred from dependency checks.

**Recovery:** Timeshift must be configured with a destination, retention and a tested restore process. Review snapshots and targets in its actual interface. Snapshots do not protect all personal files; Déjà Dup is included for personal backups. No automatic snapshot or successful restore is claimed before configuration/testing.

**Offline help:** bundled Livara Markdown guides open locally; apropos searches installed tool manuals. Read a chosen manual with `man NAME` in the terminal. No internet request is made by the help search.

**Installation:** see [installation.md](installation.md). Disk installation and encryption have not yet completed an end-to-end install/reboot qualification.

**Accounts:** GNOME Users manages persistent local accounts on an installed system. Live USB sessions remain temporary unless separately configured for persistence.

**Updates:** Software Updater and software-source settings use signed distribution APT updates. Unattended security updates remain enabled in the system image configuration. Livara does not operate a release server: locally branded browser/Code/Livara packages need a source rebuild. Distribution release upgrades are disabled on the installed derivative; ordinary security/package updates remain available. Firmware follows manufacturer/fwupd support.

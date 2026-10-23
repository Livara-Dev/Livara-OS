#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
version=0.1.0
output_dir="${1:-$project_dir/dist}"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
staging_dir="$(mktemp -d)"
chmod 0755 "$staging_dir"
trap 'rm -rf -- "$staging_dir"' EXIT
install -d "$staging_dir/DEBIAN" "$staging_dir/usr/bin" \
  "$staging_dir/usr/lib/python3/dist-packages/livara" \
  "$staging_dir/usr/share/livara/toolbox" \
  "$staging_dir/usr/share/livara/icons" \
  "$staging_dir/usr/share/livara/browser" \
  "$staging_dir/usr/share/fonts/truetype/livara" \
  "$staging_dir/usr/share/livara/terminal" \
  "$staging_dir/usr/share/livara/branding" \
  "$staging_dir/usr/share/gnome-shell/extensions/livara-glass@livara.local" \
  "$staging_dir/usr/share/plymouth/themes/livara" \
  "$staging_dir/usr/share/applications" \
  "$staging_dir/usr/share/icons/hicolor/scalable/apps" \
  "$staging_dir/usr/share/backgrounds/livara" \
  "$staging_dir/usr/share/glib-2.0/schemas" \
  "$staging_dir/usr/share/doc/livara-desktop"
install -m 0644 "$project_dir"/src/livara/*.py "$staging_dir/usr/lib/python3/dist-packages/livara/"
install -m 0644 "$project_dir/share/livara/toolbox/Containerfile" "$staging_dir/usr/share/livara/toolbox/"
install -m 0644 "$project_dir/share/livara/icons/"*.svg "$staging_dir/usr/share/livara/icons/"
install -m 0644 "$project_dir/artwork/livara-logo.png" "$staging_dir/usr/share/livara/logo.png"
install -m 0644 "$project_dir/artwork/livara-browser.png" "$staging_dir/usr/share/livara/browser-logo.png"
install -m 0644 "$project_dir/artwork/livara-code.png" "$staging_dir/usr/share/livara/code-logo.png"
install -m 0644 "$project_dir/artwork/livara-logo.png" "$staging_dir/usr/share/plymouth/themes/livara/logo.png"
install -m 0644 "$project_dir/share/plymouth/"* "$staging_dir/usr/share/plymouth/themes/livara/"
install -m 0644 "$project_dir/share/applications/"*.desktop "$staging_dir/usr/share/applications/"
install -m 0644 "$project_dir"/artwork/org.livara.*.svg "$staging_dir/usr/share/icons/hicolor/scalable/apps/"
install -m 0644 "$project_dir/artwork/"livara-*.svg "$staging_dir/usr/share/backgrounds/livara/"
for wallpaper in glass aurora dusk verdant; do
  install -m 0644 "$project_dir/artwork/livara-$wallpaper.png" "$staging_dir/usr/share/backgrounds/livara/"
done
install -m 0644 "$project_dir/share/livara/90_livara.gschema.override" "$staging_dir/usr/share/glib-2.0/schemas/"
install -m 0644 "$project_dir/share/livara/org.livara.desktop.gschema.xml" "$staging_dir/usr/share/glib-2.0/schemas/"
install -m 0644 "$project_dir/share/gnome-shell/extensions/livara-glass@livara.local/"* "$staging_dir/usr/share/gnome-shell/extensions/livara-glass@livara.local/"
install -d "$staging_dir/usr/share/livara/help" "$staging_dir/etc/calamares/modules" "$staging_dir/etc/calamares/branding/livara" "$staging_dir/usr/lib/x86_64-linux-gnu/calamares/modules/livara" "$staging_dir/etc/ufw/applications.d"
install -m 0644 "$project_dir"/docs/*.md "$staging_dir/usr/share/livara/help/"
install -m 0644 "$project_dir/share/calamares/settings.conf" "$staging_dir/etc/calamares/"
install -m 0644 "$project_dir"/share/calamares/modules/*.conf "$staging_dir/etc/calamares/modules/"
install -m 0644 "$project_dir"/share/calamares/branding/livara/* "$staging_dir/etc/calamares/branding/livara/"
install -m 0644 "$project_dir/artwork/livara-logo.png" "$staging_dir/etc/calamares/branding/livara/logo.png"
install -m 0644 "$project_dir"/share/calamares/job/* "$staging_dir/usr/lib/x86_64-linux-gnu/calamares/modules/livara/"
install -m 0755 "$project_dir/share/calamares/livara-install" "$staging_dir/usr/bin/"
install -m 0644 "$project_dir/share/ufw/livara-connect" "$staging_dir/etc/ufw/applications.d/"
install -d "$staging_dir/etc/apt/apt.conf.d"
install -m 0644 "$project_dir"/share/apt/* "$staging_dir/etc/apt/apt.conf.d/"
install -m 0644 "$project_dir/LICENSE" "$staging_dir/usr/share/doc/livara-desktop/copyright"
install -m 0644 "$project_dir/artwork/README.md" "$staging_dir/usr/share/doc/livara-desktop/artwork-notes.md"
install -m 0644 "$project_dir/share/livara/terminal/livara.bash" "$staging_dir/usr/share/livara/terminal/"
install -m 0755 "$project_dir/share/livara/terminal/livara-terminal" "$staging_dir/usr/bin/"
install -m 0755 "$project_dir/share/livara/branding/apply-branding.py" "$staging_dir/usr/share/livara/branding/"
install -m 0644 "$project_dir"/fonts/ttf/*.ttf "$staging_dir/usr/share/fonts/truetype/livara/"
install -m 0644 "$project_dir/fonts/OFL.txt" "$staging_dir/usr/share/fonts/truetype/livara/"
install -m 0644 "$project_dir/fonts/OFL.txt" "$staging_dir/usr/share/doc/livara-desktop/font-license.txt"
install -d "$staging_dir/usr/share/livara/fonts"
cp -R "$project_dir/fonts/sources" "$staging_dir/usr/share/livara/fonts/"
install -m 0644 "$project_dir/fonts/OFL.txt" "$staging_dir/usr/share/livara/fonts/"
if [[ -d "$project_dir/fonts/vendor" ]]; then
  cp -R "$project_dir/fonts/vendor" "$staging_dir/usr/share/livara/fonts/"
fi
install -D -m 0644 "$project_dir/share/fontconfig/60-livara-fonts.conf" "$staging_dir/usr/share/fontconfig/conf.avail/60-livara-fonts.conf"
install -d "$staging_dir/etc/fonts/conf.d"
ln -s /usr/share/fontconfig/conf.avail/60-livara-fonts.conf "$staging_dir/etc/fonts/conf.d/60-livara-fonts.conf"
find "$staging_dir/usr/share/livara/fonts" -type d -exec chmod 0755 {} +
find "$staging_dir/usr/share/livara/fonts" -type f -exec chmod 0644 {} +
install -m 0644 "$project_dir/share/livara/browser/"*.py "$staging_dir/usr/share/livara/browser/"
install -m 0644 "$project_dir/forks/tor/upstream.json" "$staging_dir/usr/share/livara/browser/tor-upstream.json"
install -m 0644 "$project_dir/forks/tor/files.json" "$staging_dir/usr/share/livara/browser/tor-files.json"
install -m 0755 "$project_dir/share/livara/browser/livara-browser" "$staging_dir/usr/bin/livara-browser"
for app in livara livara-center livara-settings livara-monitor livara-studio livara-chat livara-code livara-graphics livara-essentials livara-palette; do
  case "$app" in
    livara) module=cli; argument='' ;;
    livara-center) module=gui; argument='' ;;
    livara-settings) module=gui; argument='mode="settings"' ;;
    livara-monitor) module=monitor_gui; argument='' ;;
    livara-studio) module=studio_gui; argument='' ;;
    livara-chat) module=web_gui; argument='chat=True' ;;
    livara-code) module=code_launcher; argument='' ;;
    livara-essentials) module=essentials_gui; argument='' ;;
    livara-palette) module=palette; argument='' ;;
    livara-graphics) module=gpu_gui; argument='' ;;
  esac
  cat > "$staging_dir/usr/bin/$app" <<EOF
#!/usr/bin/python3
from livara.$module import main
raise SystemExit(main($argument))
EOF
  chmod 0755 "$staging_dir/usr/bin/$app"
done
find "$staging_dir/etc" -type f -printf '/etc/%P\n' | sort > "$staging_dir/DEBIAN/conffiles"
cat > "$staging_dir/DEBIAN/control" <<EOF
Package: livara-desktop
Version: $version
Section: utils
Priority: optional
Architecture: all
Maintainer: Livara OS contributors <livara@localhost>
Depends: python3 (>= 3.11), python3-gi, python3-cairo, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-gdkpixbuf-2.0, gir1.2-adw-1, gir1.2-webkit-6.0, libglib2.0-bin, librsvg2-common, webp-pixbuf-loader, fontconfig, gpaste-2, gnome-sushi, obs-studio, timeshift, deja-dup, flatpak, kdeconnect, update-manager, software-properties-gtk, fwupd, power-profiles-daemon, calamares, cryptsetup-initramfs, grub-pc-bin, grub-efi-amd64-bin, efibootmgr, btrfs-progs, squashfs-tools
Recommends: gnome-terminal, podman, uidmap, slirp4netns, fuse-overlayfs, yaru-theme-gtk, yaru-theme-icon
Description: Livara desktop control center and security workspace
 Native GTK desktop app, read-only system checks, SHA-256 verification,
 evidence workspaces, and an isolated Kali Linux toolbox.
EOF
cat > "$staging_dir/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    glib-compile-schemas /usr/share/glib-2.0/schemas
    fc-cache -f /usr/share/fonts/truetype/livara
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
EOF
cat > "$staging_dir/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = purge ]; then
    if command -v glib-compile-schemas >/dev/null 2>&1; then
        glib-compile-schemas /usr/share/glib-2.0/schemas
    fc-cache -f /usr/share/fonts/truetype/livara
    fi
fi
EOF
chmod 0755 "$staging_dir/DEBIAN/postinst" "$staging_dir/DEBIAN/postrm"
dpkg-deb --root-owner-group --build "$staging_dir" "$output_dir/livara-desktop_${version}_all.deb"


#!/usr/bin/env bash
set -euo pipefail
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8
if getent passwd ubuntu >/dev/null; then
  userdel -r ubuntu
fi
# Docker owns /etc/hosts and /etc/hostname during builds; ISO assembly writes them.
cat > /usr/lib/os-release <<'EOF'
NAME="Livara OS"
PRETTY_NAME="Livara OS 0.1 (Verdant Preview)"
ID=livara
ID_LIKE="ubuntu debian"
LOGO=org.livara.Center
VERSION="0.1.0 (Verdant)"
VERSION_ID="0.1"
VERSION_CODENAME=noble
UBUNTU_CODENAME=noble
EOF
printf 'Livara OS 0.1 · Verdant Preview\nBased on Ubuntu 24.04 LTS\n' > /etc/issue
cat > /etc/casper.conf <<'EOF'
export USERNAME="livara"
export USERFULLNAME="Livara Live Session"
export HOST="livara"
export BUILD_SYSTEM="Ubuntu"
export FLAVOUR="Ubuntu"
EOF
mkdir -p /etc/skel/.config/autostart /etc/skel/Livara/Cases /etc/skel/Livara/Workspace
cat > /etc/skel/.config/mimeapps.list <<'EOF'
[Default Applications]
x-scheme-handler/http=org.livara.Browser.desktop;
x-scheme-handler/https=org.livara.Browser.desktop;
text/html=org.livara.Browser.desktop;
application/xhtml+xml=org.livara.Browser.desktop;
EOF
mkdir -p /var/crash
cp /usr/share/applications/org.livara.Center.desktop /etc/skel/.config/autostart/
cat > /etc/skel/.config/autostart/livara-live-session.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Livara Live Session Settings
Exec=/usr/local/bin/livara-live-session
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
cat > /usr/local/bin/livara-live-session <<'EOF'
#!/bin/sh
# Only the ephemeral live session gets an unlocked screen. Installed desktops do not.
if grep -q 'boot=casper' /proc/cmdline; then
    gsettings set org.gnome.desktop.screensaver lock-enabled false
    gsettings set org.gnome.desktop.session idle-delay 0
    # Casper's desktop defaults are applied after system schema overrides.
    # Initialize Livara's intended appearance once per ephemeral home directory.
    if [ ! -e "$HOME/.config/livara/live-initialized" ]; then
        if /usr/bin/python3 -c 'from livara.desktop import apply_live_defaults; apply_live_defaults()'; then
            mkdir -p "$HOME/.config/livara"
            touch "$HOME/.config/livara/live-initialized"
        fi
    fi
fi
# Create rootless mappings for Casper's dynamically created live user.
if command -v getsubids >/dev/null && ! getsubids "$(id -un)" | grep -q .; then
    sudo /usr/local/sbin/livara-live-user-setup
fi
EOF
chmod 0755 /usr/local/bin/livara-live-session
cat > /usr/local/sbin/livara-live-user-setup <<'EOF'
#!/bin/sh
set -eu
# Casper creates the account during boot, after the image's package installation.
grep -q 'boot=casper' /proc/cmdline || exit 1
test "${SUDO_USER:-}" = livara || exit 1
usermod --add-subuids 100000-165535 --add-subgids 100000-165535 livara
EOF
chmod 0755 /usr/local/sbin/livara-live-user-setup
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/10-livara.conf <<'EOF'
[main]
plugins=keyfile
[keyfile]
unmanaged-devices=none
EOF
# Ubuntu's container seed can mark all network devices unmanaged.
rm -f /usr/lib/NetworkManager/conf.d/10-globally-managed-devices.conf
mkdir -p /etc/containers /etc/modules-load.d
cat > /etc/containers/storage.conf <<'EOF'
[storage]
driver = "overlay"
[storage.options.overlay]
mount_program = "/usr/bin/fuse-overlayfs"
EOF
printf 'fuse\n' > /etc/modules-load.d/livara.conf
systemctl enable NetworkManager.service gdm3.service apt-daily.timer apt-daily-upgrade.timer
systemctl set-default graphical.target
# The toolbox is daemonless and rootless; rootful API/auto-update jobs are unused.
systemctl disable podman.service podman.socket podman-auto-update.service \
  podman-auto-update.timer podman-restart.service podman-clean-transient.service
if [[ -f /etc/systemd/system/livara-selftest.service ]]; then
  chmod 0755 /usr/lib/livara/live-selftest
  systemctl enable livara-selftest.service
fi
cat > /etc/sysctl.d/60-livara.conf <<'EOF'
kernel.randomize_va_space=2
kernel.dmesg_restrict=1
fs.protected_hardlinks=1
fs.protected_symlinks=1
EOF
# No listening security-tool services are enabled by the image.
# Firewall policy is inbound-deny/outbound-allow, applied at live boot.
sed -i 's/^ENABLED=.*/ENABLED=yes/' /etc/ufw/ufw.conf
systemctl enable ufw.service
# Live accounts must be able to use rootless Podman's unprivileged namespaces.
# Scope Ubuntu's AppArmor user-namespace exception to the packaged Podman executable.
if [[ -d /etc/apparmor.d && ! -f /etc/apparmor.d/podman ]]; then
  cat > /etc/apparmor.d/livara-podman <<'EOF'
abi <abi/4.0>,
include <tunables/global>
/usr/bin/podman flags=(unconfined) {
  userns,
  include if exists <local/livara-podman>
}
EOF
fi
printf 'LANG=en_US.UTF-8\n' > /etc/default/locale
# Tor runs only when the desktop user selects the isolated onion mode.
systemctl disable tor.service tor@default.service || true
# Ubuntu restricts unprivileged namespaces. Grant them only to these trusted
# application binaries; Chromium and Gecko retain their own content sandboxes.
if [[ -d /etc/apparmor.d ]]; then
  for livara_app in code browser; do
    cat > "/etc/apparmor.d/livara-$livara_app" <<EOF
abi <abi/4.0>,
include <tunables/global>
/opt/livara-$livara_app/livara-$livara_app flags=(unconfined) {
  userns,
  include if exists <local/livara-$livara_app>
}
EOF
  done
  cat > /etc/apparmor.d/livara-tor-browser <<'EOF'
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
EOF
  if command -v apparmor_parser >/dev/null; then
    for livara_policy in /etc/apparmor.d/livara-code /etc/apparmor.d/livara-browser /etc/apparmor.d/livara-tor-browser; do
      apparmor_parser --skip-kernel-load --skip-read-cache "$livara_policy"
    done
  fi
fi
# NVIDIA's open kernel modules and DRM KMS support the Wayland compositor.
# PRIME chooses the rendering device; do not force the discrete GPU globally.
cat > /etc/modprobe.d/60-livara-nvidia-kms.conf <<'EOF'
options nvidia_drm modeset=1 fbdev=1
EOF
bash /usr/lib/livara/verify-graphics-kernel
if [[ -f /usr/share/plymouth/themes/livara/livara.plymouth ]]; then
  update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth /usr/share/plymouth/themes/livara/livara.plymouth 200
  update-alternatives --set default.plymouth /usr/share/plymouth/themes/livara/livara.plymouth
fi
# Identity assets are replaced before initramfs compilation so fallback boot
# screens and GDM receive the same mark. Package notices stay intact.
/usr/bin/python3 /usr/share/livara/branding/apply-branding.py
/usr/bin/python3 /usr/share/livara/branding/apply-branding.py --audit
glib-compile-schemas --strict /usr/share/glib-2.0/schemas
rm -f /etc/machine-id
dbus-uuidgen --ensure=/etc/machine-id
update-initramfs -u -k all
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id
rm -f /root/.bash_history
find /var/log -type f -exec truncate -s 0 {} +


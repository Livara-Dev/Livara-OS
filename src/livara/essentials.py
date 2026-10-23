"""Desktop feature catalog, bounded local stores and real service adapters."""
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
from . import core, desktop, preferences, theme

FEATURES = (
 ("theme", "Theme Studio", "Color, glass, corners, borders, fonts, sounds and icons.", "Design", None),
 ("profiles", "Desktop profiles", "Gaming, Work, Security Lab and Battery Saver, with a real power-profile adapter.", "Design", None),
 ("layouts", "Desktop layouts", "Save the desktop and restore arrangements to matching open apps.", "Design", None),
 ("palette", "Command palette", "Search apps, files, settings and Studio tools with one shortcut.", "Productivity", "livara-palette"),
 ("tiling", "Window zones", "Draw up to nine zones and move the focused window with a shortcut.", "Productivity", None),
 ("clipboard", "Clipboard history", "Opt-in text and image history, with private-app exclusions.", "Productivity", "gpaste-client"),
 ("preview", "Quick Look", "Open Files, select an image, PDF, video or code file, and press Space.", "Productivity", "nautilus"),
 ("capture", "Screen recorder", "Record a window or screen, mix microphone audio and mask sensitive areas.", "Productivity", "obs"),
 ("recovery", "Recovery snapshots", "Configure a real Timeshift snapshot destination before making system changes.", "System", "timeshift-gtk"),
 ("permissions", "Permission dashboard", "Inspect sandboxed apps and control their network, files and audio access.", "Security", "flatpak"),
 ("lab", "Security Lab", "Project scope, private evidence, notes and an isolated working directory.", "Security", None),
 ("hardware", "Hardware assistant", "Read driver, firmware, Secure Boot and hybrid graphics readiness.", "System", None),
 ("connect", "Livara Connect", "Pair a phone with KDE Connect for files, notifications and clipboard sharing.", "Productivity", "kdeconnect-app"),
 ("help", "Offline documentation", "Search bundled Livara guides and installed tool manuals locally.", "System", None),
 ("install", "Install Livara", "Calamares disk, encryption, account and bootloader setup.", "System", "calamares"),
 ("accounts", "Persistent accounts", "Manage local users and passwords on an installed system.", "System", "gnome-control-center"),
 ("updates", "Updates & firmware", "Trusted APT updates, firmware tools and locally rebuilt Livara packages.", "System", "update-manager"),
)
PROFILES = {
 "Gaming": ({"notification-banners": False, "idle-delay": 0, "glass-enabled": False}, "performance"),
 "Work": ({"notification-banners": True, "dock-autohide": False, "dock-intellihide": False, "dynamic-workspaces": True}, "balanced"),
 "Security Lab": ({"notification-banners": False, "dynamic-workspaces": False, "workspace-count": 6, "remember-recent-files": False}, "balanced"),
 "Battery Saver": ({"animations": False, "glass-enabled": False, "clock-seconds": False, "idle-delay": 300}, "power-saver"),
}
DEFAULT_ZONES = [[0, 0, .5, 1], [.5, 0, .5, 1]]


def name(value):
    if not isinstance(value, str): raise ValueError("Enter a name")
    value = unicodedata.normalize("NFC", value.strip())
    if not 1 <= len(value) <= 64 or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Use a name of 1–64 characters")
    return value


def validate_zones(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 9: raise ValueError("Draw between one and nine zones")
    result = []
    for rect in value:
        if not isinstance(rect, list) or len(rect) != 4 or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in rect):
            raise ValueError("Zones must use normalized coordinates")
        x, y, w, h = rect
        if w < .06 or h < .06 or x + w > 1.001 or y + h > 1.001: raise ValueError("A zone must fit inside the display")
        result.append([round(v, 4) for v in rect])
    return result


def validate_layout(value):
    if not isinstance(value, dict) or set(value) != {"preferences", "windows"}: raise ValueError("Invalid desktop layout")
    prefs = preferences.validate_values(value["preferences"])
    if set(prefs) - set(desktop.APPEARANCE_PRESET_KEYS): raise ValueError("A layout cannot change input or privacy settings")
    windows = value["windows"]
    if not isinstance(windows, list) or len(windows) > 100: raise ValueError("At most 100 windows can be saved")
    for window in windows:
        if not isinstance(window, dict) or set(window) != {"app", "ordinal", "workspace", "monitor", "rect", "maximized", "fullscreen"}: raise ValueError("Invalid window placement")
        if not isinstance(window["app"], str) or not 1 <= len(window["app"]) <= 255 or any(c in window["app"] for c in "/\\\n\r\0"): raise ValueError("Invalid app ID")
        for key, limit in (("ordinal", 100), ("workspace", 35), ("monitor", 31)):
            if type(window[key]) is not int or not 0 <= window[key] <= limit: raise ValueError("Invalid window index")
        validate_zones([window["rect"]])
        if type(window["maximized"]) is not bool or type(window["fullscreen"]) is not bool: raise ValueError("Invalid window state")
    return {"preferences": prefs, "windows": windows}


class NamedStore:
    """Private inert JSON, with locks, bounded records and atomic replacement."""
    def __init__(self, kind, validator, config_home=None):
        if kind not in ("layouts", "themes"): raise ValueError("Unknown feature store")
        base = Path(config_home or os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        if not base.is_absolute(): raise ValueError("Use an absolute configuration directory")
        self.folder = base / "livara/essentials"
        self.path = self.folder / (kind + ".json")
        self.validator = validator

    @contextmanager
    def locked(self):
        for path in (self.folder.parent, self.folder):
            if path.is_symlink(): raise ValueError("Feature storage cannot be a symbolic link")
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.stat().st_uid != os.getuid(): raise ValueError("Feature storage must belong to this user")
            path.chmod(0o700)
        fd = os.open(self.folder / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError("Invalid feature storage lock")
            fcntl.flock(fd, fcntl.LOCK_EX);yield
        finally: os.close(fd)

    def _read(self):
        if not self.path.exists() and not self.path.is_symlink(): return {}
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 2 * 1024 * 1024: raise ValueError("Feature file is invalid or too large")
            def unique(pairs):
                result = {}
                for key, item in pairs:
                    if key in result: raise ValueError("Duplicate feature keys")
                    result[key] = item
                return result
            value = json.load(stream, object_pairs_hook=unique)
        if not isinstance(value, dict) or len(value) > 64: raise ValueError("At most 64 items can be stored")
        return {name(key): self.validator(item) for key, item in value.items()}

    def list(self):
        with self.locked(): return self._read()

    def save(self, label, value):
        label, value = name(label), self.validator(value)
        with self.locked():
            items = self._read();items[label] = value
            if len(items) > 64: raise ValueError("Remove an old item before saving more")
            self._write(items)

    def delete(self, label):
        with self.locked():
            items = self._read();items.pop(name(label), None);self._write(items)

    def _write(self, items):
        data = json.dumps(items, ensure_ascii=False, allow_nan=False).encode()
        if len(data) > 2 * 1024 * 1024: raise ValueError("Feature store is too large")
        fd, path = tempfile.mkstemp(dir=self.folder, prefix=".essentials-")
        try:
            with os.fdopen(fd, "wb") as stream: stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(path, self.path)
        finally: Path(path).unlink(missing_ok=True)


def shell_call(method, argument=None):
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    params = GLib.Variant("(s)", (json.dumps(argument),)) if argument is not None else None
    result = bus.call_sync("org.gnome.Shell", "/org/livara/Desktop", "org.livara.Desktop", method,
                           params, GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, 5000, None)
    return json.loads(result.unpack()[0])


def appearance_snapshot():
    values = {}
    for key in desktop.APPEARANCE_PRESET_KEYS:
        item = desktop.read_option(key)
        if item is None: continue
        try:
            preferences.validate_value(key, item)
            if key == 'wallpaper-image' and item: desktop.validate_wallpaper_image(item)
        except ValueError: continue
        values[key] = item
    return values


def save_layout(label, *, store=None, capture=shell_call):
    values = appearance_snapshot()
    value = validate_layout({"preferences": values, "windows": capture("GetLayout")})
    (store or NamedStore("layouts", validate_layout)).save(label, value)
    return value


def restore_layout(label, *, store=None, apply=shell_call):
    items = (store or NamedStore("layouts", validate_layout)).list()
    if label not in items: raise ValueError("This layout no longer exists")
    layout = validate_layout(items[label])
    # The Shell validates the entire placement list before desktop preferences
    # change; unavailable desktop schemas remain untouched by the normal backend.
    result = apply("ApplyLayout", layout["windows"])
    result["desktop"] = desktop._apply_options(layout["preferences"])
    return result


def power_state():
    from gi.repository import Gio
    proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        None, "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles", "net.hadess.PowerProfiles", None)
    current, supported = proxy.get_cached_property("ActiveProfile"), proxy.get_cached_property("Profiles")
    if current is None or supported is None: raise ValueError("Power profiles are unavailable on this device/session")
    return proxy, current.unpack(), [p["Profile"] for p in supported.unpack()]


def apply_profile(label, with_power=True):
    if label not in PROFILES: raise ValueError("Choose a desktop profile")
    prefs, requested = PROFILES[label]
    before = {key: desktop.read_option(key) for key in prefs}
    result = desktop._apply_options(prefs)
    result["previous"] = {key: value for key, value in before.items() if value is not None}
    result["power"] = "unchanged"
    if with_power:
        try:
            from gi.repository import Gio, GLib
            proxy, previous, supported = power_state()
            if requested not in supported: raise ValueError("Requested power mode is not offered by this hardware")
            proxy.call_sync("org.freedesktop.DBus.Properties.Set", GLib.Variant("(ssv)",
                ("net.hadess.PowerProfiles", "ActiveProfile", GLib.Variant("s", requested))), Gio.DBusCallFlags.NONE, 5000, None)
            result["power"] = requested;result["previous_power"] = previous
        except Exception as error: result["power"] = "Unavailable: " + str(error)
    return result


def diagnostic(command, timeout=10):
    if not command or not shutil.which(command[0]): return {"available": False, "output": command[0] + " is not installed"}
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return {"available": True, "exit_code": result.returncode, "output": (result.stdout + result.stderr)[:131072]}
    except (OSError, subprocess.TimeoutExpired) as error: return {"available": False, "output": str(error)}


def hardware_report():
    return {label: diagnostic(command) for label, command in (
        ("Firmware", ["fwupdmgr", "get-devices", "--json"]),
        ("Drivers", ["ubuntu-drivers", "devices"]), ("Secure Boot", ["mokutil", "--sb-state"]),
        ("Displays", ["loginctl", "show-session", os.environ.get("XDG_SESSION_ID", "self"), "--property=Type", "--property=Remote"]),
        ("Storage", ["lsblk", "--json", "--output", "NAME,TYPE,FSTYPE,SIZE,MOUNTPOINTS,TRAN"]))}


def flatpak_apps():
    result = diagnostic(["flatpak", "list", "--app", "--columns=application,name"])
    if not result["available"] or result.get("exit_code") != 0: return []
    apps = []
    for line in result["output"].splitlines():
        identifier, _, title = line.partition("\t")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,254}", identifier): apps.append((identifier, title or identifier))
    return apps[:500]


def permission_command(identifier, permission, allowed):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,254}", identifier): raise ValueError("Invalid Flatpak app ID")
    if type(allowed) is not bool: raise ValueError("Choose an on/off permission")
    flags = {"network": ("--share=network", "--unshare=network"), "home": ("--filesystem=home", "--nofilesystem=home"),
             "audio": ("--socket=pulseaudio", "--nosocket=pulseaudio")}
    if permission not in flags: raise ValueError("Unknown sandbox permission")
    return ["flatpak", "override", "--user", flags[permission][0 if allowed else 1], identifier]


def create_lab(label, directory=None):
    target = core.create_case(label, directory)
    for folder in ("work", "notes"):
        (target / folder).mkdir(mode=0o700, exist_ok=True)
    scope = target / "notes/scope.md"
    if not scope.exists():
        fd = os.open(scope, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream: stream.write("# Project scope\n\nAuthorized systems:\n\nGoals:\n\nBoundaries:\n\nEvidence notes:\n")
    return target


def help_documents(directory=None):
    base = Path(directory) if directory else Path("/usr/share/livara/help")
    if not base.is_dir(): base = Path(__file__).resolve().parents[2] / "docs"
    return sorted((p for p in base.glob("*.md") if p.is_file() and not p.is_symlink() and p.stat().st_size <= 512 * 1024), key=lambda p: p.stem)


def manual_search(query):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 128 or "\0" in query: raise ValueError("Enter a manual topic of up to 128 characters")
    return diagnostic(["apropos", "--long", "--", query.strip()], timeout=5)


def installed_theme_names(kind):
    if kind not in ('icons','sounds'):raise ValueError('Unknown theme kind')
    paths=[Path.home()/'.local/share'/kind,Path('/usr/local/share')/kind,Path('/usr/share')/kind]
    if kind=='icons':paths.insert(0,Path.home()/'.icons')
    result=set()
    for root in paths:
        try:
            for path in root.iterdir():
                if path.is_dir() and (path/'index.theme').is_file():result.add(path.name)
        except OSError:continue
    return sorted(result,key=str.casefold)


def validate_theme_bundle(value):
    if not isinstance(value,dict) or set(value)!={'tokens','preferences','extras'}:raise ValueError('Invalid theme bundle')
    tokens=theme.validate(value['tokens'])
    prefs=preferences.validate_values(value['preferences'])
    if set(prefs)-set(desktop.APPEARANCE_PRESET_KEYS):raise ValueError('Theme contains nonvisual preferences')
    extras=value['extras']
    if not isinstance(extras,dict) or set(extras)-{'icons','sounds','event-sounds'}:raise ValueError('Unknown theme option')
    for key,item in extras.items():
        if key=='event-sounds':
            if type(item)is not bool:raise ValueError('Invalid sound switch')
        elif not isinstance(item,str) or not 1<=len(item)<=128 or item in ('.','..') or any(c in item for c in '/\\\n\r\0'):raise ValueError('Invalid theme name')
    return {'tokens':tokens,'preferences':prefs,'extras':dict(extras)}


def current_theme_bundle(tokens=None):
    prefs=appearance_snapshot()
    extras={}
    for name,schema,key in [('icons','org.gnome.desktop.interface','icon-theme'),('sounds','org.gnome.desktop.sound','theme-name'),('event-sounds','org.gnome.desktop.sound','event-sounds')]:
        settings=desktop.settings_for(schema)
        if settings and settings.props.settings_schema.has_key(key):extras[name]=settings.get_value(key).unpack()
    return validate_theme_bundle({'tokens':tokens or theme.read_values(),'preferences':prefs,'extras':extras})


def apply_theme_bundle(value):
    value=validate_theme_bundle(value)
    mappings={'icons':('org.gnome.desktop.interface','icon-theme'),'sounds':('org.gnome.desktop.sound','theme-name'),'event-sounds':('org.gnome.desktop.sound','event-sounds')}
    for name,item in value['extras'].items():
        if name in ('icons','sounds') and item not in installed_theme_names(name):raise ValueError('Install this '+name+' theme before applying it')
        desktop.prepare_setting(*mappings[name],item)
    # Existing desktop backend validates installed cursors and images and rolls
    # its own preferences back on write errors. Multi-file theme apply is not
    # advertised as an atomic system transaction.
    result=desktop._apply_options(value['preferences']);theme.apply(value['tokens'])
    for name,item in value['extras'].items():desktop.write_setting(*mappings[name],item)
    return result

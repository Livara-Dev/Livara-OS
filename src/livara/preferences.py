"""Searchable desktop preference definitions and a private, inert preset store.

No setting names, commands or filesystem targets are accepted from presets
outside this catalog. Runtime GSettings availability is checked by desktop.py.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import copy
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import unicodedata

CATALOG = []
SCHEMAS = {
    "livara": "org.livara.desktop", "interface": "org.gnome.desktop.interface",
    "wm": "org.gnome.desktop.wm.preferences", "mutter": "org.gnome.mutter",
    "dock": "org.gnome.shell.extensions.dash-to-dock", "background": "org.gnome.desktop.background",
    "notifications": "org.gnome.desktop.notifications", "privacy": "org.gnome.desktop.privacy",
    "session": "org.gnome.desktop.session", "lock": "org.gnome.desktop.screensaver",
    "keyboard": "org.gnome.desktop.peripherals.keyboard", "mouse": "org.gnome.desktop.peripherals.mouse",
    "touchpad": "org.gnome.desktop.peripherals.touchpad", "color": "org.gnome.settings-daemon.plugins.color",
}


def _add(section, name, title, description, kind, schema, key=None, *, choices=None, bounds=None, unit=""):
    row = dict(name=name, title=title, description=description, section=section,
               kind=kind, schema=SCHEMAS[schema], key=key or name, unit=unit)
    if choices is not None:
        row["choices"] = [(item, item.replace("-", " ").title()) if isinstance(item, str) else item for item in choices]
    if bounds is not None:
        row["range"] = bounds
    row["keywords"] = " ".join((name, title, description, section))
    CATALOG.append(row)


_add("appearance", "appearance", "Appearance", "Dark or light desktop applications", "choice", "livara", choices=[("dark", "Dark"), ("light", "Light")])
_add("appearance", "accent", "Accent color", "Eight coordinated application and desktop accents", "choice", "livara", choices=[("purple", "Iris"), ("blue", "Ocean"), ("sage", "Sage"), ("bark", "Cocoa"), ("orange", "Sunset"), ("red", "Ruby"), ("olive", "Olive"), ("magenta", "Orchid")])
_add("appearance", "wallpaper", "Livara wallpaper", "Choose an original background; replaces a custom image", "choice", "livara", choices=[("halo", "Halo"), ("glass", "Prism"), ("aurora", "Aurora"), ("dusk", "Dusk"), ("verdant", "Verdant")])
_add("appearance", "wallpaper-image", "Your wallpaper", "Use a local PNG, JPEG or WebP image; presets keep its local path", "image", "background", "picture-uri")
_add("appearance", "wallpaper-style", "Wallpaper fit", "Fit, fill, tile or span your desktop background", "choice", "background", "picture-options", choices=[("zoom", "Fill"), ("scaled", "Fit"), ("stretched", "Stretch"), ("centered", "Center"), ("spanned", "Span displays"), ("wallpaper", "Tile"), ("none", "No picture")])
_add("appearance", "glass-enabled", "Liquid glass", "Translucent desktop surfaces and background blur", "bool", "livara")
_add("appearance", "blur-radius", "Glass blur", "Adjust background blur; zero keeps the background sharp", "int", "livara", bounds=(0, 60, 1), unit="px")

_add("windows", "animations", "Desktop animations", "Disable motion across the desktop when preferred", "bool", "interface", "enable-animations")
_add("windows", "window-button-style", "Button style", "Livara traffic lights or standard native controls", "choice", "livara", choices=[("traffic-lights", "Traffic lights"), ("default", "Native")])
_add("windows", "window-buttons", "Button side", "Physical edge for close, minimize and green controls", "choice", "wm", "button-layout", choices=[("close,minimize,maximize:", "Left"), (":minimize,maximize,close", "Right")])
_add("windows", "window-button-size", "Button diameter", "Traffic-light size in logical pixels", "int", "livara", bounds=(10, 22, 1), unit="px")
_add("windows", "window-button-symbols", "Always show symbols", "Keep action symbols visible instead of showing them on hover", "bool", "livara")
_add("windows", "window-green-action", "Green button action", "Livara apps: Shift-click always maximizes or restores; F11 toggles fullscreen", "choice", "livara", choices=[("fullscreen", "Fullscreen"), ("maximize", "Maximize")])
for action, title in (("close", "Close"), ("minimize", "Minimize"), ("maximize", "Green control")):
    _add("windows", "window-" + action + "-color", title + " color", "Choose a six-digit traffic-light color", "color", "livara")
_add("windows", "window-animation-style", "Window transition", "Choose the opening and closing effect", "choice", "livara", choices=[("zoom", "Zoom"), ("lift", "Lift"), ("fade", "Fade"), ("off", "Off")])
_add("windows", "window-animation-duration", "Transition duration", "Time for opening and closing; follows reduced motion", "int", "livara", bounds=(80, 600, 10), unit="ms")
_add("windows", "edge-tiling", "Edge tiling", "Drag a window to the screen edge to tile it", "bool", "mutter")
_add("windows", "hot-corners", "Hot corners", "Open the overview from the screen corner", "bool", "interface", "enable-hot-corners")
_add("windows", "center-new-windows", "Center new windows", "Center windows that do not request their own position", "bool", "mutter")
_add("windows", "attach-modal-dialogs", "Attach dialogs", "Keep modal dialogs attached to their parent windows", "bool", "mutter")
_add("windows", "focus-mode", "Window focus", "Choose click-to-focus or pointer focus", "choice", "wm", choices=[("click", "Click"), ("sloppy", "Pointer"), ("mouse", "Strict pointer")])
_add("windows", "focus-new-windows", "New window focus", "Choose the window manager's smart or strict focus policy", "choice", "wm", choices=[("smart", "Smart"), ("strict", "Strict")])
_add("windows", "raise-on-click", "Raise on click", "Bring a clicked window above other windows", "bool", "wm")
_add("windows", "auto-raise", "Raise on pointer focus", "Automatically raise focused windows in pointer-focus modes", "bool", "wm")
_add("windows", "auto-raise-delay", "Auto-raise delay", "Wait before raising a pointer-focused window", "int", "wm", bounds=(0, 10000, 50), unit="ms")
_add("windows", "resize-with-right-button", "Right-button resize", "Use the window modifier and right mouse button to resize", "bool", "wm")
for action, label in (("double", "Double-click titlebar"), ("middle", "Middle-click titlebar"), ("right", "Right-click titlebar")):
    _add("windows", "titlebar-" + action + "-click", label, "Choose the window-manager titlebar action; app-drawn titlebars can differ", "choice", "wm", "action-" + action + "-click-titlebar", choices=[("toggle-maximize", "Maximize / restore"), ("toggle-maximize-horizontally", "Maximize horizontally"), ("toggle-maximize-vertically", "Maximize vertically"), ("minimize", "Minimize"), ("menu", "Window menu"), ("lower", "Lower"), ("none", "Nothing")])

_add("dock", "dock-position", "Dock edge", "Choose the edge for your favorite applications", "choice", "dock", choices=[("BOTTOM", "Bottom"), ("LEFT", "Left"), ("RIGHT", "Right"), ("TOP", "Top")])
_add("dock", "dock-size", "Icon size", "Make room or make a statement", "int", "dock", "dash-max-icon-size", bounds=(16, 128, 1), unit="px")
for name, key, title, description in (("dock-extended", "extend-height", "Extend to screen edge", "Choose a floating dock or an edge panel"), ("dock-autohide", "autohide", "Auto-hide", "Reveal the dock at the screen edge"), ("dock-intellihide", "intellihide", "Dodge windows", "Move the dock out of the way of overlapping windows"), ("dock-trash", "show-trash", "Show trash", "Keep trash accessible from the dock"), ("dock-mounts", "show-mounts", "Show mounted drives", "Keep mounted media visible")):
    _add("dock", name, title, description, "bool", "dock", key)

for name, key, title in (("interface-font", "font-name", "Interface font"), ("document-font", "document-font-name", "Document font"), ("monospace-font", "monospace-font-name", "Monospace font")):
    _add("typography", name, title, "Choose an installed family, style and size; individual apps can override it", "font", "interface", key)
_add("typography", "titlebar-system-font", "Use interface font in titles", "Some applications draw their own titlebars", "bool", "wm", "titlebar-uses-system-font")
_add("typography", "titlebar-font", "Window title font", "Used by window-manager titles when the interface-font option is off", "font", "wm")
_add("typography", "text-scale", "Text scale", "Scale desktop text without changing display resolution", "float", "interface", "text-scaling-factor", bounds=(0.5, 3.0, 0.05))
_add("typography", "font-antialiasing", "Font smoothing", "Choose grayscale, subpixel or unsmoothed text", "choice", "interface", choices=[("none", "None"), ("grayscale", "Grayscale"), ("rgba", "Subpixel")])
_add("typography", "font-hinting", "Font hinting", "Balance glyph shape and pixel alignment", "choice", "interface", choices=["none", "slight", "medium", "full"])
_add("typography", "font-rgba-order", "Subpixel order", "Match your panel when subpixel smoothing is enabled", "choice", "interface", choices=[("rgb", "RGB"), ("bgr", "BGR"), ("vrgb", "Vertical RGB"), ("vbgr", "Vertical BGR")])

_add("workspaces", "dynamic-workspaces", "Dynamic workspaces", "Create another workspace when the last one is used", "bool", "mutter")
_add("workspaces", "workspace-count", "Workspace count", "Used when dynamic workspaces are disabled", "int", "wm", "num-workspaces", bounds=(1, 36, 1))
_add("workspaces", "workspace-names", "Workspace names", "Name workspaces in order, separated by semicolons", "strv", "wm")
_add("workspaces", "workspaces-primary-only", "Workspaces on primary display", "Other displays keep the same workspace when enabled", "bool", "mutter", "workspaces-only-on-primary")
_add("workspaces", "clock-format", "Clock format", "12-hour or 24-hour desktop clock", "choice", "interface", choices=[("24h", "24-hour"), ("12h", "12-hour")])
for name, key, title in (("clock-date", "clock-show-date", "Show date"), ("clock-weekday", "clock-show-weekday", "Show weekday"), ("clock-seconds", "clock-show-seconds", "Show seconds"), ("battery-percentage", "show-battery-percentage", "Battery percentage")):
    _add("workspaces", name, title, "Customize the desktop status area", "bool", "interface", key)

_add("privacy", "notification-banners", "Notification banners", "Allow applications to display pop-up notifications", "bool", "notifications", "show-banners")
_add("privacy", "lockscreen-notifications", "Lock-screen notifications", "Allow notifications to appear while the screen is locked", "bool", "notifications", "show-in-lock-screen")
_add("privacy", "remember-recent-files", "Recent file history", "Let compatible applications remember recently opened files", "bool", "privacy")
_add("privacy", "remember-app-usage", "Application usage history", "Let the desktop remember which applications you use", "bool", "privacy")
_add("privacy", "screen-lock", "Automatic screen lock", "Lock the session after the display becomes idle", "bool", "lock", "lock-enabled")
_add("privacy", "idle-delay", "Idle screen delay", "Seconds before the desktop becomes idle; zero disables the idle timer", "int", "session", bounds=(0, 86400, 60), unit="s")
_add("privacy", "lock-delay", "Lock delay", "Seconds between screen blanking and locking", "int", "lock", bounds=(0, 86400, 15), unit="s")

_add("input", "cursor-theme", "Pointer theme", "Choose from locally installed cursor themes", "choice", "interface", choices=[])
_add("input", "cursor-size", "Pointer size", "Pointer diameter; the cursor theme must provide the requested size", "int", "interface", bounds=(16, 96, 1), unit="px")
_add("input", "locate-pointer", "Locate pointer", "Press Control to highlight the pointer", "bool", "interface")
_add("input", "cursor-blink", "Blink text cursor", "Animate insertion cursors in compatible applications", "bool", "interface")
_add("input", "cursor-blink-time", "Text cursor blink period", "Time for a complete blink cycle", "int", "interface", bounds=(100, 2500, 100), unit="ms")
_add("input", "overlay-scrolling", "Overlay scrollbars", "Let compatible applications use compact overlay scrollbars", "bool", "interface")
_add("input", "primary-paste", "Middle-click paste", "Allow primary-selection paste in GTK applications", "bool", "interface", "gtk-enable-primary-paste")
_add("input", "keyboard-repeat", "Key repeat", "Repeat a character while its key is held", "bool", "keyboard", "repeat")
_add("input", "keyboard-delay", "Key repeat delay", "Wait before repeating a held key", "int", "keyboard", "delay", bounds=(100, 2000, 25), unit="ms")
_add("input", "keyboard-interval", "Key repeat interval", "Time between repeated characters", "int", "keyboard", "repeat-interval", bounds=(10, 500, 5), unit="ms")
_add("input", "mouse-speed", "Mouse speed", "Slower or faster pointer motion for supported mice", "float", "mouse", "speed", bounds=(-1.0, 1.0, 0.05))
_add("input", "mouse-natural-scroll", "Mouse natural scrolling", "Make mouse scrolling follow content movement", "bool", "mouse", "natural-scroll")
_add("input", "mouse-left-handed", "Left-handed mouse", "Swap the primary and secondary mouse buttons", "bool", "mouse", "left-handed")
_add("input", "mouse-acceleration", "Mouse acceleration", "Choose adaptive acceleration or a flat pointer response", "choice", "mouse", "accel-profile", choices=["default", "flat", "adaptive"])
_add("input", "mouse-double-click", "Double-click interval", "Maximum interval between the two clicks", "int", "mouse", "double-click", bounds=(100, 1500, 25), unit="ms")
_add("input", "touchpad-speed", "Touchpad speed", "Pointer motion for a compatible touchpad", "float", "touchpad", "speed", bounds=(-1.0, 1.0, 0.05))
for name, key, title, description in (("touchpad-tap", "tap-to-click", "Tap to click", "A light touch acts as a click"), ("touchpad-natural-scroll", "natural-scroll", "Touchpad natural scrolling", "Make touchpad scrolling follow content movement"), ("touchpad-disable-typing", "disable-while-typing", "Disable touchpad while typing", "Reduce accidental pointer movement"), ("touchpad-tap-drag", "tap-and-drag", "Tap and drag", "Drag after tapping the touchpad"), ("touchpad-drag-lock", "tap-and-drag-lock", "Tap-drag lock", "Continue a tap drag briefly after lifting a finger"), ("touchpad-two-finger-scroll", "two-finger-scrolling-enabled", "Two-finger scrolling", "Scroll with two fingers on a supported touchpad"), ("touchpad-edge-scroll", "edge-scrolling-enabled", "Edge scrolling", "Scroll at the edge of a supported touchpad")):
    _add("input", name, title, description, "bool", "touchpad", key)
_add("input", "touchpad-click-method", "Touchpad click method", "Use click areas or finger count on supported hardware", "choice", "touchpad", "click-method", choices=[("default", "Device default"), ("none", "None"), ("areas", "Areas"), ("fingers", "Fingers")])
_add("input", "touchpad-handedness", "Touchpad handedness", "Follow the mouse or choose a separate handedness", "choice", "touchpad", "left-handed", choices=[("mouse", "Follow mouse"), ("right", "Right"), ("left", "Left")])
_add("input", "touchpad-send-events", "Touchpad availability", "Disable the touchpad globally or only when a mouse is connected", "choice", "touchpad", "send-events", choices=[("enabled", "Enabled"), ("disabled", "Disabled"), ("disabled-on-external-mouse", "Disable with external mouse")])

_add("display", "night-light", "Night Light", "Warm supported displays in a running GNOME session", "bool", "color", "night-light-enabled")
_add("display", "night-light-temperature", "Night Light temperature", "Lower values look warmer; this is a Livara UI range", "int", "color", bounds=(1000, 10000, 100), unit="K")
_add("display", "night-light-automatic", "Sunset to sunrise", "Use GNOME's automatic schedule when location information is available", "bool", "color", "night-light-schedule-automatic")
_add("display", "night-light-from", "Evening start hour", "Manual schedule: hours after midnight, such as 20.5 for 20:30", "float", "color", "night-light-schedule-from", bounds=(0.0, 24.0, 0.25), unit="h")
_add("display", "night-light-to", "Morning end hour", "Manual schedule: hours after midnight, such as 6.5 for 06:30", "float", "color", "night-light-schedule-to", bounds=(0.0, 24.0, 0.25), unit="h")

BY_NAME = {item["name"]: item for item in CATALOG}
assert len(BY_NAME) == len(CATALOG)


def _unsafe_text(value):
    # Persian joining controls are legitimate text, unlike control characters
    # and direction overrides that can disguise names or paths.
    return any(unicodedata.category(c).startswith("C") and c not in "\u200c\u200d" for c in value)


def validate_value(name, value):
    """Validate preset/UI values without importing GI or executing commands."""
    if name not in BY_NAME:
        raise ValueError(f"Unknown desktop preference: {name}")
    spec = BY_NAME[name]
    kind = spec["kind"]
    if kind == "bool":
        valid = type(value) is bool
    elif kind in ("int", "float"):
        valid = (type(value) is int if kind == "int" else type(value) in (int, float))
        valid = valid and spec["range"][0] <= value <= spec["range"][1] and (kind == "int" or math.isfinite(value))
    elif kind == "strv":
        if isinstance(value, str):
            value = [part.strip() for part in value.split(";") if part.strip()]
        valid = isinstance(value, list) and len(value) <= 36 and all(isinstance(item, str) and len(item) <= 80 and not _unsafe_text(item) for item in value)
    else:
        valid = isinstance(value, str) and len(value) <= (4096 if kind == "image" else 256) and not _unsafe_text(value)
        if kind == "color":
            valid = valid and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value))
            if valid:
                value = value.lower()
        elif kind == "choice":
            if name == "cursor-theme":
                valid = valid and bool(value) and value not in (".", "..") and "/" not in value and "\\" not in value
            else:
                valid = valid and value in [row[0] for row in spec["choices"]]
        elif kind == "font":
            valid = valid and bool(value.strip())
        elif kind == "image":
            valid = valid and (not value or value.startswith(("/", "file:///")))
    if not valid:
        raise ValueError(f"Invalid value for {spec['title']}")
    return copy.deepcopy(value)


def validate_values(values):
    if not isinstance(values, dict) or len(values) > len(BY_NAME):
        raise ValueError("A preset must contain a bounded object of desktop preferences")
    return {name: validate_value(name, value) for name, value in values.items()}


def _name(value):
    if not isinstance(value, str):
        raise ValueError("Enter a preset name")
    value = unicodedata.normalize("NFC", value.strip())
    if not 1 <= len(value) <= 64 or value in (".", "..") or any(c in "/\\" for c in value) or _unsafe_text(value):
        raise ValueError("Use a preset name of 1–64 characters, without slashes or control characters")
    return value


class PresetStore:
    """A user-private, atomic, locked JSON store containing inert values only."""
    MAX_SIZE = 2 * 1024 * 1024
    MAX_PRESETS = 64

    def __init__(self, config_home=None):
        base = Path(config_home) if config_home is not None else Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        if not base.is_absolute():
            base = Path.home() / ".config"
        self.directory = base / "livara"
        self.path = self.directory / "appearance-presets.json"

    @contextmanager
    def _lock(self):
        import fcntl
        if self.directory.is_symlink():
            raise ValueError("The Livara preferences folder must not be a symbolic link")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.directory.is_dir() or self.directory.stat().st_uid != os.getuid():
            raise ValueError("The Livara preferences folder must belong to this user")
        self.directory.chmod(0o700)
        try:
            descriptor = os.open(self.directory / ".appearance-presets.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as error:
            raise ValueError("The preset lock could not be opened safely") from error
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode) or os.fstat(descriptor).st_uid != os.getuid():
                raise ValueError("The preset lock must be a regular file owned by this user")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {"schema": 1, "presets": {}}
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > self.MAX_SIZE:
                    raise ValueError("The preset file must be a bounded regular file owned by this user")
                def duplicate_safe(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("The preset file contains duplicate keys")
                        result[key] = value
                    return result
                document = json.load(stream, object_pairs_hook=duplicate_safe,
                                     parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("Invalid numeric preset value")))
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("The existing preset file could not be read safely; it was preserved") from error
        if not isinstance(document, dict) or document.get("schema") != 1 or set(document) != {"schema", "presets"}:
            raise ValueError("Unsupported preset-file format; the file was preserved")
        rows = document["presets"]
        if not isinstance(rows, dict) or len(rows) > self.MAX_PRESETS:
            raise ValueError("The preset file contains too many presets")
        for name, row in rows.items():
            if _name(name) != name or not isinstance(row, dict) or set(row) != {"values", "created_at", "updated_at"}:
                raise ValueError("The preset file contains invalid metadata")
            if not all(isinstance(row[key], str) and len(row[key]) <= 40 for key in ("created_at", "updated_at")):
                raise ValueError("The preset file contains invalid timestamps")
            row["values"] = validate_values(row["values"])
        return document

    def _write(self, document):
        data = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if len(data.encode("utf-8")) > self.MAX_SIZE:
            raise ValueError("The preset file is too large")
        descriptor, temporary = tempfile.mkstemp(prefix=".appearance-presets-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def list(self):
        with self._lock():
            return {name: copy.deepcopy(row["values"]) for name, row in self._read()["presets"].items()}

    def save(self, name, values):
        name, values = _name(name), validate_values(values)
        with self._lock():
            document = self._read()
            rows = document["presets"]
            if name not in rows and len(rows) >= self.MAX_PRESETS:
                raise ValueError("Delete a preset before saving more than 64")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            rows[name] = {"values": values, "created_at": rows.get(name, {}).get("created_at", now), "updated_at": now}
            self._write(document)

    def delete(self, name):
        name = _name(name)
        with self._lock():
            document = self._read()
            if name not in document["presets"]:
                raise ValueError("This preset no longer exists")
            del document["presets"][name]
            self._write(document)

    def rename(self, old, new):
        old, new = _name(old), _name(new)
        with self._lock():
            document = self._read()
            rows = document["presets"]
            if old not in rows or (new in rows and new != old):
                raise ValueError("Choose an existing preset and a new, unused name")
            if old != new:
                rows[new] = rows.pop(old)
                rows[new]["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self._write(document)

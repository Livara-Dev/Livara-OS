"""Desktop preferences, applied through the user's GNOME settings only."""

from __future__ import annotations

from pathlib import Path
import copy
import os
import re
import time
from urllib.parse import unquote, urlsplit

from . import preferences

ACCENTS = {
    "blue": ("Ocean", "#82bfff"),
    "purple": ("Iris", "#c5a3ff"),
    "sage": ("Sage", "#9ce6cb"),
    "bark": ("Cocoa", "#d6b79f"),
    "orange": ("Sunset", "#ffbe8b"),
    "red": ("Ruby", "#ff9797"),
    "olive": ("Olive", "#d7df8b"),
    "magenta": ("Orchid", "#efa7ff"),
}
WALLPAPERS = {"halo": "Halo", "glass": "Prism", "aurora": "Aurora", "dusk": "Dusk", "verdant": "Verdant"}
PRESETS = {
    "Halo": {"accent": "purple", "appearance": "dark", "wallpaper": "halo", "glass-enabled": True, "dock-position": "BOTTOM", "dock-size": 52, "dock-extended": False},
    "Prism": {"accent": "purple", "appearance": "dark", "wallpaper": "glass", "glass-enabled": True, "dock-position": "BOTTOM", "dock-size": 48, "dock-extended": False},
    "Aurora": {"accent": "sage", "appearance": "dark", "wallpaper": "aurora", "glass-enabled": True, "dock-position": "BOTTOM", "dock-size": 44, "dock-extended": False},
    "Sunrise": {"accent": "orange", "appearance": "light", "wallpaper": "dusk", "glass-enabled": True, "dock-position": "BOTTOM", "dock-size": 48, "dock-extended": False},
    "Classic Desktop": {"accent": "orange", "appearance": "dark", "wallpaper": "verdant", "glass-enabled": False, "dock-position": "LEFT", "dock-size": 42, "dock-extended": True},
}
TERMINAL_PROFILE = "7d5f8bb6-2368-46a6-9f3f-99b2f7fcab4a"
TERMINAL_PALETTE = [
    "#151323", "#f28fad", "#a6e3b7", "#f5d49a", "#92bfff", "#c6a0ff", "#91dfec", "#d5deef",
    "#6e738d", "#ffadc2", "#c1f2cb", "#ffe2af", "#b4d4ff", "#dfc4ff", "#b7f0f7", "#ffffff",
]
FAVORITES = ["org.livara.Center.desktop", "org.gnome.Nautilus.desktop", "org.livara.Browser.desktop",
             "org.livara.Terminal.desktop", "org.livara.Monitor.desktop", "org.livara.Settings.desktop",
             "org.livara.Studio.desktop", "org.livara.Code.desktop", "org.livara.Chat.desktop"]
WINDOW_DEFAULTS = {
    "window-button-style": "traffic-lights",
    "window-button-size": 14,
    "window-button-symbols": False,
    "window-green-action": "fullscreen",
    "window-close-color": "#ff5f57",
    "window-minimize-color": "#febc2e",
    "window-maximize-color": "#28c840",
    "window-animation-style": "zoom",
    "window-animation-duration": 220,
}
WINDOW_COLOR_KEYS = ("window-close-color", "window-minimize-color", "window-maximize-color")
WINDOW_STYLE_KEYS = ("window-button-style", "window-button-size", "window-button-symbols", "window-green-action", *WINDOW_COLOR_KEYS)


# Public names map to real installed schemas and keys. Unknown schemas are not created.
OPTIONS = {row["name"]: (row["schema"], row["key"]) for row in preferences.CATALOG}
APPEARANCE_PRESET_KEYS = tuple(row["name"] for row in preferences.CATALOG
    if row["section"] in ("appearance", "dock", "typography", "workspaces") or
    row["name"] in (*WINDOW_DEFAULTS, "window-buttons", "center-new-windows", "attach-modal-dialogs", "cursor-theme", "cursor-size"))


def settings_for(schema: str):
    try:
        from gi.repository import Gio
    except ImportError:
        return None
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(schema, True) is None:
        return None
    return Gio.Settings.new(schema)


def read_option(name: str):
    schema, key = OPTIONS[name]
    settings = settings_for(schema)
    if settings is None or not settings.props.settings_schema.has_key(key):
        return None
    value = settings.get_value(key).unpack()
    return _local_wallpaper_path(value) if name == "wallpaper-image" else value


def prepare_setting(schema: str, key: str, value):
    """Check native type, schema range and policy before a settings write."""
    from gi.repository import GLib
    settings = settings_for(schema)
    if settings is None or not settings.props.settings_schema.has_key(key):
        raise ValueError("This desktop setting is unavailable in the current session")
    if not settings.is_writable(key):
        raise ValueError("This desktop setting is managed and cannot be changed")
    try:
        variant = GLib.Variant(settings.get_value(key).get_type_string(), value)
    except (TypeError, OverflowError, ValueError) as error:
        raise ValueError(f"Invalid value for {key}") from error
    if not settings.range_check(key, variant):
        raise ValueError(f"The desktop does not support this value for {key}")
    return settings, variant


def write_setting(schema: str, key: str, value) -> None:
    settings, variant = prepare_setting(schema, key, value)
    if not settings.set_value(key, variant):
        raise ValueError(f"The desktop could not apply {key}")


def set_option(name: str, value) -> None:
    value = preferences.validate_value(name, value)
    schema, key = OPTIONS[name]
    if name == "wallpaper-image":
        set_wallpaper_image(value)
        return
    if name == "cursor-theme" and value not in cursor_themes():
        raise ValueError("Choose a locally installed pointer theme")
    targets = _option_targets({name})
    snapshots = _setting_snapshots(targets)
    try:
        dock_fixed = _prepare_dock_mode({name: value}) if name in ("dock-autohide", "dock-intellihide") else None
        write_setting(schema, key, value)
        if dock_fixed is not None:
            write_setting("org.gnome.shell.extensions.dash-to-dock", "dock-fixed", dock_fixed)
        if name in WINDOW_STYLE_KEYS or name == "window-buttons":
            apply_window_style()
        if name in ("accent", "appearance", "wallpaper"):
            apply_palette(update_wallpaper=name == "wallpaper")
    except Exception as error:
        failures = _rollback(snapshots)
        if name in WINDOW_STYLE_KEYS or name == "window-buttons":
            try:
                apply_window_style()
            except Exception:
                failures.append("GTK window styles")
        if failures:
            raise ValueError("The change failed and these settings could not be restored: " + ", ".join(failures)) from error
        raise ValueError("The change could not be applied; previous preferences were restored. " + str(error)) from error


def _option_targets(names):
    """Include derived desktop keys when preserving a preference operation."""
    targets = {OPTIONS[name] for name in names}
    if set(names).intersection(("dock-autohide", "dock-intellihide")):
        targets.add(("org.gnome.shell.extensions.dash-to-dock", "dock-fixed"))
    if set(names).intersection(("accent", "appearance")):
        targets.update(("org.gnome.desktop.interface", key) for key in ("color-scheme", "gtk-theme", "icon-theme"))
    if set(names).intersection(("wallpaper", "wallpaper-image")):
        targets.update((("org.gnome.desktop.background", "picture-uri"),
                        ("org.gnome.desktop.background", "picture-uri-dark"),
                        ("org.gnome.desktop.screensaver", "picture-uri")))
    return targets


def _setting_snapshots(targets):
    snapshots = []
    for schema, key in sorted(targets):
        settings = settings_for(schema)
        if settings is not None and settings.props.settings_schema.has_key(key):
            snapshots.append((settings, key, settings.get_user_value(key)))
    return snapshots


def apply_rendering_mode(full: bool) -> dict:
    """Apply an explicit rendering choice together, including its motion choice."""
    if type(full) is not bool:
        raise ValueError("Choose Full Glass or Efficient rendering")
    values = {"glass-enabled": full, "blur-radius": 24 if full else 0, "animations": full}
    for name, value in values.items():
        prepare_setting(*OPTIONS[name], value)
    return _apply_options(values, preserve_reduced_motion=False)


def validate_window_value(name: str, value):
    """Validate before persisting values used in CSS and window animations."""
    if name in WINDOW_COLOR_KEYS:
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Enter a six-digit color such as #ff5f57")
        return value.lower()
    if name == "window-button-style" and value not in ("traffic-lights", "default"):
        raise ValueError("Choose Livara traffic lights or native window buttons")
    if name == "window-green-action" and value not in ("fullscreen", "maximize"):
        raise ValueError("Choose full screen or maximize for the green button")
    if name == "window-animation-style" and value not in ("zoom", "lift", "fade", "off"):
        raise ValueError("Unknown window animation style")
    if name == "window-button-size" and (type(value) is not int or not 10 <= value <= 22):
        raise ValueError("Window button size must be 10–22 pixels")
    if name == "window-animation-duration" and (type(value) is not int or not 80 <= value <= 600):
        raise ValueError("Window animation duration must be 80–600 milliseconds")
    if name == "window-button-symbols" and type(value) is not bool:
        raise ValueError("Window button symbols must be on or off")
    return value


def window_style_values() -> dict:
    """Return a complete, validated style even with an older/missing schema."""
    values = {}
    for key in WINDOW_STYLE_KEYS:
        current = read_option(key)
        try:
            values[key] = validate_window_value(key, current) if current is not None else WINDOW_DEFAULTS[key]
        except (ValueError, TypeError):
            values[key] = WINDOW_DEFAULTS[key]
    values["window-buttons"] = read_option("window-buttons") or "close,minimize,maximize:"
    return values


def apply_window_style(*, config_home=None):
    """Update only Livara's managed per-user GTK window-control styles."""
    from . import window_style
    return window_style.apply_user_style(window_style_values(), config_home=config_home)


def reset_window_preferences() -> None:
    """Restore Livara window controls without changing desktop motion or glass."""
    for name, value in WINDOW_DEFAULTS.items():
        schema, key = OPTIONS[name]
        write_setting(schema, key, value)
    write_setting(*OPTIONS["window-buttons"], "close,minimize,maximize:")
    apply_window_style()


def _local_wallpaper_path(value) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        uri = urlsplit(value)
        if uri.scheme == "file" and uri.netloc in ("", "localhost") and not uri.query and not uri.fragment:
            path = Path(unquote(uri.path, errors="strict"))
            return str(path) if path.is_absolute() else ""
        return value if not uri.scheme and Path(value).is_absolute() else ""
    except (ValueError, UnicodeError):
        return ""


def validate_wallpaper_image(value: str) -> Path:
    """Accept local raster images only; never download an image or interpret XML."""
    path_string = _local_wallpaper_path(value)
    if not path_string or "\0" in path_string:
        raise ValueError("Choose a local PNG, JPEG or WebP image")
    path = Path(path_string)
    if not path.is_file():
        raise ValueError("The selected wallpaper is missing or is not a regular image file")
    if not 0 < path.stat().st_size <= 64 * 1024 * 1024:
        raise ValueError("Choose a wallpaper smaller than 64 MiB")
    with path.open("rb") as stream:
        head = stream.read(32)
    if not (head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff") or
            (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
        raise ValueError("The selected file is not a PNG, JPEG or WebP image")
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        info = GdkPixbuf.Pixbuf.get_file_info(str(path))
        if not info or info[0] is None or not (1 <= info[1] <= 32768 and 1 <= info[2] <= 32768) or info[1] * info[2] > 100_000_000:
            raise ValueError("Choose a readable wallpaper up to 100 megapixels and 32768 pixels per side")
    except ImportError:
        # The desktop runtime depends on GdkPixbuf. Stdlib-only source checks
        # still enforce local files, size and raster signatures.
        pass
    return path.resolve()


def _builtin_wallpaper_path() -> Path:
    wallpaper = read_option("wallpaper") or "glass"
    if wallpaper not in WALLPAPERS:
        raise ValueError("Unknown Livara wallpaper")
    path = Path("/usr/share/backgrounds/livara") / f"livara-{wallpaper}.png"
    source = Path(__file__).resolve().parents[2] / "artwork" / path.name
    return path if path.is_file() else source


def _write_wallpaper(path: Path) -> None:
    uri = path.as_uri()
    # Check all available targets before changing any of them.
    targets = [("org.gnome.desktop.background", "picture-uri"),
               ("org.gnome.desktop.background", "picture-uri-dark"),
               ("org.gnome.desktop.screensaver", "picture-uri")]
    available = []
    for schema, key in targets:
        settings = settings_for(schema)
        if settings is not None and settings.props.settings_schema.has_key(key):
            prepare_setting(schema, key, uri)
            available.append((schema, key))
    if not available or targets[0] not in available:
        raise ValueError("The desktop wallpaper service is unavailable")
    snapshots = _setting_snapshots(available)
    try:
        for schema, key in available:
            write_setting(schema, key, uri)
    except Exception as error:
        failures = _rollback(snapshots)
        if failures:
            raise ValueError("The wallpaper failed and these settings could not be restored: " + ", ".join(failures)) from error
        raise ValueError("The wallpaper could not be applied; previous backgrounds were restored. " + str(error)) from error


def set_wallpaper_image(value: str) -> None:
    path = validate_wallpaper_image(value) if value else validate_wallpaper_image(str(_builtin_wallpaper_path()))
    _write_wallpaper(path)


def get_custom_wallpaper() -> str:
    path = read_option("wallpaper-image") or ""
    if path and Path(path).name in {f"livara-{name}.png" for name in WALLPAPERS}:
        candidate = Path(path)
        if candidate.parent in (Path("/usr/share/backgrounds/livara"), Path(__file__).resolve().parents[2] / "artwork"):
            return ""
    return path


def apply_palette(*, update_wallpaper: bool = False) -> None:
    accent = read_option("accent") or "blue"
    appearance = read_option("appearance") or "dark"
    wallpaper = read_option("wallpaper") or "glass"
    if accent not in ACCENTS or wallpaper not in WALLPAPERS or appearance not in ("light", "dark"):
        raise ValueError("Unknown desktop palette")
    theme = f"Yaru-{accent}" if accent != "orange" else "Yaru"
    write_setting("org.gnome.desktop.interface", "color-scheme", "prefer-dark" if appearance == "dark" else "default")
    write_setting("org.gnome.desktop.interface", "gtk-theme", theme + ("-dark" if appearance == "dark" else ""))
    write_setting("org.gnome.desktop.interface", "icon-theme", theme)
    if update_wallpaper:
        set_wallpaper_image("")


def cursor_themes() -> list[str]:
    paths = [Path.home() / ".icons", Path.home() / ".local/share/icons",
             Path("/usr/local/share/icons"), Path("/usr/share/icons")]
    names = set()
    for root in paths:
        try:
            names.update(path.name for path in root.iterdir() if path.is_dir() and (path / "cursors").is_dir())
        except OSError:
            continue
    current = read_option("cursor-theme")
    if isinstance(current, str) and current and "/" not in current and "\\" not in current:
        names.add(current)
    return sorted(names, key=str.casefold)


def installed_fonts() -> list[str]:
    try:
        import gi
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import PangoCairo
        return sorted({family.get_name() for family in PangoCairo.FontMap.get_default().list_families()}, key=str.casefold)
    except (ImportError, ValueError):
        return []


def preference_metadata() -> list[dict]:
    """Canonical searchable UI catalog; availability is determined at runtime."""
    catalog = copy.deepcopy(preferences.CATALOG)
    for row in catalog:
        settings = settings_for(row["schema"])
        row["available"] = settings is not None and settings.props.settings_schema.has_key(row["key"])
        row["writable"] = bool(row["available"] and settings.is_writable(row["key"]))
        if row["name"] == "cursor-theme":
            row["choices"] = [(name, name) for name in cursor_themes()]
    return catalog


_extension_status_cache = {}


def shell_extension_note(uuid: str) -> str:
    """Observe the Shell's runtime state, rather than equating a schema with a service."""
    cached = _extension_status_cache.get(uuid)
    now = time.monotonic()
    if cached and now - cached[0] < 5:
        return cached[1]
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync("org.gnome.Shell", "/org/gnome/Shell",
            "org.gnome.Shell.Extensions", "GetExtensionInfo", GLib.Variant("(s)", (uuid,)),
            GLib.VariantType.new("(a{sv})"), Gio.DBusCallFlags.NO_AUTO_START, 1000, None)
        info = reply.unpack()[0]
        state = info.get("state")
        if state == 1:
            note = ""
        elif state == 3:
            note = "The desktop extension failed to load. Open Extensions for its error, then log out and back in after updating."
        elif state == 4:
            note = "The desktop extension is incompatible with this GNOME version."
        elif not info:
            note = "The required desktop extension is not installed. Install the Livara desktop update, then log out and back in."
        else:
            note = "Enable the desktop extension in Extensions to use this control."
    except Exception:
        # GNOME's interface is absent outside the graphical session. Saving a
        # preference remains allowed; do not claim that its renderer is running.
        note = "This control takes effect in a GNOME session with its desktop extension running."
    _extension_status_cache[uuid] = (now, note)
    return note


def inactive_reason(name: str) -> str:
    """Explain controls whose native desktop consumer currently ignores them."""
    dependencies = {
        "workspace-count": ("dynamic-workspaces", False, "Turn off Dynamic workspaces to choose a fixed count."),
        "titlebar-font": ("titlebar-system-font", False, "Turn off Use interface font in titles to choose a separate title font."),
        "font-rgba-order": ("font-antialiasing", "rgba", "Choose Subpixel font smoothing to use this order."),
        "auto-raise-delay": ("auto-raise", True, "Enable Raise on pointer focus to use this delay."),
        "cursor-blink-time": ("cursor-blink", True, "Enable Blink text cursor to use this period."),
        "keyboard-delay": ("keyboard-repeat", True, "Enable Key repeat to use this delay."),
        "keyboard-interval": ("keyboard-repeat", True, "Enable Key repeat to use this interval."),
        "lock-delay": ("screen-lock", True, "Enable Automatic screen lock to use this delay."),
        "window-animation-style": ("animations", True, "Enable Desktop animations to use window transitions."),
        "window-animation-duration": ("animations", True, "Enable Desktop animations to use window transitions."),
        "night-light-temperature": ("night-light", True, "Enable Night Light to use this temperature."),
        "night-light-automatic": ("night-light", True, "Enable Night Light to configure its schedule."),
        "night-light-from": ("night-light-automatic", False, "Turn off Sunset to sunrise to set a manual start time."),
        "night-light-to": ("night-light-automatic", False, "Turn off Sunset to sunrise to set a manual end time."),
    }
    dependency = dependencies.get(name)
    if dependency:
        option, expected, explanation = dependency
        actual = read_option(option)
        if actual is not None and actual != expected:
            return explanation
    if name in ("night-light-from", "night-light-to") and read_option("night-light") is False:
        return "Enable Night Light to configure its schedule."
    if name == "window-animation-duration" and read_option("window-animation-style") == "off":
        return "Choose a window transition to use this duration."
    return ""


def _prepare_dock_mode(values: dict):
    """A visible dock needs fixed mode when neither hiding behavior is active."""
    schema = "org.gnome.shell.extensions.dash-to-dock"
    settings = settings_for(schema)
    if settings is None or not settings.props.settings_schema.has_key("dock-fixed"):
        return None
    auto = values["dock-autohide"] if "dock-autohide" in values else read_option("dock-autohide")
    dodge = values["dock-intellihide"] if "dock-intellihide" in values else read_option("dock-intellihide")
    if auto is None or dodge is None:
        return None
    fixed = not (auto or dodge)
    prepare_setting(schema, "dock-fixed", fixed)
    return fixed


def _rollback(snapshots):
    failures = []
    for settings, key, value in reversed(snapshots):
        try:
            if value is None:
                settings.reset(key)
            elif not settings.set_value(key, value):
                failures.append(key)
        except Exception:
            failures.append(key)
    return failures


def _apply_options(values: dict, *, reset: bool = False, preserve_reduced_motion: bool = True) -> dict:
    """Preflight a bounded group and roll back user overrides on write failure."""
    values = preferences.validate_values(values)
    available, skipped, snapshots = {}, [], []
    for name, value in values.items():
        schema, key = OPTIONS[name]
        settings = settings_for(schema)
        if settings is None or not settings.props.settings_schema.has_key(key):
            skipped.append(name)
            continue
        if preserve_reduced_motion and not reset and name == "animations" and value and not read_option("animations"):
            skipped.append(name)  # Aesthetic presets never turn reduced motion off.
            continue
        if name == "wallpaper-image":
            if value:
                value = str(validate_wallpaper_image(value))
            native_value = Path(value).as_uri() if value else _builtin_wallpaper_path().as_uri()
        else:
            native_value = value
        if name == "cursor-theme" and value not in cursor_themes():
            raise ValueError("This preset's pointer theme is not installed")
        prepare_setting(schema, key, native_value)
        available[name] = value
    dock_fixed = _prepare_dock_mode(available) if set(available).intersection(("dock-autohide", "dock-intellihide")) else None
    target_keys = {OPTIONS[name] for name in available}
    if dock_fixed is not None:
        target_keys.add(("org.gnome.shell.extensions.dash-to-dock", "dock-fixed"))
    if set(available).intersection(("accent", "appearance")):
        target_keys.update(("org.gnome.desktop.interface", key) for key in ("color-scheme", "gtk-theme", "icon-theme"))
    if set(available).intersection(("wallpaper", "wallpaper-image")):
        target_keys.update((("org.gnome.desktop.background", "picture-uri"), ("org.gnome.desktop.background", "picture-uri-dark"), ("org.gnome.desktop.screensaver", "picture-uri")))
    for schema, key in sorted(target_keys):
        settings = settings_for(schema)
        if settings is not None and settings.props.settings_schema.has_key(key):
            snapshots.append((settings, key, settings.get_user_value(key)))
    try:
        for name, value in available.items():
            if name == "wallpaper-image":
                continue
            schema, key = OPTIONS[name]
            if reset:
                settings_for(schema).reset(key)
            else:
                write_setting(schema, key, value)
        if dock_fixed is not None:
            write_setting("org.gnome.shell.extensions.dash-to-dock", "dock-fixed", dock_fixed)
        if set(available).intersection(("accent", "appearance", "wallpaper")):
            apply_palette(update_wallpaper="wallpaper" in available)
        if "wallpaper-image" in available:
            set_wallpaper_image("" if reset and "wallpaper" in available else available["wallpaper-image"])
        if set(available).intersection((*WINDOW_STYLE_KEYS, "window-buttons")):
            apply_window_style()
    except Exception as error:
        failures = _rollback(snapshots)
        try:
            if set(available).intersection((*WINDOW_STYLE_KEYS, "window-buttons")):
                apply_window_style()
        except Exception:
            failures.append("GTK window styles")
        if failures:
            raise ValueError("The desktop rejected this change; some preferences could not be restored: " + ", ".join(failures)) from error
        raise ValueError("The desktop rejected this change; previous preferences were restored. " + str(error)) from error
    return {"applied": list(available), "unavailable": skipped}


def reset_options(names) -> dict:
    if not isinstance(names, (list, tuple)) or any(name not in OPTIONS for name in names):
        raise ValueError("Choose known preferences to reset")
    values = {}
    for name in dict.fromkeys(names):
        settings = settings_for(OPTIONS[name][0])
        key = OPTIONS[name][1]
        if settings is not None and settings.props.settings_schema.has_key(key):
            if name == "wallpaper-image":
                values[name] = ""
            else:
                value = settings.get_default_value(key)
                if value is not None:
                    values[name] = value.unpack()
    return _apply_options(values, reset=True)


def list_custom_presets(*, config_home=None) -> dict:
    return preferences.PresetStore(config_home).list()


def save_custom_preset(name: str, values=None, *, config_home=None) -> None:
    if values is None:
        values = {}
        for key in APPEARANCE_PRESET_KEYS:
            value = read_option(key)
            if value is not None:
                try:
                    values[key] = preferences.validate_value(key, value)
                except ValueError:
                    # Other apps can set values outside Livara's UI range.
                    # Leave those preferences untouched rather than overriding them.
                    continue
    preferences.PresetStore(config_home).save(name, values)


def rename_custom_preset(old: str, new: str, *, config_home=None) -> None:
    preferences.PresetStore(config_home).rename(old, new)


def delete_custom_preset(name: str, *, config_home=None) -> None:
    preferences.PresetStore(config_home).delete(name)


def apply_custom_preset(name: str, *, config_home=None) -> dict:
    presets = list_custom_presets(config_home=config_home)
    if name not in presets:
        raise ValueError("This preset no longer exists")
    return _apply_options(presets[name])


def apply_preset(name: str) -> None:
    if name not in PRESETS:
        raise ValueError("Unknown desktop preset")
    _apply_options(PRESETS[name])


def apply_live_defaults() -> None:
    """Apply after Casper has written Ubuntu's live-session preferences."""
    from gi.repository import Gio
    apply_preset("Prism")
    write_setting("org.gnome.shell", "favorite-apps", FAVORITES)
    for name, value in {
        "dock-autohide": False, "dock-intellihide": False, "dock-mounts": False,
        "dock-trash": True, "window-buttons": "close,minimize,maximize:",
    }.items():
        set_option(name, value)
    # Use actual per-user preferences after Casper's distro defaults are applied.
    write_setting("org.gnome.login-screen", "logo", "/usr/share/livara/logo.png")
    if settings_for("org.gnome.Terminal.ProfilesList"):
        configure_terminal(make_default=True)
    Gio.Settings.sync()


def configure_terminal(make_default: bool = False, reset: bool = False) -> str:
    """Initialize Livara's profile once, preserving later user customization."""
    from gi.repository import Gio, GLib
    source = Gio.SettingsSchemaSource.get_default()
    profile_schema = source.lookup("org.gnome.Terminal.Legacy.Profile", True) if source else None
    profiles = settings_for("org.gnome.Terminal.ProfilesList")
    if profile_schema is None or profiles is None:
        raise ValueError("GNOME Terminal is not installed")
    existing = profiles.get_strv("list")
    if TERMINAL_PROFILE in existing and not reset:
        if make_default:
            profiles.set_string("default", TERMINAL_PROFILE)
        Gio.Settings.sync()
        return TERMINAL_PROFILE
    profile = Gio.Settings.new_with_path(
        "org.gnome.Terminal.Legacy.Profile",
        f"/org/gnome/terminal/legacy/profiles:/:{TERMINAL_PROFILE}/",
    )
    # A dedicated profile receives Livara's theme on first launch. Subsequent
    # launches preserve edits, and an explicit reset can restore these defaults.
    values = {
        "visible-name": "Livara Glass", "foreground-color": "#edf2ff",
        "background-color": "#101323", "use-theme-colors": False,
        "bold-color-same-as-fg": False, "bold-color": "#ddc6ff",
        "palette": TERMINAL_PALETTE, "use-system-font": False, "font": "Livara Mono 12",
        "cursor-shape": "ibeam", "cursor-blink-mode": "system", "cursor-colors-set": True,
        "cursor-background-color": "#c6a0ff", "cursor-foreground-color": "#101323",
        "highlight-colors-set": True, "highlight-background-color": "#594477",
        "highlight-foreground-color": "#ffffff", "scrollbar-policy": "never",
        "scrollback-lines": 20000, "scrollback-unlimited": False,
        "scroll-on-output": False, "scroll-on-keystroke": True,
        "use-custom-command": True,
        "custom-command": "/bin/bash --rcfile /usr/share/livara/terminal/livara.bash",
        "login-shell": False, "cell-height-scale": 1.12,
        "default-size-columns": 106, "default-size-rows": 30,
        "use-transparent-background": True, "use-theme-transparency": False,
        "background-transparency-percent": 9,
    }
    for key, value in values.items():
        # Transparency is an Ubuntu VTE extension. Keep the same functional
        # profile on other GNOME Terminal builds that lack those optional keys.
        if not profile_schema.has_key(key):
            continue
        old = profile.get_value(key)
        variant = GLib.Variant(old.get_type_string(), value)
        if not profile.range_check(key, variant) or not profile.set_value(key, variant):
            raise ValueError(f"Unable to apply terminal preference: {key}")
    if TERMINAL_PROFILE not in existing:
        profiles.set_strv("list", [*existing, TERMINAL_PROFILE])
    if make_default:
        profiles.set_string("default", TERMINAL_PROFILE)
    terminal_settings = settings_for("org.gnome.Terminal.Legacy.Settings")
    if terminal_settings:
        terminal_settings.set_string("theme-variant", "dark")
    Gio.Settings.sync()
    return TERMINAL_PROFILE

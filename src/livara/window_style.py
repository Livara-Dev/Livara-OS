"""User-controlled window decorations, with bounded edits to GTK user CSS.

The standard GTK controls keep their native actions. Livara's own header bars
can opt into native_controls for the configurable green-button action and F11.
This module's CSS/storage helpers do not require PyGObject.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import tempfile
from collections.abc import Mapping

DEFAULTS = {
    "window-button-style": "traffic-lights",
    "window-button-size": 14,
    "window-button-symbols": False,
    "window-close-color": "#ff5f57",
    "window-minimize-color": "#febc2e",
    "window-maximize-color": "#28c840",
    "window-green-action": "fullscreen",
    "window-buttons": "close,minimize,maximize:",
}
COLOR_KEYS = ("window-close-color", "window-minimize-color", "window-maximize-color")
STYLE_KEYS = tuple(key for key in DEFAULTS if key != "window-buttons")
BEGIN = "/* BEGIN LIVARA WINDOW CONTROLS */"
END = "/* END LIVARA WINDOW CONTROLS */"
_live_handle = None


def normalized_values(values: Mapping | None = None) -> dict:
    result = {**DEFAULTS, **{key: value for key, value in (values or {}).items() if key in DEFAULTS}}
    if result["window-button-style"] not in ("traffic-lights", "default"):
        raise ValueError("Choose Livara traffic lights or the default window controls")
    if type(result["window-button-size"]) is not int or not 10 <= result["window-button-size"] <= 22:
        raise ValueError("Window control size must be between 10 and 22 pixels")
    if type(result["window-button-symbols"]) is not bool:
        raise ValueError("The window control symbols preference must be on or off")
    if result["window-green-action"] not in ("fullscreen", "maximize"):
        raise ValueError("Choose fullscreen or maximize for the green control")
    for key in COLOR_KEYS:
        value = result[key]
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Window control colors must use #RRGGBB")
        result[key] = value.lower()
    layout = result["window-buttons"]
    if not isinstance(layout, str) or len(layout) > 256 or not re.fullmatch(r"[a-zA-Z0-9_,:\-]*", layout):
        raise ValueError("Invalid window control layout")
    return result


def read_values() -> dict:
    """Read installed schemas; retain useful defaults outside a GNOME session."""
    values = dict(DEFAULTS)
    try:
        from gi.repository import Gio
        source = Gio.SettingsSchemaSource.get_default()
        if source:
            schema = source.lookup("org.livara.desktop", True)
            if schema:
                settings = Gio.Settings.new("org.livara.desktop")
                for key in STYLE_KEYS:
                    if schema.has_key(key):
                        values[key] = settings.get_value(key).unpack()
            schema = source.lookup("org.gnome.desktop.wm.preferences", True)
            if schema and schema.has_key("button-layout"):
                values["window-buttons"] = Gio.Settings.new("org.gnome.desktop.wm.preferences").get_string("button-layout")
        return normalized_values(values)
    except (ImportError, ValueError, RuntimeError):
        return dict(DEFAULTS)


def _selectors(action: str) -> list[str]:
    return [f"windowcontrols button.{action}", f"headerbar button.titlebutton.{action}",
            f".titlebar button.titlebutton.{action}", f".livara-window-controls button.livara-{action}"]


def css_for_values(values: Mapping | None = None, gtk_version: int = 4) -> str:
    """Render real GTK3/GTK4 CSS; never interpolate unchecked CSS text."""
    if gtk_version not in (3, 4):
        raise ValueError("GTK version must be 3 or 4")
    prefs = normalized_values(values)
    if prefs["window-button-style"] == "default":
        return ""
    size = prefs["window-button-size"]
    selectors = [selector for action in ("close", "minimize", "maximize") for selector in _selectors(action)]
    all_buttons = ",\n".join(selectors)
    images = ",\n".join(selector + " image" for selector in selectors)
    symbols = ",\n".join([images, ".livara-window-controls .livara-control-symbol"])
    visible = []
    for selector in selectors:
        visible.extend([selector + ":hover image", selector + ":focus image"])
    visible.extend([".livara-window-controls:hover .livara-control-symbol",
                    ".livara-window-controls button:focus .livara-control-symbol",
                    ".livara-window-controls.symbols-visible .livara-control-symbol"])
    opacity = "1" if prefs["window-button-symbols"] else "0"
    css = f'''/* Livara traffic lights. Native labels, tooltips and keyboard actions remain. */
{all_buttons} {{
  min-width: {size}px;
  min-height: {size}px;
  padding: 0;
  margin: 3px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.20);
  background-image: linear-gradient(to bottom, rgba(255,255,255,0.25), rgba(255,255,255,0.02) 45%, rgba(0,0,0,0.08));
  box-shadow: inset 0 1px rgba(255,255,255,0.16);
  color: rgba(20, 15, 25, 0.82);
  transition: background-color 100ms ease, box-shadow 100ms ease;
}}
{symbols} {{
  opacity: {opacity};
  color: rgba(20, 15, 25, 0.82);
}}
.livara-window-controls .livara-control-symbol {{
  font-size: {max(6, size - 6)}px;
  font-weight: bold;
  min-width: 0;
  min-height: 0;
  padding: 0;
  margin: 0;
}}
.livara-window-controls button.livara-window-control {{ margin: 0; }}
{', '.join(visible)} {{ opacity: 1; }}
'''
    if gtk_version == 4:
        css += f"{images} {{ -gtk-icon-size: {max(8, size - 4)}px; }}\n"
    else:
        css += f"{images} {{ -gtk-icon-transform: scale({max(8, size - 4) / 16:.3f}); }}\n"
    for action, key in (("close", "window-close-color"), ("minimize", "window-minimize-color"), ("maximize", "window-maximize-color")):
        css += ",\n".join(_selectors(action)) + f" {{ background-color: {prefs[key]}; }}\n"
        css += ",\n".join(selector + ":hover" for selector in _selectors(action)) + " { box-shadow: inset 0 0 0 1px rgba(0,0,0,0.16), 0 0 0 1px rgba(255,255,255,0.12); }\n"
        css += ",\n".join(selector + ":disabled" for selector in _selectors(action)) + " { opacity: 0.45; }\n"
    return css


def _replace_block(original: str, css: str) -> str:
    starts, ends = original.count(BEGIN), original.count(END)
    if (starts, ends) == (0, 0):
        return original + ("\n" + BEGIN + "\n" + css.rstrip() + "\n" + END + "\n" if css else "")
    if (starts, ends) != (1, 1):
        raise ValueError("GTK CSS contains an incomplete or duplicate Livara window-controls block; the file was preserved")
    start, finish = original.index(BEGIN), original.index(END)
    if finish < start:
        raise ValueError("GTK CSS contains reversed Livara window-controls markers; the file was preserved")
    if start and original[start - 1] == "\n":
        start -= 1  # The managed block owns its preceding separator newline.
    finish += len(END)
    if original[finish:finish + 1] == "\n":
        finish += 1
    replacement = "\n" + BEGIN + "\n" + css.rstrip() + "\n" + END + "\n" if css else ""
    return original[:start] + replacement + original[finish:]


def apply_user_style(values: Mapping, config_home: Path | None = None) -> list[Path]:
    """Atomically update only Livara's marked block in GTK3 and GTK4 CSS."""
    prefs = normalized_values(values)
    if config_home is None:
        configured = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        config_home = configured if configured.is_absolute() else Path.home() / ".config"
    plans = []
    for version in (3, 4):
        path = Path(config_home) / f"gtk-{version}.0/gtk.css"
        if path.is_symlink():
            raise ValueError(f"{path} is a symbolic link; its target was preserved")
        original = path.read_text(encoding="utf-8") if path.exists() else ""
        changed = _replace_block(original, css_for_values(prefs, version))
        if changed != original:
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
            plans.append((path, changed, mode))
    # Validate both files before changing either one.
    for path, content, mode in plans:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".livara-window-controls-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return [path for path, _content, _mode in plans]


class _LiveStyle:
    def __init__(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, Gio, Gtk
        self.Gtk, self.display = Gtk, Gdk.Display.get_default()
        self.provider = Gtk.CssProvider()
        self.connections = []
        if self.display:
            # Live native controls must update even while GTK's startup-loaded
            # copy of the managed user stylesheet still contains older values.
            Gtk.StyleContext.add_provider_for_display(self.display, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        source = Gio.SettingsSchemaSource.get_default()
        if source and source.lookup("org.livara.desktop", True):
            self.settings = Gio.Settings.new("org.livara.desktop")
            self.connections.append((self.settings, self.settings.connect("changed", self.changed)))
        if source and source.lookup("org.gnome.desktop.interface", True):
            interface = Gio.Settings.new("org.gnome.desktop.interface")
            self.connections.append((interface, interface.connect("changed::enable-animations", lambda *args: self.refresh())))
            self.connections.append((interface, interface.connect("changed::color-scheme", lambda *args: self.refresh())))
        self.refresh()

    def changed(self, _settings, key):
        if key in STYLE_KEYS or key.startswith("theme-"):
            self.refresh()

    def refresh(self):
        from . import theme, desktop
        generated = theme.css(theme.read_values(), light=desktop.read_option("appearance") == "light", motion=desktop.read_option("animations") is not False)
        self.provider.load_from_data((css_for_values(read_values()) + generated).encode("utf-8"))

    def dispose(self):
        for settings, signal in self.connections:
            settings.disconnect(signal)
        self.connections.clear()
        if self.display:
            self.Gtk.StyleContext.remove_provider_for_display(self.display, self.provider)


def install_live_style():
    """Install one shared live GTK4 provider per native application process."""
    global _live_handle
    if _live_handle is None:
        _live_handle = _LiveStyle()
    return _live_handle


def configure_native_headerbar(window, headerbar):
    from .native_controls import configure_native_headerbar as configure
    return configure(window, headerbar)

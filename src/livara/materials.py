"""Shared native materials, hierarchy and live desktop appearance.

GTK does not expose compositor backdrop refraction. These materials use opaque
content surfaces, layered tint, specular edges and elevation rather than making
text and entire windows transparent. Shell blur remains the compositor's job.
"""
from __future__ import annotations

import re

_live_style = None


def css(*, dark=True, accent="#c5a3ff", glass=True, motion=True):
    """Render GTK 4 CSS from bounded tokens; keep text readable in both modes."""
    if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        raise ValueError("A material accent must be a six-digit color")
    base, surface, ink, muted, edge = (
        ("#111019", "#211f2a", "#f5f2fc", "#bdb8cc", ".13") if dark else
        ("#f3f1f8", "#ffffff", "#242032", "#686174", ".11"))
    shade = "#000000" if dark else "#514361"
    border = "#ffffff" if dark else "#514361"
    duration = "160ms" if motion else "0ms"
    # Use a solid base behind every gradient. There is no text/background alpha
    # multiplication and no reliance on wallpaper contrast for legibility.
    layer = (f"linear-gradient(135deg, alpha(white,.09), alpha(white,.015) 40%, alpha({accent},.05))"
             if glass else "none")
    sheen = (f"inset 0 1px alpha(white,{'.15' if dark else '.9'}), inset 0 -1px alpha({shade},.08), 0 8px 24px alpha({shade},.14)"
             if glass else "none")
    rgb = [int(accent[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    accent_ink = "#171022" if sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722))) > .48 else "#ffffff"
    label_accent = accent if dark else f"shade({accent},.52)"
    return f"""
/* Livara native material system. Content remains opaque and legible. */
@define-color accent_color {accent};
@define-color accent_bg_color {accent};
@define-color accent_fg_color {accent_ink};
window, window.studio-window, window.livara-web {{
  background-color: {base}; color: {ink};
  background-image: linear-gradient(145deg, alpha({accent},{'.055' if glass else '0'}), transparent 45%);
}}
headerbar, .livara-web headerbar {{
  min-height: 48px; padding: 6px 14px;
  background-color: {surface}; background-image: {layer};
  border-bottom: 1px solid alpha({border},{edge});
  box-shadow: inset 0 1px alpha(white,{'.13' if glass else '0'});
  color: {ink};
}}
headerbar .title {{ font-weight: 600; }}
headerbar .subtitle {{ font-size: 11px; color: {muted}; }}
.sidebar, .studio-sidebar, .navigation-sidebar {{
  background-color: {surface}; background-image: {layer};
  border-right: 1px solid alpha({border},{edge});
}}
.sidebar .navigation-sidebar, .studio-sidebar .navigation-sidebar {{ background: transparent; border: none; }}
.brand {{ font-size: 20px; font-weight: 800; letter-spacing: 1px; color: {ink}; }}
.brand-sub, .footer {{ color: {muted}; font-size: 11px; letter-spacing: .4px; }}
.muted, .livara-web .web-status {{ color: {muted}; }}
.eyebrow, .lv-eyebrow, .metric-title {{ color: {label_accent}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
.hero-title, .home-title {{ font-size: 38px; font-weight: 700; letter-spacing: -1px; color: {ink}; }}
.page-title, .graphics-title {{ font-size: 30px; font-weight: 700; letter-spacing: -.7px; color: {ink}; }}
.card-title {{ font-size: 17px; font-weight: 600; color: {ink}; }}
.small {{ font-size: 12px; }}
.card, .metric-card, .studio-card, .essentials-card, .tool-workspace,
.lv-preview-card, .lv-palette-card, .lv-preset, .home-action {{
  background-color: {surface}; background-image: {layer};
  border: 1px solid alpha({border},{edge}); border-radius: 22px;
  box-shadow: {sheen}; color: {ink};
}}
.hero, .studio-hero {{
  background-color: {surface};
  background-image: linear-gradient(120deg, alpha({accent},{'.18' if glass else '.08'}), alpha({accent},.015) 65%), {layer};
  border: 1px solid alpha({border},{'.23' if glass else edge}); border-radius: 28px;
  box-shadow: {sheen}; color: {ink};
}}
.metric, .metric-value {{ font-size: 32px; font-weight: 600; letter-spacing: -1px; color: {ink}; font-feature-settings: "tnum"; }}
.timer-value {{ color: {ink}; }}
.nav, .mode, .navigation-sidebar row {{
  border-radius: 12px; border: 1px solid transparent;
  background: transparent; color: {ink};
  transition: background-color {duration} ease, box-shadow {duration} ease;
}}
.nav:hover, .mode:hover, .navigation-sidebar row:hover {{ background-color: alpha({accent},.08); }}
.nav:checked, .mode:checked, .navigation-sidebar row:selected {{
  background-color: alpha({accent},{'.17' if dark else '.13'});
  background-image: {layer}; border-color: alpha({accent},.2);
  box-shadow: inset 0 1px alpha(white,{'.12' if glass else '0'}); color: {ink};
}}
.boxed-list {{ background: {surface}; border: 1px solid alpha({border},{edge}); border-radius: 18px; color: {ink}; }}
.boxed-list > row {{ background: transparent; color: {ink}; padding: 5px 8px; }}
.boxed-list > row:selected {{ background-color: alpha({accent},.13); }}
button.primary, button.lv-primary, button.suggested-action {{
  background-color: {accent}; background-image: linear-gradient(to bottom, alpha(white,.16), transparent);
  color: {accent_ink}; border: 1px solid alpha(white,.18); border-radius: 12px;
  padding: 10px 18px; font-weight: 600; box-shadow: 0 3px 8px alpha({shade},.12);
}}
button.secondary, button.quiet, .home-action {{
  background-color: {surface}; background-image: {layer}; color: {ink};
  border: 1px solid alpha({border},{edge}); border-radius: 12px;
}}
button.secondary:hover, button.quiet:hover, .home-action:hover {{ background-color: alpha({accent},.14); border-color: alpha({accent},.4); }}
button:disabled {{ opacity: .5; }}
entry, searchentry, dropdown, .livara-web entry.address {{
  background-color: {base}; color: {ink}; border: 1px solid alpha({border},{edge});
  border-radius: 12px; min-height: 32px; box-shadow: inset 0 1px 2px alpha({shade},.05);
}}
entry:focus-within, searchentry:focus-within {{ border-color: alpha({accent},.75); box-shadow: 0 0 0 2px alpha({accent},.16); }}
textview, textview text, .text-frame, .zone-canvas {{ background-color: {base}; color: {ink}; }}
.text-frame {{ border-color: alpha({border},{edge}); }}
.livara-web tabbar, .livara-web .web-status {{ background-color: {surface}; color: {muted}; }}
.palette-search {{ font-size: 20px; padding: 10px 14px; }}
.feature-nav-icon {{ color: {label_accent}; }}
.navigation-sidebar .feature-nav-row {{ padding: 4px 2px; }}
popover > contents {{ background-color: {surface}; color: {ink}; border: 1px solid alpha({border},{edge}); border-radius: 18px; box-shadow: 0 12px 32px alpha({shade},.22); }}
separator {{ background-color: alpha({border},.08); min-height: 1px; }}
scale highlight, progressbar progress {{ background-color: {accent}; }}
switch:checked {{ background-color: {accent}; color: {accent_ink}; }}
.pass {{ color: {'#91dfb9' if dark else '#177b4b'}; }}
.review {{ color: {'#f3ce88' if dark else '#895b08'}; }}
"""


class _LiveMaterials:
    def __init__(self):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, Gio, Gtk
        self.Adw, self.Gtk = Adw, Gtk
        self.accent_override = None
        self.display = Gdk.Display.get_default()
        self.provider = Gtk.CssProvider()
        if self.display:
            # Above per-app base CSS, below Theme Studio previews and user CSS.
            Gtk.StyleContext.add_provider_for_display(self.display, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.connections = []
        source = Gio.SettingsSchemaSource.get_default()
        for name in ("org.livara.desktop", "org.gnome.desktop.interface"):
            if source and source.lookup(name, True):
                settings = Gio.Settings.new(name)
                self.connections.append((settings, settings.connect("changed", self.changed)))
        self.refresh()

    def changed(self, _settings, key):
        if key in ("appearance", "accent", "glass-enabled", "enable-animations", "color-scheme", "font-name"):
            self.refresh()

    def refresh(self):
        from . import desktop
        dark = desktop.read_option("appearance") != "light"
        accent = self.accent_override or desktop.ACCENTS.get(desktop.read_option("accent"), desktop.ACCENTS["purple"])[1]
        self.Adw.StyleManager.get_default().set_color_scheme(
            self.Adw.ColorScheme.FORCE_DARK if dark else self.Adw.ColorScheme.FORCE_LIGHT)
        self.provider.load_from_data(css(dark=dark, accent=accent,
            glass=desktop.read_option("glass-enabled") is not False,
            motion=desktop.read_option("animations") is not False).encode())

    def dispose(self):
        for settings, signal in self.connections:
            settings.disconnect(signal)
        self.connections.clear()
        if self.display:
            self.Gtk.StyleContext.remove_provider_for_display(self.display, self.provider)


def install_live_style():
    """Install one shared native provider per process after GTK initialization."""
    global _live_style
    if _live_style is None:
        _live_style = _LiveMaterials()
    return _live_style


def set_accent_override(accent):
    """Keep an application's explicit local accent, such as Studio's saved look."""
    if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        raise ValueError("A material accent must be a six-digit color")
    style = install_live_style()
    style.accent_override = accent
    style.refresh()

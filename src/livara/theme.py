"""Validated visual tokens shared by Livara's native apps and GTK user styles."""
from __future__ import annotations
import os
from pathlib import Path
import re
import stat
import tempfile

DEFAULTS = {"theme-enabled": False, "theme-accent": "#c5a3ff", "theme-radius": 22,
            "theme-border": 1, "theme-opacity": 92}
BEGIN, END = "/* BEGIN LIVARA THEME STUDIO */", "/* END LIVARA THEME STUDIO */"


def validate(values):
    if not isinstance(values, dict) or set(values) - DEFAULTS.keys():
        raise ValueError("Unknown Theme Studio settings")
    result = {**DEFAULTS, **values}
    if type(result["theme-enabled"]) is not bool: raise ValueError("Invalid theme switch")
    if not isinstance(result["theme-accent"], str) or not re.fullmatch(r"#[a-fA-F0-9]{6}", result["theme-accent"]):
        raise ValueError("Use a six-digit #RRGGBB accent")
    for key, low, high in (("theme-radius", 0, 36), ("theme-border", 0, 4), ("theme-opacity", 60, 100)):
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
    result["theme-accent"] = result["theme-accent"].lower()
    return result


def read_values():
    from .desktop import settings_for
    settings = settings_for("org.livara.desktop")
    values = dict(DEFAULTS)
    if settings:
        for key in values:
            if settings.props.settings_schema.has_key(key): values[key] = settings.get_value(key).unpack()
    try: return validate(values)
    except ValueError: return dict(DEFAULTS)


def css(values, *, light=False, motion=True):
    value = validate(values)
    if not value["theme-enabled"]: return ""
    accent = value["theme-accent"]
    rgb = [int(accent[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    luminance = sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722)))
    ink = "#09050f" if luminance > .48 else "#ffffff"
    surface = "248,245,253" if light else "12,8,18"
    duration = "140ms" if motion else "0ms"
    return f"""@define-color accent_color {accent};
@define-color accent_bg_color {accent};
@define-color accent_fg_color {ink};
.card, .hero, .boxed-list, .lv-preview-card, .lv-palette-card, .lv-preset,
.studio-card, .tool-workspace, .essentials-card {{
 border-radius:{value['theme-radius']}px; border:{value['theme-border']}px solid alpha({accent},.32);
 background-color:rgba({surface},{value['theme-opacity'] / 100:.2f});
 background-image:linear-gradient(135deg,alpha(white,.10),alpha(white,.015) 45%,alpha({accent},.06));
 box-shadow:inset 0 1px alpha(white,.14),inset 0 -1px alpha(black,.08),0 8px 24px alpha(black,.12);
 transition-duration:{duration};
}}
button.primary, .lv-primary, .nav:checked, switch:checked {{ background-color:{accent}; color:{ink}; }}
.eyebrow, .lv-eyebrow {{ color:{accent}; }}
"""


def replace_block(text, generated):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError("Existing Theme Studio CSS markers are damaged; the file was preserved")
    block = "\n" + BEGIN + "\n" + generated + END + "\n" if generated else ""
    if BEGIN not in text: return text + block
    start, end = text.index(BEGIN), text.index(END)
    if start > end: raise ValueError("Theme Studio markers are reversed")
    if start and text[start - 1] == "\n": start -= 1
    end += len(END)
    if text[end:end + 1] == "\n": end += 1
    return text[:start] + block + text[end:]


def apply(values, *, config_home=None):
    from . import desktop
    value = validate(values)
    settings = desktop.settings_for("org.livara.desktop")
    if settings is None: raise ValueError("Livara desktop settings are not installed")
    for key, item in value.items(): desktop.prepare_setting("org.livara.desktop", key, item)
    base = Path(config_home or os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    if not base.is_absolute(): raise ValueError("Use an absolute configuration directory")
    generated = css(value, light=desktop.read_option("appearance") == "light", motion=desktop.read_option("animations") is not False)
    plans = []
    for version in (3, 4):
        path = base / f"gtk-{version}.0/gtk.css"
        if path.is_symlink() or path.parent.is_symlink(): raise ValueError("GTK stylesheet links are preserved")
        if path.exists():
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024 * 1024: raise ValueError("GTK stylesheet is not a bounded regular file")
        original = path.read_text() if path.exists() else ""
        plans.append((path, replace_block(original, generated)))
    for path, data in plans:
        if not data and not path.exists(): continue
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".livara-theme-")
        try:
            with os.fdopen(fd, "w") as stream: stream.write(data)
            os.replace(name, path)
        finally: Path(name).unlink(missing_ok=True)
    for key, item in value.items(): desktop.write_setting("org.livara.desktop", key, item)
    return value

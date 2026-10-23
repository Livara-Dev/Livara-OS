#!/usr/bin/env python3
"""Exercise real GNOME schemas using an isolated in-memory settings backend."""
import os
os.environ["GSETTINGS_BACKEND"] = "memory"
from livara import desktop

for accent in desktop.ACCENTS:
    desktop.set_option("accent", accent)
    assert desktop.read_option("accent") == accent

for name in desktop.PRESETS:
    desktop.apply_preset(name)
    for key, value in desktop.PRESETS[name].items():
        assert desktop.read_option(key) == value, (name, key)
for key, value in {
    "blur-radius": 40, "dock-autohide": True, "dock-intellihide": True,
    "dock-trash": False, "dock-mounts": False, "animations": False,
    "hot-corners": True, "edge-tiling": True, "battery-percentage": True, "text-scale": 1.15, "clock-format": "12h",
    "clock-weekday": True, "clock-seconds": True, "dynamic-workspaces": False,
    "workspace-count": 5, "window-buttons": "close,minimize,maximize:",
    "notification-banners": False,
}.items():
    desktop.set_option(key, value)
    assert desktop.read_option(key) == value, key
for key, value in (("accent", "invalid"), ("blur-radius", 200)):
    before = desktop.read_option(key)
    try:
        desktop.set_option(key, value)
        raise AssertionError("Invalid setting accepted")
    except ValueError:
        assert desktop.read_option(key) == before
desktop.apply_live_defaults()
assert desktop.read_option("dock-position") == "BOTTOM"
assert desktop.read_option("dock-mounts") is False
assert desktop.settings_for("org.gnome.desktop.background").get_string("picture-uri").endswith("/livara-glass.png")
print("PASS: four presets, real GNOME settings read-back, and invalid values rejected", flush=True)

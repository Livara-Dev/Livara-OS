#!/usr/bin/env python3
"""Optional GTK icon workflow test in Xvfb/Openbox with a private XDG profile.

Needs Python GI/GTK4/libadwaita/GdkPixbuf SVG+WebP loaders, Pillow and xdotool.
Run in an isolated D-Bus/X11 session with PYTHONPATH=src. It writes only to a
temporary user profile and LIVARA_ICON_TEST_OUTPUT (default /tmp/livara-icon-test).
The screenshot is an actual test-container Settings window, not an OS boot.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
profile = tempfile.TemporaryDirectory(prefix="livara-icon-profile-")
home = Path(profile.name)
for name in ("config", "data", "home"):
    (home / name).mkdir()
os.environ.update(HOME=str(home / "home"), XDG_CONFIG_HOME=str(home / "config"),
                  XDG_DATA_HOME=str(home / "data"), XDG_DATA_DIRS=str(ROOT / "share") + ":/usr/local/share:/usr/share",
                  GSETTINGS_BACKEND="memory", GTK_A11Y="none", LIVARA_DATA_DIR=str(ROOT / "share/livara"))
out = Path(os.environ.get("LIVARA_ICON_TEST_OUTPUT", "/tmp/livara-icon-test"));out.mkdir(parents=True, exist_ok=True)
icons = home / "data/icons/hicolor/scalable/apps";icons.mkdir(parents=True)
for icon in (ROOT / "artwork").glob("org.livara.*.svg"): shutil.copy2(icon, icons)
(icons.parent.parent / "index.theme").write_text("[Icon Theme]\nName=Hicolor\nDirectories=scalable/apps\n\n[scalable/apps]\nSize=48\nType=Scalable\nContext=Applications\n")
import gi
gi.require_version("Gtk", "4.0");gi.require_version("Adw", "1");gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gio, GLib, Gtk, GdkPixbuf
from PIL import Image, ImageGrab
from livara import app_icons
from livara.gui import settings_main

checks, errors = [], []
def require(test, message):
    if not test: raise AssertionError(message)
def guarded(function):
    def run():
        try: function()
        except Exception as error:
            traceback.print_exc();errors.append(str(error));Gio.Application.get_default().quit()
        return False
    return run

@guarded
def start():
    app = Gio.Application.get_default();ui = app.app_icons_ui
    app.stack.set_visible_child_name("icons")
    require(len(ui.apps) > 0, "No actual desktop launchers found")
    ui.test_app = next(a for a in ui.apps if a.id == "org.livara.Settings.desktop")
    ui.before = Path(ui.test_app.filename).read_bytes()
    # Exercise the actual chooser, allowing its asynchronous selection to finish.
    ui.choose(ui.test_app)
    ui.chooser.set_file(Gio.File.new_for_path(str(ROOT / "artwork/livara-browser.png")))
    GLib.timeout_add(700, accept)

@guarded
def accept():
    ui = Gio.Application.get_default().app_icons_ui
    require(ui.chooser.get_file() is not None, "Image chooser did not select the actual file")
    ui.chooser.emit("response", Gtk.ResponseType.ACCEPT)
    GLib.timeout_add(100, applied)

@guarded
def applied():
    app = Gio.Application.get_default();ui = app.app_icons_ui
    if ui.busy:
        GLib.timeout_add(100, applied);return
    target, _, state = ui.manager.paths(ui.test_app.id)
    require(state.exists() and target.exists(), "Actual chooser/worker did not save the icon")
    entry = Gio.DesktopAppInfo.new_from_filename(str(target))
    require(entry.get_commandline() == Gio.DesktopAppInfo.new_from_filename(ui.test_app.filename).get_commandline(), "Launcher command changed")
    require(entry.get_icon().to_string().endswith(".png"), "Gio did not load the saved PNG icon")
    require(Path(ui.test_app.filename).read_bytes() == ui.before, "System launcher was modified")
    require(ui.manager.customized(ui.test_app.id), "Custom status not recorded")
    checks.append("Actual native chooser, background apply, Gio icon readback and unchanged system launcher/command")
    ui.search.set_text("Livara");ui.filter_changed()
    ui.custom_only.set_active(True)
    require("1 app ·" in ui.count.get_text(), "Customized filter did not find the real override")
    checks.append("Actual app search and customized-only filter")
    ui.custom_only.set_active(False)
    GLib.timeout_add(500, capture)

@guarded
def capture():
    ui = Gio.Application.get_default().app_icons_ui
    ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(out / "app-icons.png")
    ui.restore(ui.test_app)
    GLib.timeout_add(100, restored)

@guarded
def restored():
    app = Gio.Application.get_default();ui = app.app_icons_ui
    if ui.busy:
        GLib.timeout_add(100, restored);return
    require(not ui.manager.customized(ui.test_app.id), "Restore did not remove the icon override")
    require(not ui.manager.paths(ui.test_app.id)[0].exists(), "Default app did not return to inherited launcher")
    require(Path(ui.test_app.filename).read_bytes() == ui.before, "System launcher changed during restore")
    checks.append("Native Restore returns default app to its untouched installed launcher")
    for ext in ("png", "jpeg", "webp", "ico"):
        file = out / ("fixture." + ext);Image.new("RGBA" if ext != "jpeg" else "RGB", (64, 64), "purple").save(file)
        require(app_icons.render_icon(file).startswith(b"\x89PNG\r\n\x1a\n"), "Image decoder failed: " + ext)
    require(app_icons.render_icon(ROOT / "artwork/org.livara.Code.svg").startswith(b"\x89PNG"), "Real Livara SVG could not decode")
    checks.append("Actual PNG, JPEG, WebP, ICO and Livara SVG decoding into owned PNGs")
    # Verify the new page does not force the window beyond the existing target.
    ui.custom_only.set_active(False);ui.search.set_text("");ui.filter_changed()
    xid = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--name", "^Livara Settings$"], text=True).splitlines()[0]
    subprocess.run(["xdotool", "windowsize", xid, "800", "600"], check=True)
    GLib.timeout_add(600, finish)

@guarded
def finish():
    app = Gio.Application.get_default()
    require(app.window.get_width() <= 800 and app.window.get_height() <= 600, "Icon page does not fit 800x600")
    checks.append("Actual icon page fits an 800x600 X11 window request")
    record = {"result": "passed", "checks": checks, "context": "Actual GTK4/Xvfb/Openbox in a temporary XDG profile; not an ISO boot", "source_sha256": {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ("src/livara/app_icons.py", "src/livara/app_icons_ui.py", "src/livara/gui.py")}}
    (out / "native-result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True);app.quit()

GLib.timeout_add_seconds(2, start)
def timeout():
    errors.append("Native icon test timed out");Gio.Application.get_default().quit();return False
GLib.timeout_add_seconds(40, timeout)
code = settings_main()
if errors: raise RuntimeError(errors)
raise SystemExit(code)

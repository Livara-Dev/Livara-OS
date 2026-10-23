#!/usr/bin/env python3
"""Exercise the real GTK4 Livara Settings CSD under Xvfb + a small X11 WM.

Run in the native-test image (not a GNOME Shell/compositor qualification):
  xvfb-run -a dbus-run-session -- python3 scripts/window-controls-smoke.py
The runner isolates HOME, user configuration and the GSettings memory backend.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".build/window-controls"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="livara-controls-") as temporary:
        sandbox = Path(temporary)
        schemas = sandbox / "schemas"
        schemas.mkdir()
        shutil.copy2(ROOT / "share/livara/org.livara.desktop.gschema.xml", schemas)
        subprocess.run(["glib-compile-schemas", "--strict", str(schemas)], check=True)
        os.environ.update({"HOME": str(sandbox / "home"), "XDG_CONFIG_HOME": str(sandbox / "config"),
                           "XDG_DATA_HOME": str(sandbox / "data"), "GSETTINGS_SCHEMA_DIR": str(schemas),
                           "GSETTINGS_BACKEND": "memory", "GTK_A11Y": "none",
                           "LIVARA_DATA_DIR": str(ROOT / "share/livara")})
        Path(os.environ["HOME"]).mkdir()
        icons = Path(os.environ["XDG_DATA_HOME"]) / "icons/hicolor/scalable/apps"
        icons.mkdir(parents=True)
        for asset in (ROOT / "artwork").glob("org.livara.*.svg"):
            shutil.copy2(asset, icons)
        (icons.parent.parent / "index.theme").write_text("[Icon Theme]\nName=Hicolor\nDirectories=scalable/apps\n\n[scalable/apps]\nSize=48\nType=Scalable\nMinSize=16\nMaxSize=256\nContext=Applications\n")
        # A tiny X11 WM is required for real _NET_WM_STATE_FULLSCREEN/maximize.
        with (OUTPUT / "openbox.log").open("w") as wm_log:
            wm = subprocess.Popen(["openbox", "--sm-disable"], stdout=wm_log, stderr=subprocess.STDOUT)
            try:
                return exercise()
            finally:
                wm.terminate()
                try:
                    wm.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    wm.kill()
                    wm.wait()


def exercise() -> int:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk
    from PIL import ImageGrab
    from livara import desktop, gui, window_style

    results = {"gtk": f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
               "adwaita": f"{Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}",
               "scope": "Native GTK4 Settings under Xvfb/Openbox; GNOME Shell window effects are not exercised.",
               "checks": [], "css_errors": []}
    # Parse all generated GTK4 CSS, including representative extremes.
    for size in (10, 14, 22):
        provider = Gtk.CssProvider()
        provider.connect("parsing-error", lambda provider, section, error: results["css_errors"].append(str(error)))
        provider.load_from_data(window_style.css_for_values({"window-button-size": size}).encode())
    assert not results["css_errors"], results["css_errors"]
    state = {"phase": 0, "failure": None, "started": time.monotonic(), "app": None, "window": None}

    def check(condition, text):
        if not condition:
            raise AssertionError(text)
        results["checks"].append(text)
        print("PASS:", text, flush=True)

    def shot(name):
        ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(OUTPUT / name)

    def find_window():
        model = Gtk.Window.get_toplevels()
        for index in range(model.get_n_items()):
            window = model.get_item(index)
            if window.get_title() == "Livara Settings":
                return window
        return None

    def preference(name):
        app = state["app"]
        if hasattr(app, "preferences_ui"):
            binding = app.preferences_ui.bindings[name]
            widget, item = binding["widget"], binding["item"]
            if item["kind"] in ("int", "float"):
                return widget.livara_scale, item["range"]
            if item["kind"] == "choice":
                return widget, item["choices"]
            return widget, "color" if item["kind"] == "color" else None
        return next((widget, values) for key, widget, values in app.preference_widgets if key == name)

    def select(name, value):
        widget, values = preference(name)
        widget.set_selected(next(index for index, pair in enumerate(values) if pair[0] == value))

    def xkey(key):
        found = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "^Livara Settings$"],
                               check=True, capture_output=True, text=True)
        window_id = found.stdout.splitlines()[0]
        subprocess.run(["xdotool", "windowactivate", "--sync", window_id], check=True)
        subprocess.run(["xdotool", "key", "--clearmodifiers", key], check=True)

    def coordinates(button):
        ok, rectangle = button.compute_bounds(state["window"])
        assert ok
        return rectangle.get_x(), rectangle.get_y(), rectangle.get_width(), rectangle.get_height()

    def tick():
        try:
            if time.monotonic() - state["started"] > 45:
                raise TimeoutError("Native GTK smoke exceeded 45 seconds")
            phase = state["phase"]
            if phase == 0:
                window = find_window()
                if window is None or not window.get_mapped():
                    return True
                state.update(window=window, app=window.get_application())
                handle = state["app"].headerbar_controls
                state["handle"] = handle
                state["width"] = handle.buttons["close"].get_width()
                check(handle.box.get_visible(), "Real Settings headerbar shows custom traffic lights")
                check(not handle.headerbar.get_show_start_title_buttons() and not handle.headerbar.get_show_end_title_buttons(), "Stock title buttons are hidden while custom CSD is active")
                check(handle.buttons["close"].get_tooltip_text() == "Close window", "Native close button has an accessible semantic label")
                live = window_style.install_live_style()
                live.provider.connect("parsing-error", lambda provider, section, error: results["css_errors"].append(str(error)))
                preference("window-button-size")[0].set_value(22)
                color = preference("window-close-color")[0]
                color.livara_color_entry.set_text("#dd3377")
                color.livara_color_entry.emit("activate")
                preference("window-button-symbols")[0].set_active(True)
                select("window-buttons", ":minimize,maximize,close")
            elif phase == 1:
                handle = state["handle"]
                check(desktop.read_option("window-button-size") == 22, "Settings diameter scale persisted its value")
                check(handle.buttons["close"].get_width() > state["width"], "Live CSS enlarged actual native button allocation")
                check(desktop.read_option("window-close-color") == "#dd3377", "Settings hex-color control persisted its value")
                check(handle.box.has_css_class("symbols-visible"), "Settings symbol switch updated the live controls")
                check(coordinates(handle.buttons["close"])[0] > state["window"].get_width() / 2, "Right-side preference physically moved the native controls")
                shot("right-customized.png")
                select("window-buttons", "close,minimize,maximize:")
                # Headerbar layout can be RTL, while the controls keep physical
                # placement and their red/yellow/green LTR order.
                handle.headerbar.set_direction(Gtk.TextDirection.RTL)
                handle._packing_widget.set_direction(Gtk.TextDirection.RTL)
            elif phase == 2:
                handle = state["handle"]
                xs = [coordinates(handle.buttons[key])[0] for key in ("close", "minimize", "maximize")]
                check(xs[0] < state["window"].get_width() / 2, "Physical left-side preference survives an RTL headerbar")
                check(xs == sorted(xs), "Traffic-light red/yellow/green order remains LTR under RTL")
                handle.headerbar.set_direction(Gtk.TextDirection.LTR)
                handle._packing_widget.set_direction(Gtk.TextDirection.LTR)
                select("window-button-style", "default")
            elif phase == 3:
                handle = state["handle"]
                check(not handle.box.get_visible(), "Native-style preference hides custom buttons")
                check(handle.headerbar.get_show_start_title_buttons() == handle._stock["start"] and handle.headerbar.get_show_end_title_buttons() == handle._stock["end"], "Native-style preference restores original stock-button visibility")
                select("window-button-style", "traffic-lights")
                select("window-green-action", "fullscreen")
                handle.buttons["maximize"].emit("clicked")
            elif phase == 4:
                if not state["window"].is_fullscreen():
                    return True
                check(True, "Green native button entered real window-manager fullscreen")
                check("Exit fullscreen" in state["handle"].buttons["maximize"].get_tooltip_text(), "Green tooltip follows native fullscreen state")
                shot("fullscreen.png")
                xkey("F11")
            elif phase == 5:
                if state["window"].is_fullscreen():
                    return True
                check(True, "Actual F11 key left fullscreen through the GTK shortcut controller")
                select("window-green-action", "maximize")
                state["handle"].buttons["maximize"].emit("clicked")
            elif phase == 6:
                if not state["window"].is_maximized():
                    return True
                check(True, "Green maximize preference invokes real native maximize")
                state["handle"].buttons["maximize"].emit("clicked")
            elif phase == 7:
                if state["window"].is_maximized():
                    return True
                check(True, "Green maximize preference restores the native window")
                select("window-green-action", "fullscreen")
                # Use the actual Gdk pointer event path for Shift-click.
                found = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "^Livara Settings$"], check=True, capture_output=True, text=True)
                window_id = found.stdout.splitlines()[0]
                x, y, width, height = coordinates(state["handle"].buttons["maximize"])
                subprocess.run(["xdotool", "keydown", "Shift_L", "mousemove", "--window", window_id, str(int(x + width / 2)), str(int(y + height / 2)), "click", "1", "keyup", "Shift_L"], check=True)
            elif phase == 8:
                if not state["window"].is_maximized():
                    return True
                check(not state["window"].is_fullscreen(), "Actual Shift-click green maximizes instead of fullscreen")
                state["window"].unmaximize()
                state["handle"].buttons["minimize"].emit("clicked")
            elif phase == 9:
                if not (state["window"].get_surface().get_state() & Gdk.ToplevelState.MINIMIZED):
                    return True
                check(True, "Yellow native button minimizes through the window manager")
                state["window"].present()
            elif phase == 10:
                if state["window"].get_surface().get_state() & Gdk.ToplevelState.MINIMIZED:
                    return True
                check(True, "The minimized native window can be restored")
                preference("animations")[0].set_active(False)
                state["app"].stack.set_visible_child_name("system")
            elif phase == 11:
                check(not desktop.read_option("animations"), "Settings reduced-motion switch updates the desktop animation preference")
                check(state["app"].stack.get_transition_duration() == 0, "Native Settings transitions stop under reduced motion")
                state["app"].stack.set_visible_child_name("customize")
                if hasattr(state["app"], "preferences_ui"):
                    state["app"].preferences_ui.tab_buttons["windows"].set_active(True)
                    state["app"].preferences_ui.select_section("windows")
                widget, _ = preference("window-button-style")
                widget.grab_focus()
                # Reveal the new window-controls section in its actual scroll.
                ancestor = widget.get_parent()
                while ancestor and not isinstance(ancestor, Gtk.ScrolledWindow):
                    ancestor = ancestor.get_parent()
                if ancestor:
                    adjustment = ancestor.get_vadjustment()
                    adjustment.set_value(260 if hasattr(state["app"], "preferences_ui") else 700)
            elif phase == 12:
                # A second live window proves native close preserves application
                # guards, then releases the binding when the window is destroyed.
                child = Adw.ApplicationWindow(application=state["app"], title="Livara close guard", default_width=360, default_height=180)
                header = Adw.HeaderBar()
                content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                content.append(header)
                content.append(Gtk.Label(label="Controlled close-request fixture"))
                child.set_content(content)
                state["child"] = child
                state["child_handle"] = window_style.configure_native_headerbar(child, header)
                state["guard"] = child.connect("close-request", lambda *args: True)
                child.present()
            elif phase == 13:
                state["child_handle"].buttons["close"].emit("clicked")
                check(state["child"].get_visible(), "Custom red control respects an application's close-request guard")
                state["child"].disconnect(state["guard"])
                state["child_handle"].buttons["close"].emit("clicked")
                check(state["child_handle"]._disposed, "Destroying the controlled child releases settings and shortcut bindings")
                state["window"].present()
            elif phase == 14:
                shot("final.png")
                shutil.copy2(OUTPUT / "final.png", ROOT / "docs/livara-window-controls.png")
                check(not results["css_errors"], "Generated and live GTK CSS produced zero parsing errors")
                state["handle"].buttons["close"].emit("clicked")
                check(state["handle"]._disposed, "Main native close action destroys the window and releases its binding")
                return False
            state["phase"] += 1
            return True
        except Exception:
            state["failure"] = traceback.format_exc()
            print(state["failure"], file=sys.stderr, flush=True)
            shot("failure.png")
            if state["app"]:
                state["app"].quit()
            return False

    GLib.timeout_add(350, tick)
    result = gui.main(mode="settings")
    results["failure"] = state["failure"]
    results["completed_phases"] = state["phase"]
    (OUTPUT / "result.json").write_text(json.dumps(results, indent=2) + "\n")
    if state["failure"] or state["phase"] != 14:
        return 1
    return result


if __name__ == "__main__":
    sys.exit(main())

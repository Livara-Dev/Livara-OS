#!/usr/bin/env python3
"""Capture unmodified Livara GTK apps in a clearly identified test environment.

Needs GTK4/libadwaita, Cairo GI bridge, SVG loader, Xvfb, Openbox, xdotool and PIL.
The runner never builds an OS/ISO. System observations are from its container.
"""
from __future__ import annotations

import argparse
import hashlib
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
OUTPUT = ROOT / "docs/screenshots"
EVIDENCE = ROOT / ".build/native-gallery"
APPS = ("center", "settings", "monitor", "studio", "graphics")
ORIGIN = "Actual Livara GTK4 apps on Ubuntu 24.04 under Xvfb/Openbox; this is not a booted Livara desktop."


def prepare(sandbox: Path):
    schemas = sandbox / "schemas"
    schemas.mkdir()
    shutil.copy2(ROOT / "share/livara/org.livara.desktop.gschema.xml", schemas)
    subprocess.run(["glib-compile-schemas", "--strict", str(schemas)], check=True)
    os.environ.update(HOME=str(sandbox / "home"), XDG_CONFIG_HOME=str(sandbox / "config"),
                      XDG_DATA_HOME=str(sandbox / "data"), GSETTINGS_SCHEMA_DIR=str(schemas),
                      GSETTINGS_BACKEND="memory", GTK_A11Y="none",
                      LIVARA_DATA_DIR=str(ROOT / "share/livara"))
    Path(os.environ["HOME"]).mkdir()
    data = Path(os.environ["XDG_DATA_HOME"])
    icons = data / "icons/hicolor/scalable/apps"
    icons.mkdir(parents=True)
    for source in (ROOT / "artwork").glob("org.livara.*.svg"):
        shutil.copy2(source, icons)
    (icons.parent.parent / "index.theme").write_text("[Icon Theme]\nName=Hicolor\nDirectories=scalable/apps\n\n[scalable/apps]\nSize=48\nType=Scalable\nMinSize=16\nMaxSize=256\nContext=Applications\n")
    fonts = data / "fonts"
    fonts.mkdir()
    for source in (ROOT / "fonts/ttf").glob("*.ttf"):
        shutil.copy2(source, fonts)
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "fontconfig/conf.d"
    config.mkdir(parents=True)
    shutil.copy2(ROOT / "share/fontconfig/60-livara-fonts.conf", config)
    if shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", str(fonts)], check=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", choices=APPS)
    parser.add_argument("--only", choices=APPS, nargs="+", help="recapture selected apps and retain other existing gallery entries")
    parser.add_argument("--view", nargs="+", help="recapture selected section keys within one app")
    parser.add_argument("--skip-probe", action="store_true", help="reuse already-qualified native button metrics")
    parser.add_argument("--preloaded-css-probe", action="store_true")
    options = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if options.preloaded_css_probe:
        return css_probe()
    if options.app:
        return capture_app(options.app, options.view)
    entries = []
    failures = []
    with tempfile.TemporaryDirectory(prefix="livara-gallery-") as temporary:
        prepare(Path(temporary))
        with (EVIDENCE / "openbox.log").open("w") as stream:
            wm = subprocess.Popen(["openbox", "--sm-disable"], stdout=stream, stderr=subprocess.STDOUT)
            compositor = subprocess.Popen(["xcompmgr", "-n"], stdout=stream, stderr=subprocess.STDOUT) if shutil.which("xcompmgr") else None
            try:
                # Probe first so source reviewers can inspect exact native
                # metrics while the actual-app gallery continues serially.
                probe_log = EVIDENCE / "preloaded-css.log"
                if not options.skip_probe:
                    with probe_log.open("w") as stream:
                        probe = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--preloaded-css-probe"],
                                               stdout=stream, stderr=subprocess.STDOUT, timeout=20)
                    if probe.returncode:
                        print(probe_log.read_text(), file=sys.stderr)
                for name in (options.only or APPS):
                    log = EVIDENCE / (name + ".log")
                    command = [sys.executable, str(Path(__file__).resolve()), "--app", name]
                    if options.view:
                        command += ["--view", *options.view]
                    with log.open("w") as output:
                        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=60)
                    metadata = EVIDENCE / (name + ".json")
                    if metadata.is_file():
                        entries.extend(json.loads(metadata.read_text()).get("screenshots", []))
                    if result.returncode:
                        failures.append(name)
                        print(log.read_text(), file=sys.stderr)
                    print(f"Captured {name}: {'PASS' if not result.returncode else 'FAILED'}", flush=True)
            finally:
                if compositor is not None:
                    compositor.terminate()
                    compositor.wait(timeout=5)
                wm.terminate()
                try:
                    wm.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    wm.kill()
                    wm.wait()
    manifest = OUTPUT / "native-manifest.json"
    if options.only and manifest.is_file():
        prior = json.loads(manifest.read_text())
        replaced = {entry["file"] for entry in entries}
        entries = [entry for entry in prior.get("screenshots", []) if entry["file"] not in replaced] + entries
    result = {"origin": ORIGIN, "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "limitations": ["No GNOME Shell desktop, login, installer, boot splash or window effects were captured.",
                              "Native package availability, processes, CPU/RAM/network and graphics results reflect the test container.",
                              "The named gallery look and Studio notes are explicitly marked examples saved through the real apps; the timer is a real running session.",
                              "The uncompiled Gecko source fork and the separate official Tor Browser are outside this native-app capture."],
              "screenshots": entries, "failed_apps": failures}
    (OUTPUT / "native-manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 1 if failures else 0


def capture_app(name: str, views: list[str] | None = None) -> int:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gdk, Gio, GLib, Gtk
    from PIL import ImageGrab
    from livara import desktop

    settings = Gio.Settings.new("org.gnome.desktop.interface")
    settings.set_string("font-name", "Livara Sans 11")
    settings.set_string("monospace-font-name", "Livara Mono 11")
    Gio.Settings.new("org.gnome.desktop.wm.preferences").set_string("button-layout", "close,minimize,maximize:")
    if name == "settings":
        # Initialize the actual built-in background just as a Livara session
        # does; leave the minimal Ubuntu image's missing stock wallpaper out.
        desktop.set_wallpaper_image("")
    metadata = {"origin": ORIGIN, "app": name, "screenshots": [], "failure": None}
    state = {"app": None, "window": None, "step": 0, "started": time.monotonic(), "prepared": False}
    modules = {"center": "gui", "settings": "gui", "monitor": "monitor_gui", "studio": "studio_gui", "graphics": "gpu_gui"}
    titles = {"center": "Livara Control Center", "settings": "Livara Settings", "monitor": "Livara Task Manager", "studio": "Livara Studio", "graphics": "Livara Graphics"}
    plan = {
        "center": [("home", "center-overview", "Livara Control Center", "Live container summary and app navigation."),
                   ("toolbox", "security-toolbox", "Security toolbox", "Actual native tool availability in the small test image; the full OS package set is not installed here."),
                   ("cases", "case-workspaces", "Case workspaces", "An empty real workspace, ready to create a case."),
                   ("shield", "security-shield", "Livara Shield", "Read-only security checks of the test container."),
                   ("verify", "file-verification", "File verification", "Native SHA-256 verification screen; no file or checksum is fabricated."),
                   ("apps", "app-launcher", "Livara apps", "Native app catalog with actual launcher controls.")],
        "settings": [("appearance", "settings-personalize", "Settings · Look", "Redesigned Look section with actual presets, wallpaper preview, and an explicitly labeled gallery preset saved through the real UI."),
                     ("appearance-lower", "settings-look-controls", "Settings · Look controls", "Actual wallpaper, glass, and color controls below the Look preview."),
                     ("windows", "settings-window-controls", "Settings · Windows", "The Windows section with native traffic-light controls and motion preferences."),
                     ("windows-lower", "settings-window-palette", "Settings · Window palette", "Actual color controls and remaining window preferences below the native window preview."),
                     ("dock", "settings-dock", "Settings · Dock", "Real dock options exposed by available schemas; unavailable controls stay disabled in this container."),
                     ("typography", "settings-typography", "Settings · Type", "Actual font controls and a live font preview using the supplied Livara fonts."),
                     ("typography-lower", "settings-type-controls", "Settings · Type controls", "Additional font, scale, and rendering controls."),
                     ("workspaces", "settings-spaces", "Settings · Spaces", "Actual workspace, clock, and status-area preferences."),
                     ("privacy", "settings-focus", "Settings · Focus", "Actual notifications, recent-history, lock, and session controls."),
                     ("input", "settings-input", "Settings · Input", "Actual pointer, touchpad, and keyboard controls available to the test session."),
                     ("display", "settings-display", "Settings · Display", "Actual display and night-light preferences; unavailable device options remain disabled."),
                     ("search", "settings-search", "Settings · Search", "Real catalog search for font controls, with filtered sections and visible match counts."),
                     ("preview", "settings-real-preview", "Settings · Real window preview", "The app's real native preview window, opened through its existing action."),
                     ("system", "settings-device", "Device and connectivity", "Device panel launchers; this capture does not open GNOME hardware panels.")],
        "monitor": [("overview", "monitor-overview", "Task Manager overview", "Live CPU, memory, network, disk and uptime observations from the container."),
                    ("processes", "monitor-processes", "Task Manager processes", "Actual test-container processes; selected manager cannot signal itself.")],
        "studio": [("home", "studio-home", "Studio · Overview", "The actual redesigned workspace Home with default favorites and truthful empty activity history."),
                   ("tools", "studio-tools", "Studio · Workbench", "The real JSON formatter run on its built-in sample in the redesigned workspace."),
                   ("search", "studio-search", "Studio · Search", "Real tool search for color and the actual Color Prism output."),
                   ("notes", "studio-notes", "Studio · Notebook", "An explicitly labeled English/Persian gallery example saved through the redesigned Notebook."),
                   ("focus", "studio-focus", "Studio · Focus", "A real running 25-minute local timer; no completed history is invented."),
                   ("appearance", "studio-appearance", "Studio · Customize", "The actual app-specific accent, density, and editor-size popover.")],
        "graphics": [("overview", "graphics-overview", "Graphics observations", "Actual container hardware/driver observations; no GPU pass-through is configured.")],
    }[name]
    if views:
        plan = [item for item in plan if item[0] in views]
        if len(plan) != len(set(views)):
            raise ValueError("A requested view is not part of this app's capture plan")

    def find():
        windows = Gtk.Window.get_toplevels()
        for index in range(windows.get_n_items()):
            window = windows.get_item(index)
            if window.get_title() == titles[name] and window.get_mapped():
                return window
        return None

    def preference(key):
        return next(widget for name, widget, values in state["app"].preference_widgets if name == key)

    def scroll_to(widget, value):
        ancestor = widget
        while ancestor and not isinstance(ancestor, Gtk.ScrolledWindow):
            ancestor = ancestor.get_parent()
        if ancestor:
            ancestor.get_vadjustment().set_value(value)

    def prepare_view(key):
        app = state["app"]
        if name == "settings":
            ui = app.preferences_ui
            if ui._preview_window:
                ui._preview_window.close()
            if key == "system":
                app.stack.set_visible_child_name("system")
                return
            app.stack.set_visible_child_name("customize")
            ui.search.set_text("")
            if key == "search":
                ui.search.set_text("font")
                ui.filter_changed()
                return
            section = "windows" if key == "preview" else key.removesuffix("-lower")
            ui.tab_buttons[section].set_active(True)
            ui.select_section(section)
            page = ui.stack.get_child_by_name(section)
            page.get_vadjustment().set_value(0)
            if key.endswith("-lower"):
                # A newly visible GtkScrolledWindow needs one layout frame
                # before its adjustment exposes the full page extent.
                state["scroll_bottom"] = page
            if key == "appearance" and not state.get("saved_gallery_look"):
                ui.preset_dialog()
                ui._preset_name_entry.set_text("Gallery example · Livara look")
                ui._preset_dialog.response("save")
                state["saved_gallery_look"] = True
            if key == "preview":
                ui.open_preview()
            return
        if name in ("center", "monitor"):
            app.stack.set_visible_child_name(key)
            if name == "monitor" and key == "processes" and app.snapshot:
                own = next((row for row in app.rows.values() if row.process.pid == os.getpid()), None)
                if own:
                    app.process_list.select_row(own)
        elif name == "studio":
            app.customize_button.get_popover().popdown()
            app.search.set_text("")
            if key == "appearance":
                app.mode_buttons["home"].set_active(True)
                app.customize_button.get_popover().popup()
                return
            if key == "search":
                app.open_tool("color")
                app.search.set_text("color")
                app.filter_tools(app.search)
                app.run_current_tool()
                return
            app.mode_buttons[key].set_active(True)
            if key == "tools":
                app.open_tool("json")
                app.run_current_tool()
            elif key == "notes":
                app.new_note_template("blank")
                app.note_title.set_text("Gallery example · local notebook")
                app.note_body.get_buffer().set_text("This is an example page created for the Livara screenshot gallery.\n\nA quiet place for an idea, a project plan, or a useful reminder.\n\nیادداشت نمونه برای نمایش قلم فارسی لیوارا\n\nThis sample contains no personal information.")
                app.save_note()
            elif key == "focus":
                app.focus_label.set_text("Gallery example · explore Livara")
                app.start_focus()

    def tick():
        try:
            if time.monotonic() - state["started"] > 45:
                raise TimeoutError("The actual native app did not finish its capture plan")
            if state["window"] is None:
                window = find()
                if window is None:
                    return True
                state.update(window=window, app=window.get_application())
                # Leave the real native default sizing; remove the pointer from
                # the app to avoid capturing transient tooltips.
                subprocess.run(["xdotool", "mousemove", "1275", "895"], check=True)
                return True
            app = state["app"]
            if name == "monitor" and (app.snapshot is None or time.monotonic() - state["started"] < 7):
                return True
            if name == "graphics" and app.busy:
                return True
            if name == "studio" and app.job_pending:
                return True
            if state["step"] >= len(plan):
                if name == "studio":
                    app.reset_focus()
                app.quit()
                return False
            key, filename, label, detail = plan[state["step"]]
            if not state["prepared"]:
                prepare_view(key)
                state["prepared"] = True
                return True
            pending_scroll = state.pop("scroll_bottom", None)
            if pending_scroll is not None:
                adjustment = pending_scroll.get_vadjustment()
                adjustment.set_value(max(0, adjustment.get_upper() - adjustment.get_page_size()))
                return True
            # No synthetic widgets, metric values, compositing or screenshot
            # overlays: this is the actual X11 framebuffer after GTK rendered.
            path = OUTPUT / ("native-" + filename + ".png")
            ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(path)
            metadata["screenshots"].append({"file": path.name, "title": label, "detail": detail, "origin": ORIGIN, "app": name, "source_sha256": metadata.get("source_sha256", {}), "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print("Captured", path.name, flush=True)
            state["step"] += 1
            state["prepared"] = False
            return True
        except Exception:
            metadata["failure"] = traceback.format_exc()
            print(metadata["failure"], file=sys.stderr, flush=True)
            if state["app"]:
                state["app"].quit()
            return False

    GLib.timeout_add(900, tick)
    module = __import__("livara." + modules[name], fromlist=["main"])
    source_files = [ROOT / "src/livara" / (modules[name] + ".py")]
    if name == "settings":
        source_files.append(ROOT / "src/livara/settings_ui.py")
    metadata["source_sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
    result = module.main(mode="settings" if name == "settings" else "center") if name in ("center", "settings") else module.main()
    (EVIDENCE / (name + ".json")).write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    return 1 if metadata["failure"] or state["step"] != len(plan) else result


def css_probe() -> int:
    # Make a fresh HOME, ensuring GTK loads a real managed user CSS file before
    # any display/provider initialization, then observe the default-style switch.
    with tempfile.TemporaryDirectory(prefix="livara-preloaded-css-") as temporary:
        root = Path(temporary)
        os.environ["HOME"] = str(root)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        from livara import window_style
        window_style.apply_user_style({"window-button-size": 22})
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gio, GLib, Gtk
        observations = {"origin": ORIGIN, "probe": "Preloaded managed GTK4 user CSS then native/default style", "measurements": []}
        Gio.Settings.new("org.gnome.desktop.interface").set_string("font-name", "Livara Sans 11")
        preferences = Gio.Settings.new("org.livara.desktop")
        preferences.set_int("window-button-size", 22)
        app = Adw.Application(application_id="org.livara.NativeCSSProbe")
        state = {"phase": 0}

        def activate(application):
            window = Adw.ApplicationWindow(application=application, title="Livara GTK CSS reload probe", default_width=400, default_height=180)
            header = Adw.HeaderBar()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.append(header)
            window.set_content(box)
            live = window_style.install_live_style()
            state.update(window=window, header=header, live=live)
            window.present()

        def walk(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from walk(child)
                child = child.get_next_sibling()

        def measure():
            if state["phase"] < 2:
                close = next(widget for widget in walk(state["header"]) if isinstance(widget, Gtk.Button) and widget.has_css_class("close"))
            else:
                close = state["handle"].buttons["close"]
            observations["measurements"].append({"phase": state["phase"],
                "kind": "stock" if state["phase"] < 2 else "custom",
                "style": window_style.read_values()["window-button-style"],
                "diameter_preference": window_style.read_values()["window-button-size"],
                "close_width": close.get_width(), "close_height": close.get_height()})
            if state["phase"] < 2:
                from PIL import ImageGrab
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(EVIDENCE / ("preloaded-css-" + str(state["phase"]) + ".png"))
            if state["phase"] == 0:
                preferences.set_string("window-button-style", "default")
                window_style.apply_user_style({"window-button-style": "default"})
            elif state["phase"] == 1:
                observations["css_after_default"] = (root / "config/gtk-4.0/gtk.css").read_text()
                preferences.set_string("window-button-style", "traffic-lights")
                preferences.set_int("window-button-size", 14)
                state["handle"] = window_style.configure_native_headerbar(state["window"], state["header"])
            elif state["phase"] == 2:
                preferences.set_int("window-button-size", 22)
            elif state["phase"] == 3:
                preferences.set_int("window-button-size", 10)
            else:
                (EVIDENCE / "preloaded-css.json").write_text(json.dumps(observations, indent=2) + "\n")
                print(json.dumps(observations), flush=True)
                app.quit()
                return False
            state["phase"] += 1
            return True

        app.connect("activate", activate)
        GLib.timeout_add(1000, measure)
        return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())

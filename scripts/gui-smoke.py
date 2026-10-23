#!/usr/bin/env python3
"""Start the real GTK application under Xvfb and retain a screenshot."""

import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab


def main():
    settings_mode = "--settings" in sys.argv
    output = Path(".build/settings-gui" if settings_mode else ".build/gui")
    output.mkdir(parents=True, exist_ok=True)
    with (output / "application.log").open("w") as log:
        command = [sys.executable, "-c", "from livara.gui import main; raise SystemExit(main(mode='settings'))"] if settings_mode else [sys.executable, "-m", "livara.gui"]
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            window = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("GTK application exited; inspect application.log")
                result = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "Livara Settings" if settings_mode else "Livara Control Center"], capture_output=True, text=True)
                if result.returncode == 0:
                    window = result.stdout.splitlines()[0]
                    break
                time.sleep(0.2)
            if not window:
                raise RuntimeError("GTK application did not create its window")
            time.sleep(2)
            ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(output / "overview.png")
            print(f"GTK window {window} opened and rendered; screenshot: {output / 'overview.png'}", flush=True)
            pages = ("system", "apps", "shield") if settings_mode else ("toolbox", "cases", "shield", "verify", "customize", "apps", "system")
            for number, page in enumerate(pages, start=2):
                subprocess.run(["xdotool", "key", "--window", window, f"ctrl+{number}"], check=True)
                time.sleep(1)
                if process.poll() is not None:
                    raise RuntimeError(f"Application exited on {page}")
                if page == "cases":
                    subprocess.run(["xdotool", "mousemove", "--window", window, "550", "207", "click", "1", "type", "--clearmodifiers", "gui-smoke-case"], check=True)
                    subprocess.run(["xdotool", "mousemove", "--window", window, "1000", "207", "click", "1"], check=True)
                    time.sleep(0.4)
                    if not (Path.home() / "Livara/Cases/gui-smoke-case/case.json").is_file():
                        raise RuntimeError("The create-case button did not create its workspace")
                ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(output / f"{page}.png")
                print(f"Rendered {page}", flush=True)
                if page == "customize":
                    for preset, horizontal, appearance, accent in (("sunrise", 730, "light", "orange"), ("prism", 340, "dark", "purple")):
                        subprocess.run(["xdotool", "mousemove", "--window", window, str(horizontal), "205", "click", "1"], check=True)
                        time.sleep(1)
                        for key, value in (("appearance", appearance), ("accent", accent)):
                            actual = subprocess.run(["gsettings", "get", "org.livara.desktop", key], check=True, capture_output=True, text=True).stdout.strip().strip("'")
                            if actual != value:
                                raise RuntimeError(f"Preset button did not apply {key}: {actual}")
                        ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(output / f"customize-{preset}.png")
                        print(f"Preset button applied {preset}", flush=True)
                    for full, horizontal in ((False, 560), (True, 380)):
                        subprocess.run(["xdotool", "mousemove", "--window", window, str(horizontal), "270", "click", "1"], check=True)
                        time.sleep(.5)
                        checks = (("org.livara.desktop", "glass-enabled", str(full).lower()), ("org.livara.desktop", "blur-radius", "18" if full else "0"), ("org.gnome.desktop.interface", "enable-animations", str(full).lower()))
                        for schema, key, value in checks:
                            actual = subprocess.run(["gsettings", "get", schema, key], check=True, capture_output=True, text=True).stdout.strip()
                            if actual != value:
                                raise RuntimeError(f"Rendering button did not apply {key}: {actual}")
                        print("Applied full glass" if full else "Applied efficient rendering", flush=True)
                    ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(output / "customize-glass.png")
            if "Traceback" in (output / "application.log").read_text():
                raise RuntimeError("GTK callback raised an exception; inspect application.log")
        finally:
            process.terminate()
            process.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


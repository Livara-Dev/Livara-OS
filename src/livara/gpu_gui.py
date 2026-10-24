"""Livara Graphics: observed CPU and GPU status, not a support certificate."""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading

from . import gpu


def main() -> int:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, GLib, Gtk
    except (ImportError, ValueError):
        print("Livara Graphics needs GTK4/libadwaita and python3-gi", file=sys.stderr)
        return 2

    class Graphics(Adw.Application):
        def __init__(self):
            super().__init__(application_id="org.livara.Graphics")
            self.connect("activate", self.activate)
            self.report = None
            self.busy = False

        def activate(self, app):
            if self.get_active_window():
                self.get_active_window().present()
                return
            css = Gtk.CssProvider()
            css.load_from_data(b"window{background:#08050d;color:#f5efff;}headerbar{background:#100b18;} .card{background:linear-gradient(135deg,rgba(106,46,175,.20),rgba(33,20,49,.7));border:1px solid rgba(206,157,255,.20);border-radius:24px;padding:20px;} .eyebrow{color:#cd9fff;font-size:11px;letter-spacing:2px;} .graphics-title{font-size:29px;font-weight:800;} .muted{color:#b8abc9;} button.suggested-action{background:#a866ef;color:#0b0214;} textview,textview text{background:#08050d;color:#ded0ed;} ")
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.css = css
            self.window = Adw.ApplicationWindow(application=self, title="Livara Graphics", default_width=940, default_height=740)
            self.overlay = Adw.ToastOverlay()
            self.window.set_content(self.overlay)
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.overlay.set_child(root)
            header = Adw.HeaderBar()
            from .window_style import configure_native_headerbar
            self.window_controls = configure_native_headerbar(self.window, header)
            header.pack_start(Gtk.Image.new_from_icon_name("org.livara.Graphics"))
            header.set_title_widget(Adw.WindowTitle(title="Livara Graphics", subtitle="CPU, Intel graphics and NVIDIA observations"))
            root.append(header)
            scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
            root.append(scroll)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=24, margin_bottom=24, margin_start=28, margin_end=28)
            scroll.set_child(body)
            body.append(Gtk.Label(label="X86-64 · INTEL & NVIDIA GRAPHICS", xalign=0, css_classes=["eyebrow"]))
            body.append(Gtk.Label(label="Know what’s powering your pixels.", xalign=0, wrap=True, css_classes=["graphics-title"]))
            body.append(Gtk.Label(label="Livara uses a modern HWE kernel and Mesa graphics alongside NVIDIA’s open 580 kernel driver. This panel reports your actual CPU and graphics environment.", xalign=0, wrap=True, css_classes=["muted"]))
            self.summary = Gtk.Label(label="Reading graphics status…", xalign=0, wrap=True, selectable=True, css_classes=["card"])
            body.append(self.summary)
            self.facts = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            body.append(self.facts)
            actions = Gtk.Box(spacing=10)
            self.refresh_button = Gtk.Button(label="Refresh observations")
            self.refresh_button.connect("clicked", lambda b: self.refresh())
            actions.append(self.refresh_button)
            self.copy_button = Gtk.Button(label="Copy report", sensitive=False)
            self.copy_button.connect("clicked", self.copy_report)
            actions.append(self.copy_button)
            self.install_button = Gtk.Button(label="Repair NVIDIA driver…", sensitive=False, css_classes=["suggested-action"])
            self.install_button.connect("clicked", self.install)
            actions.append(self.install_button)
            body.append(actions)
            self.install_note = Gtk.Label(label="Driver changes require your confirmation, authentication, internet, and a reboot. Live sessions use the driver baked into the image; repair is available on a persistent installed system.", xalign=0, wrap=True, css_classes=["muted"])
            body.append(self.install_note)
            body.append(Gtk.Label(label="OBSERVATION DETAILS", xalign=0, css_classes=["eyebrow"]))
            self.details = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=12, bottom_margin=12, left_margin=12, right_margin=12)
            detail_scroll = Gtk.ScrolledWindow(min_content_height=220)
            detail_scroll.set_child(self.details)
            body.append(detail_scroll)
            body.append(Gtk.Label(label="RTX 50 Blackwell requires open kernel modules and driver 570+. A successful management query does not certify rendering, games, external monitors, suspend, or every laptop configuration. CUDA toolkits are separate downloads.", xalign=0, wrap=True, css_classes=["muted"]))
            self.window.present()
            self.refresh()

        def toast(self, text):
            self.overlay.add_toast(Adw.Toast.new(text))

        def refresh(self):
            if self.busy:
                return
            self.busy = True
            self.refresh_button.set_sensitive(False)
            self.install_button.set_sensitive(False)
            def work():
                try:
                    report = gpu.diagnostics()
                    GLib.idle_add(self.render, report)
                except Exception as error:
                    GLib.idle_add(self.failed, str(error))
            threading.Thread(target=work, daemon=True).start()

        def failed(self, text):
            self.busy = False
            self.refresh_button.set_sensitive(True)
            self.toast(text)
            return False

        def render(self, report):
            self.report = report
            self.busy = False
            self.refresh_button.set_sensitive(True)
            self.copy_button.set_sensitive(True)
            self.summary.set_text(report["assessment"])
            while self.facts.get_first_child():
                self.facts.remove(self.facts.get_first_child())
            models = ", ".join(item["model"] for item in report["gpus"]) or f"{len(report['devices'])} NVIDIA PCI display device(s)"
            intel = ", ".join(f"{device['slot']} · {device['driver']} · {device['device_id']}" for device in report["intel_devices"]) or "No Intel PCI display device observed"
            cpu = report["cpu"]
            topology = f"{cpu['logical_processors_observed']} logical processors observed"
            if cpu["physical_cores_observed"] is not None:
                topology += f" · {cpu['physical_cores_observed']} physical cores observed"
            frequency_drivers = ", ".join(sorted({policy["driver"] for policy in cpu["frequency_policies"]})) or "Unavailable"
            facts = (("CPU", cpu["model"]), ("CPU topology", topology),
                     ("CPU frequency control", f"{frequency_drivers} · Intel P-state: {cpu['intel_pstate']}"),
                     ("Power profile", report["power_profile"]), ("Intel graphics", intel),
                     ("NVIDIA graphics", models), ("Kernel", report["kernel"]),
                     ("Desktop session", report["session"]), ("Secure Boot", report["secure_boot"]),
                     ("Hybrid graphics mode", report["prime_mode"]))
            for title, value in facts:
                row = Adw.ActionRow(title=title, subtitle=value)
                row.set_use_markup(False)
                row.set_subtitle_lines(3)
                self.facts.append(row)
            self.details.get_buffer().set_text(gpu.report_json(report))
            hardware = bool(report["devices"] or report["gpus"])
            self.install_button.set_sensitive(not report["live_session"] and hardware and bool(shutil.which("livara-terminal") or shutil.which("gnome-terminal")))
            if report["live_session"]:
                self.install_note.set_text("This is a temporary live session. Its driver is built into the image; installing another driver here would disappear at reboot. Build a refreshed image to change it.")
            return False

        def copy_report(self, button):
            if self.report:
                Gdk.Display.get_default().get_clipboard().set(gpu.report_json(self.report))
                self.toast("Graphics report copied")

        def install(self, button):
            if not self.report or self.report["live_session"] or not (self.report["devices"] or self.report["gpus"]):
                return
            dialog = Adw.MessageDialog(transient_for=self.window, modal=True, heading="Install the Livara RTX driver stack?", body="A terminal will refresh Ubuntu’s package lists and ask you to authenticate and confirm installation of:\n\n" + "\n".join(gpu.DRIVER_PACKAGES) + "\n\nSave your work first. Reboot after installation. This changes system packages; it does not flash your GPU firmware.")
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("install", "Open installer")
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
            def response(d, answer):
                if answer == "install":
                    command = gpu.installation_command()
                    command[0] = shutil.which("livara-terminal") or shutil.which("gnome-terminal")
                    if command[0]:
                        try:
                            subprocess.Popen(command)
                        except OSError as error:
                            self.toast(str(error))
                d.destroy()
            dialog.connect("response", response)
            dialog.present()

    return Graphics().run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())

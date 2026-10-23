"""Livara Task Manager: native resource graphs and selected-process controls."""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from . import desktop, monitor, window_style


def main() -> int:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_foreign("cairo")
        import cairo
        from gi.repository import Adw, Gdk, GLib, Gtk, Pango
    except (ImportError, ValueError):
        print("Livara Task Manager needs GTK 4 and Cairo: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1", file=sys.stderr)
        return 2

    class Graph(Gtk.DrawingArea):
        def __init__(self, color, ceiling=100.0):
            super().__init__(height_request=82, hexpand=True)
            self.color = color
            self.ceiling = ceiling
            self.values = deque(maxlen=90)
            self.previous = []
            self.progress = 1.0
            self.tick_id = None
            self.set_draw_func(self.draw)
            self.set_tooltip_text("History of the last 90 observations")

        def push(self, value, animated):
            if self.tick_id is not None:
                self.remove_tick_callback(self.tick_id)
                self.tick_id = None
            self.previous = list(self.values)
            self.values.append(max(0.0, value))
            self.progress = 0.0 if animated and self.get_mapped() else 1.0
            self.started = time.monotonic()
            if self.progress < 1:
                self.tick_id = self.add_tick_callback(self.tick)
            self.queue_draw()

        def tick(self, widget, clock):
            self.progress = min(1.0, (time.monotonic() - self.started) / 0.24)
            self.queue_draw()
            if self.progress >= 1:
                self.tick_id = None
                return False
            return True

        def draw(self, area, context, width, height):
            context.set_source_rgba(0.65, 0.71, 0.87, 0.12)
            context.set_line_width(1)
            for part in (0.25, 0.5, 0.75):
                context.move_to(0, height * part)
                context.line_to(width, height * part)
            context.stroke()
            target = list(self.values)
            if not target:
                return
            prior = ([self.previous[0]] * max(0, len(target) - len(self.previous)) + self.previous)[-len(target):] if self.previous else [0.0] * len(target)
            ease = 1 - (1 - self.progress) ** 3
            values = [old + (new - old) * ease for old, new in zip(prior, target)]
            ceiling = self.ceiling or max(1024.0, max(values) * 1.1)
            points = [(index * width / max(1, len(values) - 1), height - min(1.0, value / ceiling) * (height - 5) - 2) for index, value in enumerate(values)]
            if len(points) == 1:
                points.insert(0, (0, points[0][1]))
                points[-1] = (width, points[-1][1])
            context.move_to(0, height)
            for x, y in points:
                context.line_to(x, y)
            context.line_to(width, height)
            context.close_path()
            gradient = cairo.LinearGradient(0, 0, 0, height)
            gradient.add_color_stop_rgba(0, *self.color, 0.34)
            gradient.add_color_stop_rgba(1, *self.color, 0.02)
            context.set_source(gradient)
            context.fill()
            context.set_source_rgba(*self.color, 0.95)
            context.set_line_width(2)
            context.move_to(*points[0])
            for point in points[1:]:
                context.line_to(*point)
            context.stroke()

    class TaskManager(Adw.Application):
        def __init__(self):
            super().__init__(application_id="org.livara.Monitor")
            self.connect("activate", self.activate)

        def activate(self, app):
            if self.get_active_window():
                self.get_active_window().present()
                return
            self.sampler = monitor.Sampler()
            self.snapshot = None
            self.selected = None
            self.busy = self.closed = self.paused = False
            self.timer = None
            self.rows = {}
            self.interval = 2
            self.animated = desktop.read_option("animations") is not False
            self.css = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.apply_appearance()
            self.preferences = desktop.settings_for("org.livara.desktop")
            if self.preferences:
                self.preferences.connect("changed", lambda *args: self.apply_appearance())
            self.interface = desktop.settings_for("org.gnome.desktop.interface")
            if self.interface:
                self.interface.connect("changed::enable-animations", self.motion_changed)
            self.window = Adw.ApplicationWindow(application=self, title="Livara Task Manager", default_width=1060, default_height=760)
            self.window.set_size_request(800, 600)
            self.window.connect("close-request", self.close)
            self.overlay = Adw.ToastOverlay()
            self.window.set_content(self.overlay)
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.overlay.set_child(body)
            header = Adw.HeaderBar()
            self.window_controls = window_style.configure_native_headerbar(self.window, header)
            header.pack_start(Gtk.Image.new_from_icon_name("org.livara.Monitor"))
            title = Adw.WindowTitle(title="Livara Task Manager", subtitle="A living view of your system")
            header.set_title_widget(title)
            export = Gtk.Button(icon_name="document-save-symbolic", tooltip_text="Save a JSON snapshot")
            export.connect("clicked", self.save_report)
            header.pack_end(export)
            body.append(header)
            controls = Gtk.Box(spacing=10, margin_top=8, margin_bottom=12, margin_start=24, margin_end=24)
            self.status = Gtk.Label(label="Collecting the first observation…", xalign=0, hexpand=True, css_classes=["muted"])
            controls.append(self.status)
            intervals = Gtk.DropDown.new_from_strings(["Every second", "Every 2 seconds", "Every 5 seconds"])
            intervals.set_selected(1)
            intervals.connect("notify::selected", self.interval_changed)
            controls.append(intervals)
            self.pause = Gtk.ToggleButton(label="Pause updates")
            self.pause.connect("toggled", self.pause_changed)
            controls.append(self.pause)
            refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh now")
            refresh.connect("clicked", lambda b: self.request(force=True))
            controls.append(refresh)
            body.append(controls)
            self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=220 if self.animated else 0, vexpand=True)
            switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER, margin_bottom=12)
            body.append(switcher)
            self.stack.add_titled(self.overview_page(), "overview", "Overview")
            self.stack.add_titled(self.process_page(), "processes", "Processes")
            body.append(self.stack)
            self.window.present()
            self.restart_timer()
            self.request()

        def apply_appearance(self):
            dark = desktop.read_option("appearance") != "light"
            accent = desktop.ACCENTS.get(desktop.read_option("accent"), desktop.ACCENTS["purple"])[1]
            self.accent = tuple(int(accent[index:index + 2], 16) / 255 for index in (1, 3, 5))
            foreground, muted = ("#f0f3ff", "#aebbd4") if dark else ("#182740", "#52647c")
            background = "rgba(15,22,42,.96)" if dark else "rgba(234,241,255,.96)"
            panel = "rgba(44,54,83,.68)" if dark else "rgba(255,255,255,.78)"
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
            self.css.load_from_data(f"""
                window {{ background: {background}; color: {foreground}; }}
                headerbar {{ background: transparent; box-shadow: none; }}
                .muted {{ color: {muted}; font-size: 12px; }}
                .metric-card {{ background: {panel}; border: 1px solid alpha({foreground},.16); border-radius: 25px; padding: 20px; }}
                .metric-value {{ font-size: 30px; font-weight: 800; color: {foreground}; }}
                .metric-title {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {accent}; }}
                .boxed-list {{ background: {panel}; border: 1px solid alpha({foreground},.13); border-radius: 20px; }}
                .boxed-list > row {{ background: transparent; }}
                button {{ border-radius: 18px; }}
                searchentry {{ border-radius: 18px; }}
                .process-value {{ font-family: monospace; font-size: 12px; }}
            """.encode())
            if hasattr(self, "cpu_graph"):
                self.cpu_graph.color = self.accent
                self.cpu_graph.queue_draw()

        def motion_changed(self, settings, key):
            self.animated = settings.get_boolean(key)
            if hasattr(self, "stack"):
                self.stack.set_transition_duration(220 if self.animated else 0)

        def close(self, window):
            self.closed = True
            if self.timer is not None:
                GLib.source_remove(self.timer)
                self.timer = None
            return False

        def toast(self, text):
            if not self.closed:
                self.overlay.add_toast(Adw.Toast.new(str(text)))
            return False

        def scroll_page(self):
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=8, margin_bottom=24, margin_start=24, margin_end=24)
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.set_child(content)
            return scroll, content

        def graph_card(self, name, color, ceiling=100):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, css_classes=["metric-card"])
            card.append(Gtk.Label(label=name, xalign=0, css_classes=["metric-title"]))
            value = Gtk.Label(label="—", xalign=0, css_classes=["metric-value"])
            card.append(value)
            graph = Graph(color, ceiling)
            card.append(graph)
            return card, value, graph

        def overview_page(self):
            scroll, box = self.scroll_page()
            grid = Gtk.Grid(column_spacing=16, row_spacing=16, column_homogeneous=True)
            cpu, self.cpu_label, self.cpu_graph = self.graph_card("PROCESSOR", self.accent)
            ram, self.memory_label, self.memory_graph = self.graph_card("MEMORY", (0.47, 0.73, 1.0))
            rx, self.receive_label, self.receive_graph = self.graph_card("NETWORK · RECEIVE", (0.55, 0.89, 0.73), None)
            tx, self.send_label, self.send_graph = self.graph_card("NETWORK · SEND", (1.0, 0.72, 0.50), None)
            for column, row, card in ((0, 0, cpu), (1, 0, ram), (0, 1, rx), (1, 1, tx)):
                grid.attach(card, column, row, 1, 1)
            box.append(grid)
            self.summary = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            self.summary_rows = {}
            for key, title in (("processor", "Processor capacity"), ("memory", "Memory available"), ("swap", "Swap"), ("storage", "Home filesystem"), ("uptime", "System uptime"), ("load", "Load average"), ("network", "Network interfaces")):
                row = Adw.ActionRow(title=title, subtitle="Waiting for an observation")
                row.set_subtitle_lines(2)
                self.summary.append(row)
                self.summary_rows[key] = row
            box.append(self.summary)
            box.append(Gtk.Label(label="Observations come from the running system. Network rates exclude loopback traffic; charts retain 90 samples.", wrap=True, xalign=0, css_classes=["muted"]))
            return scroll

        def process_page(self):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_start=24, margin_end=24, margin_bottom=20)
            tools = Gtk.Box(spacing=10)
            self.search = Gtk.SearchEntry(placeholder_text="Search name, command, or PID…", hexpand=True)
            self.search.connect("search-changed", lambda e: self.refresh_processes())
            tools.append(self.search)
            self.mine = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
            self.mine.connect("notify::active", lambda *args: self.refresh_processes())
            tools.append(Gtk.Label(label="My processes"))
            tools.append(self.mine)
            self.sort = Gtk.DropDown.new_from_strings(["Highest CPU", "Most memory", "Name", "PID"])
            self.sort.connect("notify::selected", lambda *args: self.refresh_processes())
            tools.append(self.sort)
            page.append(tools)
            self.process_count = Gtk.Label(label="Waiting for processes…", xalign=0, css_classes=["muted"])
            page.append(self.process_count)
            self.process_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["boxed-list"])
            self.process_list.connect("row-selected", self.process_selected)
            scrolling = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=160)
            scrolling.set_child(self.process_list)
            page.append(scrolling)
            self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["metric-card"])
            self.detail_title = Gtk.Label(label="Select a process", xalign=0, css_classes=["heading"])
            self.details.append(self.detail_title)
            self.detail_description = Gtk.Label(label="View its command, owner, thread count, and current state.", xalign=0, wrap=True, selectable=True, css_classes=["muted"])
            self.detail_description.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            self.details.append(self.detail_description)
            actions = Gtk.Box(spacing=10)
            self.action_buttons = {}
            for action, title in (("pause", "Pause process"), ("resume", "Resume"), ("terminate", "End process")):
                button = Gtk.Button(label=title, sensitive=False)
                button.connect("clicked", lambda b, a=action: self.confirm_action(a))
                actions.append(button)
                self.action_buttons[action] = button
            self.details.append(actions)
            page.append(self.details)
            page.append(Gtk.Label(label="CPU per process uses 100% per logical processor. Process actions require selection and confirmation; Livara never requests elevated privileges.", wrap=True, xalign=0, css_classes=["muted"]))
            return page

        def interval_changed(self, dropdown, spec):
            self.interval = (1, 2, 5)[dropdown.get_selected()]
            self.restart_timer()

        def restart_timer(self):
            if self.timer is not None:
                GLib.source_remove(self.timer)
            self.timer = GLib.timeout_add_seconds(self.interval, self.on_timer)

        def on_timer(self):
            if self.closed:
                return False
            self.request()
            return True

        def pause_changed(self, button):
            self.paused = button.get_active()
            button.set_label("Resume updates" if self.paused else "Pause updates")
            if self.paused:
                self.status.set_text("Updates paused · Refresh now takes one observation")
            else:
                self.request()

        def request(self, force=False):
            if self.busy or self.closed or self.paused and not force:
                return
            self.busy = True
            def work():
                try:
                    value, error = self.sampler.sample(), None
                except (OSError, ValueError) as exception:
                    value, error = None, str(exception)
                GLib.idle_add(self.receive, value, error)
            threading.Thread(target=work, daemon=True).start()

        def receive(self, sample, error):
            self.busy = False
            if self.closed:
                return False
            if error:
                self.status.set_text("Observation unavailable: " + error)
                return False
            self.snapshot = sample
            self.status.set_text(("Paused · " if self.paused else "Live · ") + time.strftime("%H:%M:%S"))
            self.cpu_label.set_text(f"{sample.cpu:.1f}%")
            self.memory_label.set_text(monitor.format_bytes(sample.memory_used))
            self.receive_label.set_text(monitor.format_bytes(sample.network_receive) + "/s")
            self.send_label.set_text(monitor.format_bytes(sample.network_send) + "/s")
            for graph, value in ((self.cpu_graph, sample.cpu), (self.memory_graph, sample.memory_used / max(1, sample.memory_total) * 100), (self.receive_graph, sample.network_receive), (self.send_graph, sample.network_send)):
                graph.push(value, self.animated)
            summaries = {
                "processor": f"{sample.logical_cpus} logical processors · {len(sample.processes)} observed processes",
                "memory": f"{monitor.format_bytes(sample.memory_available)} available of {monitor.format_bytes(sample.memory_total)}",
                "swap": f"{monitor.format_bytes(sample.swap_used)} used of {monitor.format_bytes(sample.swap_total)}" if sample.swap_total else "No swap configured",
                "storage": f"{monitor.format_bytes(sample.disk_free)} free of {monitor.format_bytes(sample.disk_total)} · {Path.home()}",
                "uptime": monitor.format_uptime(sample.uptime),
                "load": " / ".join(f"{value:.2f}" for value in sample.load) + " · 1, 5, and 15 minutes",
                "network": " · ".join(f"{name}: ↓ {monitor.format_bytes(values[0])}, ↑ {monitor.format_bytes(values[1])}" for name, values in sample.network_totals.items()) or "No non-loopback interfaces observed",
            }
            for key, text in summaries.items():
                self.summary_rows[key].set_subtitle(text)
            self.refresh_processes()
            return False

        def refresh_processes(self):
            if not self.snapshot or not hasattr(self, "process_list"):
                return
            query = self.search.get_text().casefold()
            processes = [process for process in self.snapshot.processes if (not self.mine.get_active() or process.uid == os.geteuid()) and query in f"{process.pid} {process.name} {process.command}".casefold()]
            key = (lambda p: (-p.cpu, p.pid), lambda p: (-p.rss, p.pid), lambda p: (p.name.casefold(), p.pid), lambda p: p.pid)[self.sort.get_selected()]
            processes.sort(key=key)
            shown = processes[:250]
            self.process_count.set_text(f"{len(processes)} matching processes · showing {len(shown)} · select a row for details")
            wanted = {process.identity for process in shown}
            for identity in list(self.rows):
                if identity not in wanted:
                    self.process_list.remove(self.rows.pop(identity))
            for process in shown:
                row = self.rows.get(process.identity)
                if row is None:
                    row = Adw.ActionRow(title=process.name)
                    row.set_selectable(True)
                    row.set_activatable(True)
                    row.cpu_label = Gtk.Label(width_chars=11, css_classes=["process-value"])
                    row.ram_label = Gtk.Label(width_chars=13, css_classes=["process-value"])
                    row.add_suffix(row.cpu_label)
                    row.add_suffix(row.ram_label)
                    row.process = process
                    self.rows[process.identity] = row
                    self.process_list.append(row)
                row.process = process
                row.set_title(process.name)
                row.set_subtitle(f"PID {process.pid} · User {process.uid} · {process.state} · {process.threads} threads")
                row.cpu_label.set_text(f"{process.cpu:.1f}% CPU")
                row.ram_label.set_text(monitor.format_bytes(process.rss))
            ranks = {process.identity: index for index, process in enumerate(shown)}
            self.process_list.set_sort_func(lambda a, b: ranks.get(a.process.identity, 999) - ranks.get(b.process.identity, 999))
            self.process_list.invalidate_sort()
            if self.selected:
                current = next((process for process in self.snapshot.processes if process.identity == self.selected.identity), None)
                if current:
                    self.selected = current
                    self.show_details()
                else:
                    self.detail_title.set_text(f"{self.selected.name} has exited")
                    for button in self.action_buttons.values():
                        button.set_sensitive(False)

        def process_selected(self, listing, row):
            if row is not None:
                self.selected = row.process
                self.show_details()

        def show_details(self):
            process = self.selected
            self.detail_title.set_text(f"{process.name} · PID {process.pid}")
            states = {"R": "Running", "S": "Sleeping", "D": "Waiting for I/O", "T": "Paused", "t": "Tracing stop", "Z": "Zombie", "I": "Idle"}
            self.detail_description.set_text(f"{states.get(process.state, process.state)} · User {process.uid} · Parent {process.parent} · {process.threads} threads\n{process.command[:2048]}")
            controllable = process.uid == os.geteuid() and process.pid not in (1, os.getpid())
            self.action_buttons["pause"].set_sensitive(controllable and process.state not in ("T", "t", "Z"))
            self.action_buttons["resume"].set_sensitive(controllable and process.state in ("T", "t"))
            self.action_buttons["terminate"].set_sensitive(controllable and process.state != "Z")

        def confirm_action(self, action):
            selected = self.selected
            if selected is None:
                return
            title = {"pause": "Pause", "resume": "Resume", "terminate": "End"}[action]
            description = {"pause": "The selected process will stop running until resumed.", "resume": "The selected process will continue running.", "terminate": "The selected process will receive a request to exit. Unsaved work in that application may be lost."}[action]
            dialog = Adw.MessageDialog.new(self.window, f"{title} {selected.name}?", f"PID {selected.pid} · User {selected.uid}\n\n{description}")
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("apply", f"{title} process")
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.set_response_appearance("apply", Adw.ResponseAppearance.DESTRUCTIVE if action != "resume" else Adw.ResponseAppearance.SUGGESTED)
            def response(widget, answer):
                if answer != "apply":
                    return
                def work():
                    try:
                        monitor.control_process(selected, action)
                        message = f"{title} request sent to {selected.name}"
                    except (OSError, ValueError, RuntimeError) as error:
                        message = str(error)
                    GLib.idle_add(self.toast, message)
                    GLib.idle_add(lambda: self.request(force=True))
                threading.Thread(target=work, daemon=True).start()
            dialog.connect("response", response)
            dialog.present()

        def save_report(self, button):
            if self.snapshot is None:
                self.toast("Wait for the first observation")
                return
            sample = self.snapshot
            chooser = Gtk.FileChooserNative(title="Save a system snapshot", transient_for=self.window, action=Gtk.FileChooserAction.SAVE, accept_label="Save", cancel_label="Cancel")
            chooser.set_current_name("livara-system-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
            def response(dialog, answer):
                if answer == Gtk.ResponseType.ACCEPT:
                    filename = dialog.get_file().get_path()
                    if filename:
                        try:
                            monitor.export_snapshot(sample, Path(filename))
                            self.toast("Private system snapshot saved")
                        except (OSError, ValueError) as error:
                            self.toast(error)
                dialog.destroy()
            chooser.connect("response", response)
            chooser.show()

    return TaskManager().run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())

"""Native GTK 4 / libadwaita Control Center, with real local data."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

from . import __version__, core, desktop, window_style


def main(mode="center") -> int:
    if mode not in ("center", "settings"):
        raise ValueError("Unknown Livara window mode")
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, Gio, GLib, Gtk
    except (ImportError, ValueError):
        print("Livara Center requires GTK 4: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1", file=sys.stderr)
        return 2

    class Center(Adw.Application):
        def __init__(self):
            super().__init__(application_id="org.livara.Settings" if mode == "settings" else "org.livara.Center", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.add_main_option("page", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING, "Open a Livara page", "PAGE")
            self.connect("command-line", self.command_line)
            self.connect("activate", self.activate)

        def command_line(self, app, request):
            self.activate(app)
            option = request.get_options_dict().lookup_value("page", None)
            if option:
                page = option.get_string()
                if page not in self.navigation: return 2
                self.stack.set_visible_child_name(page)
            return 0

        def activate(self, application):
            if self.get_active_window():
                self.get_active_window().present()
                return
            self.palette_css = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.palette_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.desktop_settings = desktop.settings_for("org.livara.desktop")
            if self.desktop_settings:
                self.desktop_settings.connect("changed", self.desktop_preferences_changed)
            self.refresh_appearance()
            self.window_style_handle = window_style.install_live_style()
            self.title = "Livara Settings" if mode == "settings" else "Livara Control Center"
            self.window = Adw.ApplicationWindow(application=self, title=self.title, default_width=1100, default_height=720)
            self.window.set_size_request(740, 540) if mode == "settings" else self.window.set_size_request(860, 640)
            self.toast_overlay = Adw.ToastOverlay()
            self.window.set_content(self.toast_overlay)
            shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.toast_overlay.set_child(shell)
            header = Adw.HeaderBar()
            self.headerbar_controls = window_style.configure_native_headerbar(self.window, header)
            fullscreen = Gtk.Button(icon_name="view-fullscreen-symbolic", tooltip_text="Enter or leave full screen (F11)")
            fullscreen.connect("clicked", self.toggle_fullscreen)
            header.pack_end(fullscreen)
            header.set_title_widget(Gtk.Label(label=self.title, css_classes=["small", "muted"]))
            shell.append(header)
            body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
            shell.append(body)
            sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, width_request=220, css_classes=["sidebar"])
            self.margins(sidebar, 22)
            body.append(sidebar)
            brand = Gtk.Box(spacing=8)
            brand_icon = Gtk.Image.new_from_icon_name("org.livara.Center")
            brand_icon.set_pixel_size(36)
            brand.append(brand_icon)
            brand.append(self.label("LIVARA", "brand"))
            sidebar.append(brand)
            sidebar.append(self.label("OPERATING SYSTEM", "brand-sub"))
            sidebar.append(Gtk.Box(height_request=16))
            nav_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            nav_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            nav_scroll.set_child(nav_box)
            sidebar.append(nav_scroll)
            self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=240, hexpand=True, vexpand=True)
            self.stack.set_hhomogeneous(False)
            self.stack.set_vhomogeneous(False)
            interface = desktop.settings_for("org.gnome.desktop.interface")
            if interface:
                def motion(*args):
                    self.stack.set_transition_duration(240 if interface.get_boolean("enable-animations") else 0)
                interface.connect("changed::enable-animations", motion)
                motion()
            body.append(self.stack)
            self.navigation = {}
            group = None
            pages = (
                ("customize", "Personalize", "customize", self.customize_page),
                ("icons", "App icons", "customize", self.app_icons_page),
                ("essentials", "Feature hub", "grid", self.essentials_page),
                ("system", "Device & connectivity", "grid", self.system_page),
                ("apps", "Livara apps", "grid", self.apps_page),
                ("shield", "Security overview", "shield", self.shield_page),
            ) if mode == "settings" else (
                ("home", "Overview", "grid", self.home_page),
                ("toolbox", "Security toolbox", "terminal", self.toolbox_page),
                ("cases", "Case workspaces", "folder", self.cases_page),
                ("shield", "Livara Shield", "shield", self.shield_page),
                ("verify", "Livara Verify", "verify", self.verify_page),
                ("customize", "Make it yours", "customize", self.customize_page),
                ("icons", "App icons", "customize", self.app_icons_page),
                ("essentials", "Feature hub", "grid", self.essentials_page),
                ("apps", "Livara apps", "grid", self.apps_page),
                ("system", "Device & connectivity", "grid", self.system_page),
            )
            for name, title, icon, make_page in pages:
                button = Gtk.ToggleButton(css_classes=["nav"])
                row = Gtk.Box(spacing=12)
                nav_icon = Gtk.Image.new_from_file(str(core.DATA_DIR / "icons" / f"{icon}.svg"))
                nav_icon.set_pixel_size(18)
                row.append(nav_icon)
                row.append(Gtk.Label(label=title, xalign=0))
                button.set_child(row)
                if group:
                    button.set_group(group)
                else:
                    group = button
                button.connect("toggled", lambda b, key=name: self.stack.set_visible_child_name(key) if b.get_active() else None)
                self.navigation[name] = button
                nav_box.append(button)
                self.stack.add_named(make_page(), name)
                action = Gio.SimpleAction.new("page-" + name, None)
                action.connect("activate", lambda a, p, key=name: self.stack.set_visible_child_name(key))
                self.add_action(action)
                self.set_accels_for_action("app.page-" + name, ["<Primary>" + str(len(self.navigation))])
            group.set_active(True)
            self.stack.connect("notify::visible-child-name", lambda stack, spec: self.navigation[stack.get_visible_child_name()].set_active(True))
            sidebar.append(self.label("YOUR DESKTOP.\nYOUR WORKBENCH.", "footer"))
            sidebar.append(self.label(f"PREVIEW  {__version__}  /  AMD64", "footer"))
            self.window.present()

        def toggle_fullscreen(self, button=None):
            if self.window.is_fullscreen():
                self.window.unfullscreen()
            else:
                self.window.fullscreen()

        def desktop_preferences_changed(self, *args):
            self.refresh_appearance()
            self.sync_preference_widgets()

        def refresh_appearance(self):
            dark = desktop.read_option("appearance") != "light"
            glass = desktop.read_option("glass-enabled") is not False
            accent = desktop.ACCENTS.get(desktop.read_option("accent"), desktop.ACCENTS["purple"])[1]
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
            text = "#f0f5ff" if dark else "#182b49"
            muted = "#acbbd3" if dark else "#526782"
            panel = "rgba(28,20,43,.72)" if dark else "rgba(242,247,255,.78)"
            base = "rgba(7,4,14,.96)" if dark else "rgba(232,241,255,.96)"
            if not glass:
                panel = "#1c2844" if dark else "#f2f7ff"
                base = "#0f172b" if dark else "#e8f1ff"
            css = f"""
                window {{ background: {base}; color: {text}; }}
                headerbar {{ background: transparent; box-shadow: none; }}
                .sidebar {{ background: {panel}; border-right: 1px solid alpha({text},.12); }}
                .brand {{ font-size: 26px; font-weight: 800; letter-spacing: 3px; }}
                .brand-sub {{ color: {muted}; font-size: 10px; letter-spacing: 2px; }}
                .nav {{ padding: 11px 15px; border-radius: 20px; background: transparent; box-shadow: none; border: 1px solid transparent; }}
                .nav:checked {{ background: alpha({accent},.18); color: {accent}; border-color: alpha({accent},.25); }}
                .nav:hover {{ background: alpha({accent},.12); }}
                .eyebrow {{ color: {accent}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
                .hero-title {{ font-size: 38px; font-weight: 800; letter-spacing: -1px; }}
                .page-title {{ font-size: 29px; font-weight: 800; }}
                .muted {{ color: {muted}; }}
                .small {{ font-size: 12px; }}
                .card {{ background: {panel}; background-image: linear-gradient(135deg, alpha(white,.10), alpha(white,.01) 45%, alpha({accent},.07)); border: 1px solid alpha({text},.20); border-radius: 25px; padding: 20px; box-shadow: 0 6px 22px rgba(0,0,0,.10); }}
                .hero {{ background: linear-gradient(125deg, alpha({accent},.28), alpha({accent},.06)); border: 1px solid alpha({text},.28); border-radius: 30px; padding: 28px; box-shadow: 0 10px 32px rgba(0,0,0,.12); }}
                .metric {{ font-size: 26px; font-weight: 700; }}
                .card-title {{ font-size: 17px; font-weight: 700; }}
                button.primary {{ background: {accent}; color: #11223e; font-weight: 700; border: 1px solid rgba(255,255,255,.25); border-radius: 24px; padding: 11px 18px; }}
                button.secondary {{ background: alpha({accent},.13); background-image: linear-gradient(to bottom, alpha(white,.09), transparent); color: {text}; border: 1px solid alpha({text},.16); border-radius: 22px; padding: 10px 15px; }}
                .pass {{ color: #8cdab7; }} .review {{ color: #e4b95f; }} .unknown {{ color: {muted}; }}
                entry, searchentry {{ border-radius: 18px; padding: 8px; }}
                .boxed-list {{ background: {panel}; border: 1px solid alpha({text},.14); border-radius: 22px; }}
                .boxed-list > row {{ background: transparent; }}
                .footer {{ color: {muted}; font-size: 11px; }}
            """
            self.palette_css.load_from_data(css.encode())

        def margins(self, widget, amount):
            for side in ("top", "bottom", "start", "end"):
                getattr(widget, "set_margin_" + side)(amount)

        def label(self, text, *classes):
            return Gtk.Label(label=text, xalign=0, wrap=True, css_classes=list(classes))

        def action_row(self, title, subtitle=""):
            row = Adw.ActionRow()
            row.set_use_markup(False)
            row.set_title(title)
            row.set_subtitle(subtitle)
            return row

        def button(self, text, callback, primary=False):
            button = Gtk.Button(label=text, css_classes=["primary" if primary else "secondary"], halign=Gtk.Align.START)
            button.connect("clicked", callback)
            return button

        def page(self, eyebrow, title, subtitle):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
            self.margins(box, 32)
            heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            heading.append(self.label(eyebrow, "eyebrow"))
            heading.append(self.label(title, "page-title"))
            heading.append(self.label(subtitle, "muted"))
            box.append(heading)
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.set_child(box)
            scroll.set_propagate_natural_height(False)
            return scroll, box

        def card(self, title, text, button=None):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True, css_classes=["card"])
            box.append(self.label(title, "card-title"))
            box.append(self.label(text, "muted", "small"))
            if button:
                box.append(button)
            return box

        def toast(self, message):
            self.toast_overlay.add_toast(Adw.Toast.new(str(message)))

        def terminal(self, command):
            terminal = shutil.which("livara-terminal") or shutil.which("gnome-terminal")
            if not terminal:
                self.toast("Install gnome-terminal to open this tool")
                return
            # The fixed wrapper only keeps the terminal open; user arguments use "$@".
            subprocess.Popen([terminal, "--", "bash", "-c", '"$@"; result=$?; printf "\\nExit status: %s\\nPress Enter to close." "$result"; read -r reply', "livara", *command])

        def open_folder(self, path):
            try:
                path.mkdir(parents=True, exist_ok=True)
                Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)
            except Exception as error:
                self.toast(error)

        def home_page(self):
            scroll, box = self.page("WELCOME TO LIVARA", "Make room for what’s possible.", "Your glass desktop, creative tools, and security workbench.")
            hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=13, css_classes=["hero"])
            hero.append(self.label("LIVARA GLASS  /  YOUR NEXT PERSPECTIVE", "eyebrow"))
            hero.append(self.label("Fluid by design.\nYours by choice.", "hero-title"))
            hero.append(self.label("Built for your ideas. Made to feel like Livara.\nYour tools and security workbench, one touch away.", "muted"))
            hero_actions = Gtk.Box(spacing=10)
            hero_actions.append(self.button("Make it yours  →", lambda b: self.stack.set_visible_child_name("customize"), True))
            hero_actions.append(self.button("Explore tools", lambda b: self.stack.set_visible_child_name("toolbox")))
            hero.append(hero_actions)
            box.append(hero)
            status = core.system_status()
            metrics = Gtk.Box(spacing=12, homogeneous=True)
            for value, title in ((f"{status['memory_available'] / 2**30:.1f} GB", "MEMORY AVAILABLE"), (f"{status['disk_free'] / 2**30:.1f} GB", "STORAGE FREE"), (str(status["native_tools_installed"]), "NATIVE SECURITY TOOLS")):
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["card"])
                card.append(self.label(title, "eyebrow"))
                card.append(self.label(value, "metric"))
                metrics.append(card)
            box.append(metrics)
            box.append(self.label("A FEW GOOD PLACES TO START", "eyebrow"))
            row = Gtk.Box(spacing=12, homogeneous=True)
            row.append(self.card("Your next investigation", "Keep evidence, notes, and reports together.", self.button("Create a case  ↗", lambda b: self.stack.set_visible_child_name("cases"))))
            row.append(self.card("Know your system", "Read local security settings with Livara Shield.", self.button("Open Shield  ↗", lambda b: self.stack.set_visible_child_name("shield"))))
            box.append(row)
            box.append(self.label(f"{status['distribution']}  ·  {status['architecture']}  ·  Linux {status['kernel']}", "footer"))
            return scroll

        def toolbox_page(self):
            scroll, box = self.page("THE WORKBENCH", "Tools for the curious.", "Native desktop tools and isolated Kali profiles, together in one place.")
            row = Gtk.Box(spacing=10)
            row.append(self.button("Prepare Kali core", lambda b: self.terminal(["livara", "toolbox", "setup"]), True))
            row.append(self.button("Open Kali shell", lambda b: self.terminal(["livara", "toolbox", "run", "--", "bash"])))
            box.append(row)
            box.append(self.label("Core tools work offline after preparation. Download specialized profiles or the complete Kali catalog to expand your workbench.", "small", "muted"))
            complete = self.card("The complete Kali catalog", "Download Kali’s kali-linux-everything collection. Requires internet and a persistent disk with substantial free space; it is not bundled in this ISO.")
            actions = Gtk.Box(spacing=10)
            actions.append(self.button("Choose storage…", self.choose_toolbox_storage))
            actions.append(self.button("Download all Kali tools", self.prepare_full_toolbox, True))
            complete.append(actions)
            box.append(complete)
            search = Gtk.SearchEntry(placeholder_text="Search tools or categories…")
            box.append(search)
            listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            rows = []
            for tool in core.TOOLS:
                if tool["command"] is None:
                    continue
                row = self.action_row(tool["name"], subtitle=f"{tool['category']} · {tool['description']}")
                row.set_subtitle_lines(2)
                if "profile" in tool:
                    button = self.button("Set up · " + tool["profile"], lambda b, p=tool["profile"]: self.terminal(["livara", "toolbox", "setup", "--profile", p]))
                    button.set_tooltip_text("Build this profile; then run its tools with livara toolbox run --profile " + tool["profile"])
                elif shutil.which(tool["command"]):
                    if tool["command"] == "wireshark":
                        button = self.button("Open", lambda b: subprocess.Popen(["wireshark"]))
                    else:
                        button = self.button("Open help", lambda b, t=tool: self.terminal([t["command"], t["help"]]))
                else:
                    button = Gtk.Label(label="Not installed", css_classes=["muted", "small"])
                button.set_valign(Gtk.Align.CENTER)
                row.add_suffix(button)
                listbox.append(row)
                rows.append((row, " ".join(str(v) for v in tool.values()).lower()))
            search.connect("search-changed", lambda entry: [row.set_visible(entry.get_text().lower() in text) for row, text in rows])
            box.append(listbox)
            box.append(self.label("Use network and web testing tools on systems you own or have permission to assess.", "footer"))
            return scroll

        def prepare_full_toolbox(self, button):
            if "boot=casper" in core.read_text("/proc/cmdline") and core.toolbox_storage() is None:
                self.choose_toolbox_storage(button, prepare_full=True)
            else:
                self.terminal(["livara", "toolbox", "setup", "--profile", "full"])

        def choose_toolbox_storage(self, button, prepare_full=False):
            dialog = Gtk.FileChooserNative(title="Choose a persistent disk folder", transient_for=self.window, action=Gtk.FileChooserAction.SELECT_FOLDER, accept_label="Use folder", cancel_label="Cancel")
            def response(chooser, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    try:
                        path = Path(chooser.get_file().get_path()) / "Livara-Toolbox"
                        core.configure_toolbox_storage(path)
                        self.toast(f"Kali images will use {path}")
                        if prepare_full:
                            self.terminal(["livara", "toolbox", "setup", "--profile", "full"])
                    except (OSError, ValueError) as error:
                        self.toast(error)
                chooser.destroy()
            dialog.connect("response", response)
            dialog.show()

        def customize_page(self):
            from .settings_ui import SettingsStudio
            self.preferences_ui = SettingsStudio(self)
            return self.preferences_ui.build()

        def sync_preference_widgets(self):
            if hasattr(self, "preferences_ui") and hasattr(self.preferences_ui, "root"):
                self.preferences_ui.refresh()

        def app_icons_page(self):
            from .app_icons_ui import AppIconsPage
            self.app_icons_ui = AppIconsPage(self)
            return self.app_icons_ui.build()

        def essentials_page(self):
            scroll, box = self.page("LIVARA ESSENTIALS", "A little more possibility.", "Design, productivity, security and system tools in one place.")
            from .essentials import FEATURES
            box.append(self.button("Open Livara Essentials", lambda b: self.launch_app("livara-essentials"), True))
            for category in ("Design", "Productivity", "Security", "System"):
                entries = [title for key, title, hint, group, command in FEATURES if group == category]
                box.append(self.card(category, " · ".join(entries)))
            return scroll

        def launch_app(self, command, *args):
            if not shutil.which(command):
                self.toast(f"{command} is not installed")
                return
            try:
                subprocess.Popen([command, *args])
            except OSError as error:
                self.toast(error)

        def apps_page(self):
            scroll, box = self.page("MADE FOR LIVARA", "Your everyday creative toolkit.", "Native Livara applications, with a shared purple identity and real local tools.")
            apps = (
                ("Browser", "A source-built Livara browser with spaces, vertical tabs, customization and a separate official Tor Browser mode.", "livara-browser", "org.livara.Browser"),
                ("Code", "A fully branded extensible workbench with an AMOLED theme, integrated terminal and Livara productivity tools.", "livara-code", "org.livara.Code"),
                ("Task Manager", "Live CPU, memory, network graphs and searchable processes with confirmed controls.", "livara-monitor", "org.livara.Monitor"),
                ("Studio", "30 local tools, a private Notebook, a Focus room, and customizable creative workspaces.", "livara-studio", "org.livara.Studio"),
                ("Settings", "Personalize glass, color, motion and desktop layout, then open device and connectivity panels.", "livara-settings", "org.livara.Settings"),
                ("Terminal", "A dedicated Livara palette, purple prompt, branded startup, and a profile you can customize.", "livara-terminal", "org.livara.Terminal"),
                ("Graphics", "Inspect NVIDIA hardware, driver readiness, kernel, rendering and installation guidance.", "livara-graphics", "org.livara.Graphics"),
                ("Chat", "chat.livara.org in a dedicated app window. An internet connection and the website’s services are required.", "livara-chat", "org.livara.Chat"),
            )
            for title, description, command, icon in apps:
                card = self.card(title, description)
                heading = Gtk.Box(spacing=12)
                image = Gtk.Image.new_from_icon_name(icon)
                image.set_pixel_size(40)
                heading.append(image)
                heading.append(self.button("Open " + title + "  ↗", lambda b, c=command: self.launch_app(c)))
                card.append(heading)
                box.append(card)
            return scroll

        def system_page(self):
            scroll, box = self.page("LIVARA SETTINGS", "Make your device feel at home.", "Livara desktop controls live in Personalize. Device controls open the system’s hardware and account panels.")
            groups = (
                ("CONNECTIONS", (("Wi-Fi", "wifi"), ("Network & VPN", "network"), ("Bluetooth", "bluetooth"))),
                ("DEVICE", (("Displays", "display"), ("Sound", "sound"), ("Power", "power"), ("Keyboard", "keyboard"), ("Mouse & touchpad", "mouse"))),
                ("YOU & YOUR SYSTEM", (("Privacy", "privacy"), ("Accessibility", "universal-access"), ("Users", ("system", "users")), ("Date & time", ("system", "datetime")))),
            )
            for title, panels in groups:
                box.append(self.label(title, "eyebrow"))
                listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
                for label, panel in panels:
                    row = self.action_row(label, subtitle="Open device settings in a separate window")
                    action = self.button("Open  ↗", lambda b, p=panel: self.launch_app("gnome-control-center", *(p if isinstance(p, tuple) else (p,))))
                    action.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(action)
                    listing.append(row)
                box.append(listing)
            row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=2, row_spacing=8, column_spacing=8)
            for title, callback in (("Graphics & RTX", lambda b: self.launch_app("livara-graphics")), ("Disks & storage", lambda b: self.launch_app("gnome-disks")), ("Reset Livara Terminal theme", self.reset_terminal), ("Design Livara fonts", self.design_fonts)):
                row.insert(self.button(title, callback), -1)
            box.append(row)
            return scroll

        def design_fonts(self, button):
            try:
                source = Path("/usr/share/livara/fonts/sources/LivaraSans-Regular.ufo")
                if not source.is_dir():
                    source = Path(__file__).resolve().parents[2] / "fonts/sources/LivaraSans-Regular.ufo"
                workspace = Path.home() / "Livara/Fonts"
                if workspace.is_symlink():
                    raise ValueError("Choose a regular Livara/Fonts folder before editing fonts")
                workspace.mkdir(parents=True, exist_ok=True)
                target = workspace / source.name
                if target.is_symlink():
                    raise ValueError("The editable font path must be a regular folder")
                if not target.exists():
                    shutil.copytree(source, target)
                elif not target.is_dir():
                    raise ValueError("The editable font path must be a folder")
                self.launch_app("fontforge", str(target))
                self.toast(f"Your editable copy is in {target}")
            except (OSError, ValueError) as error:
                self.toast(error)

        def reset_terminal(self, button):
            try:
                desktop.configure_terminal(reset=True)
                self.toast("Livara Terminal theme restored")
            except (OSError, ValueError, TypeError, GLib.Error) as error:
                self.toast(error)

        def change_preference(self, name, value):
            if hasattr(self, "preferences_ui"):
                self.preferences_ui.set_option(name, value)

        def rendering_mode(self, full):
            if hasattr(self, "preferences_ui"):
                self.preferences_ui.rendering_mode(full)

        def apply_desktop_preset(self, name):
            if hasattr(self, "preferences_ui"):
                self.preferences_ui.apply_builtin(name)

        def cases_page(self):
            scroll, box = self.page("LIVARA CASES", "Give every discovery a home.", "Private local workspaces for evidence, notes, and reports.")
            entry = Gtk.Entry(placeholder_text="Case name, e.g. home-lab-review", hexpand=True)
            row = Gtk.Box(spacing=10)
            row.append(entry)
            def create(button):
                try:
                    path = core.create_case(entry.get_text())
                    entry.set_text("")
                    self.toast(f"Created {path.name}")
                    self.refresh_cases()
                except (OSError, ValueError) as error:
                    self.toast(error)
            row.append(self.button("Create case", create, True))
            box.append(row)
            box.append(self.card("Keep a record you can check", "Seal a case to record SHA-256 hashes. Verify it later to find changed, missing, or added files. Keep a trusted copy of the manifest separately; hashes do not prove authorship."))
            self.case_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            box.append(self.case_list)
            box.append(self.button("Open Cases folder  ↗", lambda b: self.open_folder(core.cases_root())))
            self.refresh_cases()
            return scroll

        def refresh_cases(self):
            while self.case_list.get_first_child():
                self.case_list.remove(self.case_list.get_first_child())
            paths = sorted(core.cases_root().glob("*/case.json"))
            if not paths:
                self.case_list.append(self.action_row("Your first case starts here", subtitle="Create a workspace using the field above."))
            for metadata in paths:
                path = metadata.parent
                row = self.action_row(path.name, subtitle="Manifest recorded" if (path / "manifest.json").exists() else "Ready for your notes and evidence")
                for title, action in (("Open", lambda p: self.open_folder(p)), ("Seal", self.seal), ("Verify", self.verify_case)):
                    button = self.button(title, lambda b, p=path, fn=action: fn(p))
                    button.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(button)
                self.case_list.append(row)

        def background(self, work, success):
            def task():
                try:
                    result = work()
                    GLib.idle_add(success, result)
                except Exception as error:
                    GLib.idle_add(self.toast, str(error))
            threading.Thread(target=task, daemon=True).start()

        def seal(self, path):
            def success(result):
                self.toast(f"Recorded hashes for {len(result['files'])} files")
                self.refresh_cases()
            self.background(lambda: core.seal_case(path), success)

        def verify_case(self, path):
            def success(result):
                self.toast(f"All {result['checked']} files match" if result["ok"] else f"Changes found: {len(result['changed'])} modified, {len(result['missing'])} missing, {len(result['added'])} added")
            self.background(lambda: core.verify_case(path), success)

        def shield_page(self):
            scroll, box = self.page("LIVARA SHIELD", "A clearer view of your security.", "Read-only checks of your local system. Refresh to observe the current state.")
            report_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            def refresh(button=None):
                def success(report):
                    while report_list.get_first_child():
                        report_list.remove(report_list.get_first_child())
                    for check in report:
                        row = self.action_row(check["name"], subtitle=check["detail"])
                        row.add_suffix(Gtk.Label(label={"pass": "Configured", "review": "Review", "unknown": "Unknown"}[check["state"]], css_classes=[check["state"], "small"]))
                        report_list.append(row)
                self.background(core.shield_report, success)
            row = Gtk.Box(spacing=10)
            row.append(self.button("Refresh checks", refresh, True))
            row.append(self.button("Firewall settings  ↗", lambda b: subprocess.Popen(["gufw"]) if shutil.which("gufw") else self.terminal(["sudo", "ufw", "status", "verbose"])))
            box.append(row)
            box.append(report_list)
            box.append(self.card("Signals, with context", "These checks cover a small set of local settings. Unknown means the setting could not be read. Shield does not certify a system as secure or silently change its configuration."))
            refresh()
            return scroll

        def verify_page(self):
            scroll, box = self.page("LIVARA VERIFY", "Know what you downloaded.", "Calculate a SHA-256 fingerprint, or compare a file against a trusted checksum.")
            self.verify_path = None
            chosen = self.label("No file selected", "muted")
            expected = Gtk.Entry(placeholder_text="Expected SHA-256 (optional)")
            result = self.label("Your checksum will appear here.", "small")
            result.set_selectable(True)
            def choose(button):
                dialog = Gtk.FileChooserNative(title="Choose a file", transient_for=self.window, action=Gtk.FileChooserAction.OPEN, accept_label="Choose", cancel_label="Cancel")
                def response(chooser, response_id):
                    if response_id == Gtk.ResponseType.ACCEPT:
                        self.verify_path = Path(chooser.get_file().get_path())
                        chosen.set_text(str(self.verify_path))
                    chooser.destroy()
                dialog.connect("response", response)
                dialog.show()
            box.append(self.button("Choose a file…", choose))
            box.append(chosen)
            box.append(expected)
            def verify(button):
                if self.verify_path is None:
                    self.toast("Choose a file first")
                    return
                checksum = expected.get_text().strip() or None
                file_path = self.verify_path
                button.set_sensitive(False)
                result.set_text("Calculating…")
                def work():
                    try:
                        digest, matches = core.verify_file(file_path, checksum)
                        return f"{digest}\n\n" + ("SHA-256 matches the expected checksum." if checksum and matches else "SHA-256 MISMATCH." if checksum else "SHA-256 calculated. Compare this with a trusted publisher’s checksum.")
                    except (OSError, ValueError) as error:
                        return str(error)
                def success(text):
                    result.set_text(text)
                    button.set_sensitive(True)
                self.background(work, success)
            box.append(self.button("Calculate & verify", verify, True))
            box.append(self.card("File fingerprint", "SHA-256 detects byte-level differences. A match is useful when the expected checksum comes from a source you trust."))
            box.append(result)
            return scroll

    argv = sys.argv if Path(sys.argv[0]).name in ("livara-settings", "livara-center", "gui.py") else [sys.argv[0]]
    return Center().run(argv)


def settings_main() -> int:
    return main(mode="settings")


if __name__ == "__main__":
    sys.exit(main())


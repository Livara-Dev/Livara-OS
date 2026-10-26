"""Livara Studio: a native, local utility desk with notes and a focus timer."""

from __future__ import annotations

import sys
import os
import threading
import time
import stat
from pathlib import Path
from datetime import datetime, timezone

from . import desktop, materials, studio, window_style, halo


def main() -> int:
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango
    except (ImportError, ValueError):
        print("Livara Studio requires GTK 4 and libadwaita.", file=sys.stderr)
        return 2

    class Studio(Adw.Application):
        def __init__(self):
            super().__init__(application_id="org.livara.Studio", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.add_main_option("tool", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING, "Open a Studio tool", "TOOL")
            self.connect("command-line", self.command_line)
            self.connect("activate", self.activate)
            self.note_store = None
            self.note_id = None
            self.note_dirty = False
            self.loading_note = False
            self.loading_note_list = False
            self.confirmed_close = False
            self.focus_state = "ready"
            self.focus_source = None
            self.focus_remaining = 25 * 60
            self.focus_total = 25 * 60
            self.focus_label_text = ""
            self.focus_display_value = ""
            self.job_pending = False
            self.tool_generation = 0
            self.dialogs = []
            self.category = "All"
            self.tool_drafts = {}
            self.result_ready = False
            self.notes_archived = False
            self.workspace_store = None
            self.workspace_state = {"favorites": ["json", "calculator", "unicode"], "recent": [],
                                    "preferences": {"accent": "violet", "density": "comfortable", "editor-size": 13}}
            try:
                self.workspace_store = studio.WorkspaceState()
                self.workspace_state = self.workspace_store.read()
            except (OSError, ValueError):
                pass

        def activate(self, application):
            if self.get_active_window():
                self.get_active_window().present()
                return
            self.motion_settings = desktop.settings_for("org.gnome.desktop.interface")
            self.animations = self.motion_settings.get_boolean("enable-animations") if self.motion_settings else True
            if self.motion_settings:
                self.motion_settings.connect("changed::enable-animations", self.motion_changed)
                self.motion_settings.connect("changed::font-name", lambda *args: self.install_style())
                self.motion_settings.connect("changed::monospace-font-name", lambda *args: self.install_style())
            self.install_style()
            self.window = Adw.ApplicationWindow(application=self, title="Livara Studio", default_width=1260, default_height=860,
                                                css_classes=["studio-window"])
            self.window.set_size_request(860, 620)
            self.window.set_icon_name("org.livara.Studio")
            self.window.connect("close-request", self.close_requested)
            self.window.connect("destroy", lambda *args: self.remove_focus_source())
            self.overlay = Adw.ToastOverlay()
            self.window.set_content(self.overlay)
            shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.overlay.set_child(shell)
            header = Adw.HeaderBar()
            self.window_controls = window_style.configure_native_headerbar(self.window, header)
            header.set_title_widget(Gtk.Label(label="Livara Studio", css_classes=["muted"]))
            customize = Gtk.MenuButton(label="Customize", css_classes=["quiet"])
            self.customize_button = customize
            customize.set_popover(self.build_customize_popover())
            header.pack_end(customize)
            shell.append(header)
            body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=False, vexpand=True)
            body.set_position(250)
            body.set_resize_start_child(False)
            body.set_shrink_start_child(False)
            body.set_shrink_end_child(False)
            shell.append(body)
            sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, width_request=225, css_classes=["studio-sidebar"])
            self.margin(sidebar, 18)
            body.set_start_child(sidebar)
            brand = Gtk.Box(spacing=10)
            icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            if icon_theme.has_icon("org.livara.Studio"):
                icon = Gtk.Image.new_from_icon_name("org.livara.Studio")
            elif icon_theme.has_icon("org.livara.Center"):
                icon = Gtk.Image.new_from_icon_name("org.livara.Center")
            else:
                candidates = (Path("/usr/share/livara/logo.png"), Path(__file__).resolve().parents[2] / "artwork" / "livara-logo.png")
                logo = next((path for path in candidates if path.is_file()), None)
                icon = Gtk.Image.new_from_file(str(logo)) if logo else Gtk.Image()
            icon.set_pixel_size(38)
            brand.append(icon)
            brand.append(self.label("STUDIO", "brand"))
            sidebar.append(brand)
            sidebar.append(self.label("A place to make progress.", "muted", "small"))
            modes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            self.mode_buttons = {}
            group = None
            for key, name, glyph in (("home", "Overview", "view-grid-symbolic"), ("tools", "Tool library", "applications-utilities-symbolic"), ("notes", "Notebook", "document-edit-symbolic"), ("focus", "Focus room", "alarm-symbolic")):
                button = Gtk.ToggleButton(css_classes=["mode"])
                contents = Gtk.Box(spacing=10)
                contents.append(Gtk.Image.new_from_icon_name(glyph))
                contents.append(Gtk.Label(label=name, xalign=0))
                button.set_child(contents)
                if group:
                    button.set_group(group)
                else:
                    group = button
                button.connect("toggled", lambda b, k=key: self.show_mode(k) if b.get_active() else None)
                modes.append(button)
                self.mode_buttons[key] = button
            sidebar.append(modes)
            self.search = Gtk.SearchEntry(placeholder_text="Search tools · Ctrl F")
            self.search.set_tooltip_text("Search names, categories, and descriptions")
            self.search.connect("search-changed", self.filter_tools)
            sidebar.append(self.search)
            self.category_picker = Gtk.DropDown.new_from_strings(["All tools", "Favorites", *dict.fromkeys(tool["category"] for tool in studio.TOOLS)])
            self.category_picker.connect("notify::selected", self.category_changed)
            sidebar.append(self.category_picker)
            catalog_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            self.catalog_scroll = catalog_scroll
            self.catalog = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
            self.catalog.connect("row-selected", self.tool_selected)
            catalog_scroll.set_child(self.catalog)
            sidebar.append(catalog_scroll)
            self.catalog_rows = []
            for tool in studio.TOOLS:
                row = self.action_row(tool["name"], tool["category"])
                row.set_title_lines(2)
                row.set_subtitle_lines(1)
                row.tool = tool
                self.catalog.append(row)
                query = " ".join(str(tool.get(k, "")) for k in ("id", "name", "category", "hint")).casefold()
                self.catalog_rows.append((row, query))
            self.catalog_empty = self.label("No tools found.\nTry another search or category.", "muted", "small")
            self.catalog_empty.set_visible(False)
            sidebar.append(self.catalog_empty)
            sidebar.append(self.label("LOCAL BY DESIGN\nCtrl+Enter to run · Ctrl+F to find", "muted", "small"))
            self.stack = Gtk.Stack(hexpand=True, vexpand=True, transition_duration=230)
            self.stack.add_css_class('lv-content-canvas')
            self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE if self.animations else Gtk.StackTransitionType.NONE)
            body.set_end_child(self.stack)
            self.stack.add_named(self.build_home_page(), "home")
            self.stack.add_named(self.build_tools_page(), "tools")
            self.stack.add_named(self.build_notes_page(), "notes")
            self.stack.add_named(self.build_focus_page(), "focus")
            self.mode_buttons["home"].set_active(True)
            self.catalog.unselect_all()
            self.add_shortcut("run", ["<Primary>Return"], lambda *args: self.run_current_tool() if self.stack.get_visible_child_name() == "tools" else None)
            self.add_shortcut("find", ["<Primary>f"], lambda *args: self.search.grab_focus())
            self.add_shortcut("copy-output", ["<Primary><Shift>c"], lambda *args: self.copy_output())
            for number, mode in enumerate(("home", "tools", "notes", "focus"), start=1):
                self.add_shortcut("show-" + mode, ["<Primary>" + str(number)], lambda a, p, key=mode: self.mode_buttons[key].set_active(True))
            self.add_shortcut("save-note", ["<Primary>s"], lambda *args: self.save_note() if self.stack.get_visible_child_name() == "notes" else None)
            self.add_shortcut("focus-toggle", ["<Primary><Shift>space"], lambda *args: self.pause_focus() if self.focus_state == "running" else self.start_focus())
            self.window.present()
            self.refresh_home()

        def install_style(self):
            if not hasattr(self, "style_provider"):
                self.style_provider = Gtk.CssProvider()
                Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            preferences = self.workspace_state.get("preferences", {})
            accents = {"violet": "#c5a3ff", "ocean": "#8dcaff", "mint": "#9ce6cb", "rose": "#ffafd5"}
            accent = accents.get(preferences.get("accent"), accents["violet"])
            size = int(preferences.get("editor-size", 13))
            def font_family(key, fallback):
                value = self.motion_settings.get_string(key) if self.motion_settings else fallback
                family = Pango.FontDescription.from_string(value).get_family() or fallback
                return family.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")[:200]
            ui_font = font_family("font-name", "Livara Sans")
            mono_font = font_family("monospace-font-name", "Livara Mono")
            compact = preferences.get("density") == "compact"
            pad = 14 if compact else 22
            css = f"""
                window.studio-window {{ background: #08050e; color: #f2eafc; font-family: "{ui_font}", 'Livara Persian', sans-serif; }}
                headerbar {{ background: #0d0814; box-shadow: none; border-bottom: 1px solid #25192f; }}
                .studio-sidebar {{ background: #100a19; border-right: 1px solid #2b1d38; }}
                .brand {{ font-size: 18px; font-weight: 800; letter-spacing: 3px; color: #f0e2ff; }}
                .eyebrow {{ color: {accent}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
                .page-title {{ font-size: 34px; font-weight: 600; letter-spacing: -1px; }}
                .home-title {{ font-size: 42px; font-weight: 600; letter-spacing: -1px; }}
                .card-title {{ font-size: 18px; font-weight: 600; }}
                .muted {{ color: #ac98bd; }}
                .small {{ font-size: 11px; }}
                .studio-card {{ background: #130c1e; border: 1px solid #33223f; border-radius: 22px; padding: {pad}px; }}
                .studio-hero {{ background: linear-gradient(125deg, #251236, #100a1b); border: 1px solid #56366b; border-radius: 26px; padding: 28px; }}
                .home-action {{ background: #171022; border: 1px solid #38264a; border-radius: 20px; padding: {pad}px; color: #eee0ff; }}
                .home-action:hover {{ background: #251435; border-color: {accent}; }}
                .feature-glyph {{ font-size: 26px; color: {accent}; }}
                .metric {{ font-size: 26px; font-weight: 600; color: #f2e6ff; }}
                .mode {{ border-radius: 13px; padding: 11px 14px; background: transparent; border: 1px solid transparent; font-weight: 600; }}
                .mode:checked {{ background: #30203f; color: {accent}; border-color: #543568; }}
                .navigation-sidebar row {{ border-radius: 12px; margin: 2px 0; padding: 2px; }}
                .navigation-sidebar row:selected {{ background: #30203f; }}
                button.primary {{ background: {accent}; color: #1a0d28; border-radius: 13px; padding: 10px 18px; font-weight: 700; }}
                button.secondary {{ background: #22152f; border: 1px solid #3c284d; border-radius: 13px; padding: 9px 14px; }}
                button.quiet {{ background: transparent; border: 1px solid #35233f; border-radius: 11px; padding: 7px 11px; }}
                button.pinned {{ color: {accent}; background: #30203f; }}
                entry, searchentry, dropdown {{ border-radius: 12px; }}
                textview {{ background: transparent; color: #e8def3; padding: 12px; }}
                textview text {{ background: transparent; }}
                textview.studio-editor {{ font-size: {size}px; font-family: "{mono_font}", 'Livara Persian', monospace; }}
                textview.note-editor {{ font-family: "{ui_font}", 'Livara Persian', sans-serif; font-size: {size + 2}px; }}
                .note-title {{ font-size: 22px; font-weight: 600; background: transparent; border: none; box-shadow: none; }}
                .text-frame {{ background: #08050e; border: 1px solid #2f203b; border-radius: 14px; }}
                .timer-value {{ font-size: 68px; font-weight: 300; font-feature-settings: "tnum"; color: #f3e8ff; }}
                .focus-progress trough {{ min-height: 7px; border-radius: 7px; background: #32213f; }}
                .focus-progress progress {{ min-height: 7px; border-radius: 7px; background: {accent}; }}
                .boxed-list {{ background: #130c1e; border: 1px solid #33223f; border-radius: 18px; }}
                .boxed-list > row {{ background: transparent; }}
                .result-status {{ color: {accent}; }}
                .error-status {{ color: #ffb4c4; }}
                .empty-icon {{ font-size: 42px; color: #77538e; }}
            """
            self.style_provider.load_from_data(css.encode("utf-8"))
            materials.set_accent_override(accent)

        def action_row(self, title, subtitle=""):
            row = Adw.ActionRow(activatable=True)
            row.set_use_markup(False)
            row.set_title(str(title))
            row.set_subtitle(str(subtitle))
            return row

        def build_customize_popover(self):
            popover = Gtk.Popover()
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, width_request=260)
            self.margin(panel, 16)
            panel.append(self.label("MAKE IT YOURS", "eyebrow"))
            panel.append(self.label("Your Studio, your rhythm.", "card-title"))
            prefs = self.workspace_state.get("preferences", {})
            for title, key, choices in (("Accent", "accent", [("violet", "Iris"), ("ocean", "Ocean"), ("mint", "Mint"), ("rose", "Rose")]),
                                        ("Density", "density", [("comfortable", "Comfortable"), ("compact", "Compact")])):
                row = Gtk.Box(spacing=10)
                row.append(self.label(title, "muted"))
                picker = Gtk.DropDown.new_from_strings([name for value, name in choices])
                picker.set_hexpand(True)
                picker.set_selected(next((i for i, (value, name) in enumerate(choices) if value == prefs.get(key)), 0))
                picker.connect("notify::selected", lambda item, param, name=key, values=choices: self.change_studio_preference(name, values[item.get_selected()][0]))
                row.append(picker)
                panel.append(row)
            row = Gtk.Box(spacing=10)
            row.append(self.label("Editor text size", "muted"))
            editor_size = Gtk.SpinButton.new_with_range(11, 22, 1)
            editor_size.set_value(prefs.get("editor-size", 13))
            editor_size.connect("value-changed", lambda item: self.change_studio_preference("editor-size", int(item.get_value())))
            row.append(editor_size)
            panel.append(row)
            panel.append(self.label("Appearance is saved for your next visit. Tool inputs and results stay in this session.", "small", "muted"))
            popover.set_child(panel)
            return popover

        def change_studio_preference(self, key, value):
            try:
                if self.workspace_store:
                    self.workspace_state = self.workspace_store.set_preferences(**{key: value})
                else:
                    self.workspace_state["preferences"][key] = value
                self.install_style()
            except (OSError, ValueError) as error:
                self.toast(error)

        def workspace_change(self, method, *args):
            try:
                if self.workspace_store:
                    self.workspace_state = getattr(self.workspace_store, method)(*args)
                elif method == "set_favorite":
                    identifier, enabled = args
                    favorites = self.workspace_state["favorites"]
                    if identifier in favorites:
                        favorites.remove(identifier)
                    if enabled:
                        favorites.append(identifier)
                    self.toast("Pinned for this session; workspace storage is unavailable")
                elif method == "record_tool":
                    identifier = args[0]
                    recent = [record for record in self.workspace_state["recent"] if record["id"] != identifier]
                    self.workspace_state["recent"] = [{"id": identifier, "used_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, *recent][:8]
                self.refresh_home()
            except (OSError, ValueError) as error:
                self.toast(error)

        def build_home_page(self):
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=23)
            self.margin(page, 30)
            scroll.set_child(page)
            actions = Gtk.Box(spacing=10)
            actions.append(self.button("Start creating", lambda button: self.open_tool("json"), True))
            actions.append(self.button("New note", lambda button: self.new_note_template("blank")))
            page.append(halo.hero("STUDIO  /  MADE FOR THE MOMENT", "Less friction.\nMore flow.",
                "Thirty thoughtful tools. One quiet notebook. A little space to focus.", actions))
            self.home_metrics = Gtk.Box(spacing=14, homogeneous=True)
            page.append(self.home_metrics)
            journeys = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=3,
                                   row_spacing=14, column_spacing=14, homogeneous=True)
            for icon, title, subtitle, callback in (("✦", "Shape your data", "Format JSON, compare text, inspect files.", lambda: self.open_tool("json")),
                                                    ("✎", "Keep the good ideas", "A notebook with search, templates and exports.", lambda: self.mode_buttons["notes"].set_active(True)),
                                                    ("◷", "Find your focus", "One clear task. A timer that stays out of the way.", lambda: self.mode_buttons["focus"].set_active(True))):
                journeys.append(self.home_card(icon, title, subtitle, callback))
            page.append(journeys)
            page.append(self.label("PINNED TO YOUR WORKSPACE", "eyebrow"))
            self.favorite_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=3,
                                           row_spacing=12, column_spacing=12, homogeneous=True)
            page.append(self.favorite_grid)
            page.append(self.label("PICK UP WHERE YOU LEFT OFF", "eyebrow"))
            self.recent_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            page.append(self.recent_list)
            return scroll

        def home_card(self, icon, title, subtitle, callback):
            button = Gtk.Button(css_classes=["home-action"], hexpand=True)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
            box.append(self.label(icon, "feature-glyph"))
            box.append(self.label(title, "card-title"))
            description = self.label(subtitle, "muted", "small")
            description.set_max_width_chars(27)
            box.append(description)
            button.set_child(box)
            button.connect("clicked", lambda item: callback())
            return button

        def clear_children(self, parent):
            while parent.get_first_child():
                parent.remove(parent.get_first_child())

        def refresh_home(self):
            if not hasattr(self, "favorite_grid"):
                return
            self.clear_children(self.home_metrics)
            try:
                notes = len(self.notes().list_notes())
                history = studio.focus_history(30)
                minutes = sum(item["seconds"] for item in history) // 60
            except (OSError, ValueError):
                notes, minutes = 0, 0
            for value, label in ((len(studio.TOOLS), "Local tools"), (notes, "Saved notes"), (minutes, "Focus minutes · last 30 sessions")):
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, css_classes=["studio-card"])
                card.append(self.label(str(value), "metric"))
                card.append(self.label(label, "muted", "small"))
                self.home_metrics.append(card)
            self.clear_children(self.favorite_grid)
            favorites = self.workspace_state.get("favorites", [])
            for identifier in favorites:
                tool = next((item for item in studio.TOOLS if item["id"] == identifier), None)
                if tool:
                    self.favorite_grid.append(self.home_card("✧", tool["name"], tool["category"], lambda key=identifier: self.open_tool(key)))
            if not favorites:
                self.favorite_grid.append(self.label("Pin a tool with its star to keep it here.", "muted"))
            self.clear_children(self.recent_list)
            for record in self.workspace_state.get("recent", [])[:5]:
                tool = next((item for item in studio.TOOLS if item["id"] == record["id"]), None)
                if tool:
                    row = self.action_row(tool["name"], tool["category"] + " · " + record["used_at"].replace("T", " ").replace("+00:00", " UTC"))
                    row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                    row.connect("activated", lambda item, key=tool["id"]: self.open_tool(key))
                    self.recent_list.append(row)
            if not self.recent_list.get_first_child():
                self.recent_list.append(self.action_row("A fresh start", "Run a tool to add it to your recent activity. Inputs and results are not recorded."))

        def open_tool(self, identifier):
            self.search.set_text("")
            self.category_picker.set_selected(0)
            for row, query in self.catalog_rows:
                if row.tool["id"] == identifier:
                    if self.catalog.get_selected_row() is row:
                        self.tool_selected(self.catalog, row)
                    else:
                        self.catalog.select_row(row)
                    break

        def toggle_favorite(self, button):
            if not self.current_tool:
                return
            identifier = self.current_tool["id"]
            favorite = identifier not in self.workspace_state.get("favorites", [])
            self.workspace_change("set_favorite", identifier, favorite)
            self.update_favorite_button()
            self.filter_tools(self.search)

        def update_favorite_button(self):
            if not hasattr(self, "favorite_button") or not self.current_tool:
                return
            active = self.current_tool["id"] in self.workspace_state.get("favorites", [])
            self.favorite_button.set_label("★ Pinned" if active else "☆ Pin tool")
            self.favorite_button.set_tooltip_text("Remove from favorites" if active else "Pin to your workspace")

        def category_changed(self, picker, param):
            index = picker.get_selected()
            values = ["All", "Favorites", *dict.fromkeys(tool["category"] for tool in studio.TOOLS)]
            self.category = values[index] if index < len(values) else "All"
            self.filter_tools(self.search)

        def margin(self, widget, amount):
            for side in ("top", "bottom", "start", "end"):
                getattr(widget, "set_margin_" + side)(amount)

        def label(self, text, *classes):
            return Gtk.Label(label=str(text), xalign=0, wrap="eyebrow" not in classes, css_classes=list(classes))

        def button(self, title, callback, primary=False):
            button = Gtk.Button(label=title, css_classes=["primary" if primary else "secondary"])
            button.connect("clicked", callback)
            return button

        def toast(self, text):
            self.overlay.add_toast(Adw.Toast.new(str(text)))

        def add_shortcut(self, name, accelerators, callback):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
            self.set_accels_for_action("app." + name, accelerators)

        def show_mode(self, key):
            if not hasattr(self, "stack"):
                return
            self.stack.set_visible_child_name(key)
            self.catalog_scroll.set_visible(key == "tools")
            self.category_picker.set_visible(key == "tools")
            self.catalog_empty.set_visible(key == "tools" and not any(row.get_visible() for row, query in self.catalog_rows))
            if key == "home":
                self.refresh_home()
            elif key == "notes":
                self.refresh_notes()
            elif key == "focus":
                self.refresh_focus_history()
            elif key == "tools" and self.current_tool is None:
                row = next((row for row, query in self.catalog_rows if row.get_visible()), None)
                if row:
                    self.catalog.select_row(row)

        def motion_changed(self, settings, key):
            self.animations = settings.get_boolean("enable-animations")
            if hasattr(self, "stack"):
                kind = Gtk.StackTransitionType.CROSSFADE if self.animations else Gtk.StackTransitionType.NONE
                self.stack.set_transition_type(kind)
                self.timer_stack.set_transition_type(kind)
                self.result_stack.set_transition_type(kind)
                if self.job_pending:
                    self.spinner.set_visible(self.animations)
                if self.focus_state == "running":
                    self.remove_focus_source()
                    self.focus_source = GLib.timeout_add(100 if self.animations else 500, self.focus_tick)

        def filter_tools(self, entry):
            query = entry.get_text()
            identifiers = {tool["id"] for tool in studio.search_tools(query[:256], self.category,
                                                                      self.workspace_state.get("favorites", []))}
            for row, query in self.catalog_rows:
                row.set_visible(row.tool["id"] in identifiers)
            if hasattr(self, "catalog_empty"):
                self.catalog_empty.set_visible(not identifiers)
                self.catalog_scroll.set_visible(bool(identifiers))
            if hasattr(self, "stack") and entry.get_text().strip():
                self.mode_buttons["tools"].set_active(True)

        def text_area(self, minimum=150, editable=True):
            text = Gtk.TextView(monospace=True, editable=editable, cursor_visible=editable, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                css_classes=["studio-editor"])
            scroll = Gtk.ScrolledWindow(min_content_height=minimum, vexpand=True, css_classes=["text-frame"])
            scroll.set_child(text)
            return scroll, text

        def text(self, widget):
            buffer = widget.get_buffer()
            return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

        def build_tools_page(self):
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
            self.margin(page, 28)
            scroll.set_child(page)
            self.tool_category = self.label("LOCAL WORKBENCH", "eyebrow")
            page.append(self.tool_category)
            heading = Gtk.Box(spacing=14)
            titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7, hexpand=True)
            self.tool_title = self.label("Choose your next tool", "page-title")
            self.tool_hint = self.label("Make a small task feel effortless.", "muted")
            titles.append(self.tool_title)
            titles.append(self.tool_hint)
            heading.append(titles)
            self.favorite_button = self.button("☆ Pin tool", self.toggle_favorite)
            self.favorite_button.set_valign(Gtk.Align.START)
            heading.append(self.favorite_button)
            page.append(heading)
            panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True, vexpand=True)
            panes.set_position(440)
            panes.set_shrink_start_child(False)
            panes.set_shrink_end_child(False)
            page.append(panes)
            input_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["studio-card"])
            input_actions = Gtk.Box(spacing=6)
            input_actions.append(self.label("INPUT", "eyebrow"))
            input_actions.append(Gtk.Box(hexpand=True))
            input_actions.append(self.button("Paste", lambda button: self.paste_input()))
            self.load_input_button = self.button("Open…", lambda button: self.choose_input())
            input_actions.append(self.load_input_button)
            input_actions.append(self.button("Sample", lambda button: self.load_sample()))
            input_card.append(input_actions)
            input_scroll, self.input_view = self.text_area(240)
            input_card.append(input_scroll)
            self.option_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
            self.option_title = self.label("OPTIONS", "eyebrow")
            self.option_entry = Gtk.Entry(hexpand=True)
            self.diff_scroll, self.diff_view = self.text_area(145)
            self.option_box.append(self.option_title)
            self.option_box.append(self.option_entry)
            self.option_box.append(self.diff_scroll)
            input_card.append(self.option_box)
            run_row = Gtk.Box(spacing=10)
            self.run_button = self.button("Run tool  ↗", lambda button: self.run_current_tool(), True)
            run_row.append(self.run_button)
            self.spinner = Gtk.Spinner(visible=False)
            run_row.append(self.spinner)
            self.work_status = self.label("Ctrl + Enter", "muted", "small")
            self.work_status.set_hexpand(True)
            run_row.append(self.work_status)
            input_card.append(run_row)
            panes.set_start_child(input_card)
            output_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["studio-card"])
            output_actions = Gtk.Box(spacing=6)
            output_actions.append(self.label("RESULT", "eyebrow"))
            output_actions.append(Gtk.Box(hexpand=True))
            self.copy_button = self.button("Copy", lambda button: self.copy_output())
            self.save_button = self.button("Save…", lambda button: self.save_output())
            output_actions.append(self.copy_button)
            output_actions.append(self.save_button)
            output_card.append(output_actions)
            self.result_stack = Gtk.Stack(vexpand=True, transition_duration=140,
                                          transition_type=Gtk.StackTransitionType.CROSSFADE if self.animations else Gtk.StackTransitionType.NONE)
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
            empty.append(self.label("✧", "empty-icon"))
            empty.append(self.label("A little clarity, right here.", "card-title"))
            empty.append(self.label("Run the tool to see your result.\nCopy it, save it, or keep it in Notes.", "muted", "small"))
            self.result_stack.add_named(empty, "empty")
            output_scroll, self.output_view = self.text_area(300, editable=False)
            self.result_stack.add_named(output_scroll, "result")
            self.result_stack.set_visible_child_name("empty")
            output_card.append(self.result_stack)
            result_footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.result_info = self.label("Ready for your next idea", "muted", "small")
            self.result_info.set_hexpand(True)
            result_footer.append(self.result_info)
            self.reuse_button = self.button("Use as input", lambda button: self.reuse_result())
            self.result_note_button = self.button("Keep in Notes", lambda button: self.result_to_note())
            result_actions = Gtk.Box(spacing=7)
            result_actions.append(self.reuse_button)
            result_actions.append(self.result_note_button)
            result_footer.append(result_actions)
            output_card.append(result_footer)
            panes.set_end_child(output_card)
            self.current_tool = None
            self.set_result_ready(False)
            return scroll

        def set_result_ready(self, ready):
            self.result_ready = ready
            for button in (self.copy_button, self.save_button, self.reuse_button, self.result_note_button):
                button.set_sensitive(ready)

        def save_tool_draft(self):
            if self.current_tool:
                identifier = self.current_tool["id"]
                self.tool_drafts.pop(identifier, None)
                self.tool_drafts[identifier] = (self.text(self.input_view), self.option_entry.get_text(),
                                                self.text(self.diff_view), self.text(self.output_view), self.result_ready)
                while len(self.tool_drafts) > 6:
                    self.tool_drafts.pop(next(iter(self.tool_drafts)))

        def tool_selected(self, listing, row):
            if row is None or not hasattr(self, "input_view"):
                return
            self.save_tool_draft()
            self.current_tool = row.tool
            self.tool_generation += 1
            self.tool_category.set_text(str(row.tool["category"]).upper() + " / LOCAL WORKBENCH")
            self.tool_title.set_text(row.tool["name"])
            self.tool_hint.set_text(row.tool["hint"])
            label = row.tool.get("option_label") or ""
            self.option_box.set_visible(bool(label))
            self.option_title.set_text(str(label))
            self.option_entry.set_visible(row.tool["id"] != "diff")
            self.diff_scroll.set_visible(row.tool["id"] == "diff")
            self.load_input_button.set_label("Folder…" if row.tool["input_kind"] == "directory" else "File…" if row.tool["input_kind"] == "file" else "Open…")
            draft = self.tool_drafts.get(row.tool["id"])
            if draft:
                value, option, compared, output, ready = draft
                self.input_view.get_buffer().set_text(value)
                self.option_entry.set_text(option)
                self.diff_view.get_buffer().set_text(compared)
                self.output_view.get_buffer().set_text(output)
                self.set_result_ready(ready)
                self.result_stack.set_visible_child_name("result" if output else "empty")
            else:
                self.output_view.get_buffer().set_text("")
                self.load_sample()
                self.set_result_ready(False)
                self.result_stack.set_visible_child_name("empty")
            self.work_status.set_text("Working on another tool…" if self.job_pending else "Ctrl + Enter")
            self.run_button.set_sensitive(not self.job_pending)
            self.update_favorite_button()
            self.mode_buttons["tools"].set_active(True)
            self.stack.set_visible_child_name("tools")

        def reuse_result(self):
            if self.result_ready:
                self.input_view.get_buffer().set_text(self.text(self.output_view))
                self.toast("Result placed in the input editor")

        def result_to_note(self):
            if not self.result_ready:
                return
            value, title = self.text(self.output_view), self.current_tool["name"] + " result"
            if len(value.encode("utf-8")) > 256 * 1024:
                self.toast("This result exceeds the 256 KiB note limit. Save it as a file instead.")
                return
            def create():
                self.clear_note()
                self.note_title.set_text(title)
                self.note_body.get_buffer().set_text(value)
                self.mode_buttons["notes"].set_active(True)
                self.toast("Result is a note draft. Save it when you are ready.")
            self.guard_note_changes(create)

        def load_sample(self):
            if self.current_tool is None:
                return
            self.input_view.get_buffer().set_text(str(self.current_tool.get("sample", "")))
            option = str(self.current_tool.get("option_default", ""))
            self.option_entry.set_text(option)
            self.diff_view.get_buffer().set_text(option)

        def run_current_tool(self):
            if self.current_tool is None or self.job_pending:
                return
            tool = self.current_tool
            value = self.text(self.input_view)
            option = self.text(self.diff_view) if tool["id"] == "diff" else self.option_entry.get_text()
            generation = self.tool_generation
            started = time.monotonic()
            self.job_pending = True
            self.run_button.set_sensitive(False)
            self.work_status.set_text("Working…")
            self.result_info.set_text("Working locally…")
            self.set_result_ready(False)
            self.spinner.set_visible(self.animations)
            self.spinner.start()

            def work():
                try:
                    result = studio.run_tool(tool["id"], value, option)
                    error = None
                except Exception as failure:
                    result, error = "", str(failure)

                def finish():
                    self.job_pending = False
                    self.run_button.set_sensitive(True)
                    self.spinner.stop()
                    self.spinner.set_visible(False)
                    if generation == self.tool_generation:
                        self.output_view.get_buffer().set_text(("Could not complete this task:\n" + error) if error else str(result))
                        self.result_stack.set_visible_child_name("result")
                        self.set_result_ready(not error)
                        self.work_status.set_text("Check the input and try again" if error else "Done · nothing was saved automatically")
                        self.result_info.set_text("Review the input or load the sample" if error else f"{len(str(result)):,} characters · {time.monotonic() - started:.2f} seconds")
                        if error:
                            self.work_status.add_css_class("error-status")
                        else:
                            self.work_status.remove_css_class("error-status")
                    else:
                        self.work_status.set_text("")
                    if not error:
                        self.workspace_change("record_tool", tool["id"])
                    return GLib.SOURCE_REMOVE

                GLib.idle_add(finish)

            threading.Thread(target=work, daemon=True).start()

        def paste_input(self):
            clipboard = self.window.get_clipboard()

            def ready(source, result):
                try:
                    value = source.read_text_finish(result)
                    if value is None:
                        self.toast("The clipboard does not contain text")
                    elif len(value) > 1_000_000:
                        self.toast("Clipboard text is too large for this workspace")
                    else:
                        self.input_view.get_buffer().set_text(value)
                except GLib.Error as error:
                    self.toast(error)

            clipboard.read_text_async(None, ready)

        def copy_output(self):
            if self.stack.get_visible_child_name() != "tools" or not self.result_ready:
                return
            value = self.text(self.output_view)
            if value:
                self.window.get_clipboard().set(value)
                self.toast("Result copied")
            else:
                self.toast("Run a tool to create a result first")

        def file_dialog(self, title, action, accept, handler, filename=None):
            chooser = Gtk.FileChooserNative(title=title, transient_for=self.window, action=action, accept_label=accept, cancel_label="Cancel")
            if filename:
                chooser.set_current_name(filename)
            self.dialogs.append(chooser)

            def response(dialog, result):
                try:
                    if result == Gtk.ResponseType.ACCEPT and dialog.get_file():
                        path = dialog.get_file().get_path()
                        if path is None:
                            self.toast("Choose a local file or folder")
                        else:
                            handler(Path(path))
                except (OSError, ValueError, UnicodeError) as error:
                    self.toast(error)
                finally:
                    self.dialogs.remove(dialog)
                    dialog.destroy()

            chooser.connect("response", response)
            chooser.show()

        def choose_input(self):
            if self.current_tool is None:
                return
            kind = self.current_tool["input_kind"]
            if kind in ("file", "directory"):
                action = Gtk.FileChooserAction.SELECT_FOLDER if kind == "directory" else Gtk.FileChooserAction.OPEN
                self.file_dialog("Choose an input " + ("folder" if kind == "directory" else "file"), action, "Choose", lambda p: self.input_view.get_buffer().set_text(str(p)))
            else:
                def load(path):
                    if not path.is_file():
                        raise ValueError("Choose a regular text file")
                    with path.open("r", encoding="utf-8") as stream:
                        value = stream.read(1_000_001)
                    if len(value) > 1_000_000:
                        raise ValueError("Choose a text file smaller than one million characters")
                    self.input_view.get_buffer().set_text(value)
                self.file_dialog("Load a UTF-8 text file", Gtk.FileChooserAction.OPEN, "Load", load)

        def save_output(self):
            value = self.text(self.output_view)
            if not self.result_ready or not value:
                self.toast("Run a tool to create a result first")
                return
            name = self.current_tool["id"] if self.current_tool else "result"
            self.file_dialog("Save Studio result", Gtk.FileChooserAction.SAVE, "Save", lambda p: self.write_result(p, value), filename=f"livara-{name}.txt")

        def write_result(self, path, value):
            # New exports may contain generated secrets; keep them private.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("Choose a regular export file")
                os.fchmod(stream.fileno(), 0o600)
                os.ftruncate(stream.fileno(), 0)
                stream.write(value)
            self.toast(f"Saved {path.name}")

        def build_notes_page(self):
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
            self.margin(page, 28)
            scroll.set_child(page)
            page.append(self.label("YOUR PRIVATE NOTEBOOK", "eyebrow"))
            page.append(self.label("Good thoughts deserve a home.", "page-title"))
            page.append(self.label("Ideas, project plans, and the useful things you want to keep. Yours, on this device.", "muted"))
            panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True, vexpand=True)
            panes.set_position(260)
            panes.set_shrink_start_child(False)
            panes.set_shrink_end_child(False)
            page.append(panes)
            library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, width_request=220, css_classes=["studio-card"])
            heading = Gtk.Box(spacing=8)
            heading.append(self.label("YOUR PAGES", "eyebrow"))
            heading.append(Gtk.Box(hexpand=True))
            self.note_count = self.label("0", "muted", "small")
            heading.append(self.note_count)
            library.append(heading)
            self.note_search = Gtk.SearchEntry(placeholder_text="Find a thought…")
            self.note_search.connect("search-changed", lambda e: self.refresh_notes())
            library.append(self.note_search)
            self.note_archive_toggle = Gtk.ToggleButton(label="Browse archive", css_classes=["quiet"])
            self.note_archive_toggle.connect("toggled", self.toggle_note_archive)
            library.append(self.note_archive_toggle)
            self.notes_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
            self.notes_list.connect("row-selected", self.note_selected)
            note_list_scroll = Gtk.ScrolledWindow(min_content_height=250, hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            note_list_scroll.set_child(self.notes_list)
            library.append(note_list_scroll)
            new_note = Gtk.MenuButton(label="+ New page", css_classes=["primary"])
            template_menu = Gtk.Popover()
            template_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.margin(template_box, 8)
            for key, title in (("blank", "Blank page"), ("project", "Project plan"), ("daily", "Daily intentions"), ("research", "Research notebook")):
                def create(button, name=key):
                    template_menu.popdown()
                    self.new_note_template(name)
                template_box.append(self.button(title, create))
            template_menu.set_child(template_box)
            new_note.set_popover(template_menu)
            library.append(new_note)
            panes.set_start_child(library)
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, css_classes=["studio-card"])
            self.note_title = Gtk.Entry(placeholder_text="Give this page a title", max_length=100, css_classes=["note-title"])
            self.note_title.connect("changed", self.note_changed)
            card.append(self.note_title)
            editor_scroll, self.note_body = self.text_area(340)
            self.note_body.set_monospace(False)
            self.note_body.add_css_class("note-editor")
            self.note_body.get_buffer().connect("changed", self.note_changed)
            card.append(editor_scroll)
            self.note_counts = self.label("0 words · 0 characters", "muted", "small")
            card.append(self.note_counts)
            note_actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=4,
                                       row_spacing=8, column_spacing=8)
            self.note_save_button = self.button("Save page", lambda b: self.save_note(), True)
            note_actions.append(self.note_save_button)
            self.archive_button = self.button("Archive", lambda b: self.archive_note())
            self.archive_button.set_sensitive(False)
            note_actions.append(self.archive_button)
            export_button = Gtk.MenuButton(label="Export…", css_classes=["secondary"])
            export_menu = Gtk.Popover()
            export_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.margin(export_box, 8)
            for format, name in (("markdown", "Markdown (.md)"), ("text", "Plain text (.txt)")):
                def export(button, kind=format):
                    export_menu.popdown()
                    self.export_note(kind)
                export_box.append(self.button(name, export))
            export_menu.set_child(export_box)
            export_button.set_popover(export_menu)
            note_actions.append(export_button)
            card.append(note_actions)
            self.note_status = self.label("A fresh page · Ctrl + S to save", "muted", "small")
            card.append(self.note_status)
            panes.set_end_child(card)
            return scroll

        def notes(self):
            if self.note_store is None:
                self.note_store = studio.NoteStore()
            return self.note_store

        def refresh_notes(self):
            if not hasattr(self, "notes_list"):
                return
            self.loading_note_list = True
            try:
                listing = self.notes().list_archived if self.notes_archived else self.notes().list_notes
                rows = listing(self.note_search.get_text())
                self.clear_children(self.notes_list)
                self.note_count.set_text(str(len(rows)))
                if not rows:
                    empty = self.action_row("Nothing here yet", "Your archived pages appear here." if self.notes_archived else "Create a page or try another search.")
                    empty.set_selectable(False)
                    empty.set_activatable(False)
                    self.notes_list.append(empty)
                for note in rows:
                    stamp = str(note.get("updated_at", "")).replace("T", " ").replace("+00:00", " UTC")
                    row = self.action_row(note["title"], stamp)
                    row.set_title_lines(2)
                    row.set_subtitle_lines(1)
                    row.note_id = note["id"]
                    self.notes_list.append(row)
                    if note["id"] == self.note_id:
                        self.notes_list.select_row(row)
            except (OSError, ValueError) as error:
                self.toast(error)
            finally:
                self.loading_note_list = False

        def update_note_counts(self):
            body = self.text(self.note_body)
            self.note_counts.set_text(f"{len(body.split()):,} words · {len(body):,} characters")

        def note_changed(self, *args):
            self.update_note_counts()
            if not self.loading_note:
                self.note_dirty = True
                self.note_status.set_text("Unsaved changes · Ctrl + S to save")

        def note_selected(self, listing, row):
            if self.loading_note_list or row is None or not hasattr(row, "note_id") or row.note_id == self.note_id:
                return
            self.guard_note_changes(lambda: self.load_note(row.note_id))

        def set_note_editable(self, editable):
            self.note_title.set_editable(editable)
            self.note_body.set_editable(editable)
            self.note_body.set_cursor_visible(editable)
            self.note_save_button.set_sensitive(editable)
            self.archive_button.set_label("Archive" if editable else "Restore page")

        def toggle_note_archive(self, button):
            desired = button.get_active()
            if desired == self.notes_archived:
                return
            # The toggle reflects the current view until unsaved changes are resolved.
            button.set_active(self.notes_archived)
            def change():
                self.notes_archived = desired
                self.note_archive_toggle.set_active(desired)
                self.clear_note(keep_archive=True)
                self.refresh_notes()
            self.guard_note_changes(change)

        def load_note(self, note_id):
            try:
                read = self.notes().read_archived if self.notes_archived else self.notes().read
                note = read(note_id)
                self.loading_note = True
                self.note_id = note_id
                self.note_title.set_text(note["title"])
                self.note_body.get_buffer().set_text(note["body"])
                self.note_dirty = False
                self.set_note_editable(not self.notes_archived)
                self.note_status.set_text("Archived page · restore it to make changes" if self.notes_archived else "Saved on this device")
                self.archive_button.set_sensitive(True)
            except (OSError, ValueError) as error:
                self.toast(error)
            finally:
                self.loading_note = False

        def clear_note(self, keep_archive=False):
            self.loading_note = True
            if not keep_archive:
                self.notes_archived = False
                self.note_archive_toggle.set_active(False)
            self.note_id = None
            self.note_title.set_text("")
            self.note_body.get_buffer().set_text("")
            self.note_dirty = False
            self.set_note_editable(not self.notes_archived)
            self.note_status.set_text("Select an archived page to read or restore it" if self.notes_archived else "A fresh page · Ctrl + S to save")
            self.archive_button.set_sensitive(False)
            self.notes_list.unselect_all()
            self.loading_note = False
            self.update_note_counts()
            if not self.notes_archived:
                self.note_title.grab_focus()

        def new_note_template(self, name):
            templates = {
                "blank": ("", ""),
                "project": ("New project", "## The goal\n\nWhat would a good outcome look like?\n\n## Next steps\n\n- [ ] First small step\n- [ ] Next milestone\n\n## Decisions and notes\n\n"),
                "daily": (datetime.now().strftime("%A, %d %B"), "## Today, I want to…\n\n1. \n2. \n3. \n\n## A good thing to remember\n\n"),
                "research": ("Research notes", "## The question\n\n\n## Sources\n\n- \n\n## Findings\n\n\n## Open questions\n\n"),
            }
            if name not in templates:
                return
            def create():
                self.clear_note()
                title, body = templates[name]
                self.note_title.set_text(title)
                self.note_body.get_buffer().set_text(body)
                if name == "blank":
                    self.note_dirty = False
                    self.note_status.set_text("A fresh page · Ctrl + S to save")
                self.mode_buttons["notes"].set_active(True)
                self.refresh_notes()
            self.guard_note_changes(create)

        def save_note(self):
            if self.notes_archived:
                self.toast("Restore an archived page before editing it")
                return False
            try:
                self.note_id = self.notes().save(self.note_title.get_text(), self.text(self.note_body), self.note_id)
                self.note_dirty = False
                self.note_status.set_text("Saved on this device")
                self.archive_button.set_sensitive(True)
                self.refresh_notes()
                self.refresh_home()
                self.toast("Page saved")
                return True
            except (OSError, ValueError) as error:
                self.toast(error)
                return False

        def export_note(self, format):
            try:
                value = studio.note_export({"title": self.note_title.get_text(), "body": self.text(self.note_body)}, format)
                suffix = ".md" if format == "markdown" else ".txt"
                self.file_dialog("Export this page", Gtk.FileChooserAction.SAVE, "Export", lambda path: self.write_result(path, value), filename="livara-note" + suffix)
            except (OSError, ValueError) as error:
                self.toast(error)

        def guard_note_changes(self, continuation):
            if not self.note_dirty:
                continuation()
                return
            dialog = Adw.MessageDialog.new(self.window, "Keep your changes?", "This note has changes that have not been saved.")
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("discard", "Discard changes")
            dialog.add_response("save", "Save changes")
            dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("save")
            dialog.set_close_response("cancel")

            def respond(d, response):
                if response == "discard" or (response == "save" and self.save_note()):
                    continuation()
                elif response == "cancel":
                    self.refresh_notes()
                d.destroy()

            dialog.connect("response", respond)
            dialog.present()

        def archive_note(self):
            if self.notes_archived and self.note_id is not None:
                try:
                    identifier = self.note_id
                    self.notes().restore(identifier)
                    self.clear_note()
                    self.load_note(identifier)
                    self.refresh_notes()
                    self.refresh_home()
                    self.toast("Page restored to your notebook")
                except (OSError, ValueError) as error:
                    self.toast(error)
                return
            if self.note_id is None:
                self.toast("Save this note before archiving it")
                return
            self.guard_note_changes(self.confirm_archive_note)

        def confirm_archive_note(self):
            dialog = Adw.MessageDialog.new(self.window, "Archive this note?", "The saved note moves into Studio’s private archive. Unsaved edits are not archived.")
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("archive", "Archive note")
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")

            def respond(d, response):
                if response == "archive":
                    try:
                        self.notes().archive(self.note_id)
                        self.clear_note()
                        self.refresh_notes()
                        self.refresh_home()
                        self.toast("Note archived")
                    except (OSError, ValueError) as error:
                        self.toast(error)
                d.destroy()

            dialog.connect("response", respond)
            dialog.present()

        def build_focus_page(self):
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
            self.margin(page, 28)
            scroll.set_child(page)
            page.append(self.label("ONE THING AT A TIME", "eyebrow"))
            page.append(self.label("A little space to do your best work.", "page-title"))
            page.append(self.label("Choose your intention. Set aside a little time. Let the rest wait.", "muted"))
            session = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=2,
                                  row_spacing=16, column_spacing=16, homogeneous=True)
            hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, css_classes=["studio-hero"], width_request=290)
            title = self.label("YOUR FOCUS SESSION", "eyebrow")
            title.set_halign(Gtk.Align.CENTER)
            hero.append(title)
            self.timer_stack = Gtk.Stack(transition_duration=180, transition_type=Gtk.StackTransitionType.CROSSFADE if self.animations else Gtk.StackTransitionType.NONE,
                                         vexpand=True, margin_top=20, margin_bottom=20)
            self.timer_labels = [Gtk.Label(label="25:00", css_classes=["timer-value"]), Gtk.Label(label="25:00", css_classes=["timer-value"])]
            for number, label in enumerate(self.timer_labels):
                self.timer_stack.add_named(label, str(number))
            self.timer_stack.set_visible_child_name("0")
            hero.append(self.timer_stack)
            self.focus_progress = Gtk.ProgressBar(css_classes=["focus-progress"])
            hero.append(self.focus_progress)
            self.focus_status = self.label("Ready when you are.", "muted")
            self.focus_status.set_halign(Gtk.Align.CENTER)
            hero.append(self.focus_status)
            actions = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
            self.focus_start = self.button("Start session", lambda b: self.start_focus(), True)
            self.focus_pause = self.button("Pause", lambda b: self.pause_focus())
            self.focus_pause.set_sensitive(False)
            actions.append(self.focus_start)
            actions.append(self.focus_pause)
            actions.append(self.button("Reset", lambda b: self.reset_focus()))
            hero.append(actions)
            hero.append(self.label("Ctrl + Shift + Space · pause or resume", "muted", "small"))
            session.append(hero)
            intention = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, css_classes=["studio-card"], width_request=260)
            intention.append(self.label("SET AN INTENTION", "eyebrow"))
            intention.append(self.label("What matters right now?", "card-title"))
            self.focus_label = Gtk.Entry(placeholder_text="One task to give your attention", max_length=100)
            intention.append(self.focus_label)
            intention.append(self.label("MAKE A LITTLE TIME", "eyebrow"))
            duration_row = Gtk.Box(spacing=12)
            self.focus_minutes = Gtk.SpinButton.new_with_range(1, 180, 1)
            self.focus_minutes.set_value(25)
            self.focus_minutes.connect("value-changed", self.focus_duration_changed)
            duration_row.append(self.focus_minutes)
            duration_row.append(self.label("minutes", "muted"))
            intention.append(duration_row)
            presets = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=2, max_children_per_line=4,
                                  row_spacing=7, column_spacing=7, homogeneous=True)
            self.focus_presets = []
            for minutes in (15, 25, 45, 60):
                button = self.button(str(minutes) + " min", lambda b, value=minutes: self.focus_minutes.set_value(value))
                self.focus_presets.append(button)
                presets.append(button)
            intention.append(presets)
            intention.append(Gtk.Box(vexpand=True))
            intention.append(self.label("Small promises. Real progress.", "card-title"))
            intention.append(self.label("Only finished sessions enter your history. A reset gives you a fresh start.", "muted", "small"))
            session.append(intention)
            page.append(session)
            self.focus_metrics = Gtk.Box(spacing=12, homogeneous=True)
            page.append(self.focus_metrics)
            history_header = Gtk.Box(spacing=10)
            history_header.append(self.label("YOUR COMPLETED SESSIONS", "eyebrow"))
            history_header.append(Gtk.Box(hexpand=True))
            history_header.append(self.button("Refresh", lambda b: self.refresh_focus_history()))
            page.append(history_header)
            self.focus_history_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            page.append(self.focus_history_list)
            return scroll

        def refresh_focus_history(self):
            if not hasattr(self, "focus_history_list"):
                return
            self.clear_children(self.focus_history_list)
            self.clear_children(self.focus_metrics)
            try:
                history = studio.focus_history(30)
                total_minutes = sum(item["seconds"] for item in history) // 60
                longest = max((item["seconds"] for item in history), default=0) // 60
                for value, title in ((len(history), "Completed · last 30 sessions"), (total_minutes, "Minutes of focused work"), (longest, "Longest session · minutes")):
                    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, css_classes=["studio-card"])
                    card.append(self.label(value, "metric"))
                    card.append(self.label(title, "muted", "small"))
                    self.focus_metrics.append(card)
                if not history:
                    self.focus_history_list.append(self.action_row("Your first small victory is ahead", "Complete a session to see it here. There is no rush."))
                for item in history[:8]:
                    minutes = item["seconds"] / 60
                    stamp = str(item.get("completed_at", "")).replace("T", " ").replace("+00:00", " UTC")
                    row = self.action_row(item.get("label") or "Focus session", stamp)
                    row.add_suffix(Gtk.Label(label=f"{minutes:g} min", css_classes=["muted"]))
                    self.focus_history_list.append(row)
            except (OSError, ValueError) as error:
                self.focus_history_list.append(self.action_row("History is unavailable", str(error)))

        def focus_duration_changed(self, spin):
            if self.focus_state in ("ready", "complete"):
                self.focus_state = "ready"
                self.focus_start.set_label("Start session")
                self.focus_total = int(spin.get_value()) * 60
                self.focus_remaining = self.focus_total
                self.update_focus_display()

        def remove_focus_source(self):
            if self.focus_source is not None:
                GLib.source_remove(self.focus_source)
                self.focus_source = None

        def start_focus(self):
            if self.focus_state == "running":
                return
            if self.focus_state != "paused":
                self.focus_total = int(self.focus_minutes.get_value()) * 60
                self.focus_remaining = self.focus_total
                self.focus_label_text = self.focus_label.get_text().strip()
            self.focus_deadline = time.monotonic() + self.focus_remaining
            self.focus_state = "running"
            self.focus_start.set_sensitive(False)
            self.focus_pause.set_sensitive(True)
            self.focus_minutes.set_sensitive(False)
            self.focus_label.set_sensitive(False)
            for button in self.focus_presets:
                button.set_sensitive(False)
            self.focus_status.set_text("One thing at a time. You’ve got this.")
            self.focus_source = GLib.timeout_add(100 if self.animations else 500, self.focus_tick)
            self.update_focus_display()

        def pause_focus(self):
            if self.focus_state != "running":
                return
            self.focus_remaining = max(0, self.focus_deadline - time.monotonic())
            self.remove_focus_source()
            self.focus_state = "paused"
            self.focus_pause.set_sensitive(False)
            self.focus_start.set_label("Resume")
            self.focus_start.set_sensitive(True)
            self.focus_status.set_text("Paused. Take the time you need.")
            self.update_focus_display()

        def reset_focus(self):
            self.remove_focus_source()
            self.focus_state = "ready"
            self.focus_total = int(self.focus_minutes.get_value()) * 60
            self.focus_remaining = self.focus_total
            self.focus_start.set_label("Start session")
            self.focus_start.set_sensitive(True)
            self.focus_pause.set_sensitive(False)
            self.focus_minutes.set_sensitive(True)
            self.focus_label.set_sensitive(True)
            for button in self.focus_presets:
                button.set_sensitive(True)
            self.focus_status.set_text("Ready when you are. The unfinished session was not logged.")
            self.update_focus_display()

        def focus_tick(self):
            if self.focus_state != "running":
                self.focus_source = None
                return GLib.SOURCE_REMOVE
            self.focus_remaining = max(0, self.focus_deadline - time.monotonic())
            self.update_focus_display()
            if self.focus_remaining <= 0:
                self.focus_source = None
                self.focus_state = "complete"
                self.focus_status.set_text("Session complete. A little progress goes a long way.")
                self.focus_start.set_label("Start another")
                self.focus_start.set_sensitive(True)
                self.focus_pause.set_sensitive(False)
                self.focus_minutes.set_sensitive(True)
                self.focus_label.set_sensitive(True)
                for button in self.focus_presets:
                    button.set_sensitive(True)
                try:
                    studio.record_focus(self.focus_total, self.focus_label_text)
                    self.refresh_focus_history()
                    self.refresh_home()
                    self.toast("Focus session complete and saved")
                except (OSError, ValueError) as error:
                    self.toast(f"Session complete; history could not be saved: {error}")
                notification = Gio.Notification.new("Your focus session is complete")
                notification.set_body(self.focus_label_text or f"You completed {self.focus_total // 60} minutes of focused work.")
                self.send_notification("focus-complete", notification)
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        def update_focus_display(self):
            remaining = max(0, int(self.focus_remaining + 0.999))
            value = f"{remaining // 60:02d}:{remaining % 60:02d}"
            if value != self.focus_display_value:
                other = "1" if self.timer_stack.get_visible_child_name() == "0" else "0"
                self.timer_labels[int(other)].set_text(value)
                self.timer_stack.set_visible_child_name(other)
                self.focus_display_value = value
            self.focus_progress.set_fraction(max(0, min(1, 1 - self.focus_remaining / max(1, self.focus_total))))

        def close_requested(self, window):
            if self.confirmed_close:
                return False
            if not self.note_dirty and self.focus_state not in ("running", "paused"):
                return False
            parts = []
            if self.note_dirty:
                parts.append("Your note has unsaved changes.")
            if self.focus_state in ("running", "paused"):
                parts.append("Closing stops the focus timer. Unfinished sessions are not logged.")
            dialog = Adw.MessageDialog.new(self.window, "Before you close", " ".join(parts))
            dialog.add_response("cancel", "Keep Studio open")
            dialog.add_response("close", "Close without saving" if self.note_dirty else "Close and stop timer")
            if self.note_dirty:
                dialog.add_response("save", "Save note and close")
                dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")

            def respond(d, response):
                if response == "close" or (response == "save" and self.save_note()):
                    self.confirmed_close = True
                    self.remove_focus_source()
                    self.window.close()
                d.destroy()

            dialog.connect("response", respond)
            dialog.present()
            return True

        def command_line(self, app, request):
            option = request.get_options_dict().lookup_value("tool", None)
            tool = option.get_string() if option else None
            if tool is not None and tool not in {item["id"] for item in studio.TOOLS}: return 2
            self.activate(app)
            if tool is not None: self.open_tool(tool)
            return 0

    argv = sys.argv if Path(sys.argv[0]).name in ("livara-studio", "studio_gui.py") else [sys.argv[0]]
    return Studio().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())

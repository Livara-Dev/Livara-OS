"""Livara's searchable, sectioned design studio.

Search helpers are deliberately independent of GTK so source-only builders can
verify them. The native widgets are loaded only when SettingsStudio is created.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import unicodedata

from . import desktop

SECTION_INFO = OrderedDict((
    ("appearance", ("Look", "Your desktop, your atmosphere.", "Color, light, glass and the view behind it all.")),
    ("windows", ("Windows", "Make every movement feel right.", "Control the details of your windows, from their buttons to their motion.")),
    ("dock", ("Dock", "Keep your favorites close.", "Shape your dock, its behavior, and the way you launch things.")),
    ("typography", ("Type", "Find your everyday type.", "Choose readable fonts, a comfortable scale, and a cursor that suits you.")),
    ("workspaces", ("Spaces", "A little more room to think.", "Workspaces, clock details, and your desktop’s status area.")),
    ("privacy", ("Focus", "Decide what gets your attention.", "Notifications, recent history, and the way your session locks.")),
    ("input", ("Input", "Make every touch your own.", "Tune the pointer, touchpad, and keyboard controls your device exposes.")),
    ("display", ("Display", "Set a gentler glow.", "Adjust the display preferences available in your desktop session.")),
))


def search_text(value: object) -> str:
    """Fold case, compatibility forms and accents; do not interpret regexes."""
    return "".join(char for char in unicodedata.normalize("NFKD", str(value)).casefold() if not unicodedata.combining(char))


def matching_preferences(catalog: list[dict], query: str, section: str | None = None) -> list[dict]:
    tokens = search_text(query[:256]).split()
    matches = []
    for item in catalog:
        if section is not None and item.get("section") != section:
            continue
        keywords = item.get("keywords", [])
        if isinstance(keywords, (tuple, list)):
            keywords = " ".join(str(value) for value in keywords)
        section_info = SECTION_INFO.get(item.get("section"), (item.get("section", ""), "", ""))
        haystack = search_text(" ".join(str(value) for value in (item.get("name", ""), item.get("title", ""), item.get("description", ""), keywords, *section_info)))
        if all(token in haystack for token in tokens):
            matches.append(item)
    return matches


def catalog_sections(catalog: list[dict]) -> list[str]:
    present = {item.get("section", "appearance") for item in catalog}
    return [key for key in SECTION_INFO if key in present] + sorted(present.difference(SECTION_INFO))


class SettingsStudio:
    def __init__(self, owner):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango
        self.Adw, self.Gdk, self.Gio, self.GLib, self.Gtk, self.Pango = Adw, Gdk, Gio, GLib, Gtk, Pango
        self.owner = owner
        self.catalog = desktop.preference_metadata()
        self.sections = catalog_sections(self.catalog)
        self.bindings = {}
        self.rows = {}
        self.row_groups = []
        self.previews = []
        self.signals = []
        self._refresh_source = None
        self._updating = False
        self._preview_window = None
        self.current_section = self.sections[0] if self.sections else "appearance"
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)

    def label(self, text, *classes, wrap=True):
        return self.Gtk.Label(label=text, xalign=0, wrap=wrap, css_classes=list(classes))

    def button(self, text, callback, *, primary=False, icon=None):
        button = self.Gtk.Button(label=text, css_classes=["lv-primary" if primary else "lv-button"])
        if icon:
            row = self.Gtk.Box(spacing=7, halign=self.Gtk.Align.CENTER)
            row.append(self.Gtk.Image.new_from_icon_name(icon))
            row.append(self.Gtk.Label(label=text))
            button.set_child(row)
        button.connect("clicked", callback)
        return button

    def build(self):
        Gtk = self.Gtk
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["lv-settings"])
        for edge in ("top", "bottom", "start", "end"):
            getattr(self.root, "set_margin_" + edge)(18)
        title_row = Gtk.Box(spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        titles.append(self.label("LIVARA DESIGN STUDIO", "lv-eyebrow"))
        titles.append(self.label("Make it yours.", "lv-studio-title"))
        title_row.append(titles)
        self.save_look_button = self.button("Save this look", lambda b: self.preset_dialog(), primary=True, icon="document-save-symbolic")
        title_row.append(self.save_look_button)
        self.root.append(title_row)
        search_row = Gtk.Box(spacing=10)
        self.search = Gtk.SearchEntry(placeholder_text="Search colors, fonts, dock, windows…", hexpand=True, css_classes=["lv-search"])
        self.search.set_tooltip_text("Search every available setting · Ctrl+F")
        self.search.connect("search-changed", self.filter_changed)
        self.search.connect("stop-search", lambda entry: entry.set_text(""))
        search_row.append(self.search)
        self.search_count = self.label("", "lv-muted", "lv-small")
        search_row.append(self.search_count)
        self.root.append(search_row)
        self.tabs = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=3, max_children_per_line=8, column_spacing=6, row_spacing=6, homogeneous=True, css_classes=["lv-tabs"])
        self.tab_buttons = {}
        group = None
        for section in self.sections:
            label = SECTION_INFO.get(section, (section.title(), "", ""))[0]
            button = Gtk.ToggleButton(label=label, css_classes=["lv-tab"])
            if group:
                button.set_group(group)
            else:
                group = button
            button.connect("toggled", lambda b, s=section: self.select_section(s) if b.get_active() else None)
            self.tabs.insert(button, -1)
            self.tab_buttons[section] = button
        self.root.append(self.tabs)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=180, hexpand=True, vexpand=True)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        self.root.append(self.stack)
        self.section_decor = {}
        self.section_summaries = {}
        self.reset_buttons = {}
        for section in self.sections:
            self.stack.add_named(self.make_section(section), section)
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        empty.append(Gtk.Image.new_from_icon_name("edit-find-symbolic"))
        empty.append(self.label("No controls found", "lv-section-title"))
        empty.append(self.label("Try “font”, “dock”, “blur”, or “clock”.", "lv-muted"))
        empty.append(self.button("Clear search", lambda b: self.search.set_text("")))
        self.stack.add_named(empty, "empty")
        if self.sections:
            self.tab_buttons[self.current_section].set_active(True)
        action = self.Gio.SimpleAction.new("find-settings", None)
        action.connect("activate", self.focus_search)
        self.owner.add_action(action)
        self.owner.set_accels_for_action("app.find-settings", ["<Primary>f"])
        for schema in sorted({desktop.OPTIONS[item["name"]][0] for item in self.catalog if item["name"] in desktop.OPTIONS}):
            settings = desktop.settings_for(schema)
            if settings:
                self.signals.append((settings, settings.connect("changed", self.changed)))
        self.owner.window.connect("unrealize", lambda *args: self.dispose())
        self.signals.append((self.owner.window, self.owner.window.connect('notify::css-classes', self.changed)))
        self.refresh()
        return self.root

    def focus_search(self, *args):
        self.owner.stack.set_visible_child_name("customize")
        self.search.grab_focus()
        self.search.select_region(0, -1)

    def make_section(self, section):
        Gtk = self.Gtk
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(page)
        heading = Gtk.Box(spacing=12, margin_top=4, margin_bottom=2)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        info = SECTION_INFO.get(section, (section.title(), section.title(), ""))
        text.append(self.label(info[1], "lv-section-title"))
        text.append(self.label(info[2], "lv-muted", "lv-small"))
        heading.append(text)
        reset = self.button("Reset section", lambda b, s=section: self.reset_section(s), icon="edit-undo-symbolic")
        self.reset_buttons[section] = reset
        heading.append(reset)
        page.append(heading)
        self.section_decor[section] = []
        if section == "appearance":
            feature_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=2, column_spacing=12, row_spacing=12, homogeneous=True)
            feature_grid.insert(self.make_presets(), -1)
            feature_grid.insert(self.make_preview(section), -1)
            page.append(feature_grid)
            self.section_decor[section].append(feature_grid)
        elif section in ("windows", "typography", "dock"):
            preview = self.make_preview(section)
            page.append(preview)
            self.section_decor[section].append(preview)
        status = self.label("", "lv-muted", "lv-small")
        page.append(status)
        self.section_summaries[section] = status
        entries = [item for item in self.catalog if item.get("section") == section]
        # Window colors are a palette of three compact cards, rather than three
        # more long rows. Every card still has a picker and an explicit hex Apply.
        colors = [item for item in entries if item.get("kind") == "color" and item["name"] in desktop.WINDOW_COLOR_KEYS]
        ordinary = [item for item in entries if item not in colors]
        groups = OrderedDict()
        for item in ordinary:
            name = item["name"]
            if section == "windows":
                group = "MOTION" if name in ("animations", "window-animation-style", "window-animation-duration") else "WINDOW CONTROLS" if name.startswith("window-") else "WINDOW BEHAVIOR"
            elif section == "input":
                group = "TOUCHPAD" if name.startswith("touchpad") else "KEYBOARD" if name.startswith("keyboard") else "POINTER & INTERACTION"
            elif section == "typography":
                group = "YOUR FONTS" if item["kind"] == "font" or name == "titlebar-system-font" else "SCALE & RENDERING"
            elif section == "workspaces":
                group = "STATUS AREA" if name.startswith("clock") or name == "battery-percentage" else "WORKSPACES"
            elif section == "privacy":
                group = "NOTIFICATIONS" if "notification" in name else "HISTORY" if name.startswith("remember-") else "SESSION & LOCK"
            else:
                group = item.get("group", "CONTROLS")
            groups.setdefault(group, []).append(item)
        for group, items in groups.items():
            group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
            group_box.append(self.label(group, "lv-eyebrow"))
            listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["lv-control-list"])
            names = []
            for item in items:
                row = self.make_row(item)
                listing.append(row)
                names.append(item["name"])
            group_box.append(listing)
            page.append(group_box)
            self.row_groups.append((group_box, names))
        if colors:
            palette = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            palette.append(self.label("YOUR WINDOW PALETTE", "lv-eyebrow"))
            grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=3, homogeneous=True, column_spacing=10, row_spacing=10)
            for item in colors:
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["lv-palette-card"])
                card.append(self.label(item["title"], "lv-card-title"))
                widget = self.make_widget(item)
                card.append(widget)
                self.rows[item["name"]] = card
                grid.insert(card, -1)
            palette.append(grid)
            page.append(palette)
            self.row_groups.append((palette, [item["name"] for item in colors]))
        if section == "windows":
            note = self.label("Green can enter full screen in Livara apps; Shift-click maximizes or restores, and F11 toggles full screen. Reopen other GTK apps if their old control style remains. Desktop motion and Efficient rendering take priority over window effects.", "lv-muted", "lv-small")
            page.append(note)
        if section == "appearance":
            advanced = Gtk.Box(spacing=8)
            for title, command in (("Tweaks", "gnome-tweaks"), ("Extensions", "extension-manager"), ("Advanced", "dconf-editor")):
                advanced.append(self.button(title, lambda b, c=command: self.owner.launch_app(c)))
            page.append(advanced)
        page.append(Gtk.Box(height_request=8))
        return scroll

    def make_presets(self):
        Gtk = self.Gtk
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, width_request=280)
        heading = Gtk.Box(spacing=8)
        heading.append(self.label("START WITH A MOOD", "lv-eyebrow", wrap=False))
        heading.append(Gtk.Box(hexpand=True))
        root.append(heading)
        gallery = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=2, homogeneous=True, column_spacing=10, row_spacing=10)
        details = {"Halo": ("Luminous glass · floating dock", "lv-halo"), "Prism": ("Violet · dark · glass", "lv-prism"), "Aurora": ("Sage · dark · glass", "lv-aurora"), "Sunrise": ("Warm · light · glass", "lv-sunrise"), "Classic Desktop": ("A familiar side dock", "lv-classic")}
        for name in desktop.PRESETS:
            subtitle, style = details.get(name, ("Livara desktop preset", "lv-prism"))
            button = Gtk.Button(width_request=140, css_classes=["lv-preset", style])
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
            swatches = Gtk.Box(spacing=4)
            for index in range(3):
                swatches.append(Gtk.Box(width_request=18, height_request=7, css_classes=["lv-swatch", "lv-swatch-" + str(index)]))
            content.append(swatches)
            content.append(self.label(name, "lv-card-title"))
            content.append(self.label(subtitle, "lv-preset-caption"))
            button.set_child(content)
            button.connect("clicked", lambda b, n=name: self.apply_builtin(n))
            gallery.insert(button, -1)
        root.append(gallery)
        custom_head = Gtk.Box(spacing=10, margin_top=5)
        custom_head.append(self.label("SAVED BY YOU", "lv-eyebrow", wrap=False))
        custom_head.append(Gtk.Box(hexpand=True))
        root.append(custom_head)
        self.custom_presets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        saved_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=36, max_content_height=108, propagate_natural_height=True)
        saved_scroll.set_child(self.custom_presets)
        root.append(saved_scroll)
        self.refresh_custom_presets()
        return root

    def refresh_custom_presets(self):
        if getattr(self, '_disposed', False):
            return
        Gtk = self.Gtk
        if not hasattr(self, "custom_presets"):
            return
        while self.custom_presets.get_first_child():
            self.custom_presets.remove(self.custom_presets.get_first_child())
        try:
            presets = desktop.list_custom_presets()
        except (OSError, ValueError) as error:
            self.custom_presets.append(self.label(str(error), "lv-muted", "lv-small"))
            return
        if not presets:
            empty = self.label("Your next favorite look starts here. Save these settings as a named preset.", "lv-muted", "lv-small")
            empty.set_max_width_chars(30)
            self.custom_presets.append(empty)
        for name in presets:
            row = Gtk.Box(spacing=8, css_classes=["lv-saved-preset"])
            apply = self.button(name, lambda b, n=name: self.apply_custom(n))
            apply.set_hexpand(True)
            row.append(apply)
            rename = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Rename “" + name + "”", css_classes=["lv-icon-button"])
            rename.connect("clicked", lambda b, n=name: self.preset_dialog(n))
            row.append(rename)
            delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete “" + name + "”", css_classes=["lv-icon-button"])
            delete.connect("clicked", lambda b, n=name: self.delete_preset(n))
            row.append(delete)
            self.custom_presets.append(row)

    def preset_dialog(self, old_name=None):
        Gtk, Adw = self.Gtk, self.Adw
        dialog = Adw.MessageDialog(transient_for=self.owner.window, modal=True, heading="Rename your look" if old_name else "Save your current look", body="A preset remembers your visual choices, layout and fonts. Focus, privacy and input behavior stay separate. Custom images keep their local file paths.")
        self._preset_dialog = dialog
        entry = Gtk.Entry(text=old_name or "", placeholder_text="For example, Midnight study", max_length=60)
        self._preset_name_entry = entry
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Rename" if old_name else "Save look")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.set_response_enabled("save", bool(entry.get_text().strip()))
        entry.connect("changed", lambda e: dialog.set_response_enabled("save", bool(e.get_text().strip())))
        def response(d, answer):
            if answer == "save":
                try:
                    if old_name:
                        desktop.rename_custom_preset(old_name, entry.get_text())
                    else:
                        desktop.save_custom_preset(entry.get_text())
                    self.refresh_custom_presets()
                    self.owner.toast("Look renamed" if old_name else "Your look is saved")
                except (OSError, ValueError, TypeError) as error:
                    self.owner.toast(error)
            d.destroy()
            self._preset_dialog = None
        dialog.connect("response", response)
        dialog.present()
        entry.grab_focus()

    def delete_preset(self, name):
        try:
            saved = desktop.list_custom_presets()[name]
            desktop.delete_custom_preset(name)
            self.refresh_custom_presets()
            toast = self.Adw.Toast.new("Deleted “" + name + "”")
            toast.set_button_label("Undo")
            self._undo_preset_toast = toast
            def restore(*args):
                try:
                    desktop.save_custom_preset(name, values=saved)
                    self.refresh_custom_presets()
                    self.owner.toast("Look restored")
                except (OSError, ValueError, TypeError) as error:
                    self.owner.toast(error)
            toast.connect("button-clicked", restore)
            self.owner.toast_overlay.add_toast(toast)
        except (KeyError, OSError, ValueError, TypeError) as error:
            self.owner.toast(error)

    def apply_builtin(self, name):
        self.change(lambda: desktop.apply_preset(name), "“" + name + "” is ready")

    def apply_custom(self, name):
        self.change(lambda: desktop.apply_custom_preset(name), "“" + name + "” applied")

    def make_preview(self, section):
        Gtk = self.Gtk
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, width_request=280, css_classes=["lv-preview-card"])
        head = Gtk.Box(spacing=10)
        head.append(self.label("PREVIEW", "lv-eyebrow", wrap=False))
        head.append(Gtk.Box(hexpand=True))
        head.append(self.button("Try a window", lambda b: self.open_preview()))
        root.append(head)
        overlay = Gtk.Overlay(css_classes=["lv-preview-screen"])
        picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER, height_request=142)
        overlay.set_child(picture)
        sample = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        window = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["lv-preview-window"])
        header = Gtk.Box(spacing=6)
        lights = []
        for color in ("close", "minimize", "maximize"):
            dot = Gtk.Box(width_request=13, height_request=13, css_classes=["lv-preview-light", "lv-preview-" + color])
            header.append(dot)
            lights.append(dot)
        header.append(Gtk.Box(hexpand=True))
        header.append(self.label("Livara", "lv-preview-label"))
        window.append(header)
        sample_title = self.label("A space for your next idea.", "lv-preview-title")
        sample_title.set_max_width_chars(24)
        window.append(sample_title)
        detail = self.label("", "lv-preview-label")
        detail.set_max_width_chars(30)
        window.append(detail)
        sample.append(window)
        overlay.add_overlay(sample)
        root.append(overlay)
        modes = Gtk.Box(spacing=8)
        modes.append(self.button("Full Glass", lambda b: self.rendering_mode(True)))
        modes.append(self.button("Efficient", lambda b: self.rendering_mode(False)))
        mode_text = self.label("", "lv-muted", "lv-small", wrap=False)
        mode_text.set_hexpand(True)
        mode_text.set_halign(Gtk.Align.END)
        modes.append(mode_text)
        root.append(modes)
        self.previews.append({"picture": picture, "title": sample_title, "detail": detail, "mode": mode_text, "lights": lights, "section": section})
        return root

    def make_row(self, item):
        Gtk, Adw = self.Gtk, self.Adw
        row = Adw.ActionRow()
        row.set_use_markup(False)
        row.set_title(item["title"])
        row.set_subtitle(item.get("description", ""))
        row.set_subtitle_lines(2)
        row.add_css_class("lv-control-row")
        widget = self.make_widget(item)
        widget.set_valign(Gtk.Align.CENTER)
        row.add_suffix(widget)
        self.rows[item["name"]] = row
        return row

    def make_widget(self, item):
        Gtk, Gdk = self.Gtk, self.Gdk
        name, kind = item["name"], item["kind"]
        current = desktop.read_option(name)
        if kind == "bool":
            widget = Gtk.Switch(valign=Gtk.Align.CENTER)
            widget.connect("notify::active", lambda w, p: self.set_option(name, w.get_active()))
        elif kind in ("int", "float"):
            widget = Gtk.Box(spacing=8)
            minimum, maximum, step = item["range"]
            widget.livara_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minimum, maximum, step)
            widget.livara_scale.set_size_request(112, -1)
            widget.livara_scale.set_draw_value(False)
            widget.livara_spin = Gtk.SpinButton.new_with_range(minimum, maximum, step)
            widget.livara_spin.set_digits(2 if kind == "float" else 0)
            widget.livara_spin.set_width_chars(5)
            widget.livara_spin.set_tooltip_text("Type a value or use the arrow keys")
            widget.append(widget.livara_scale)
            widget.append(widget.livara_spin)
            if item.get("unit"):
                widget.append(self.label(item["unit"], "lv-value"))
            widget.livara_scale.connect("value-changed", lambda w: self.set_option(name, round(w.get_value(), 3) if kind == "float" else round(w.get_value())))
            widget.livara_spin.connect("value-changed", lambda w: self.set_option(name, round(w.get_value(), 3) if kind == "float" else round(w.get_value())))
        elif kind == "choice":
            widget = Gtk.DropDown.new_from_strings([label for value, label in item["choices"]])
            widget.connect("notify::selected", lambda w, p: self.set_option(name, item["choices"][w.get_selected()][0]) if w.get_selected() < len(item["choices"]) else None)
        elif kind == "color":
            widget = Gtk.Box(spacing=6)
            widget.livara_color_picker = Gtk.ColorButton(use_alpha=False, title="Choose " + item["title"].lower(), tooltip_text="Choose a color")
            widget.livara_color_entry = Gtk.Entry(width_chars=8, max_length=7, tooltip_text="Color in #RRGGBB format")
            apply = Gtk.Button(icon_name="emblem-ok-symbolic", tooltip_text="Apply hex color", css_classes=["lv-icon-button"])
            def picked(picker):
                color = picker.get_rgba()
                self.set_option(name, "#{:02x}{:02x}{:02x}".format(*(round(value * 255) for value in (color.red, color.green, color.blue))))
            widget.livara_color_picker.connect("color-set", picked)
            widget.livara_color_entry.connect("activate", lambda e: self.set_option(name, e.get_text()))
            apply.connect("clicked", lambda b: self.set_option(name, widget.livara_color_entry.get_text()))
            widget.append(widget.livara_color_picker)
            widget.append(widget.livara_color_entry)
            widget.append(apply)
        elif kind == "font":
            widget = Gtk.FontButton(use_font=True, use_size=True, title="Choose " + item["title"].lower())
            widget.connect("font-set", lambda b: self.set_option(name, b.get_font()))
        elif kind == "image":
            widget = Gtk.Box(spacing=6)
            widget.livara_image_label = self.button("Choose image…", lambda b: self.choose_wallpaper())
            widget.append(widget.livara_image_label)
            clear = Gtk.Button(icon_name="edit-clear-symbolic", tooltip_text="Use a built-in Livara wallpaper", css_classes=["lv-icon-button"])
            clear.connect("clicked", lambda b: self.set_option(name, ""))
            widget.append(clear)
        elif kind == "strv":
            widget = self.button("Edit names…", lambda b: self.edit_names(item))
        else:
            widget = Gtk.Entry(width_chars=16, max_length=512)
            widget.connect("activate", lambda e: self.set_option(name, e.get_text()))
        widget.set_sensitive(current is not None and item.get("writable", True))
        self.bindings[name] = {"widget": widget, "item": item}
        return widget

    def choose_wallpaper(self):
        Gtk = self.Gtk
        dialog = Gtk.FileChooserNative(title="Choose your desktop image", transient_for=self.owner.window, action=Gtk.FileChooserAction.OPEN, accept_label="Use image", cancel_label="Cancel")
        self._wallpaper_dialog = dialog
        filter_ = Gtk.FileFilter()
        filter_.set_name("PNG, JPEG, or WebP images")
        for mime in ("image/png", "image/jpeg", "image/webp"):
            filter_.add_mime_type(mime)
        dialog.add_filter(filter_)
        def response(chooser, answer):
            if answer == Gtk.ResponseType.ACCEPT:
                file = chooser.get_file()
                if file and file.get_path():
                    self.set_option("wallpaper-image", file.get_path())
            chooser.destroy()
            self._wallpaper_dialog = None
        dialog.connect("response", response)
        dialog.show()

    def edit_names(self, item):
        Gtk, Adw = self.Gtk, self.Adw
        dialog = Adw.MessageDialog(transient_for=self.owner.window, modal=True, heading=item["title"], body="Write one name per line.")
        editor = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10, bottom_margin=10, left_margin=10, right_margin=10)
        editor.get_buffer().set_text("\n".join(desktop.read_option(item["name"]) or []))
        scroll = Gtk.ScrolledWindow(min_content_height=180, min_content_width=300)
        scroll.set_child(editor)
        dialog.set_extra_child(scroll)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Apply names")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        def response(d, answer):
            if answer == "save":
                buffer = editor.get_buffer()
                value = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
                self.set_option(item["name"], value.splitlines())
            d.destroy()
        dialog.connect("response", response)
        dialog.present()

    def reset_section(self, section):
        names = [item["name"] for item in self.catalog if item.get("section") == section and desktop.read_option(item["name"]) is not None]
        self.change(lambda: desktop.reset_options(names), "Section restored to its defaults")

    def rendering_mode(self, full):
        self.change(lambda: desktop.apply_rendering_mode(full), "Full Glass enabled" if full else "Efficient rendering enabled")

    def set_option(self, name, value):
        if not self._updating:
            self.change(lambda: desktop.set_option(name, value))

    def change(self, callback, message=None):
        try:
            callback()
            self.refresh()
            self.owner.refresh_appearance()
            if message:
                self.owner.toast(message)
        except (OSError, ValueError, TypeError, self.GLib.Error) as error:
            self.refresh()
            self.owner.toast(error)

    def changed(self, *args):
        if getattr(self, '_disposed', False):
            return
        if self._refresh_source is None:
            self._refresh_source = self.GLib.idle_add(self._refresh_idle)

    def _refresh_idle(self):
        self._refresh_source = None
        self.refresh()
        return False

    def refresh(self):
        if self._updating or getattr(self, '_disposed', False):
            return
        self._updating = True
        try:
            for name, binding in self.bindings.items():
                item, widget = binding["item"], binding["widget"]
                kind = item["kind"]
                value = desktop.read_option(name)
                reason = desktop.inactive_reason(name) if value is not None else ""
                native = desktop.settings_for(item["schema"])
                writable = bool(native is not None and native.is_writable(item["key"]))
                item["writable"] = writable
                widget.set_sensitive(value is not None and writable and not reason)
                if value is None:
                    widget.set_tooltip_text("This control needs a compatible desktop session")
                    continue
                if not writable:
                    widget.set_tooltip_text("This setting is managed by your system")
                elif reason:
                    widget.set_tooltip_text(reason)
                else:
                    widget.set_tooltip_text(item.get("description", ""))
                service_note = ""
                if name in ("glass-enabled", "blur-radius", "window-animation-style", "window-animation-duration"):
                    service_note = desktop.shell_extension_note("livara-glass@livara.local")
                elif name.startswith("dock-"):
                    service_note = desktop.shell_extension_note("ubuntu-dock@ubuntu.com")
                row = self.rows.get(name)
                if row is not None and hasattr(row, "set_subtitle"):
                    row.set_subtitle(reason or service_note or item.get("description", ""))
                if not reason and writable and service_note:
                    widget.set_tooltip_text(service_note)
                if kind == "bool":
                    widget.set_active(value)
                elif kind in ("int", "float"):
                    widget.livara_scale.set_value(value)
                    widget.livara_spin.set_value(value)
                elif kind == "choice":
                    selected = next((index for index, pair in enumerate(item["choices"]) if pair[0] == value), self.Gtk.INVALID_LIST_POSITION)
                    widget.set_selected(selected)
                elif kind == "color":
                    color = self.Gdk.RGBA()
                    if color.parse(value):
                        widget.livara_color_picker.set_rgba(color)
                    widget.livara_color_entry.set_text(value)
                elif kind == "font":
                    widget.set_font(value)
                elif kind == "image":
                    custom = desktop.get_custom_wallpaper()
                    widget.livara_image_label.set_label(Path(custom).name if custom else "Choose image…")
                    widget.livara_image_label.set_tooltip_text(custom or "Use your own local image")
                elif kind == "strv":
                    widget.set_label(f"{len(value)} names · Edit…")
                else:
                    widget.set_text(str(value))
            self.refresh_preview()
            self.refresh_css()
            self.filter_changed()
        finally:
            self._updating = False

    def refresh_preview(self):
        accent = desktop.read_option("accent") or "purple"
        appearance = desktop.read_option("appearance") or "dark"
        glass = desktop.read_option("glass-enabled") is not False
        radius = desktop.read_option("blur-radius") or 0
        wallpaper = desktop.get_custom_wallpaper()
        if not wallpaper or not Path(wallpaper).is_file():
            name = desktop.read_option("wallpaper") or "glass"
            wallpaper = str(Path("/usr/share/backgrounds/livara") / f"livara-{name}.png")
            if not Path(wallpaper).is_file():
                wallpaper = str(Path(__file__).resolve().parents[2] / "artwork" / f"livara-{name}.png")
        for preview in self.previews:
            if Path(wallpaper).is_file() and getattr(preview["picture"], "livara_filename", None) != wallpaper:
                preview["picture"].set_filename(wallpaper)
                preview["picture"].livara_filename = wallpaper
            live = self.owner.window.has_css_class('lv-native-glass')
            material = 'Live refraction' if glass and live else 'Opaque fallback' if glass else 'Solid surfaces'
            preview["detail"].set_text(f"{desktop.ACCENTS.get(accent, (accent, ''))[0]} · {appearance.title()} · {material}")
            preview["mode"].set_text("Motion off" if desktop.read_option("animations") is False else "Motion on")
            if preview["section"] == "typography":
                font = desktop.read_option("interface-font") or "Sans 11"
                attrs = self.Pango.AttrList()
                attrs.insert(self.Pango.attr_font_desc_new(self.Pango.FontDescription.from_string(font)))
                preview["title"].set_attributes(attrs)
        duration = 180 if desktop.read_option("animations") is not False else 0
        self.stack.set_transition_duration(duration)

    def filter_changed(self, *args):
        if not hasattr(self, "stack"):
            return
        query = self.search.get_text()
        names = {item["name"] for item in matching_preferences(self.catalog, query)}
        active = bool(query.strip())
        self.search_count.set_text(f"{len(names)} controls" if active else "")
        for name, row in self.rows.items():
            row.set_visible(name in names)
        for container, group_names in self.row_groups:
            container.set_visible(any(name in names for name in group_names))
        for section, decorations in self.section_decor.items():
            for widget in decorations:
                widget.set_visible(not active)
            count = sum(item["name"] in names for item in self.catalog if item.get("section") == section)
            self.tab_buttons[section].set_sensitive(count > 0 or not active)
            available = sum(item.get("writable", True) and desktop.read_option(item["name"]) is not None for item in self.catalog if item.get("section") == section)
            self.reset_buttons[section].set_sensitive(available > 0)
            self.section_summaries[section].set_text(f"{count} matching controls" if active else "Changes apply as you explore. Unavailable device controls stay disabled.")
        if not names:
            self.stack.set_visible_child_name("empty")
        else:
            matches = [section for section in self.sections if any(item["name"] in names and item.get("section") == section for item in self.catalog)]
            if self.current_section not in matches:
                self.current_section = matches[0]
            self.stack.set_visible_child_name(self.current_section)
            self.tab_buttons[self.current_section].set_active(True)

    def select_section(self, section):
        self.current_section = section
        if hasattr(self, "stack"):
            self.stack.set_visible_child_name(section)

    def open_preview(self):
        if self._preview_window:
            self._preview_window.present()
            return
        from . import window_style
        Gtk, Adw = self.Gtk, self.Adw
        window = Adw.ApplicationWindow(application=self.owner, title="Livara Design Preview", default_width=560, default_height=350)
        self._preview_window = window
        header = Adw.HeaderBar()
        window.livara_controls = window_style.configure_native_headerbar(window, header)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, css_classes=["lv-settings"], margin_top=18, margin_bottom=18, margin_start=20, margin_end=20)
        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        shell.append(header)
        shell.append(box)
        box.append(self.label("A real window. Your real choices.", "lv-section-title"))
        box.append(self.label("Try its traffic lights, move it, or press F11. Your desktop handles this preview just like any other window.", "lv-muted"))
        box.append(Gtk.Entry(placeholder_text="A place for your next idea…"))
        box.append(self.button("Looks good", lambda b: window.close(), primary=True))
        window.set_content(shell)
        def closed(*args):
            self._preview_window = None
            return False
        window.connect("close-request", closed)
        window.present()

    def refresh_css(self):
        dark = desktop.read_option("appearance") != "light"
        text = "#f5efff" if dark else "#24172f"
        muted = "#b6a7cb" if dark else "#6d5b7b"
        panel = "#211f2a" if dark else "#ffffff"
        border = "rgba(255,255,255,.13)" if dark else "rgba(81,67,97,.11)"
        accent = desktop.ACCENTS.get(desktop.read_option("accent"), desktop.ACCENTS["purple"])[1]
        label_accent = accent if dark else f"shade({accent},.52)"
        glass = desktop.read_option("glass-enabled") is not False
        sheen = f"linear-gradient(135deg,alpha(white,.09),alpha(white,.015) 40%,alpha({accent},.05))" if glass else "none"
        elevation = "inset 0 1px alpha(white,.14),0 8px 24px alpha(black,.10)" if glass else "none"
        close, minimize, maximize = (desktop.read_option(key) or desktop.WINDOW_DEFAULTS[key] for key in desktop.WINDOW_COLOR_KEYS)
        # dconf edits outside this UI are still data, never CSS source.
        for key, value in zip(desktop.WINDOW_COLOR_KEYS, (close, minimize, maximize)):
            try:
                desktop.validate_window_value(key, value)
            except ValueError:
                if key.endswith("close-color"): close = desktop.WINDOW_DEFAULTS[key]
                elif key.endswith("minimize-color"): minimize = desktop.WINDOW_DEFAULTS[key]
                else: maximize = desktop.WINDOW_DEFAULTS[key]
        css = f'''
.lv-settings {{ color: {text}; }}
.lv-settings .lv-eyebrow {{ color: {label_accent}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
.lv-settings .lv-studio-title {{ font-size: 33px; font-weight: 600; letter-spacing: -1px; }}
.lv-settings .lv-section-title {{ font-size: 25px; font-weight: 600; letter-spacing: -.6px; }}
.lv-settings .lv-muted {{ color: {muted}; }}
.lv-settings .lv-small {{ font-size: 11px; }}
.lv-settings .lv-card-title {{ font-size: 15px; font-weight: 600; }}
.lv-settings .lv-button, .lv-settings .lv-icon-button {{ background: alpha({accent},.12); border: 1px solid {border}; border-radius: 12px; padding: 9px 12px; color: {text}; box-shadow: none; }}
.lv-settings .lv-primary {{ background-color:{accent}; background-image:linear-gradient(to bottom,alpha(white,.16),transparent); color:#160822; font-weight:600; border-radius:12px; padding:10px 16px; box-shadow:0 3px 8px alpha(black,.12); }}
.lv-settings .lv-tabs flowboxchild {{ padding: 0; }}
.lv-settings .lv-tab {{ border:1px solid transparent; border-radius:16px; background:alpha({accent},.07); padding:9px 7px; color:{muted}; box-shadow:none; }}
.lv-settings .lv-tab:checked {{ background:alpha({accent},.17); border-color:alpha({accent},.25); color:{text}; }}
.lv-settings .lv-search {{ border-radius:15px; border:1px solid {border}; background:{panel}; padding:8px 12px; }}
.lv-settings .lv-control-list {{ background-color:{panel}; background-image:{sheen}; border:1px solid {border}; border-radius:24px; box-shadow:{elevation}; }}
.lv-settings .lv-control-row {{ background:transparent; padding:4px 3px; }}
.lv-settings .lv-control-row label.subtitle {{ font-size:11px; color:{muted}; }}
.lv-settings .lv-control-list > row:not(:last-child) {{ border-bottom:1px solid alpha(#ac87cc,.10); }}
.lv-settings dropdown > button {{ border-radius:11px; background:alpha({accent},.12); border:1px solid {border}; box-shadow:none; }}
.lv-settings .lv-value {{ min-width:15px; font-size:12px; font-weight:600; color:{label_accent}; }}
.lv-settings .lv-preview-card {{ background-color:{panel}; background-image:{sheen}; border:1px solid {border}; border-radius:22px; padding:18px; box-shadow:{elevation}; }}
.lv-settings .lv-preview-screen {{ border-radius:15px; background:#110a1d; }}
.lv-settings .lv-preview-window {{ background-color:{panel}; background-image:{sheen}; border:1px solid {border}; border-radius:14px; padding:14px; box-shadow:{elevation}; }}
.lv-settings .lv-preview-label {{ color:{muted}; font-size:11px; }}
.lv-settings .lv-preview-title {{ color:{text}; font-size:19px; font-weight:600; }}
.lv-settings .lv-preview-light {{ border-radius:50%; }}
.lv-settings .lv-preview-close {{ background:{close}; }}
.lv-settings .lv-preview-minimize {{ background:{minimize}; }}
.lv-settings .lv-preview-maximize {{ background:{maximize}; }}
.lv-settings .lv-preset {{ border:1px solid {border}; border-radius:17px; background:{panel}; padding:0; box-shadow:none; }}
.lv-settings .lv-preset:hover {{ border-color:{accent}; }}
.lv-settings .lv-preset-caption {{ font-size:10px; color:{muted}; }}
.lv-settings .lv-halo {{ background:linear-gradient(120deg,alpha(#a692f4,.42),alpha(#70cede,.13)); }}
.lv-settings .lv-prism {{ background:linear-gradient(125deg,alpha(#a564e9,.28),{panel}); }}
.lv-settings .lv-aurora {{ background:linear-gradient(125deg,alpha(#49c998,.23),{panel}); }}
.lv-settings .lv-sunrise {{ background:linear-gradient(125deg,alpha(#ffac63,.25),{panel}); }}
.lv-settings .lv-classic {{ background:linear-gradient(125deg,alpha(#ba8a61,.22),{panel}); }}
.lv-settings .lv-swatch {{ border-radius:5px; background:#bf8aff; }}
.lv-settings .lv-aurora .lv-swatch {{ background:#9ce6cb; }}
.lv-settings .lv-sunrise .lv-swatch {{ background:#ffbe8b; }}
.lv-settings .lv-classic .lv-swatch {{ background:#d6b79f; }}
.lv-settings .lv-swatch-1 {{ opacity:.60; }}
.lv-settings .lv-swatch-2 {{ opacity:.30; }}
.lv-settings .lv-saved-preset {{ border:1px solid {border}; border-radius:13px; padding:5px; }}
.lv-settings .lv-palette-card {{ background-color:{panel}; background-image:{sheen}; border:1px solid {border}; border-radius:18px; padding:14px; box-shadow:{elevation}; }}
.lv-settings spinbutton {{ border-radius:10px; background:alpha(#b879f2,.09); border:1px solid {border}; font-size:11px; }}
.lv-settings entry {{ border-radius:11px; padding:7px; }}
'''
        self.css.load_from_data(css.encode())

    def dispose(self):
        if getattr(self, '_disposed', False):
            return
        self._disposed = True
        if self._refresh_source is not None:
            self.GLib.source_remove(self._refresh_source)
            self._refresh_source = None
        for settings, signal in self.signals:
            settings.disconnect(signal)
        self.signals.clear()
        if self._preview_window:
            self._preview_window.close()

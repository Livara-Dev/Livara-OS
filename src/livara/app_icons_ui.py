"""Searchable native icon customization for every exposed desktop launcher."""
from __future__ import annotations

import threading
from . import app_icons


class AppIconsPage:
    def __init__(self, owner):
        from gi.repository import Adw, Gio, GLib, Gtk
        self.Adw, self.Gio, self.GLib, self.Gtk = Adw, Gio, GLib, Gtk
        self.owner = owner
        self.manager = app_icons.IconManager()
        self.apps, self.limit, self.busy = [], 75, False
        self.chooser = None

    def build(self):
        Gtk = self.Gtk
        scroll, box = self.owner.page("YOUR ICONS", "Every app. Your signature.", "Change launcher and dock icons for Livara, default, and other installed apps. Your changes stay in your account.")
        self.root = box
        search_row = Gtk.Box(spacing=10)
        self.search = Gtk.SearchEntry(placeholder_text="Search app names or launcher IDs…", hexpand=True)
        self.search.connect("search-changed", self.filter_changed)
        self.search.connect("stop-search", lambda e: e.set_text(""))
        search_row.append(self.search)
        self.refresh_button = self.owner.button("Refresh", lambda b: self.reload())
        search_row.append(self.refresh_button)
        box.append(search_row)
        filters = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1, max_children_per_line=2, column_spacing=12)
        self.hidden = Gtk.CheckButton(label="Include background launchers")
        self.custom_only = Gtk.CheckButton(label="Only customized icons")
        for widget in (self.hidden, self.custom_only):
            widget.connect("toggled", self.filter_changed); filters.insert(widget, -1)
        box.append(filters)
        self.count = self.owner.label("", "muted", "small");box.append(self.count)
        self.listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        box.append(self.listing)
        self.more = self.owner.button("Show more apps", self.show_more)
        box.append(self.more)
        box.append(self.owner.label("Choose PNG, SVG, JPEG, WebP, ICO, or another supported local image (up to 8 MiB). Livara keeps its own copy, so you can move the original. Some running apps need reopening; app-internal toolbar and website icons follow their own settings.", "muted", "small"))
        self.status = self.owner.label("", "small");box.append(self.status)
        self.owner.window.connect("close-request", lambda window: self.busy)
        self.reload()
        return scroll

    def reload(self):
        if self.busy: return
        try:
            self.apps = app_icons.installed_apps()
            self.filter_changed()
        except (OSError, ValueError) as error: self.owner.toast(str(error))

    def filter_changed(self, *args):
        self.limit = 75;self.render()

    def show_more(self, *args):
        self.limit += 75;self.render()

    def render(self):
        Gtk = self.Gtk
        child = self.listing.get_first_child()
        while child:
            nxt = child.get_next_sibling();self.listing.remove(child);child = nxt
        matches = app_icons.search_apps(self.apps, self.search.get_text(), include_hidden=self.hidden.get_active())
        if self.custom_only.get_active(): matches = [app for app in matches if self.manager.customized(app.id)]
        self.count.set_text(f"{len(matches)} app{'s' if len(matches) != 1 else ''} · showing {min(len(matches), self.limit)}")
        for app in matches[:self.limit]:
            custom = self.manager.customized(app.id)
            row = self.Adw.ActionRow(title=app.name, subtitle=app.id + (" · Custom icon" if custom else ""))
            row.set_use_markup(False)
            row.set_title_lines(2);row.set_subtitle_lines(1)
            row.set_tooltip_text(app.id)
            image = Gtk.Image.new_from_gicon(app.icon) if app.icon else Gtk.Image.new_from_icon_name("application-x-executable")
            image.set_pixel_size(40);image.set_margin_end(8);row.add_prefix(image)
            actions = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
            choose = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Choose icon for " + app.name)
            choose.connect("clicked", lambda b, a=app: self.choose(a))
            restore = Gtk.Button(icon_name="edit-undo-symbolic", tooltip_text="Restore original icon for " + app.name)
            restore.set_sensitive(custom and not self.busy)
            restore.connect("clicked", lambda b, a=app: self.restore(a))
            actions.append(choose);actions.append(restore);row.add_suffix(actions)
            self.listing.append(row)
        if not matches:
            row = self.Adw.ActionRow(title="No apps found", subtitle="Try another name, show background launchers, or refresh after installing an app.")
            self.listing.append(row)
        self.more.set_visible(len(matches) > self.limit)
        self.listing.set_sensitive(not self.busy)

    def choose(self, app):
        Gtk = self.Gtk
        if self.busy or self.chooser is not None: return
        dialog = Gtk.FileChooserNative(title="Choose icon for " + app.name, transient_for=self.owner.window, action=Gtk.FileChooserAction.OPEN, accept_label="Use icon", cancel_label="Cancel")
        dialog.set_modal(True)
        self.chooser = dialog
        filter_ = Gtk.FileFilter();filter_.set_name("Images and SVG icons")
        filter_.add_pixbuf_formats();filter_.add_mime_type("image/svg+xml");dialog.add_filter(filter_)
        def response(chooser, answer):
            if answer == Gtk.ResponseType.ACCEPT:
                file = chooser.get_file()
                if file and file.get_path(): self.apply(app, file.get_path())
            chooser.destroy();self.chooser = None
        dialog.connect("response", response);dialog.show()

    def apply(self, app, filename):
        self.work(lambda: self.manager.apply(app, filename), "Custom icon saved for " + app.name)

    def restore(self, app):
        self.work(lambda: self.manager.restore(app.id), "Original icon restored for " + app.name)

    def work(self, operation, message):
        if self.busy: return
        self.busy = True;self.listing.set_sensitive(False);self.refresh_button.set_sensitive(False)
        self.status.set_text("Updating your app icon…")
        def run():
            try: operation();error = None
            except Exception as exception: error = str(exception)
            self.GLib.idle_add(self.finished, message, error)
        threading.Thread(target=run, daemon=True).start()

    def finished(self, message, error):
        self.busy = False;self.refresh_button.set_sensitive(True)
        self.status.set_text(error or message)
        self.owner.toast(error or message)
        self.reload()
        return False

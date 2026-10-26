"""Enable clear GTK chrome only while GNOME confirms a live optical backplate.

No screenshots or desktop capture happen in apps. Losing the compositor service
immediately restores the normal opaque material. Widgets and text stay sharp.
"""
from __future__ import annotations

_provider = None
CSS = """
window.lv-native-glass, window.lv-native-glass > contents {
 background-color: transparent; background-image: none;
}
.lv-native-glass headerbar {
 background-color: rgba(28,34,50,.12);
 background-image: linear-gradient(to bottom,rgba(255,255,255,.10),rgba(255,255,255,.01));
 border-bottom: 1px solid rgba(230,240,255,.22);
}
.lv-native-glass .sidebar, .lv-native-glass .studio-sidebar,
.lv-native-glass .navigation-sidebar {
 background-color: rgba(28,34,50,.10); background-image: none;
 border-right: 1px solid rgba(230,240,255,.22);
}
.lv-native-glass .halo-sidebar { background-color:rgba(28,34,50,.10); }
.lv-native-glass .lv-content-canvas {
 background-color: rgba(16,20,32,.68); border-radius: 22px;
}
window.lv-native-glass.lv-native-glass-light {
 background-color: rgba(245,248,255,.70);
}
.lv-native-glass-light headerbar, .lv-native-glass-light .sidebar,
.lv-native-glass-light .studio-sidebar,
.lv-native-glass-light .navigation-sidebar { background-color: rgba(245,248,255,.28); }
.lv-native-glass-light .lv-content-canvas { background-color: rgba(250,251,255,.78); }
"""


class NativeGlass:
    def __init__(self, window, headerbar):
        import gi
        gi.require_version('Gtk', '4.0')
        from gi.repository import Gio, Gtk, Gdk, Adw
        global _provider
        self.window = window
        self.headerbar = headerbar
        self.active = False
        self.surface = None
        self.region_idle = 0
        self.sidebar = None
        self.sidebar_searched = False
        self.last_regions = None
        self.id = window.get_application().get_application_id()
        self.key = window.get_application().get_dbus_object_path() + '/window/' + str(window.get_id())
        self.stopped = False
        self.epoch = 0
        self.proxy = None
        self.signals = []
        self.Gio = Gio
        self.theme = Adw.StyleManager.get_default()
        self.theme_signal = self.theme.connect('notify::dark', lambda *args: self.update_theme())
        if _provider is None:
            _provider = Gtk.CssProvider()
            _provider.load_from_data(CSS.encode())
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), _provider,
                                                     Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        window.connect('destroy', self.destroy)
        window.connect('realize', self.realized)
        window.connect('unrealize', self.unrealized)
        self.update_theme()
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_AUTO_START,
                                 None, 'org.livara.Glass', '/org/livara/Glass',
                                 'org.livara.Glass1', None, self.connected)

    def set_active(self, active):
        if self.stopped:
            return
        self.active = active
        if active:
            self.last_regions = None
            self.window.add_css_class('lv-native-glass')
            self.queue_regions()
        else:
            self.window.remove_css_class('lv-native-glass')

    def realized(self, *_args):
        self.surface = self.window.get_surface()
        if self.surface:
            self.surface_signal = self.surface.connect('layout', self.queue_regions)

    def unrealized(self, *_args):
        if self.surface:
            self.surface.disconnect(self.surface_signal)
            self.surface = None

    def queue_regions(self, *_args):
        from gi.repository import GLib
        if not self.stopped and self.active and not self.region_idle:
            self.region_idle = GLib.idle_add(self.send_regions)

    def send_regions(self):
        from gi.repository import GLib
        self.region_idle = 0
        if self.stopped or not self.active:
            return False
        if not self.sidebar_searched:
            self.sidebar_searched = True
            pending = [self.window]
            for _ in range(4096):
                if not pending:
                    break
                widget = pending.pop()
                if any(widget.has_css_class(c) for c in ('sidebar', 'studio-sidebar', 'navigation-sidebar')):
                    self.sidebar = widget
                    break
                child = widget.get_last_child()
                while child:
                    pending.append(child)
                    child = child.get_prev_sibling()
        rectangles = []
        for widget in (self.headerbar, self.sidebar):
            if widget is None:
                continue
            valid, bounds = widget.compute_bounds(self.window)
            if not valid:
                continue
            x, y = max(0., bounds.get_x()), max(0., bounds.get_y())
            width = max(0., min(bounds.get_width(), self.window.get_width() - x))
            height = max(0., min(bounds.get_height(), self.window.get_height() - y))
            rectangles.append((x, y, width, height))
        if rectangles == self.last_regions:
            return False
        self.last_regions = rectangles
        self.proxy.call('SetRegions', GLib.Variant('(ssa(dddd))', (self.id, self.key, rectangles)),
                        self.Gio.DBusCallFlags.NO_AUTO_START, 1000, None, self.regions_finished)
        return False

    def regions_finished(self, proxy, result):
        try:
            proxy.call_finish(result)
        except Exception:
            # The full-window optical plate remains the fallback on older
            # compositor revisions, without clearing any additional surfaces.
            pass

    def update_theme(self):
        if self.stopped:
            return
        if self.theme.get_dark():
            self.window.remove_css_class('lv-native-glass-light')
        else:
            self.window.add_css_class('lv-native-glass-light')

    def connected(self, _source, result):
        try:
            proxy = self.Gio.DBusProxy.new_for_bus_finish(result)
        except Exception:
            return
        if self.stopped:
            return
        self.proxy = proxy
        self.signals = [proxy.connect('g-signal', self.changed),
                        proxy.connect('notify::g-name-owner', lambda *args: self.refresh())]
        self.refresh()

    def refresh(self):
        from gi.repository import GLib
        if self.stopped:
            return
        self.epoch += 1
        epoch = self.epoch
        if not self.proxy.get_name_owner():
            self.set_active(False)
            return
        self.proxy.call('GetStatus', GLib.Variant('(ss)', (self.id, self.key)),
                        self.Gio.DBusCallFlags.NO_AUTO_START, 1000, None,
                        lambda proxy, result: self.status(proxy, result, epoch))

    def status(self, proxy, result, epoch):
        try:
            active = proxy.call_finish(result).unpack()[0]
        except Exception:
            active = False
        # A late reply from a dead owner must never clear the opaque fallback.
        if epoch == self.epoch:
            self.set_active(active and bool(proxy.get_name_owner()))

    def changed(self, _proxy, _sender, name, values):
        if name == 'Changed':
            app, path, active = values.unpack()
            if app == self.id and path == self.key:
                self.epoch += 1
                self.set_active(active)

    def destroy(self, *_args):
        from gi.repository import GLib
        self.stopped = True
        if self.region_idle:
            GLib.source_remove(self.region_idle)
            self.region_idle = 0
        self.unrealized()
        self.theme.disconnect(self.theme_signal)
        if self.proxy:
            for signal in self.signals:
                self.proxy.disconnect(signal)
        self.signals.clear()


def attach(window, headerbar):
    application = window.get_application()
    if (application and application.get_dbus_object_path() and hasattr(window, 'get_id')
            and not hasattr(window, '_livara_glass')):
        window._livara_glass = NativeGlass(window, headerbar)

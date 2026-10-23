"""Native GTK window controls; importing this module does not load GI.

The buttons invoke Gtk.Window operations, so the application's close-request
handlers and the window manager remain responsible for closing and positioning.
"""
from __future__ import annotations


def button_side(layout: str | None) -> str:
    """Return the headerbar packing side containing the close button."""
    left, _, right = str(layout or "close,minimize,maximize:").partition(":")
    if "close" in left.split(","):
        return "start"
    if "close" in right.split(","):
        return "end"
    return "start" if left.strip() else "end"


def packing_side(layout: str | None, *, rtl: bool = False) -> str:
    """Convert the requested physical edge to Gtk.HeaderBar logical packing."""
    side = button_side(layout)
    return {"start": "end", "end": "start"}[side] if rtl else side


def green_operation(action: str, *, fullscreen: bool, maximized: bool,
                    shift: bool = False) -> str:
    """Choose an operation from actual native window state."""
    if shift or action == "maximize":
        return "unmaximize" if maximized else "maximize"
    return "unfullscreen" if fullscreen else "fullscreen"


def _window_state(window, name: str) -> bool:
    try:
        return bool(getattr(window, "is_" + name)())
    except (AttributeError, TypeError):
        return False


class NativeHeaderbar:
    """A retained, disposable binding between one headerbar and its settings."""

    def __init__(self, window, headerbar, Gtk, Gdk):
        from . import desktop, window_style

        self.window = window
        self.headerbar = headerbar
        self.Gtk = Gtk
        self.Gdk = Gdk
        self._style = window_style
        self._disposed = False
        self._side = None
        self._shift = False
        self._settings_signals = []
        self._window_signals = []
        self._headerbar_signals = []
        self._stock = {}
        self.values = {}
        # Adw.HeaderBar wraps a Gtk.CenterBox whose direction can differ from
        # the headerbar widget. Physical start/end placement follows that box.
        def packing_widget(widget):
            if isinstance(widget, Gtk.CenterBox):
                return widget
            child = widget.get_first_child()
            while child is not None:
                found = packing_widget(child)
                if found is not None:
                    return found
                child = child.get_next_sibling()
            return None
        self._packing_widget = packing_widget(headerbar) or headerbar
        window_style.install_live_style()
        if hasattr(headerbar, "get_show_start_title_buttons"):
            for side in ("start", "end"):
                self._stock[side] = getattr(headerbar, "get_show_" + side + "_title_buttons")()
        elif hasattr(headerbar, "get_show_title_buttons"):
            self._stock["all"] = headerbar.get_show_title_buttons()

        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7,
                           valign=Gtk.Align.CENTER,
                           css_classes=["livara-window-controls"])
        self.box.set_direction(Gtk.TextDirection.LTR)
        self.buttons = {}
        for name, symbol in (("close", "×"), ("minimize", "−"), ("maximize", "↗")):
            button = Gtk.Button(valign=Gtk.Align.CENTER,
                                css_classes=["livara-window-control", "livara-" + name, name])
            label = Gtk.Label(label=symbol, css_classes=["livara-control-symbol"])
            button.set_child(label)
            button.set_focus_on_click(False)
            self.buttons[name] = button
            self.box.append(button)
        self._label(self.buttons["close"], "Close window")
        self._label(self.buttons["minimize"], "Minimize window")
        self.buttons["close"].connect("clicked", lambda button: self.window.close())
        self.buttons["minimize"].connect("clicked", lambda button: self.window.minimize())
        self.buttons["maximize"].connect("clicked", self._green_clicked)

        # Record Shift before Gtk.Button handles the click. Do not claim the
        # gesture; pointer and keyboard activation continue through GTK normally.
        gesture = Gtk.GestureClick.new()
        gesture.set_button(1)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect("pressed", self._pressed)
        self.buttons["maximize"].add_controller(gesture)
        self.green_gesture = gesture
        keys = Gtk.EventControllerKey.new()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key_pressed)
        self.buttons["maximize"].add_controller(keys)
        self.green_keys = keys

        self.shortcuts = Gtk.ShortcutController.new()
        self.shortcuts.set_scope(Gtk.ShortcutScope.MANAGED)
        self.shortcuts.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.shortcuts.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_F11, Gdk.ModifierType(0)),
            Gtk.CallbackAction.new(self._fullscreen_shortcut)))
        window.add_controller(self.shortcuts)
        for signal in ("notify::fullscreened", "notify::maximized"):
            self._window_signals.append(window.connect(signal, lambda *args: self._update_green_label()))
        self._window_signals.append(window.connect("unrealize", lambda *args: self.dispose()))
        self._headerbar_signals.append((headerbar, headerbar.connect("direction-changed", lambda *args: self.refresh())))
        if self._packing_widget is not headerbar:
            self._headerbar_signals.append((self._packing_widget, self._packing_widget.connect("direction-changed", lambda *args: self.refresh())))
        for schema in ("org.livara.desktop", "org.gnome.desktop.wm.preferences"):
            settings = desktop.settings_for(schema)
            if settings:
                handler = settings.connect("changed", lambda *args: self.refresh())
                self._settings_signals.append((settings, handler))
        self.refresh()

    def _label(self, button, text):
        button.set_tooltip_text(text)
        button.update_property([self.Gtk.AccessibleProperty.LABEL], [text])

    def _pressed(self, gesture, count, x, y):
        self._shift = bool(gesture.get_current_event_state() & self.Gdk.ModifierType.SHIFT_MASK)

    def _key_pressed(self, controller, keyval, keycode, state):
        self._shift = bool(state & self.Gdk.ModifierType.SHIFT_MASK)
        return False

    def _green_clicked(self, button):
        operation = green_operation(
            self.values.get("window-green-action", "fullscreen"),
            fullscreen=_window_state(self.window, "fullscreen"),
            maximized=_window_state(self.window, "maximized"), shift=self._shift)
        self._shift = False
        if operation in ("maximize", "unmaximize") and _window_state(self.window, "fullscreen"):
            self.window.unfullscreen()
        getattr(self.window, operation)()
        self._update_green_label()

    def _fullscreen_shortcut(self, *args):
        operation = "unfullscreen" if _window_state(self.window, "fullscreen") else "fullscreen"
        getattr(self.window, operation)()
        self._update_green_label()
        return True

    def _update_green_label(self):
        operation = green_operation(
            self.values.get("window-green-action", "fullscreen"),
            fullscreen=_window_state(self.window, "fullscreen"),
            maximized=_window_state(self.window, "maximized"))
        titles = {"fullscreen": "Enter fullscreen", "unfullscreen": "Exit fullscreen",
                  "maximize": "Maximize window", "unmaximize": "Restore window"}
        symbols = {"fullscreen": "↗", "unfullscreen": "↙", "maximize": "+", "unmaximize": "−"}
        button = self.buttons["maximize"]
        self._label(button, titles[operation] + " · Shift-click to maximize or restore")
        button.get_child().set_text(symbols[operation])

    def refresh(self):
        if self._disposed:
            return
        self.values = self._style.read_values()
        custom = self.values.get("window-button-style", "traffic-lights") == "traffic-lights"
        if "all" in self._stock:
            self.headerbar.set_show_title_buttons(False if custom else self._stock["all"])
        else:
            for side, original in self._stock.items():
                getattr(self.headerbar, "set_show_" + side + "_title_buttons")(False if custom else original)
        side = packing_side(self.values.get("window-buttons"),
                            rtl=self._packing_widget.get_direction() == self.Gtk.TextDirection.RTL)
        if side != self._side:
            if self.box.get_parent() is not None:
                self.headerbar.remove(self.box)
            getattr(self.headerbar, "pack_" + side)(self.box)
            self._side = side
        self.box.set_visible(custom)
        if self.values.get("window-button-symbols", False):
            self.box.add_css_class("symbols-visible")
        else:
            self.box.remove_css_class("symbols-visible")
        self._update_green_label()

    def dispose(self):
        """Release this window's observers without touching the shared CSS."""
        if self._disposed:
            return
        self._disposed = True
        for settings, handler in self._settings_signals:
            settings.disconnect(handler)
        self._settings_signals.clear()
        for handler in self._window_signals:
            self.window.disconnect(handler)
        self._window_signals.clear()
        for widget, handler in self._headerbar_signals:
            widget.disconnect(handler)
        self._headerbar_signals.clear()
        self.window.remove_controller(self.shortcuts)
        if getattr(self.headerbar, "_livara_native_headerbar", None) is self:
            self.headerbar._livara_native_headerbar = None


def configure_native_headerbar(window, headerbar) -> NativeHeaderbar:
    """Install live traffic lights and F11 on a Gtk/Adw headerbar, once.

    Call immediately after constructing the headerbar, before packing app tools.
    Keep the returned handle only if explicit disposal or inspection is needed.
    """
    existing = getattr(headerbar, "_livara_native_headerbar", None)
    if existing is not None and not existing._disposed:
        return existing
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Gtk
    handle = NativeHeaderbar(window, headerbar, Gtk, Gdk)
    headerbar._livara_native_headerbar = handle
    return handle

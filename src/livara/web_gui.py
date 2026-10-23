"""Livara Browser and Chat: native GTK controls around the WebKit web engine.

Web content remains in WebKit's normal sandbox. No TLS exceptions, privileged
JavaScript bridge, downloaded-file execution, or insecure engine flags are used.
"""
from __future__ import annotations

import argparse
import base64
import html
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .web import (BookmarkStore, CHAT_URI, START_URI, browser_paths,
                  ensure_new_destination, normalize_address, safe_download_name)


def _artwork(chat: bool = False) -> str:
    source = Path(__file__).resolve().parents[2] / "artwork"
    candidates = ((Path("/usr/share/livara/logo.png"), source / "livara-logo.png") if chat else
                  (Path("/usr/share/livara/browser-logo.png"), source / "livara-browser.png", Path("/usr/share/livara/logo.png")))
    for path in candidates:
        if path.is_file():
            return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return ""


def _local_page(title: str, message: str, *, private: bool = False, error: bool = False, chat: bool = False) -> str:
    heading = html.escape(title)
    explanation = html.escape(message)
    links = "" if error or chat else '<nav><a href="https://chat.livara.org">Livara Chat ↗</a><a href="https://www.kali.org/tools/">Security tools ↗</a><a href="https://duckduckgo.com">Search the web ↗</a></nav>'
    mode = "PRIVATE SESSION · EPHEMERAL STORAGE" if private else "YOUR SPACE TO EXPLORE"
    product = "Livara Chat" if chat else "Livara Browser"
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'">
<title>{heading}</title><style>
:root{{color-scheme:dark;font:17px system-ui,sans-serif}}*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;color:#f2edff;background:radial-gradient(ellipse at 45% 20%,#402366 0,transparent 52%),radial-gradient(ellipse at 90% 90%,#152d48,transparent 65%),#0b0e18}}
main{{text-align:center;max-width:860px;padding:50px 28px}}img{{width:138px;height:138px;object-fit:contain;filter:drop-shadow(0 14px 38px #b574ff55)}}
.eyebrow{{font-size:11px;letter-spacing:3px;color:#c3a2ef;margin-top:32px}}h1{{font-weight:600;font-size:clamp(36px,6vw,60px);letter-spacing:-2px;margin:14px 0 20px}}p{{line-height:1.8;color:#c2bcd3;max-width:610px;margin:0 auto;overflow-wrap:anywhere}}
nav{{display:flex;flex-wrap:wrap;justify-content:center;gap:12px;margin-top:38px}}a{{color:#e9dbff;text-decoration:none;padding:15px 20px;background:#ffffff09;border:1px solid #ffffff19;border-radius:18px}}a:hover{{background:#b989ff28;border-color:#bc8cff77}}footer{{font-size:12px;color:#9b93ad;margin-top:44px}}
@media(prefers-reduced-motion:no-preference){{main{{animation:arrive .45s ease-out}}@keyframes arrive{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:none}}}}}}
</style><main><img alt="Livara" src="{_artwork(chat)}"><div class="eyebrow">{mode}</div><h1>{heading}</h1><p>{explanation}</p>{links}<footer>{product} · Powered by WebKit</footer></main></html>'''


def main(chat: bool = False, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Livara Browser and Livara Chat")
    parser.add_argument("--chat", action="store_true", help="open the dedicated Livara Chat app")
    parser.add_argument("--offline", action="store_true", help="show a local preview without loading websites")
    parser.add_argument("addresses", nargs="*")
    options = parser.parse_args(argv)
    chat = chat or options.chat

    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Adw, Gio, GLib, Gtk, WebKit

    class WebApplication(Adw.Application):
        def __init__(self):
            super().__init__(application_id="org.livara.Chat" if chat else "org.livara.Browser",
                             flags=Gio.ApplicationFlags.HANDLES_OPEN)
            self.windows = []
            self.initial_addresses = options.addresses

        def do_startup(self):
            Adw.Application.do_startup(self)
            self.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            css = Gtk.CssProvider()
            css.load_from_data(b"""
                window.livara-web { background: #0e1220; color: #f2edff; }
                .livara-web headerbar { background: alpha(#211c35,.95); border-bottom: 1px solid alpha(#c4a0ff,.14); box-shadow: none; }
                .livara-web .address { background: alpha(#0b0e18,.7); border: 1px solid alpha(#bc98f5,.22); border-radius: 15px; min-height: 36px; padding: 0 12px; }
                .livara-web button { border-radius: 12px; }
                .livara-web tabbar { background: #19182a; }
                .livara-web progressbar progress { background: linear-gradient(90deg,#8f6cf5,#e8c5ff); }
                .livara-web .web-status { padding: 5px 12px; font-size: 11px; color: #bcb4ce; background: #141724; }
                .livara-web .private-badge { color: #d4b8ff; padding: 0 8px; }
                .livara-web .bookmark-item { padding: 8px; border-radius: 12px; }
            """)
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.set_accels_for_action("win.new-tab", ["<Primary>t"])
            self.set_accels_for_action("win.close-tab", ["<Primary>w"])
            self.set_accels_for_action("win.location", ["<Primary>l"])
            self.set_accels_for_action("win.reload", ["<Primary>r", "F5"])
            self.set_accels_for_action("win.back", ["<Alt>Left"])
            self.set_accels_for_action("win.forward", ["<Alt>Right"])
            self.set_accels_for_action("win.private", ["<Primary><Shift>p"])
            self.set_accels_for_action("win.bookmark", ["<Primary>d"])
            self.set_accels_for_action("win.find", ["<Primary>f"])
            self.set_accels_for_action("win.zoom-in", ["<Primary>plus", "<Primary>equal"])
            self.set_accels_for_action("win.zoom-out", ["<Primary>minus"])
            self.set_accels_for_action("win.zoom-reset", ["<Primary>0"])

        def make_window(self, private=False):
            window = BrowserWindow(self, private=private)
            self.windows.append(window)
            window.connect("notify::visible", lambda w, _s: self.remove_window_reference(w) if not w.get_visible() else None)
            return window

        def remove_window_reference(self, window):
            if window in self.windows:
                self.windows.remove(window)
            return False

        def do_activate(self):
            if self.windows:
                self.windows[0].present()
                return
            window = self.make_window()
            addresses = self.initial_addresses
            self.initial_addresses = []
            for address in addresses or [CHAT_URI if chat else START_URI]:
                window.new_tab(address)
            window.present()

        def do_open(self, files, _n_files, _hint):
            window = self.windows[0] if self.windows else self.make_window()
            for file in files:
                window.new_tab(file.get_uri())
            window.present()

    class BrowserWindow(Adw.ApplicationWindow):
        def __init__(self, app, private=False, popup=False, session=None):
            super().__init__(application=app, title="Livara Chat" if chat else "Livara Browser")
            self.app, self.private, self.popup = app, private, popup
            self.set_default_size(1080 if chat else 1200, 790)
            self.set_icon_name("org.livara.Chat" if chat else "org.livara.Browser")
            self.add_css_class("livara-web")
            self.views = {}
            self.dialogs = set()
            self.downloads = set()
            self.store = BookmarkStore()
            if session is not None:
                self.session = session
            elif private:
                self.session = WebKit.NetworkSession.new_ephemeral()
            else:
                data, cache = browser_paths(chat=chat)
                self.session = WebKit.NetworkSession.new(str(data), str(cache))
                self.session.get_cookie_manager().set_persistent_storage(str(data / "cookies.sqlite"), WebKit.CookiePersistentStorage.SQLITE)
            if session is None:
                self.session.connect("download-started", self.download_started)
            self.overlay = Adw.ToastOverlay()
            self.set_content(self.overlay)
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.overlay.set_child(root)
            self.header = Adw.HeaderBar()
            from .window_style import configure_native_headerbar
            self.window_controls = configure_native_headerbar(self, self.header)
            root.append(self.header)
            self.back = self.button("go-previous-symbolic", "Back (Alt+Left)", lambda: self.current().go_back() if self.current() else None)
            self.forward = self.button("go-next-symbolic", "Forward (Alt+Right)", lambda: self.current().go_forward() if self.current() else None)
            self.reload = self.button("view-refresh-symbolic", "Reload (Ctrl+R)", self.reload_page)
            for widget in (self.back, self.forward, self.reload):
                self.header.pack_start(widget)
            self.header.pack_start(self.button("go-home-symbolic", "Home", lambda: self.navigate(self.current(), CHAT_URI if chat else START_URI)))
            self.address = Gtk.Entry(hexpand=True, placeholder_text="Search with DuckDuckGo or enter a web address")
            self.address.add_css_class("address")
            self.address.set_width_chars(34)
            self.address.set_max_width_chars(100)
            self.address.connect("activate", lambda entry: self.navigate(self.current(), entry.get_text()))
            self.header.set_title_widget(self.address)
            if chat:
                self.address.set_editable(False)
                self.address.set_tooltip_text("The current website address, including sign-in redirects")
                self.header.pack_end(self.button("go-jump-symbolic", "Open this page in your browser", self.open_external))
            else:
                self.header.pack_end(self.button("tab-new-symbolic", "New tab (Ctrl+T)", lambda: self.new_tab()))
                self.star = self.button("star-new-symbolic", "Bookmark this page (Ctrl+D)", self.save_bookmark)
                self.header.pack_end(self.star)
                self.bookmark_button = Gtk.MenuButton(icon_name="user-bookmarks-symbolic", tooltip_text="Saved bookmarks")
                self.bookmark_popover = Gtk.Popover()
                self.bookmark_button.set_popover(self.bookmark_popover)
                self.bookmark_button.connect("notify::active", lambda *_: self.refresh_bookmarks())
                self.header.pack_end(self.bookmark_button)
                menu = Gio.Menu()
                for label, action in (("New private window", "win.private"), ("Find on page", "win.find"), ("Zoom in", "win.zoom-in"), ("Zoom out", "win.zoom-out"), ("Reset zoom", "win.zoom-reset")):
                    menu.append(label, action)
                self.header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Browser options"))
            if private:
                badge = Gtk.Label(label="Private")
                badge.add_css_class("private-badge")
                self.header.pack_end(badge)
            self.progress = Gtk.ProgressBar()
            self.progress.set_show_text(False)
            self.progress_revealer = Gtk.Revealer(child=self.progress)
            animations = Gtk.Settings.get_default().get_property("gtk-enable-animations")
            self.progress_revealer.set_transition_duration(120 if animations else 0)
            root.append(self.progress_revealer)
            self.tabview = Adw.TabView(vexpand=True)
            self.tabview.connect("notify::selected-page", self.selected_changed)
            self.tabview.connect("page-detached", self.page_detached)
            self.tabview.connect("page-attached", self.page_attached)
            self.tabbar = Adw.TabBar(view=self.tabview, autohide=True)
            self.tabbar.set_visible(not chat)
            root.append(self.tabbar)
            self.findbar = Gtk.SearchBar()
            findbox = Gtk.Box(spacing=6, margin_top=6, margin_bottom=6, margin_start=12, margin_end=12)
            self.findentry = Gtk.SearchEntry(hexpand=True, placeholder_text="Find on this page")
            self.findentry.connect("search-changed", self.find_text)
            self.findentry.connect("next-match", lambda *_: self.current().get_find_controller().search_next() if self.current() else None)
            self.findentry.connect("previous-match", lambda *_: self.current().get_find_controller().search_previous() if self.current() else None)
            self.findentry.connect("stop-search", lambda *_: self.findbar.set_search_mode(False))
            findbox.append(self.findentry)
            findbox.append(self.button("go-up-symbolic", "Previous match", lambda: self.current().get_find_controller().search_previous()))
            findbox.append(self.button("go-down-symbolic", "Next match", lambda: self.current().get_find_controller().search_next()))
            self.findbar.set_child(findbox)
            self.findbar.connect_entry(self.findentry)
            root.append(self.findbar)
            root.append(self.tabview)
            self.status = Gtk.Label(label="Private browsing keeps this session's cookies and cache in memory." if private else "Ready", xalign=0, ellipsize=3)
            self.status.add_css_class("web-status")
            root.append(self.status)
            for name, callback in {
                "new-tab": lambda: self.new_tab(), "close-tab": self.close_tab,
                "location": self.focus_address, "reload": self.reload_page,
                "back": lambda: self.current().go_back(), "forward": lambda: self.current().go_forward(),
                "private": self.private_window, "bookmark": self.save_bookmark,
                "find": self.show_find, "zoom-in": lambda: self.zoom(.1),
                "zoom-out": lambda: self.zoom(-.1), "zoom-reset": lambda: self.current().set_zoom_level(1),
            }.items():
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, cb=callback: cb())
                self.add_action(action)
            self.connect("close-request", self.on_close)

        def button(self, icon, tooltip, callback):
            button = Gtk.Button(icon_name=icon, tooltip_text=tooltip)
            button.connect("clicked", lambda *_: callback())
            return button

        def toast(self, text):
            self.overlay.add_toast(Adw.Toast.new(str(text)[:300]))

        def current(self):
            page = self.tabview.get_selected_page()
            return page.get_child() if page else None

        def new_tab(self, address=START_URI, related=None):
            if chat and self.current() and related is None:
                self.navigate(self.current(), address)
                return self.current()
            view = WebKit.WebView(related_view=related) if related is not None else WebKit.WebView(network_session=self.session)
            view._livara_owner = self
            view.set_hexpand(True)
            view.set_vexpand(True)
            page = self.tabview.append(view)
            page.set_title("New tab")
            self.views[view] = {"page": page, "requested": address, "failed": False, "local": False}
            for signal, callback in (("notify::title", self.title_changed), ("notify::uri", self.uri_changed),
                                     ("notify::estimated-load-progress", self.progress_changed),
                                     ("load-changed", self.load_changed), ("load-failed", self.load_failed),
                                     ("create", self.create_view), ("close", self.web_close),
                                     ("decide-policy", self.decide_policy), ("permission-request", self.permission_requested)):
                view.connect(signal, callback)
            self.tabview.set_selected_page(page)
            if related is None:
                self.navigate(view, address)
            return view

        def navigate(self, view, address):
            if view is None:
                return
            try:
                uri = normalize_address(address)
            except ValueError as error:
                self.toast(error)
                return
            state = self.views[view]
            state.update(requested=uri, failed=False, local=False)
            if options.offline:
                state["local"] = True
                title = "Livara Chat" if chat else "Hello, explorer."
                message = ("Offline preview. Livara Chat connects to chat.livara.org when opened normally. Your browser and Chat keep separate profiles." if chat else "Offline preview. Enter an address when online to explore the web. Bookmarks, tabs and private windows are ready to use.")
                view.load_html(_local_page(title, message, private=self.private, chat=chat), START_URI)
            elif uri == START_URI:
                state["local"] = True
                view.load_html(_local_page("A little curiosity. Endless possibilities.", "Search from the address bar, collect your favorite places, or open a private window. A calm space for everything you discover.", private=self.private, chat=chat), START_URI)
            else:
                view.load_uri(uri)
            self.update_controls()

        def title_changed(self, view, _spec):
            if view not in self.views:
                return
            title = view.get_title() or ("Livara Chat" if chat else "New tab")
            self.views[view]["page"].set_title(title[:100])
            if self.current() == view:
                self.set_title(f"{title} — Livara {'Chat' if chat else 'Browser'}")

        def uri_changed(self, view, _spec):
            if view == self.current():
                self.update_controls()

        def selected_changed(self, *_):
            self.update_controls()

        def update_controls(self):
            view = self.current()
            if not view or view not in self.views:
                return
            state = self.views[view]
            uri = state["requested"] if state["local"] or state["failed"] else view.get_uri()
            self.address.set_text("" if uri == START_URI else (uri or ""))
            self.back.set_sensitive(view.can_go_back())
            self.forward.set_sensitive(view.can_go_forward())
            self.reload.set_icon_name("process-stop-symbolic" if view.is_loading() else "view-refresh-symbolic")
            self.reload.set_tooltip_text("Stop loading" if view.is_loading() else "Reload (Ctrl+R)")
            self.progress_changed(view, None)

        def progress_changed(self, view, _spec):
            if view == self.current():
                self.progress.set_fraction(view.get_estimated_load_progress())
                self.progress_revealer.set_reveal_child(view.is_loading())

        def load_changed(self, view, event):
            if event == WebKit.LoadEvent.COMMITTED and view in self.views:
                state = self.views[view]
                if not state["local"] and not state["failed"]:
                    state["requested"] = view.get_uri() or state["requested"]
            if view == self.current():
                self.update_controls()
                if event == WebKit.LoadEvent.FINISHED and not self.views[view]["failed"]:
                    self.status.set_label("Private session · cookies and cache stay in memory" if self.private else "Ready")

        def load_failed(self, view, _event, uri, error):
            if view not in self.views or error.matches(WebKit.network_error_quark(), WebKit.NetworkError.CANCELLED):
                return False
            state = self.views[view]
            if state["failed"]:
                return False
            state.update(requested=uri, failed=True, local=True)
            view.load_html(_local_page("This page could not be opened.", f"{uri}\n{error.message}\nCheck your connection and address, then use Reload to try again.", error=True, chat=chat), START_URI)
            self.status.set_label("Website unavailable. No certificate checks were bypassed.")
            return True

        def reload_page(self):
            view = self.current()
            if not view:
                return
            if view.is_loading():
                view.stop_loading()
            elif self.views[view]["failed"] or self.views[view]["local"]:
                self.navigate(view, self.views[view]["requested"])
            else:
                view.reload()

        def decide_policy(self, view, decision, kind):
            if kind not in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
                return False
            action = decision.get_navigation_action()
            uri = action.get_request().get_uri()
            if uri == START_URI or urlsplit(uri).scheme.lower() in ("http", "https"):
                if options.offline and uri != START_URI:
                    decision.ignore()
                    self.toast("Offline preview: websites are not loaded.")
                    return True
                return False
            decision.ignore()
            self.toast("Only HTTP and HTTPS websites can be opened here.")
            return True

        def create_view(self, opener, _action):
            if options.offline:
                return None
            if chat:
                popup = BrowserWindow(self.app, popup=True, session=self.session)
                self.app.windows.append(popup)
                popup.connect("notify::visible", lambda w, _s: self.app.remove_window_reference(w) if not w.get_visible() else None)
                popup.set_default_size(700, 760)
                popup.set_transient_for(self)
                view = popup.new_tab(related=opener)
                view.connect("ready-to-show", lambda *_: popup.present())
                return view
            return self.new_tab(related=opener)

        def web_close(self, view):
            state = self.views.get(view)
            if state:
                self.tabview.close_page(state["page"])

        def page_detached(self, _tabs, page, _position):
            # TabBar supports dragging between any TabViews by default. Keep
            # normal/private profiles, download ownership and popup chains in
            # their original window; page_attached returns a transferred tab.
            if self.tabview.get_is_transferring_page():
                return
            self.views.pop(page.get_child(), None)
            if self.tabview.get_n_pages() == 0:
                self.close()

        def page_attached(self, _tabs, page, _position):
            owner = getattr(page.get_child(), "_livara_owner", self)
            if owner is self:
                return
            def restore():
                self.tabview.transfer_page(page, owner.tabview, owner.tabview.get_n_pages())
                owner.tabview.set_selected_page(page)
                owner.present()
                owner.toast("Tabs stay in their original session window.")
                return False
            GLib.idle_add(restore)

        def close_tab(self):
            page = self.tabview.get_selected_page()
            if page:
                self.tabview.close_page(page)

        def on_close(self, *_):
            if not self.downloads:
                return False
            dialog = Adw.MessageDialog.new(self, "Downloads are still running", "Closing this window cancels its unfinished downloads.")
            dialog.add_response("stay", "Keep downloading")
            dialog.add_response("close", "Cancel downloads and close")
            dialog.set_response_appearance("close", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("stay")
            dialog.set_close_response("stay")
            def response(_dialog, result):
                if result == "close":
                    for download in tuple(self.downloads):
                        download.cancel()
                    self.downloads.clear()
                    self.close()
            dialog.connect("response", response)
            dialog.present()
            return True

        def focus_address(self):
            if not chat:
                self.address.grab_focus()
                self.address.select_region(0, -1)

        def private_window(self):
            if chat:
                return
            window = self.app.make_window(private=True)
            window.new_tab()
            window.present()

        def open_external(self):
            view = self.current()
            uri = view.get_uri() if view else CHAT_URI
            if not uri or uri == START_URI:
                uri = CHAT_URI
            try:
                Gio.AppInfo.launch_default_for_uri(normalize_address(uri), None)
            except (GLib.Error, ValueError) as error:
                self.toast(error)

        def save_bookmark(self):
            view = self.current()
            if not view or chat:
                return
            uri = view.get_uri()
            try:
                self.store.add(view.get_title() or uri or "", uri or "")
                self.toast("Bookmark saved")
                self.refresh_bookmarks()
            except (ValueError, OSError) as error:
                self.toast(error)

        def refresh_bookmarks(self):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
            label = Gtk.Label(label="Your bookmarks", xalign=0)
            label.add_css_class("heading")
            box.append(label)
            try:
                bookmarks = self.store.list()
                if not bookmarks:
                    box.append(Gtk.Label(label="Visit a website and select the star to save it.", wrap=True, max_width_chars=35))
                for item in reversed(bookmarks):
                    row = Gtk.Box(spacing=4)
                    button = Gtk.Button(label=item["title"], hexpand=True, tooltip_text=item["url"])
                    button.connect("clicked", lambda _b, uri=item["url"]: (self.new_tab(uri), self.bookmark_popover.popdown()))
                    row.append(button)
                    row.append(self.button("user-trash-symbolic", "Remove bookmark", lambda uri=item["url"]: self.remove_bookmark(uri)))
                    box.append(row)
            except (ValueError, OSError) as error:
                box.append(Gtk.Label(label=str(error), wrap=True, max_width_chars=38))
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, max_content_height=420, min_content_width=330, propagate_natural_height=True)
            scroll.set_child(box)
            self.bookmark_popover.set_child(scroll)

        def remove_bookmark(self, uri):
            try:
                self.store.remove(uri)
                self.refresh_bookmarks()
            except (ValueError, OSError) as error:
                self.toast(error)

        def show_find(self):
            self.findbar.set_search_mode(not self.findbar.get_search_mode())
            if self.findbar.get_search_mode():
                self.findentry.grab_focus()
            elif self.current():
                self.current().get_find_controller().search_finish()

        def find_text(self, entry):
            view = self.current()
            if view:
                controller = view.get_find_controller()
                if entry.get_text():
                    controller.search(entry.get_text(), WebKit.FindOptions.CASE_INSENSITIVE | WebKit.FindOptions.WRAP_AROUND, 1000)
                else:
                    controller.search_finish()

        def zoom(self, delta):
            view = self.current()
            if view:
                value = min(3.0, max(.5, view.get_zoom_level() + delta))
                view.set_zoom_level(value)
                self.toast(f"Zoom {value:.0%}")

        def permission_requested(self, view, request):
            permissions = []
            if isinstance(request, WebKit.UserMediaPermissionRequest):
                if request.get_property("is-for-video-device"):
                    permissions.append("camera")
                if request.get_property("is-for-audio-device"):
                    permissions.append("microphone")
                # Screen sharing and unknown capture requests are denied.
            elif isinstance(request, WebKit.NotificationPermissionRequest):
                permissions.append("notifications")
            if not permissions:
                request.deny()
                return True
            origin = urlsplit(view.get_uri() or "").netloc or "This website"
            dialog = Adw.MessageDialog.new(self, f"Allow {', '.join(permissions)}?", f"{origin} is requesting access. Allow only if you trust this website.")
            dialog.add_response("deny", "Deny")
            dialog.add_response("allow", "Allow access")
            dialog.set_default_response("deny")
            dialog.set_close_response("deny")
            self.dialogs.add(dialog)
            def response(_dialog, answer):
                request.allow() if answer == "allow" else request.deny()
                self.dialogs.discard(dialog)
            dialog.connect("response", response)
            dialog.present()
            return True

        def download_started(self, _session, download):
            self.downloads.add(download)
            download.set_allow_overwrite(False)
            download.connect("decide-destination", self.choose_download)
            download.connect("finished", self.download_finished)
            download.connect("failed", self.download_failed)
            download.connect("notify::estimated-progress", lambda d, _s: self.status.set_label(f"Downloading · {d.get_estimated_progress():.0%}"))

        def choose_download(self, download, suggested):
            chooser = Gtk.FileChooserNative.new("Save download", self, Gtk.FileChooserAction.SAVE, "Save", "Cancel")
            chooser.set_current_name(safe_download_name(suggested))
            downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
            if downloads and Path(downloads).is_dir():
                chooser.set_current_folder(Gio.File.new_for_path(downloads))
            self.dialogs.add(chooser)
            def response(dialog, result):
                try:
                    file = dialog.get_file() if result == Gtk.ResponseType.ACCEPT else None
                    if not file or not file.get_path():
                        download.cancel()
                    else:
                        destination = ensure_new_destination(Path(file.get_path()))
                        # WebKit 6 accepts an absolute local path, unlike the
                        # URI-based destination API in older WebKitGTK versions.
                        download.set_destination(str(destination))
                        self.status.set_label(f"Downloading {destination.name}…")
                except (ValueError, OSError) as error:
                    download.cancel()
                    self.toast(error)
                finally:
                    self.dialogs.discard(dialog)
                    dialog.destroy()
            chooser.connect("response", response)
            chooser.show()
            return True

        def download_finished(self, download):
            if download not in self.downloads:
                return
            self.downloads.discard(download)
            destination = download.get_destination()
            if destination:
                name = Path(destination).name
                self.status.set_label(f"Saved {name}")
                self.toast(f"Download saved: {name}")

        def download_failed(self, download, error):
            self.downloads.discard(download)
            self.status.set_label("Download stopped")
            self.toast(f"Download stopped: {error.message}")

    # Import Gdk only after selecting GTK 4, alongside the lazy GUI dependencies.
    from gi.repository import Gdk
    application = WebApplication()
    # Normalize searches before GApplication parses files. HTTP URIs delivered by
    # HANDLES_OPEN reach an already-running process through its do_open handler.
    try:
        addresses = [normalize_address(address) for address in options.addresses]
    except ValueError as error:
        parser.error(str(error))
    return application.run([sys.argv[0], *addresses])


def chat_main() -> int:
    return main(chat=True)


if __name__ == "__main__":
    raise SystemExit(main())

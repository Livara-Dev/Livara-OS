"""Livara Essentials: native, service-backed desktop features."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import threading
from . import desktop, essentials as backend, theme, window_style

CSS = """
window { background:#050408; color:#f0e9ff; }
headerbar { background:#09060f; color:#f0e9ff; }
scale highlight { background:#be83ff; }
button:hover { border-color:#9768c2; }
.navigation-sidebar { background:#09070f; padding:12px; border-right:1px solid #251a37; }
.navigation-sidebar row { padding:8px; border-radius:12px; margin-bottom:3px; }
.navigation-sidebar row:selected { background:#2c1945; color:#ead6ff; }
.essentials-card { background:linear-gradient(130deg,#1d112d,#0c0913); border:1px solid #37234e; border-radius:22px; padding:22px; }
.eyebrow { color:#c5a3ff; font-size:11px; font-weight:800; letter-spacing:2px; }
.hero-title { font-size:32px; font-weight:800; }
.muted { color:#b0a3c3; }
.primary { background:#c5a3ff; color:#180b29; font-weight:700; border-radius:12px; padding:10px 18px; }
.preview-title { font-size:25px; font-weight:800; }
textview, textview text { background:#0a0710; color:#e6dbfa; }
entry, dropdown { min-height:34px; }
.zone-canvas { border-radius:18px; background:#0b0812; }
"""


def main():
    import gi
    gi.require_version('Gtk', '4.0');gi.require_version('Adw', '1');gi.require_foreign('cairo')
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

    class Essentials(Adw.Application):
        def __init__(self):
            super().__init__(application_id='org.livara.Essentials', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.add_main_option('page', 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING, 'Open a feature', 'PAGE')
            self.connect('command-line', self.command_line);self.connect('activate', self.activate)
            self.last_profile = None;self.last_toast = None

        def command_line(self, app, command):
            options = command.get_options_dict();page = options.lookup_value('page', None)
            if page and page.unpack() not in {f[0] for f in backend.FEATURES}: return 2
            self.activate(self)
            if page: self.select(page.unpack())
            return 0

        def activate(self, app):
            if self.get_active_window(): self.window.present();return
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            provider = Gtk.CssProvider();provider.load_from_data(CSS.encode())
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.window = Adw.ApplicationWindow(application=self, title='Livara Essentials', default_width=1180, default_height=800)
            self.window.set_size_request(760, 560)
            self.overlay = Adw.ToastOverlay();self.window.set_content(self.overlay)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL);self.overlay.set_child(outer)
            header = Adw.HeaderBar();window_style.configure_native_headerbar(self.window, header)
            header.set_title_widget(Adw.WindowTitle(title='Livara Essentials', subtitle='Make this desktop yours'))
            outer.append(header)
            split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True);outer.append(split)
            navscroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, width_request=225)
            self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=['navigation-sidebar'])
            navscroll.set_child(self.nav);split.set_start_child(navscroll);split.set_resize_start_child(False);split.set_shrink_start_child(False)
            self.rows = {}
            for key, title, hint, category, command in backend.FEATURES:
                row = Gtk.ListBoxRow();row.key = key
                row.set_child(Gtk.Label(label=title, xalign=0));self.nav.append(row);self.rows[key] = row
            self.nav.connect('row-selected', lambda box, row: self.show(row.key) if row else None)
            self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
            split.set_end_child(self.scroller);self.select('theme');self.window.present()

        def select(self, key): self.nav.select_row(self.rows[key])
        def toast(self, message):
            if self.last_toast: self.last_toast.dismiss()
            self.last_toast = Adw.Toast(title=str(message)[:250], timeout=6)
            self.overlay.add_toast(self.last_toast)
            return self.last_toast
        def safe(self, function):
            try: return function()
            except Exception as error: self.toast(str(error));return None
        def async_task(self, function, done):
            def run():
                try: result, error = function(), None
                except Exception as caught: result, error = None, str(caught)
                def finish():
                    if error: self.toast(error)
                    else: done(result)
                    return False
                GLib.idle_add(finish)
            threading.Thread(target=run, daemon=True).start()
        def launch(self, argv):
            if not shutil.which(argv[0]): self.toast(f'{argv[0]} is not installed in this environment');return
            self.safe(lambda: Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE))
        def button(self, label, callback, primary=False):
            button = Gtk.Button(label=label, css_classes=['primary'] if primary else [])
            button.connect('clicked', lambda b: self.safe(callback));return button
        def label(self, text, cls=None):
            label = Gtk.Label(label=text, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, css_classes=[cls] if cls else [])
            return label
        def card(self, title, description=None):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, css_classes=['essentials-card'])
            box.append(self.label(title, 'title-2'))
            if description: box.append(self.label(description, 'muted'))
            self.page.append(box);return box
        def line(self, parent, *widgets):
            if all(isinstance(widget, Gtk.Button) for widget in widgets):
                row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False, min_children_per_line=1, max_children_per_line=3, column_spacing=8, row_spacing=8)
                for widget in widgets: row.insert(widget, -1)
            else:
                row = Gtk.Box(spacing=10)
                for widget in widgets: row.append(widget)
            parent.append(row);return row
        def entry(self, placeholder): return Gtk.Entry(placeholder_text=placeholder, hexpand=True)
        def text(self, parent, text='', editable=False, height=220):
            scroll = Gtk.ScrolledWindow(min_content_height=height, vexpand=True)
            view = Gtk.TextView(editable=editable, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                top_margin=14, bottom_margin=14, left_margin=14, right_margin=14)
            view.get_buffer().set_text(text);scroll.set_child(view);parent.append(scroll);return view
        def show(self, key):
            self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22, margin_start=32, margin_end=32, margin_top=28, margin_bottom=32)
            reveal = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP, transition_duration=160 if desktop.read_option('animations') is not False else 0)
            reveal.set_child(self.page);self.scroller.set_child(reveal);self.current = key
            feature = next(f for f in backend.FEATURES if f[0] == key)
            self.page.append(self.label('L I V A R A   /   ' + feature[3].upper(), 'eyebrow'))
            self.page.append(self.label(feature[1], 'hero-title'));self.page.append(self.label(feature[2], 'muted'))
            try: getattr(self, 'page_' + key)()
            except Exception as error: self.card('This feature needs attention', str(error))
            GLib.idle_add(lambda: (reveal.set_reveal_child(True), False)[1])

        def page_theme(self):
            self.bundle = getattr(self, 'loaded_theme', None) or backend.current_theme_bundle()
            self.loaded_theme = None;self.tokens = dict(self.bundle['tokens']);self.tokens['theme-enabled'] = True
            card = self.card('A look that belongs to you', 'Preview your accent, surface, corners and borders before applying. GTK apps may need reopening; apps with their own renderer keep their own themes.')
            preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=['essentials-card'])
            preview.set_name('theme-preview');preview.append(self.label('Your space. Your rhythm.', 'preview-title'))
            preview.append(self.label('AMOLED surfaces · soft edges · a personal accent', 'muted'))
            preview.append(self.button('A little more Livara', lambda: self.toast('This is a visual preview'), True));card.append(preview)
            if not hasattr(self, 'preview_provider'):
                self.preview_provider = Gtk.CssProvider();Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.preview_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
            accent = self.entry('#c5a3ff');accent.set_text(self.tokens['theme-accent'])
            accent.connect('changed', lambda entry: self.preview_change('theme-accent', entry.get_text()))
            self.line(card, self.label('Accent'), accent)
            for key, title, low, high in [('theme-radius', 'Corner radius', 0, 36), ('theme-border', 'Border width', 0, 4), ('theme-opacity', 'Surface opacity', 60, 100)]:
                scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, 1);scale.set_value(self.tokens[key]);scale.set_hexpand(True);scale.set_draw_value(True)
                scale.connect('value-changed', lambda widget, k=key: self.preview_change(k, int(widget.get_value())))
                caption = self.label(title);caption.set_size_request(115, -1);self.line(card, caption, scale)
            self.update_preview()
            self.line(card, self.button('Apply theme', lambda: self.theme_apply(), True), self.button('Restore app styling', lambda: self.disable_theme()))
            saved = self.card('Your theme collection', 'Save visual tokens locally. Import and export use inert, validated JSON.')
            self.theme_name = self.entry('Theme name');self.line(saved, self.theme_name, self.button('Save', self.theme_save))
            self.theme_choices = Gtk.DropDown.new_from_strings([]);saved.append(self.theme_choices);self.refresh_themes()
            self.line(saved, self.button('Load preview', self.theme_load), self.button('Export…', lambda: self.theme_file(False)), self.button('Import…', lambda: self.theme_file(True)))
            collection = self.card('One coordinated desktop', 'The theme collection also remembers visual desktop preferences, fonts, glass, cursor and sound/icon themes. Per-app icon overrides remain under App icons.')
            for kind, title in [('icons', 'Desktop icon theme'), ('sounds', 'Sound theme')]:
                names = backend.installed_theme_names(kind)
                chooser = Gtk.DropDown.new_from_strings(names);current = self.bundle['extras'].get(kind)
                if current in names: chooser.set_selected(names.index(current))
                chooser.connect('notify::selected', lambda widget, prop, k=kind, values=names: self.bundle['extras'].__setitem__(k, values[widget.get_selected()]) if widget.get_selected() < len(values) else None)
                self.line(collection, self.label(title), chooser)
            for key, title in [('glass-enabled', 'Desktop glass'), ('event-sounds', 'Interface sounds')]:
                target = self.bundle['extras'] if key == 'event-sounds' else self.bundle['preferences']
                switch = Gtk.Switch(active=target.get(key, False), halign=Gtk.Align.START)
                switch.connect('notify::active', lambda widget, prop, k=key, values=target: values.__setitem__(k, widget.get_active()))
                self.line(collection, self.label(title), switch)
            links = self.card('The finishing touches', 'Personalize fonts, cursors and desktop sounds, or replace any app icon.')
            self.line(links, self.button('Fonts & desktop', lambda: self.launch(['livara-settings', '--page', 'customize'])), self.button('App icons', lambda: self.launch(['livara-settings', '--page', 'icons'])), self.button('Sound', lambda: self.launch(['gnome-control-center', 'sound'])))
        def preview_change(self, key, value):
            candidate = {**self.tokens, key: value}
            try: self.tokens = theme.validate(candidate);self.update_preview()
            except ValueError: pass
        def update_preview(self):
            value = self.tokens
            self.preview_provider.load_from_data((f"#theme-preview {{ background:rgba(12,8,18,{value['theme-opacity']/100}); border:{value['theme-border']}px solid {value['theme-accent']}; border-radius:{value['theme-radius']}px; }} #theme-preview button {{ background:{value['theme-accent']}; color:#13091d; }}").encode())
        def theme_apply(self):
            self.bundle['tokens'] = self.tokens;backend.apply_theme_bundle(self.bundle);self.toast('Theme applied')
        def disable_theme(self): theme.apply({**self.tokens, 'theme-enabled': False});self.toast('Original app styling restored')
        def refresh_themes(self):
            self.saved_themes = backend.NamedStore('themes', backend.validate_theme_bundle).list()
            self.theme_choices.set_model(Gtk.StringList.new(list(self.saved_themes)))
        def theme_save(self): backend.NamedStore('themes', backend.validate_theme_bundle).save(self.theme_name.get_text(), {**self.bundle, 'tokens': self.tokens});self.refresh_themes();self.toast('Theme saved')
        def theme_load(self):
            index = self.theme_choices.get_selected();names = list(self.saved_themes)
            if index >= len(names): raise ValueError('Save or import a theme first')
            value = self.saved_themes[names[index]]
            # Rebuild controls from saved values without changing system settings.
            self.loaded_theme = dict(value);self.show('theme')
        def theme_file(self, importing):
            chooser = Gtk.FileChooserNative(title='Import theme' if importing else 'Export theme', transient_for=self.window,
                action=Gtk.FileChooserAction.OPEN if importing else Gtk.FileChooserAction.SAVE, accept_label='Import' if importing else 'Save', cancel_label='Cancel')
            if not importing: chooser.set_current_name('livara-theme.json')
            def response(dialog, code):
                def finish():
                    if code != Gtk.ResponseType.ACCEPT: return
                    file = dialog.get_file()
                    if importing:
                        path = Path(file.get_path())
                        info = path.stat()
                        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536: raise ValueError('Select a regular theme file of at most 64KB')
                        value = backend.validate_theme_bundle(json.loads(path.read_text()))
                        backend.NamedStore('themes', backend.validate_theme_bundle).save(path.stem, value);self.refresh_themes();self.toast('Imported; choose Load preview')
                    else:
                        file.replace_contents(json.dumps(backend.validate_theme_bundle({**self.bundle, 'tokens': self.tokens}), indent=2).encode(), None, False, Gio.FileCreateFlags.PRIVATE, None)
                        self.toast('Theme exported')
                self.safe(finish);dialog.destroy()
            chooser.connect('response', response);chooser.show()

        def page_profiles(self):
            for title, (values, power) in backend.PROFILES.items():
                card = self.card(title, ' · '.join(f'{k}: {v}' for k, v in values.items()) + f'\nPower preference: {power}, when offered by the device.')
                card.append(self.button('Apply ' + title, lambda name=title: self.profile_apply(name), True))
            self.page.append(self.button('Undo last desktop profile', self.profile_undo))
        def profile_apply(self, name):
            self.last_profile = backend.apply_profile(name);self.toast('Desktop applied. Power: ' + self.last_profile['power'])
        def profile_undo(self):
            if not self.last_profile: raise ValueError('Apply a profile first')
            desktop._apply_options(self.last_profile['previous'])
            if self.last_profile['previous'].get('animations') is True: desktop.set_option('animations', True)
            if 'previous_power' in self.last_profile:
                proxy, current, supported = backend.power_state();value = self.last_profile['previous_power']
                if value in supported: proxy.call_sync('org.freedesktop.DBus.Properties.Set', GLib.Variant('(ssv)', ('net.hadess.PowerProfiles', 'ActiveProfile', GLib.Variant('s', value))), Gio.DBusCallFlags.NONE, 5000, None)
            self.last_profile = None;self.toast('Previous profile settings restored')

        def page_layouts(self):
            card = self.card('A place for every window', 'Saves dock and workspace preferences plus window positions on each display. Restore matches open app windows; launch missing apps yourself. Requires the Livara GNOME extension.')
            label = self.entry('Layout name');self.line(card, label, self.button('Save current desktop', lambda: self.layout_save(label.get_text()), True))
            items = backend.NamedStore('layouts', backend.validate_layout).list()
            if not items: card.append(self.label('Your saved layouts will appear here.', 'muted'))
            for name, value in items.items():
                row = self.card(name, f"{len(value['windows'])} windows · {len(value['preferences'])} desktop settings")
                self.line(row, self.button('Restore', lambda n=name: self.layout_restore(n)), self.button('Delete', lambda n=name: self.layout_delete(n)))
        def layout_save(self, name): backend.save_layout(name);self.show('layouts');self.toast('Desktop layout saved')
        def layout_restore(self, name):
            result = backend.restore_layout(name);self.toast(f"Restored {result.get('applied', 0)} windows; {result.get('missing', 0)} missing")
        def layout_delete(self, name): backend.NamedStore('layouts', backend.validate_layout).delete(name);self.show('layouts')

        def page_tiling(self):
            card = self.card('Draw your workflow', 'Drag on the display below to add a zone. Super + Alt + 1…9 moves the focused window to that zone on its current monitor.')
            settings = desktop.settings_for('org.livara.desktop')
            try: self.zones = backend.validate_zones(json.loads(settings.get_string('tiling-zones')))
            except Exception: self.zones = list(backend.DEFAULT_ZONES)
            self.zone_canvas = Gtk.DrawingArea(content_height=300, hexpand=True, css_classes=['zone-canvas']);self.zone_canvas.set_draw_func(self.draw_zones);card.append(self.zone_canvas)
            drag = Gtk.GestureDrag();drag.connect('drag-begin', lambda gesture, x, y: setattr(self, 'drag_start', (x, y)))
            drag.connect('drag-end', self.zone_end);self.zone_canvas.add_controller(drag)
            self.line(card, self.button('Undo zone', self.zone_undo), self.button('Two columns', self.zone_reset), self.button('Save zones', self.zone_save, True))
        def draw_zones(self, area, cr, width, height):
            cr.set_source_rgb(.035,.025,.055);cr.paint()
            for index, (x,y,w,h) in enumerate(self.zones):
                cr.set_source_rgba(.63,.37,.95,.15 + index*.025);cr.rectangle(x*width+3,y*height+3,w*width-6,h*height-6);cr.fill_preserve()
                cr.set_source_rgba(.78,.61,1,.85);cr.set_line_width(2);cr.stroke();cr.set_font_size(24);cr.move_to(x*width+18,y*height+36);cr.show_text(str(index+1))
        def zone_end(self, gesture, dx, dy):
            def finish():
                if len(self.zones) >= 9: raise ValueError('Remove a zone before adding another')
                width, height = self.zone_canvas.get_width(), self.zone_canvas.get_height();x,y = self.drag_start
                x2,y2 = max(0,min(width,x+dx)),max(0,min(height,y+dy))
                candidate = [min(x,x2)/width,min(y,y2)/height,abs(x2-x)/width,abs(y2-y)/height]
                self.zones = backend.validate_zones(self.zones+[candidate]);self.zone_canvas.queue_draw()
            self.safe(finish)
        def zone_undo(self):
            if self.zones: self.zones.pop();self.zone_canvas.queue_draw()
        def zone_reset(self): self.zones = [list(z) for z in backend.DEFAULT_ZONES];self.zone_canvas.queue_draw()
        def zone_save(self):
            zones = backend.validate_zones(self.zones);desktop.write_setting('org.livara.desktop','tiling-zones',json.dumps(zones));self.toast('Zones saved')

        def page_palette(self):
            card = self.card('Everything, a few keys away', 'Super + Alt + Space searches installed apps, Livara settings, Studio tools, recent files and files in your Documents, Downloads and Desktop folders. File search is bounded; it is not a complete disk index.')
            card.append(self.button('Open command palette', lambda: self.launch(['livara-palette']), True))
        def page_clipboard(self):
            card = self.card('A useful memory. Your choice.', 'History is off by default. GPaste stores copied text and images locally, without encryption. The Livara extension pauses capture while locked, when an app is unknown, and in the apps you exclude. This is a convenience filter, not a security boundary; clear secrets from history.')
            settings = desktop.settings_for('org.livara.desktop')
            enabled = Gtk.Switch(active=settings.get_boolean('clipboard-history-enabled') if settings else False, halign=Gtk.Align.START)
            enabled.connect('notify::active', lambda switch, prop: self.safe(lambda: desktop.write_setting('org.livara.desktop','clipboard-history-enabled',switch.get_active())))
            self.line(card, self.label('Remember copied content'), enabled)
            excluded = self.text(card, '\n'.join(settings.get_strv('clipboard-excluded-apps')) if settings else '', True, 120)
            def save():
                buf=excluded.get_buffer();values=[v.strip() for v in buf.get_text(buf.get_start_iter(),buf.get_end_iter(),False).splitlines() if v.strip()]
                if len(values)>100 or any(not v.endswith('.desktop') or len(v)>255 or any(c in v for c in '/\\\0') for v in values): raise ValueError('Enter up to 100 desktop app IDs, one per line')
                desktop.write_setting('org.livara.desktop','clipboard-excluded-apps',values);self.toast('Exclusions saved')
            self.line(card, self.button('Save exclusions', save), self.button('Open history', lambda:self.launch(['gpaste-client','ui'])), self.button('History settings',lambda:self.launch(['gpaste-client','settings'])))
            card.append(self.label('History shortcut: Super + Alt + V. Clear history from the GPaste interface.', 'muted'))
        def page_preview(self):
            card=self.card('A glance, without losing your place', 'In Files, select a file and press Space. Sushi previews supported images, PDFs, video, audio and text/code. Press Space again or Escape to close. Decoder support depends on the file format.')
            card.append(self.button('Open Files',lambda:self.launch(['nautilus']),True))
        def page_capture(self):
            card=self.card('A recording worth sharing', 'OBS Studio provides screen and window capture, scenes, microphone mixing and hardware encoding when available. On Wayland, choose the screen or window in the system portal.')
            card.append(self.button('Open screen recorder',lambda:self.launch(['obs']),True))
            self.card('Keep private details private', 'Add a Color Source above the captured scene and resize it over a sensitive region, or crop the capture source. Inspect a short test recording before sharing. Redaction is manual; Livara does not detect secrets automatically.')
        def page_recovery(self):
            card=self.card('A way back', 'Timeshift supports scheduled system snapshots and restoring a selected snapshot. Choose a separate destination and configure retention before relying on it. Snapshots do not replace a backup of personal files.')
            self.line(card,self.button('Configure / review snapshots',lambda:self.launch(['timeshift-gtk']),True),self.button('Personal backups',lambda:self.launch(['deja-dup'])))
            self.card('Before an update', 'Create a snapshot, inspect its date and destination, then install updates. The restore interface previews the selected system and target. Livara does not silently create snapshots or promise recovery before you configure and test it.')
        def page_permissions(self):
            card=self.card('Know what an app can reach', 'These controls change per-user Flatpak overrides. They take effect when the app restarts. Native packages are not isolated by these switches. Audio access includes microphone and playback; camera access may also depend on devices and portals.')
            self.line(card,self.button('System privacy',lambda:self.launch(['gnome-control-center','privacy'])),self.button('Application permissions',lambda:self.launch(['gnome-control-center','applications'])))
            loading=self.label('Reading installed Flatpak apps…','muted');card.append(loading)
            def loaded(apps):
                loading.set_label('No Flatpak apps are installed.' if not apps else f'{len(apps)} sandboxed apps installed')
                for identifier,title in apps:
                    row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);row.append(self.label(title,'title-3'));row.append(self.label(identifier,'muted'));card.append(row)
                    self.line(row,self.button('Inspect permissions',lambda app=identifier:self.permission_inspect(app)),self.button('Reset user overrides',lambda app=identifier:self.permission_reset(app)))
                    for permission,title in [('network','Network'),('home','Home files'),('audio','Microphone + audio')]:
                        self.line(row,self.label(title),self.button('Allow',lambda a=identifier,p=permission:self.permission_set(a,p,True)),self.button('Deny',lambda a=identifier,p=permission:self.permission_set(a,p,False)))
            self.async_task(backend.flatpak_apps,loaded)
        def show_output(self,title,value):
            dialog=Adw.Window(transient_for=self.window,modal=True,title=title,default_width=760,default_height=520)
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin_start=20,margin_end=20,margin_top=20,margin_bottom=20)
            dialog.set_content(box);self.text(box,value,False,350);box.append(self.button('Close',dialog.close));dialog.present()
        def permission_inspect(self,app):
            def run(): return {kind:backend.diagnostic(command) for kind,command in [('Manifest',['flatpak','info','--show-permissions',app]),('User overrides',['flatpak','override','--user','--show',app])]}
            self.async_task(run,lambda value:self.show_output(app,json.dumps(value,indent=2)))
        def permission_set(self,app,permission,allowed):
            self.async_task(lambda:backend.diagnostic(backend.permission_command(app,permission,allowed)),self.command_result)
        def permission_reset(self,app):
            # Only this app's explicit per-user overrides; the manifest remains intact.
            backend.permission_command(app,'network',True)
            self.async_task(lambda:backend.diagnostic(['flatpak','override','--user','--reset',app]),self.command_result)
        def command_result(self,result):
            if result.get('exit_code') == 0:self.toast('Change applied; restart the app')
            else:self.show_output('Command result',result['output'])
        def page_lab(self):
            card=self.card('A clear scope. A clean workspace.', 'Create a private project with scope notes, evidence and a working folder. Only explicitly authorized systems belong in the scope. The Kali container is separate from the host but shares its network; it is not a VM.')
            name=self.entry('Project name');self.line(card,name,self.button('Create project',lambda:self.lab_create(name.get_text()),True))
            self.lab_status=self.label('');card.append(self.lab_status)
            self.line(card,self.button('Open project',self.lab_open),self.button('Open scope notes',self.lab_notes),self.button('Open isolated toolbox',self.lab_terminal))
            card.append(self.button('Evidence & security tools',lambda:self.launch(['livara-center','--page','cases'])))
        def lab_create(self,name):self.lab_path=backend.create_lab(name);self.lab_status.set_label(str(self.lab_path));self.toast('Project created')
        def lab_require(self):
            if not getattr(self,'lab_path',None):raise ValueError('Create a project first')
            return self.lab_path
        def lab_open(self): Gio.AppInfo.launch_default_for_uri(self.lab_require().as_uri(),None)
        def lab_notes(self):Gio.AppInfo.launch_default_for_uri((self.lab_require()/'notes/scope.md').as_uri(),None)
        def lab_terminal(self):
            path=self.lab_require()/'work';self.launch(['gnome-terminal','--working-directory='+str(path),'--','livara','toolbox','run','--directory',str(path),'--','bash'])
        def page_hardware(self):
            card=self.card('Know your machine', 'Read-only checks help identify available drivers, firmware, Secure Boot state and storage. Driver installation and firmware updates use their own administrator prompts.')
            self.line(card,self.button('Graphics setup',lambda:self.launch(['livara-graphics']),True),self.button('Additional drivers',lambda:self.launch(['software-properties-gtk','--open-tab=4'])),self.button('Displays',lambda:self.launch(['gnome-control-center','display'])))
            output=self.text(card,'Select Run checks to read this machine’s status. No drivers are changed.',False,320)
            card.append(self.button('Run checks',lambda:self.async_task(backend.hardware_report,lambda data:output.get_buffer().set_text(json.dumps(data,indent=2))),True))
        def page_connect(self):
            card=self.card('Your phone, beside your desktop', 'KDE Connect supports file transfer, notification sync, remote input and optional clipboard sync. Both devices must be on a trusted reachable network. Install KDE Connect on the phone and approve pairing on both devices; plugins stay under your control.')
            card.append(self.button('Pair / manage devices',lambda:self.launch(['kdeconnect-app']),True))
            self.card('Network access', 'Discovery uses TCP and UDP ports 1714–1764. The Livara Connect UFW application profile is installed, but no firewall ports are opened automatically. Restrict any rule to your trusted LAN. Clipboard sync is separate from local clipboard history.')
        def page_help(self):
            card=self.card('Answers, even offline', 'Bundled Livara guides and installed manual pages stay available without an internet connection.')
            search=self.entry('Search guide titles');card.append(search)
            listing=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);card.append(listing)
            docs=backend.help_documents()
            def populate(entry):
                while listing.get_first_child():listing.remove(listing.get_first_child())
                query=entry.get_text().casefold()
                for path in docs:
                    if query in path.stem.casefold():listing.append(self.button(path.stem.replace('-',' ').title(),lambda p=path:self.show_output(p.stem,p.read_text())))
            search.connect('changed',populate);populate(search)
            manuals=self.card('Installed tool manuals');topic=self.entry('For example: nmap, openssl, ssh')
            self.line(manuals,topic,self.button('Search manuals',lambda:self.async_task(lambda:backend.manual_search(topic.get_text()),lambda value:self.show_output('Manual search',value['output']))))
            manuals.append(self.label('Read a result in the terminal with: man <name>', 'muted'))
        def page_install(self):
            card=self.card('Make Livara your daily desktop', 'The installer configures disk partitions, optional LUKS encryption and a persistent local account. Installation erases or changes the partitions you select. Review the installer summary carefully and back up your files first.')
            live='boot=casper' in Path('/proc/cmdline').read_text().split()
            card.append(self.label('Live session detected' if live else 'Installation is available only from a Livara live USB. This session will not launch disk installation.','muted'))
            button=self.button('Open Livara installer',lambda:self.launch(['livara-install']),True);button.set_sensitive(live);card.append(button)
            self.card('Qualification', 'The installer configuration and target-file finalizer are validated separately from a complete disk installation. Encrypted install, reboot and recovery still require VM or device qualification. Do not assume a preview session proves an installed system is ready.')
        def page_accounts(self):
            card=self.card('A desktop that remembers you', 'Installed accounts keep files and preferences in their home folders. Live USB sessions are temporary unless persistence was explicitly configured. The installer creates a password-protected local account; automatic login is disabled.')
            card.append(self.button('Manage local accounts',lambda:self.launch(['gnome-control-center','user-accounts']),True))
        def page_updates(self):
            card=self.card('Keep the foundations current', 'Software Updater applies signed distribution package updates. Automatic security updates use the installed unattended-upgrades service. Review changes and maintain a configured recovery snapshot before major updates.')
            self.line(card,self.button('Check package updates',lambda:self.launch(['update-manager']),True),self.button('Update sources',lambda:self.launch(['software-properties-gtk'])))
            self.card('Livara application releases', 'There is no Livara release server configured. Rebuild the included Livara desktop, Code and browser sources to update those components. Do not enable an untrusted package source or assume upstream application auto-updaters will update a locally branded build.')
            firmware=self.card('Device firmware', 'Read firmware devices in Hardware assistant. Apply supported updates using the system firmware utility after reviewing its instructions. Physical hardware support depends on the manufacturer.')
            firmware.append(self.button('Hardware assistant',lambda:self.select('hardware')))

    app=Essentials()
    argv=sys.argv if Path(sys.argv[0]).name in ('livara-essentials','essentials_gui.py') else ['livara-essentials']
    return app.run(argv)

if __name__ == '__main__': raise SystemExit(main())

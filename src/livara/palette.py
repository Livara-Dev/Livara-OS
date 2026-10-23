"""Bounded local command palette. Entries contain argv or local paths, never shell."""
from pathlib import Path
from . import essentials, studio


def commands():
    entries=[]
    for key,title,hint,category,command in essentials.FEATURES:
        entries.append({'name':title,'detail':'Livara Essentials · '+hint,'argv':['livara-essentials','--page',key]})
    for key,title in [('customize','Personalize desktop'),('icons','Change app icons'),('system','Devices and connectivity')]:
        entries.append({'name':title,'detail':'Livara Settings','argv':['livara-settings','--page',key]})
    for tool in studio.TOOLS:
        entries.append({'name':tool['name'],'detail':'Livara Studio · '+tool['hint'],'argv':['livara-studio','--tool',tool['id']]})
    return entries


def local_files(home=None, limit=800):
    """Nonrecursive, no symlinks; bounds avoid walking an entire home directory."""
    base=Path(home or Path.home());result=[]
    for folder in ('Documents','Downloads','Desktop'):
        directory=base/folder
        if directory.is_symlink() or not directory.is_dir():continue
        try:
            for index,path in enumerate(directory.iterdir()):
                if index>=limit or len(result)>=limit:break
                if path.name.startswith('.') or path.is_symlink() or not path.is_file():continue
                result.append({'name':path.name,'detail':str(path),'path':str(path)})
        except OSError:continue
    return result


def search(entries, query, limit=50):
    terms=query.casefold().split()
    if len(query)>256:return []
    matches=[]
    for index,item in enumerate(entries):
        title=item['name'].casefold();text=title+' '+item.get('detail','').casefold()
        if all(term in text for term in terms):
            score=0 if title.startswith(query.casefold()) else 1 if query.casefold() in title else 2
            matches.append((score,index,item))
    return [item for score,index,item in sorted(matches,key=lambda row:row[:2])[:limit]]


def main():
    import gi
    gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
    from gi.repository import Adw,Gdk,Gio,GLib,Gtk
    from . import window_style
    from .essentials_gui import CSS
    import threading
    class Palette(Adw.Application):
        def __init__(self):
            super().__init__(application_id='org.livara.Palette');self.connect('activate',self.activate)
        def activate(self,app):
            if self.get_active_window():self.window.present();self.entry.grab_focus();return
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            provider=Gtk.CssProvider();provider.load_from_data(CSS.encode())
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.entries=commands();self.apps={};self.timeout=None
            for item in Gio.AppInfo.get_all():
                if not item.should_show():continue
                identifier=item.get_id()
                if not identifier:continue
                self.apps[identifier]=item
                self.entries.append({'name':item.get_display_name(),'detail':item.get_description() or 'Application','app':identifier})
            # Recent items are local files only. Do not leak their paths into logs.
            if desktop_recent_enabled():
                for item in Gtk.RecentManager.get_default().get_items()[:200]:
                    if item.is_local() and item.exists():self.entries.append({'name':item.get_display_name(),'detail':'Recent file','uri':item.get_uri()})
            self.window=Adw.ApplicationWindow(application=self,title='Livara Palette',default_width=720,default_height=620)
            self.overlay=Adw.ToastOverlay();self.window.set_content(self.overlay)
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,margin_start=20,margin_end=20,margin_bottom=20);self.overlay.set_child(box)
            header=Adw.HeaderBar();window_style.configure_native_headerbar(self.window,header)
            header.set_title_widget(Adw.WindowTitle(title='Livara Palette',subtitle='Your next move'));box.append(header)
            self.entry=Gtk.SearchEntry(placeholder_text='Apps, files, settings, tools…');box.append(self.entry)
            self.entry.connect('search-changed',self.schedule);self.entry.connect('activate',lambda e:self.open_selected())
            scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);box.append(scroll)
            self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE,css_classes=['boxed-list']);scroll.set_child(self.list)
            self.list.connect('row-activated',lambda box,row:self.open_item(row.item))
            controller=Gtk.EventControllerKey();controller.connect('key-pressed',self.key);self.window.add_controller(controller)
            self.refresh();self.window.present();self.entry.grab_focus()
            def scan():
                values=local_files()
                self.scan_complete = len(values)
                def finish():self.entries.extend(values);self.refresh();return False
                GLib.idle_add(finish)
            threading.Thread(target=scan,daemon=True).start()
        def key(self,controller,keyval,keycode,state):
            if keyval==Gdk.KEY_Escape:self.window.close();return True
            if keyval in (Gdk.KEY_Down,Gdk.KEY_Up):
                row=self.list.get_selected_row();index=row.get_index() if row else -1
                target=self.list.get_row_at_index(max(0,index+(1 if keyval==Gdk.KEY_Down else -1)))
                if target:self.list.select_row(target)
                return True
            return False
        def schedule(self,entry):
            if self.timeout:GLib.source_remove(self.timeout)
            self.timeout=GLib.timeout_add(120,self.refresh)
        def refresh(self):
            self.timeout=None
            while self.list.get_first_child():self.list.remove(self.list.get_first_child())
            for item in search(self.entries,self.entry.get_text()):
                row=Gtk.ListBoxRow();row.item=item
                box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_start=14,margin_end=14,margin_top=12,margin_bottom=12)
                box.append(Gtk.Label(label=item['name'],xalign=0,ellipsize=3))
                box.append(Gtk.Label(label=item.get('detail',''),xalign=0,ellipsize=3,css_classes=['muted']))
                row.set_child(box);self.list.append(row)
            first=self.list.get_row_at_index(0)
            if first:self.list.select_row(first)
            return False
        def open_selected(self):
            row=self.list.get_selected_row()
            if row:self.open_item(row.item)
        def open_item(self,item):
            try:
                if 'argv' in item:Gio.Subprocess.new(item['argv'],Gio.SubprocessFlags.NONE)
                elif 'app' in item:self.apps[item['app']].launch([],None)
                else:
                    uri=item.get('uri') or Path(item['path']).as_uri();Gio.AppInfo.launch_default_for_uri(uri,None)
                self.window.close()
            except Exception as error:self.overlay.add_toast(Adw.Toast(title=str(error)[:200]))
    return Palette().run(['livara-palette'])


def desktop_recent_enabled():
    from . import desktop
    return desktop.read_option('remember-recent-files') is True

if __name__=='__main__':raise SystemExit(main())

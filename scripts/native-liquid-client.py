#!/usr/bin/env python3
"""Launch the actual Settings app and expose only its material state to the test."""
import os,json
os.environ['GDK_BACKEND']='wayland'
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import GLib,Gio
from livara.gui import main
out=Path(os.environ['LIVARA_GLASS_TEST_OUTPUT'])/'client.json'
def state():
 a=Gio.Application.get_default();w=a.get_active_window() if a else None
 if w:out.write_text(json.dumps({'glass':w.has_css_class('lv-native-glass'),'title':w.get_title(),'light':w.has_css_class('lv-native-glass-light'),'windows':[{'title':v.get_title(),'glass':v.has_css_class('lv-native-glass')} for v in a.get_windows()]}))
 return True
def commands(fd, condition):
 if condition & GLib.IO_HUP: return False
 data=os.read(fd,4096)
 if not data: return False
 app=Gio.Application.get_default()
 for command in data.decode().splitlines():
  if command=='preview': app.preferences_ui.open_preview()
  elif command=='close-preview' and app.preferences_ui._preview_window: app.preferences_ui._preview_window.close()
 return True
GLib.io_add_watch(0,GLib.IO_IN | GLib.IO_HUP,commands)
GLib.timeout_add(120,state)
main(mode='settings')

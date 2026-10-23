#!/usr/bin/env python3
"""Optional native Settings workflow qualification.

Requires the Livara schemas, GTK4/libadwaita/Python GI, Pillow, Xvfb, xdotool,
Openbox and an isolated D-Bus session. It is deliberately not part of make check.
For example, after installing the desktop package:
  PYTHONPATH=src xvfb-run -a -s '-screen 0 1280x900x24' dbus-run-session -- \
    bash -c 'openbox >/tmp/livara-openbox.log 2>&1 & exec /usr/bin/python3 scripts/settings-ui-smoke.py'

All GSettings writes use a private memory backend. Presets and managed GTK files
use a temporary configuration directory. Output is .build/settings-redesign/
or LIVARA_GUI_TEST_OUTPUT, and no ISO is built.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
test_home = tempfile.TemporaryDirectory(prefix='livara-settings-ui-')
os.environ['XDG_CONFIG_HOME'] = str(Path(test_home.name) / 'config')
os.environ['GSETTINGS_BACKEND'] = 'memory'
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gio,GLib,Gtk,Gdk
from PIL import Image,ImageGrab
from livara import desktop
from livara.gui import settings_main
out=Path(os.environ.get('LIVARA_GUI_TEST_OUTPUT','.build/settings-redesign')).resolve()
out.mkdir(parents=True,exist_ok=True)
errors=[]
results=[]

def require(value,message):
 if not value:raise AssertionError(message)
def app():return Gio.Application.get_default()
def record(message):results.append(message);print(message,flush=True)
def shot(name):ImageGrab.grab(xdisplay=os.environ['DISPLAY']).save(out/name)
def choose(name,value):
 ui=app().preferences_ui
 binding=ui.bindings[name]
 kind=binding['item']['kind'];w=binding['widget']
 if kind=='choice':w.set_selected(next(i for i,pair in enumerate(binding['item']['choices']) if pair[0]==value))
 elif kind=='bool':w.set_active(value)
 elif kind in ('int','float'):w.livara_spin.set_value(value)
 else:raise RuntimeError(kind)
 require(desktop.read_option(name)==value,f'{name} did not apply: {desktop.read_option(name)!r}')
def guarded(fn):
 def run():
  try:fn()
  except Exception as error:
   import traceback;traceback.print_exc();errors.append(str(error));app().quit()
  return False
 return run

@guarded
def workflow():
 a=app();ui=a.preferences_ui
 require(len(ui.bindings)==94,'Catalog is incomplete')
 require(len(ui.sections)==8,'Expected eight categories')
 for section in ui.sections:
  ui.tab_buttons[section].set_active(True)
  require(ui.stack.get_visible_child_name()==section,'Category navigation failed')
 for name,binding in ui.bindings.items():
  expected=desktop.read_option(name)is not None and binding['item']['writable']
  require(binding['widget'].get_sensitive()==expected,'Availability incorrect: '+name)
 ui.search.set_text('font');ui.filter_changed()
 require(ui.stack.get_visible_child_name()=='typography','Search did not jump to type controls')
 require(ui.rows['interface-font'].get_visible(),'Actual matching row hidden')
 require(not ui.rows['dock-size'].get_visible(),'Unrelated row visible')
 ui.search.set_text('[no such setting]');ui.filter_changed()
 require(ui.stack.get_visible_child_name()=='empty','Missing empty results state')
 shot('empty-search.png')
 ui.search.emit('stop-search');ui.filter_changed()
 require(ui.search.get_text()=='','Escape did not clear query')
 a.lookup_action('find-settings').activate(None)
 require(a.stack.get_visible_child_name()=='customize','Search shortcut did not open Design Studio')
 choose('accent','sage')
 font=ui.bindings['interface-font']['widget'];font.set_font('Sans 13');font.emit('font-set')
 require(desktop.read_option('interface-font')=='Sans 13','Font chooser did not persist')
 choose('text-scale',1.1)
 choose('cursor-size',30)
 ui.select_section('windows')
 choose('window-buttons','close,minimize,maximize:')
 choose('window-button-size',18)
 choose('window-green-action','fullscreen')
 color=ui.bindings['window-close-color']['widget']
 color.livara_color_entry.set_text('#F5A1C7');color.livara_color_entry.emit('activate')
 require(desktop.read_option('window-close-color')=='#f5a1c7','Hex color not normalized')
 color.livara_color_entry.set_text('bad');color.livara_color_entry.emit('activate')
 require(desktop.read_option('window-close-color')=='#f5a1c7','Invalid hex changed preference')
 rgba=Gdk.RGBA();rgba.parse('#ee5588');color.livara_color_picker.set_rgba(rgba);color.livara_color_picker.emit('color-set')
 require(desktop.read_option('window-close-color')=='#ee5588','Picker did not apply')
 choose('window-animation-style','fade');choose('window-animation-duration',340)
 choose('animations',False)
 # A chooser actually selects and returns a local image through its UI response.
 wallpaper=out/'local-wallpaper.png';Image.new('RGB',(48,36),(70,30,120)).save(wallpaper)
 ui.choose_wallpaper();ui._wallpaper_dialog.set_file(Gio.File.new_for_path(str(wallpaper)))
 GLib.timeout_add(700,wallpaper_selected)

@guarded
def wallpaper_selected():
 ui=app().preferences_ui
 wallpaper=out/'local-wallpaper.png'
 require(ui._wallpaper_dialog.get_file() is not None,'Native chooser did not finish selecting the file')
 ui._wallpaper_dialog.emit('response',Gtk.ResponseType.ACCEPT)
 require(desktop.get_custom_wallpaper()==str(wallpaper),'Local wallpaper chooser did not apply')
 choose('accent','purple')
 require(desktop.get_custom_wallpaper()==str(wallpaper),'Accent replaced custom wallpaper')
 # Exercise real Save/Rename dialog responses and storage readback.
 ui.save_look_button.emit('clicked');ui._preset_name_entry.set_text('Midnight study');ui._preset_dialog.emit('response','save')
 require('Midnight study'in desktop.list_custom_presets(),'Save-look dialog did not store a preset')
 ui.preset_dialog('Midnight study');ui._preset_name_entry.set_text('Midnight desk');ui._preset_dialog.emit('response','save')
 require('Midnight desk'in desktop.list_custom_presets()and'Midnight study'not in desktop.list_custom_presets(),'Rename failed')
 choose('window-button-size',12)
 ui.apply_custom('Midnight desk')
 require(desktop.read_option('window-button-size')==18,'Custom preset did not restore look')
 require(desktop.read_option('animations')is False,'Applying a look re-enabled motion')
 ui.delete_preset('Midnight desk')
 require('Midnight desk'not in desktop.list_custom_presets(),'Delete failed')
 ui._undo_preset_toast.emit('button-clicked')
 require('Midnight desk'in desktop.list_custom_presets(),'Delete undo did not restore saved values')
 ui.delete_preset('Midnight desk')
 old_close=desktop.read_option('window-close-color')
 ui.reset_section('typography')
 require(desktop.read_option('window-close-color')==old_close,'Section reset escaped its scope')
 require(desktop.read_option('animations')is False,'Section reset enabled motion')
 ui.set_option('wallpaper-image','')
 require(desktop.get_custom_wallpaper()=='','Custom wallpaper clear failed')
 ui.select_section('appearance')
 ui.open_preview()
 require(ui._preview_window.get_title()=='Livara Design Preview','Real preview missing')
 ui._preview_window.livara_controls.buttons['maximize'].emit('clicked')
 record('94 controls / 8 categories; search + empty state + CtrlF; actual font/numeric/color/wallpaper chooser; safe saved-look save/rename/apply/delete; scoped reset PASS')
 GLib.timeout_add(800,check_preview)

@guarded
def check_preview():
 ui=app().preferences_ui
 require(ui._preview_window.is_fullscreen(),'Preview green button did not enter actual fullscreen')
 ui._preview_window.livara_controls.buttons['maximize'].emit('clicked')
 GLib.timeout_add(500,finish_preview)

@guarded
def finish_preview():
 ui=app().preferences_ui
 require(not ui._preview_window.is_fullscreen(),'Preview green button did not exit fullscreen')
 ui._preview_window.close();ui.select_section('appearance')
 record('Real preview window native fullscreen enter / exit PASS')
 GLib.timeout_add(700,resize_narrow)

@guarded
def resize_narrow():
 shot('appearance-workflow.png')
 a=app();a.window.present()
 xid=subprocess.check_output(['xdotool','search','--onlyvisible','--name','^Livara Settings$'],text=True).splitlines()[0]
 subprocess.run(['xdotool','windowsize',xid,'800','600'],check=True)
 GLib.timeout_add(700,check_narrow)

@guarded
def check_narrow():
 a=app();ui=a.preferences_ui
 print('Narrow actual size:',a.window.get_width(),a.window.get_height(),flush=True)
 require(a.window.get_width()<=800,f'Narrow window forced too wide: {a.window.get_width()}')
 require(a.window.get_height()<=600,f'Narrow window forced too tall: {a.window.get_height()}')
 ui.smoke_narrow_sections=iter(ui.sections)
 narrow_next()

@guarded
def narrow_next():
 ui=app().preferences_ui
 try:
  section=next(ui.smoke_narrow_sections)
 except StopIteration:
  ui.select_section('appearance')
  GLib.timeout_add(300,finish_narrow)
  return
 ui.tab_buttons[section].set_active(True)
 GLib.timeout_add(250,narrow_assert)

@guarded
def narrow_assert():
 a=app();ui=a.preferences_ui
 require(a.window.get_width()<=800,f'{ui.current_section} forced window too wide: {a.window.get_width()}')
 require(a.window.get_height()<=600,f'{ui.current_section} forced window too tall: {a.window.get_height()}')
 print('Narrow category rendered:',ui.current_section,a.window.get_width(),a.window.get_height(),flush=True)
 narrow_next()

@guarded
def finish_narrow():
 a=app()
 shot('narrow-800x600.png')
 record('Actual Openbox window 800x600: all eight responsive categories rendered after layout PASS')
 (out/'result.json').write_text(json.dumps({'ok':True,'checks':results,'settings':94,'sections':8,'narrow_client_width':a.window.get_width(),'narrow_client_height':a.window.get_height()},indent=2)+'\n')
 a.quit()

GLib.timeout_add_seconds(3,workflow)
result=settings_main()
if errors:raise RuntimeError(errors)
raise SystemExit(result)

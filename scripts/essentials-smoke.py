#!/usr/bin/env python3
"""Native GTK feature workflow test in an isolated Xvfb/D-Bus profile.
Captures show test-container app windows, not a booted ISO or real hardware.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import traceback

ROOT=Path(__file__).resolve().parents[1]
profile=tempfile.TemporaryDirectory(prefix='livara-essentials-profile-');base=Path(profile.name)
for name in ('home','config','data','schemas'):(base/name).mkdir()
(base/'schemas/org.livara.desktop.gschema.xml').write_bytes((ROOT/'share/livara/org.livara.desktop.gschema.xml').read_bytes())
subprocess.run(['glib-compile-schemas','--strict',str(base/'schemas')],check=True)
os.environ.update(HOME=str(base/'home'),XDG_CONFIG_HOME=str(base/'config'),XDG_DATA_HOME=str(base/'data'),GSETTINGS_SCHEMA_DIR=str(base/'schemas'),GSETTINGS_BACKEND='memory',GTK_A11Y='none')
out=Path(os.environ.get('LIVARA_ESSENTIALS_OUTPUT','/tmp/livara-essentials-test'));out.mkdir(parents=True,exist_ok=True)
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gio,GLib,Gtk
from PIL import ImageGrab
from livara import essentials,essentials_gui,desktop,theme
# Installed image assets and unavailable host theme paths are not fabricated.
# Use a valid desktop button layout in this otherwise minimal GNOME schema set.
desktop.set_option('window-buttons', 'close,minimize,maximize:')
for source in (ROOT/'fonts/ttf').glob('*.ttf'):
    fonts=base/'data/fonts';fonts.mkdir(exist_ok=True);(fonts/source.name).write_bytes(source.read_bytes())
subprocess.run(['fc-cache','-f',str(base/'data/fonts')],check=True,capture_output=True)
checks=[];errors=[];remaining=[feature[0] for feature in essentials.FEATURES]

def check(value,message):
    if not value:raise AssertionError(message)
    checks.append(message)
def guarded(fn):
    def run():
        try:fn()
        except Exception as error:traceback.print_exc();errors.append(str(error));Gio.Application.get_default().quit()
        return False
    return run
@guarded
def start():
    app=Gio.Application.get_default()
    # Failed backends must remain visibly unavailable, never fabricate layouts.
    app.tokens['theme-accent']='#be83ff';app.theme_apply()
    check(theme.read_values()['theme-accent']=='#be83ff','Real Theme Studio GSettings applied')
    check(theme.BEGIN in (base/'config/gtk-4.0/gtk.css').read_text(),'Managed GTK stylesheet written')
    app.theme_name.set_text('Violet');app.theme_save();app.theme_load()
    check(app.tokens['theme-accent']=='#be83ff','Saved theme reloads into live preview')
    app.disable_theme();check(not theme.read_values()['theme-enabled'],'Original style restored')
    GLib.timeout_add(300,next_page)
@guarded
def next_page():
    app=Gio.Application.get_default()
    if app.last_toast:app.last_toast.dismiss()
    if not remaining:
        app.select('tiling');app.zone_reset();app.zone_save()
        check(json.loads(desktop.settings_for('org.livara.desktop').get_string('tiling-zones'))==essentials.DEFAULT_ZONES,'Zones persist to the actual Shell settings')
        app.select('profiles');app.profile_apply('Battery Saver')
        check(desktop.read_option('animations') is False,'Battery profile disables animations')
        app.profile_undo()
        app.select('lab');app.lab_create('smoke-lab')
        check((app.lab_path/'notes/scope.md').is_file(),'Security Lab creates real scope notes')
        app.last_toast.dismiss();app.window.set_default_size(800,600);GLib.timeout_add(450,finish);return
    key=remaining.pop(0);app.select(key);app.capture_key=key
    GLib.timeout_add(800,capture)
@guarded
def capture():
    app=Gio.Application.get_default()
    if app.last_toast:app.last_toast.dismiss()
    ImageGrab.grab().save(out/('native-essentials-'+app.capture_key+'.png'))
    checks.append('Rendered feature: '+app.capture_key)
    GLib.timeout_add(50,next_page)
@guarded
def finish():
    app=Gio.Application.get_default();check(app.window.get_width()<=800,'Native feature UI fits 800px window')
    if app.last_toast:app.last_toast.dismiss()
    ImageGrab.grab().save(out/'native-essentials-compact.png')
    app.quit()
GLib.timeout_add(900,start)
exit_code=essentials_gui.main()
(out/'qualification.json').write_text(json.dumps({'checks':checks,'errors':errors,'exit_code':exit_code,'context':'Real GTK in Xvfb test container; no ISO boot, disk install or device qualification'},indent=2)+'\n')
raise SystemExit(1 if errors else exit_code)

#!/usr/bin/env python3
"""Real native command-palette render/search test; no result is launched."""
import json
import os
from pathlib import Path
import tempfile
import traceback
import subprocess
root=Path(__file__).resolve().parents[1];profile=tempfile.TemporaryDirectory(prefix='livara-palette-');base=Path(profile.name)
for name in ('home/Documents','config','data','schemas'):(base/name).mkdir(parents=True)
(base/'home/Documents/livara-fixture.txt').write_text('Private test fixture')
(base/'schemas/org.livara.desktop.gschema.xml').write_bytes((root/'share/livara/org.livara.desktop.gschema.xml').read_bytes())
subprocess.run(['glib-compile-schemas',str(base/'schemas')],check=True)
os.environ.update(HOME=str(base/'home'),XDG_CONFIG_HOME=str(base/'config'),XDG_DATA_HOME=str(base/'data'),XDG_DATA_DIRS=str(root/'share')+':/usr/share',GSETTINGS_SCHEMA_DIR=str(base/'schemas'),GSETTINGS_BACKEND='memory',GTK_A11Y='none')
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gio,GLib
from PIL import ImageGrab
from livara import palette
output=Path(os.environ.get('LIVARA_ESSENTIALS_OUTPUT','/tmp/livara-essentials-test'));output.mkdir(parents=True,exist_ok=True)
errors=[];checks=[]
def verify():
    try:
        app=Gio.Application.get_default();app.entry.set_text('json');app.refresh()
        row=app.list.get_row_at_index(0)
        assert row is not None;assert any('json' in entry['name'].casefold() for entry in palette.search(app.entries,'json'))
        checks.append('Studio tools and settings appear in actual native search')
        assert any(entry.get('path','').endswith('livara-fixture.txt') for entry in app.entries)
        checks.append('Bounded Documents file scan returns real local fixture')
        GLib.timeout_add(400,capture)
    except Exception as error:traceback.print_exc();errors.append(str(error));Gio.Application.get_default().quit()
    return False
def capture():
    ImageGrab.grab().save(output/'native-palette.png');Gio.Application.get_default().quit();return False
GLib.timeout_add(3000,verify)
code=palette.main();(output/'palette-qualification.json').write_text(json.dumps({'checks':checks,'errors':errors,'exit_code':code},indent=2)+'\n')
raise SystemExit(1 if errors else code)

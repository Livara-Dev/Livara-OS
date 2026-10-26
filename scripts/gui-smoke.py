#!/usr/bin/env python3
"""Exercise actual Center/Settings widgets with private user data, no pixel coordinates."""
import json
import os
from pathlib import Path
import sys
import tempfile

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, GLib
from PIL import ImageGrab


def main():
    settings = '--settings' in sys.argv
    output = Path('.build/settings-gui' if settings else '.build/gui')
    output.mkdir(parents=True, exist_ok=True)
    home = tempfile.TemporaryDirectory(prefix='livara-center-audit-')
    os.environ.update(HOME=home.name, XDG_CONFIG_HOME=home.name + '/config', GSETTINGS_BACKEND='memory')
    from livara import gui, core, desktop
    errors, checks = [], []
    def walk(widget):
        yield widget
        child = widget.get_first_child()
        while child:
            yield from walk(child)
            child = child.get_next_sibling()
    pages = ['system', 'apps', 'shield'] if settings else ['toolbox', 'cases', 'shield', 'verify', 'customize', 'apps', 'system']
    def step():
        app = Gio.Application.get_default()
        try:
            if not pages:
                app.quit()
                return False
            page = pages.pop(0)
            app.navigation[page].set_active(True)
            assert app.stack.get_visible_child_name() == page
            if page == 'cases':
                entry = next(w for w in walk(app.stack.get_visible_child())
                             if isinstance(w, Gtk.Entry) and (w.get_placeholder_text() or '').startswith('Case name'))
                entry.set_text('native-smoke')
                next(w for w in walk(app.stack.get_visible_child())
                     if isinstance(w, Gtk.Button) and w.get_label() == 'Create case').emit('clicked')
                assert (core.cases_root() / 'native-smoke/case.json').is_file()
                checks.append('Actual Create case button created its private workspace')
            if page == 'customize':
                for name, appearance in [('Sunrise', 'light'), ('Prism', 'dark')]:
                    app.preferences_ui.apply_builtin(name)
                    assert desktop.read_option('appearance') == appearance
                    checks.append('Applied ' + name + ' through the Settings workflow')
            def shot():
                ImageGrab.grab(xdisplay=os.environ['DISPLAY']).save(output / (page + '.png'))
                checks.append('Rendered ' + page)
                GLib.timeout_add(200, step)
                return False
            GLib.timeout_add(400, shot)
        except Exception as error:
            import traceback
            traceback.print_exc()
            errors.append(str(error))
            app.quit()
        return False
    GLib.timeout_add(1500, step)
    result = gui.main(mode='settings' if settings else 'center')
    (output / 'audit.json').write_text(json.dumps({'checks':checks, 'errors':errors}, indent=2) + '\n')
    home.cleanup()
    return 1 if errors else result


if __name__ == '__main__':
    raise SystemExit(main())

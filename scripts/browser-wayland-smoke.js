// SPDX-License-Identifier: GPL-3.0-or-later
// Private compositor probe: validate the installed browser's app identity/bounds.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const OUTPUT = GLib.getenv('LIVARA_GLASS_TEST_OUTPUT');
const rect = r => ({x:r.x, y:r.y, width:r.width, height:r.height});

export default class BrowserProbe extends Extension {
    enable() {
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 800, () => {
            this.run().catch(error => this.finish({status:'failed', error:String(error), stack:error.stack}));
            return GLib.SOURCE_REMOVE;
        });
    }

    async pause() {
        await new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
            resolve(); return GLib.SOURCE_REMOVE;
        }));
    }

    async run() {
        Main.overview.hide();
        const profile = GLib.dir_make_tmp('livara-browser-wayland-XXXXXX');
        Gio.File.new_for_path(profile + '/user.js').replace_contents(new TextEncoder().encode(
            'user_pref("browser.shell.checkDefaultBrowser", false);\nuser_pref("zen.welcome-screen.seen", true);\n'),
        null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        this.process = Gio.Subprocess.new(['/usr/bin/env', 'MOZ_ENABLE_WAYLAND=1',
            'GIO_LAUNCHED_DESKTOP_FILE=/usr/share/applications/org.livara.Settings.desktop',
            '/opt/livara-browser/livara-browser', '--no-remote', '--profile', profile, 'about:preferences'],
        Gio.SubprocessFlags.NONE);
        let window, app;
        for (let i = 0; i < 40; i++) {
            await this.pause();
            window = global.get_window_actors().map(a => a.meta_window).find(w => w.get_wm_class() === 'livara-browser');
            if (window) app = Shell.WindowTracker.get_default().get_window_app(window);
            if (app?.get_id() === 'org.livara.Browser.desktop' && i >= 10) break;
        }
        const info = Gio.DesktopAppInfo.new('org.livara.Browser.desktop');
        const actual = {wmclass:window?.get_wm_class(), appId:app?.get_id(), icon:info?.get_icon()?.to_string()};
        if (actual.appId !== 'org.livara.Browser.desktop' || actual.icon !== 'org.livara.Browser')
            throw new Error('Browser icon/desktop association is wrong: ' + JSON.stringify(actual));
        const frame = rect(window.get_frame_rect());
        const work = rect(global.workspace_manager.get_active_workspace().get_work_area_for_monitor(window.get_monitor()));
        if (frame.x < work.x - 4 || frame.y < work.y - 4 ||
            frame.x + frame.width > work.x + work.width + 4 || frame.y + frame.height > work.y + work.height + 4)
            throw new Error('Browser exceeds monitor work area: ' + JSON.stringify({frame, work}));
        const stream = Gio.File.new_for_path(OUTPUT + '/browser-wayland.png').replace(null, false,
            Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        try { await new Shell.Screenshot().screenshot(false, stream); }
        finally { stream.close(null); }
        this.finish({status:'passed', identity:actual, frame, workArea:work,
            clientType:window.get_client_type(), sandboxDisabled:false});
    }

    finish(data) {
        Gio.File.new_for_path(OUTPUT + '/browser.json').replace_contents(
            new TextEncoder().encode(JSON.stringify(data, null, 2)), null, false,
            Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        this.process?.force_exit();
        global.context.terminate();
    }

    disable() {}
}

// SPDX-License-Identifier: GPL-3.0-or-later
// Temporary extension loaded ONLY by test-liquid-glass.sh in a private Shell.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const OUTPUT = GLib.getenv('LIVARA_GLASS_TEST_OUTPUT');
const ROOT = GLib.getenv('LIVARA_GLASS_TEST_ROOT');
function check(condition, message) { if (!condition) throw new Error(message); }
const livePlanes = () => Main.uiGroup.get_children().filter(a => a._livaraLiquidInternal);

export default class Probe extends Extension {
    enable() {
        this.actors = [];
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 700, () => {
            this.run().catch(error => this.finish({status:'failed', error:String(error), stack:error.stack}));
            return GLib.SOURCE_REMOVE;
        });
    }

    async pause() {
        await new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
            resolve(); return GLib.SOURCE_REMOVE;
        }));
    }

    async shot(name) {
        const stream = Gio.File.new_for_path(`${OUTPUT}/${name}.png`).replace(
            null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        try { await new Shell.Screenshot().screenshot(false, stream); }
        finally { stream.close(null); }
    }

    async run() {
        Main.overview.hide(); await this.pause();
        this.client = Gio.Subprocess.new(['python3', `${ROOT}/scripts/liquid-glass-scene.py`],
            Gio.SubprocessFlags.STDIN_PIPE);
        let background;
        for (let i = 0; i < 25; i++) {
            await this.pause();
            background = global.get_window_actors().find(a =>
                a.meta_window.get_title() === 'Live optical test window');
            if (background) break;
        }
        check(background, 'Native Wayland window did not map');
        background.meta_window.move_resize_frame(false, 0, 100, 1000, 600);
        await this.pause();
        const surface = new St.Widget({x:220, y:200, width:400, height:160,
            style_class:'popup-menu-content'});
        surface.add_child(new St.Label({text:'Sharp foreground text', x:50, y:60,
            style:'color:white;font-size:20px;'}));
        Main.uiGroup.add_child(surface); this.actors.push(surface);
        await this.pause(); await this.pause();
        const production = Main.extensionManager.lookup('livara-glass@livara.local')?.stateObj;
        this.production = production;
        const manager = production?._liquid;
        const entry = manager?._entries.get(surface);
        check(entry, 'No production GPU backplate on mapped shell popup');
        check(surface.has_style_class_name('livara-liquid-surface'), 'Clear material class missing');

        // Disable softening to isolate sampled-pixel displacement from blur.
        entry.blur.radius = 0;
        entry.effect.configure(448, 208, 400, 160, 30, 0);
        await this.pause(); await this.shot('flat');
        entry.effect.configure(448, 208, 400, 160, 30, 14); entry.plane.queue_redraw();
        await this.pause(); await this.shot('refracted');
        background.meta_window.move_frame(false, 17, 100);
        await this.pause(); await this.shot('live');
        this.client.get_stdin_pipe().write_all(new TextEncoder().encode('change\n'), null);
        await this.pause(); await this.shot('updated');
        const sourceCount = entry.sources.size;
        entry.blur.radius = 12; entry.plane.queue_redraw();
        await this.pause(); await this.shot('material');

        const furniture = [];
        for (const [i, style] of ['dash-background', 'notification-banner', 'osd-window', 'modal-dialog'].entries()) {
            const actor = new St.Widget({x:760, y:180+i*95, width:210, height:80, style_class:style});
            Main.uiGroup.add_child(actor); this.actors.push(actor); furniture.push(actor);
        }
        await this.pause(); await this.pause();
        check(furniture.every(actor => manager._entries.has(actor)), 'A shell material kind lacked a live lens');
        const activeKinds = [...new Set([...manager._entries.values()].map(e => e.kind))].sort();
        check(activeKinds.length === 6, 'Not all six shell material kinds were exercised');
        for (const actor of furniture) actor.destroy();
        this.actors = [surface]; await this.pause();

        background.meta_window.minimize(); await this.pause(); await this.pause();
        check(![...manager._entries.values()].some(e => e.sources.has(background)),
            'Minimized window remained in live scene');
        background.meta_window.unminimize();
        background.meta_window.activate(global.get_current_time()); Main.overview.hide();
        await this.pause(); await this.pause();
        check(manager._entries.get(surface)?.sources.has(background), 'Restored window missing');
        Main.overview.show(); await this.pause(); await this.pause();
        check(!manager._entries.size, 'Overview retained live glass');
        Main.overview.hide(); await this.pause(); await this.pause();
        production._accessibilitySettings.set_boolean('high-contrast', true); await this.pause(); await this.pause();
        check(!manager._entries.size, 'High contrast retained live glass');
        production._accessibilitySettings.set_boolean('high-contrast', false); await this.pause(); await this.pause();
        production._interfaceSettings.set_boolean('enable-animations', false); await this.pause();
        check(manager._entries.has(surface), 'Reduced motion lost static glass');

        for (let i = 0; i < 12; i++) {
            const extra = new St.Widget({x:30+i*50, y:450, width:120, height:70,
                style_class:'popup-menu-content'});
            Main.uiGroup.add_child(extra); this.actors.push(extra);
        }
        await this.pause(); await this.pause();
        const boundedLenses = manager._entries.size;
        check(boundedLenses <= 8 && [...manager._entries.values()].reduce((s,e) => s+e.pixels, 0) <= 6000000,
            'GPU resource budget exceeded');
        check(this.actors.some(a => !a.has_style_class_name('livara-liquid-surface')),
            'Excess surfaces did not retain fallback');
        for (const extra of this.actors.slice(1)) extra.destroy();
        this.actors = this.actors.slice(0, 1); await this.pause();
        surface.hide(); await this.pause();
        check(!manager._entries.has(surface), 'Hidden popup retained GPU lens');
        production._settings.set_boolean('glass-enabled', false); await this.pause();
        check(!manager._entries.size && !livePlanes().length, 'Glass toggle leaked live backplates');
        production._settings.set_boolean('glass-enabled', true); surface.show(); await this.pause();
        check(manager._entries.has(surface), 'Glass toggle failed to restore live scene');
        production.disable(); await this.pause();
        check(!livePlanes().length, 'Full extension disable leaked GPU scenes');
        production.enable(); await this.pause(); await this.pause();
        check(production._liquid?._entries.has(surface), 'Full extension reenable failed');
        production._settings.set_boolean('glass-enabled', false); await this.pause();
        this.finish({status:'passed', sourceCount, liveGPU:true, nativeWayland:true, activeKinds,
            boundedLenses, accessibility:'overview and high contrast release scenes; reduced motion keeps static glass',
            windowPrivacy:'minimize removes source; restore reconnects',
            cleanup:'hide, toggle and full extension disable release scenes; reenable rebuilds'});
    }

    finish(data) {
        if (data.status === 'failed' && this.production) {
            data.settings = {
                material:this.production._material,
                gtkTheme:this.production._interfaceSettings.get_string('gtk-theme'),
                highContrast:this.production._accessibilitySettings.get_boolean('high-contrast'),
                writable:this.production._accessibilitySettings.is_writable('high-contrast'),
                liveKinds:[...this.production._liquid._entries.values()].map(e => e.kind),
            };
        }
        Gio.File.new_for_path(`${OUTPUT}/production.json`).replace_contents(
            new TextEncoder().encode(JSON.stringify(data, null, 2)), null, false,
            Gio.FileCreateFlags.REPLACE_DESTINATION, null);
        for (const actor of this.actors) actor.destroy();
        this.client?.force_exit();
        global.context.terminate();
    }

    disable() {}
}

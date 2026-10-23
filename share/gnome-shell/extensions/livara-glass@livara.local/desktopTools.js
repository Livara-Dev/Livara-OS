// SPDX-License-Identifier: GPL-3.0-or-later
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const INTERFACE = `<node><interface name="org.livara.Desktop">
<method name="GetLayout"><arg type="s" direction="out"/></method>
<method name="ApplyLayout"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<method name="GetStatus"><arg type="s" direction="out"/></method>
</interface></node>`;

export function validatePlacements(value) {
    if (!Array.isArray(value) || value.length > 100)
        throw new Error('At most 100 windows can be restored');
    for (const item of value) {
        if (!item || typeof item !== 'object' || Array.isArray(item) ||
            Object.keys(item).sort().join(',') !== 'app,fullscreen,maximized,monitor,ordinal,rect,workspace' ||
            typeof item.app !== 'string' || !item.app.length || item.app.length > 255 || /[\/\\\r\n\0]/.test(item.app))
            throw new Error('Invalid app placement');
        for (const [key, maximum] of [['ordinal', 100], ['workspace', 35], ['monitor', 31]]) {
            if (!Number.isInteger(item[key]) || item[key] < 0 || item[key] > maximum)
                throw new Error('Invalid placement index');
        }
        const r = item.rect;
        if (!Array.isArray(r) || r.length !== 4 || r.some(v => typeof v !== 'number' || !Number.isFinite(v) || v < 0 || v > 1) ||
            r[2] < .06 || r[3] < .06 || r[0] + r[2] > 1.001 || r[1] + r[3] > 1.001 ||
            typeof item.fullscreen !== 'boolean' || typeof item.maximized !== 'boolean')
            throw new Error('Invalid placement geometry');
    }
    return value;
}

export default class DesktopTools {
    constructor(settings) { this.settings = settings; this.signals = []; this.bindings = []; }

    enable() {
        this._export = Gio.DBusExportedObject.wrapJSObject(INTERFACE, this);
        this._export.export(Gio.DBus.session, '/org/livara/Desktop');
        this.bind('palette-shortcut', () => {
            Main.overview.hide();
            this.spawn(['livara-palette']);
        }, Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW);
        this.bind('clipboard-shortcut', () => this.spawn(['gpaste-client', 'ui']));
        for (let i = 0; i < 9; i++) this.bind(`zone-${i + 1}`, () => this.placeZone(i));
        const source = Gio.SettingsSchemaSource.get_default();
        if (source.lookup('org.gnome.GPaste', true)) {
            this.gpaste = new Gio.Settings({schema_id: 'org.gnome.GPaste'});
            this.connect(global.display, 'notify::focus-window', () => this.syncClipboard());
            this.connect(Main.sessionMode, 'updated', () => this.syncClipboard());
            this.connect(this.settings, 'changed::clipboard-excluded-apps', () => this.syncClipboard());
            this.connect(this.settings, 'changed::clipboard-history-enabled', () => {
                this.syncClipboard();
                if (this.settings.get_boolean('clipboard-history-enabled')) this.spawn(['gpaste-client', 'daemon-version']);
            });
            this.syncClipboard();
            if (this.settings.get_boolean('clipboard-history-enabled')) this.spawn(['gpaste-client', 'daemon-version']);
        }
    }

    connect(object, signal, callback) { this.signals.push([object, object.connect(signal, callback)]); }

    bind(name, callback, modes = Shell.ActionMode.NORMAL) {
        if (!this.settings.settings_schema.has_key(name)) return;
        Main.wm.addKeybinding(name, this.settings, Meta.KeyBindingFlags.NONE, modes, callback);
        this.bindings.push(name);
    }

    spawn(argv) {
        try { Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE); }
        catch (error) { Main.notify('Livara', String(error)); }
    }

    syncClipboard() {
        if (!this.gpaste) return;
        const window = global.display.focus_window;
        const app = window ? Shell.WindowTracker.get_default().get_window_app(window) : null;
        const id = app?.get_id();
        const excluded = this.settings.get_strv('clipboard-excluded-apps');
        const allowed = this.settings.get_boolean('clipboard-history-enabled') && Boolean(id) &&
            !excluded.includes(id) && !Main.sessionMode.isLocked && !Main.sessionMode.isGreeter && Main.sessionMode.hasWindows !== false;
        if (this.gpaste.get_boolean('track-changes') !== allowed)
            this.gpaste.set_boolean('track-changes', allowed);
    }

    windows() {
        return global.get_window_actors().map(actor => actor.meta_window).filter(window => window &&
            window.get_window_type() === Meta.WindowType.NORMAL && !window.get_transient_for() &&
            !window.is_on_all_workspaces()).sort((a, b) => a.get_stable_sequence() - b.get_stable_sequence());
    }

    appId(window) { return Shell.WindowTracker.get_default().get_window_app(window)?.get_id() ?? null; }

    GetStatus() {
        return JSON.stringify({zones: this.zones().length, clipboardTracking: this.gpaste?.get_boolean('track-changes') ?? false,
            clipboardAvailable: Boolean(this.gpaste), layoutAvailable: true});
    }

    GetLayout() {
        const ordinals = new Map();
        const result = [];
        for (const window of this.windows().slice(0, 100)) {
            const app = this.appId(window);
            if (!app) continue;
            const ordinal = ordinals.get(app) ?? 0;
            ordinals.set(app, ordinal + 1);
            const monitor = Math.max(0, window.get_monitor());
            const area = Main.layoutManager.getWorkAreaForMonitor(monitor);
            const frame = window.get_frame_rect();
            const w = Math.max(.06, Math.min(1, frame.width / area.width));
            const h = Math.max(.06, Math.min(1, frame.height / area.height));
            const x = Math.max(0, Math.min(1 - w, (frame.x - area.x) / area.width));
            const y = Math.max(0, Math.min(1 - h, (frame.y - area.y) / area.height));
            result.push({app, ordinal, monitor, workspace: Math.max(0, window.get_workspace()?.index() ?? 0),
                rect: [x, y, w, h], maximized: window.get_maximized() === Meta.MaximizeFlags.BOTH,
                fullscreen: window.is_fullscreen()});
        }
        return JSON.stringify(validatePlacements(result));
    }

    ApplyLayout(raw) {
        if (typeof raw !== 'string' || raw.length > 131072) throw new Error('Layout is too large');
        const placements = validatePlacements(JSON.parse(raw));
        const matches = new Map();
        for (const window of this.windows()) {
            const id = this.appId(window);
            if (!matches.has(id)) matches.set(id, []);
            matches.get(id).push(window);
        }
        let applied = 0, missing = 0;
        for (const item of placements) {
            const window = matches.get(item.app)?.[item.ordinal];
            if (!window) { missing++; continue; }
            const manager = global.workspace_manager;
            for (let attempt = 0; manager.n_workspaces <= item.workspace && attempt < 36; attempt++)
                manager.append_new_workspace(false, global.get_current_time());
            if (manager.n_workspaces <= item.workspace) { missing++; continue; }
            window.change_workspace(manager.get_workspace_by_index(item.workspace));
            this.move(window, item.monitor, item.rect);
            if (item.maximized) window.maximize(Meta.MaximizeFlags.BOTH);
            if (item.fullscreen) window.make_fullscreen();
            applied++;
        }
        return JSON.stringify({applied, missing});
    }

    move(window, monitor, rect) {
        monitor = Math.max(0, Math.min(global.display.get_n_monitors() - 1, monitor));
        const area = Main.layoutManager.getWorkAreaForMonitor(monitor);
        if (window.is_fullscreen()) window.unmake_fullscreen();
        window.unmaximize(Meta.MaximizeFlags.BOTH);
        window.move_to_monitor(monitor);
        window.move_resize_frame(true, Math.round(area.x + rect[0] * area.width), Math.round(area.y + rect[1] * area.height),
            Math.max(100, Math.round(rect[2] * area.width)), Math.max(80, Math.round(rect[3] * area.height)));
    }

    zones() {
        try {
            const zones = JSON.parse(this.settings.get_string('tiling-zones'));
            validatePlacements(zones.map(rect => ({app: 'zone.desktop', ordinal: 0, monitor: 0, workspace: 0,
                rect, maximized: false, fullscreen: false})));
            return zones.length <= 9 ? zones : [];
        } catch (_) { return []; }
    }

    placeZone(index) {
        const rect = this.zones()[index], window = global.display.focus_window;
        if (!rect || !window || window.get_window_type() !== Meta.WindowType.NORMAL || window.get_transient_for()) return;
        this.move(window, window.get_monitor(), rect);
    }

    disable() {
        if (this.gpaste) this.gpaste.set_boolean('track-changes', false);
        this.gpaste = null;
        for (const [object, id] of this.signals) object.disconnect(id);
        this.signals = [];
        for (const name of this.bindings) Main.wm.removeKeybinding(name);
        this.bindings = [];
        this._export?.unexport();this._export = null;
    }
}

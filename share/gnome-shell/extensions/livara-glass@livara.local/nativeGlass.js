// SPDX-License-Identifier: GPL-3.0-or-later
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';

const APPS = new Set(['org.livara.Center', 'org.livara.Settings', 'org.livara.Studio',
    'org.livara.Monitor', 'org.livara.Graphics', 'org.livara.Essentials',
    'org.livara.Palette', 'org.livara.Chat']);
const XML = `<node><interface name="org.livara.Glass1">
<method name="GetStatus"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
<method name="SetRegions"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="a(dddd)" direction="in"/></method>
<signal name="Changed"><arg type="s"/><arg type="s"/><arg type="b"/></signal>
</interface></node>`;

export default class NativeGlass {
    constructor(manager, material, radius) {
        this.manager = manager; this.material = material; this.radius = radius;
        this.actors = new Map(); this.ready = new Map(); this.signals = [];
        for (const [object, signal] of [[global.display, 'notify::focus-window'],
            [global.display, 'restacked'], [global.window_group, 'child-added'],
            [global.window_group, 'child-removed']])
            this.signals.push([object, object.connect(signal, () => this.queue())]);
        this.owner = Gio.bus_own_name(Gio.BusType.SESSION, 'org.livara.Glass',
            Gio.BusNameOwnerFlags.DO_NOT_QUEUE, connection => {
                this.bus = Gio.DBusExportedObject.wrapJSObject(XML,
                    {GetStatus: (id, path) => this.ready.get(JSON.stringify([id, path])) === true,
                        SetRegionsAsync: (args, invocation) => this.setRegions(args, invocation)});
                this.bus.export(connection, '/org/livara/Glass');
            }, null, null);
        this.queue();
    }

    queue() {
        if (this.idle || this.stopped) return;
        this.idle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this.idle = 0; this.refresh(); return GLib.SOURCE_REMOVE;
        });
    }

    setRegions([id, path, rectangles], invocation) {
        const actor = [...this.actors].find(([actor, state]) => state.id === id &&
            actor.meta_window.get_gtk_window_object_path() === path)?.[0];
        // Only the GTK client that owns this window can supply its chrome's
        // geometry. These are bounded uniforms, never source code or pixels.
        if (!actor || actor.meta_window.get_gtk_unique_bus_name?.() !== invocation.get_sender()) {
            invocation.return_dbus_error('org.livara.Glass.NotOwner', 'Window owner required'); return;
        }
        const frame = actor.meta_window.get_frame_rect();
        if (rectangles.length > 2 || rectangles.some(r => r.length !== 4 || !r.every(Number.isFinite) ||
            r[0] < 0 || r[1] < 0 || r[2] < 0 || r[3] < 0 || r[0] + r[2] > frame.width + 2 || r[1] + r[3] > frame.height + 2)) {
            invocation.return_dbus_error('org.livara.Glass.InvalidGeometry', 'Invalid chrome bounds'); return;
        }
        const entry = this.manager._entries.get(actor);
        if (entry) { entry.regions = rectangles; this.manager._geometry(entry); }
        invocation.return_value(null);
    }

    refresh() {
        if (this.stopped) return;
        const active = new Map();
        const focus = global.display.focus_window;
        for (const actor of global.get_window_actors()) {
            const window = actor.meta_window;
            const id = window.get_gtk_application_id() || window.get_wm_class();
            if (!APPS.has(id) || ![Meta.WindowType.NORMAL, Meta.WindowType.DIALOG].includes(window.get_window_type())) continue;
            active.set(actor, id);
            if (!this.actors.has(actor)) {
                const signals = ['notify::mapped', 'notify::allocation'].map(signal =>
                    [actor, actor.connect(signal, () => this.queue())]);
                signals.push([window, window.connect('notify::gtk-window-object-path', () => this.queue())]);
                signals.push([actor, actor.connect('destroy', () => {
                    for (const [object, signal] of signals) object.disconnect(signal);
                    this.manager.remove(actor); this.actors.delete(actor); this.queue();
                })]);
                this.actors.set(actor, {id, signals});
            }
            if (this.material() && actor.mapped && window === focus && !window.minimized) {
                try { this.manager.sync(actor, 'native', this.radius()); }
                catch (error) { this.manager.remove(actor); console.warn('Livara native material fallback: ' + error.message); }
            }
            else this.manager.remove(actor);
        }
        for (const [actor, state] of this.actors) {
            if (active.has(actor)) continue;
            for (const [object, signal] of state.signals) object.disconnect(signal);
            this.manager.remove(actor); this.actors.delete(actor);
        }
        const states = new Map();
        for (const [actor, id] of active) {
            // Use GTK's per-window bus identity, never document/window titles.
            const key = JSON.stringify([id, actor.meta_window.get_gtk_window_object_path() || '']);
            const ready = this.manager._entries.has(actor);
            states.set(key, states.has(key) ? states.get(key) && ready : ready);
        }
        for (const key of new Set([...this.ready.keys(), ...states.keys()])) {
            const ready = states.get(key) === true;
            if (this.ready.get(key) !== ready) {
                const [id, path] = JSON.parse(key);
                this.bus?.emit_signal('Changed', new GLib.Variant('(ssb)', [id, path, ready]));
            }
        }
        this.ready = states;
    }

    destroy() {
        this.stopped = true;
        if (this.idle) GLib.source_remove(this.idle);
        for (const [key, ready] of this.ready)
            if (ready) this.bus?.emit_signal('Changed', new GLib.Variant('(ssb)', [...JSON.parse(key), false]));
        for (const [actor, state] of this.actors) {
            for (const [object, signal] of state.signals) object.disconnect(signal);
            this.manager.remove(actor);
        }
        this.actors.clear();
        for (const [object, signal] of this.signals) object.disconnect(signal);
        this.bus?.unexport();
        if (this.owner) Gio.bus_unown_name(this.owner);
    }
}

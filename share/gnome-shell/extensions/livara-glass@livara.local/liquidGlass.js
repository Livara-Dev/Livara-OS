// SPDX-License-Identifier: GPL-3.0-or-later
// The shader samples a live compositor scene clone, never the foreground UI.
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';

export const DECLARATIONS = `
uniform vec2 lv_size;
uniform vec2 lv_surface;
uniform vec2 lv_light;
uniform float lv_radius;
uniform float lv_strength;
float lv_distance(vec2 p, vec2 halfSize, float r) {
    vec2 q = abs(p) - halfSize + vec2(r);
    return length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - r;
}
`;

export const FRAGMENT = `
vec2 uv = cogl_tex_coord_in[0].xy;
vec2 p = (uv - vec2(0.5)) * lv_size;
vec2 halfSize = lv_surface * 0.5;
float radius = min(lv_radius, min(halfSize.x, halfSize.y));
float distance = lv_distance(p, halfSize, radius);
vec2 q = abs(p) - halfSize + vec2(radius);
vec2 n;
if (max(q.x, q.y) > 0.0)
    n = normalize(max(q, vec2(0.0)) + vec2(0.0001)) * sign(p);
else
    n = q.x > q.y ? vec2(sign(p.x), 0.0) : vec2(0.0, sign(p.y));
float bevel = min(22.0, min(halfSize.x, halfSize.y) * 0.65);
float edge = 1.0 - smoothstep(0.0, bevel, -distance);
vec2 offset = n * lv_strength * edge * edge / lv_size;
offset += (uv - vec2(0.5)) * 0.022 * (lv_strength / 14.0) * (1.0 - edge);
vec2 refracted = clamp(uv - offset, vec2(0.001), vec2(0.999));
vec2 dispersion = n * min(0.65, lv_strength * 0.045) * edge * edge / lv_size;
vec3 scene;
scene.r = texture2D(cogl_sampler0, clamp(refracted + dispersion, vec2(0.001), vec2(0.999))).r;
scene.g = texture2D(cogl_sampler0, refracted).g;
scene.b = texture2D(cogl_sampler0, clamp(refracted - dispersion, vec2(0.001), vec2(0.999))).b;
float luminance = dot(scene, vec3(0.2126, 0.7152, 0.0722));
scene *= min(1.0, 0.30 / max(luminance, 0.001));
scene = mix(scene, vec3(0.04, 0.05, 0.08), 0.12);
vec2 light = normalize(vec2(-0.65, -0.85) + (lv_light - vec2(0.5)) * 0.5);
float rim = exp(-abs(distance + 1.1) * 1.15);
float specular = pow(max(dot(n, light), 0.0), 8.0) * rim * 0.72;
float caustic = pow(max(dot(-n, light), 0.0), 4.0) * edge * edge * 0.12;
vec3 color = scene + vec3(specular) + vec3(0.68, 0.80, 1.0) * caustic;
float mask = 1.0 - smoothstep(-0.8, 0.3, distance);
cogl_color_out = vec4(color * mask, mask) * cogl_color_in;
`;

export const LiquidLensEffect = GObject.registerClass({GTypeName:'LivaraLiquidLensEffect'},
class LiquidLensEffect extends Shell.GLSLEffect {
    _init() {
        super._init();
        this._locations = {};
        for (const name of ['size', 'surface', 'light', 'radius', 'strength'])
            this._locations[name] = this.get_uniform_location('lv_' + name);
        this.configure(400, 160, 400, 160, 28, 14);
        this.light(0.5, 0.5);
    }

    vfunc_build_pipeline() {
        this.add_glsl_snippet(Shell.SnippetHook.FRAGMENT, DECLARATIONS, FRAGMENT, true);
    }

    configure(width, height, surfaceWidth, surfaceHeight, radius, strength) {
        this.set_uniform_float(this._locations.size, 2, [width, height]);
        this.set_uniform_float(this._locations.surface, 2, [surfaceWidth, surfaceHeight]);
        this.set_uniform_float(this._locations.radius, 1, [radius]);
        this.set_uniform_float(this._locations.strength, 1, [strength]);
    }

    light(x, y) {
        this.set_uniform_float(this._locations.light, 2, [x, y]);
    }
});


// Keep the compositor's groups out of the capture: those groups have zero
// allocations and cloning them produces an empty image. Clone their allocated
// background/window actors individually, in stacking order.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const MAX_LENSES = 8;
const MAX_PIXELS = 6000000;
const PAD = 24;
const INTERNAL = '_livaraLiquidInternal';

export class LiquidBackdrops {
    constructor(animations, changed = () => {}) {
        this._animations = animations;
        this._changed = changed;
        this._candidates = new Map();
        this._entries = new Map();
        this._signals = [];
        this._watch(global.display, 'restacked', () => this._queueRebuild());
        this._watch(global.window_group, 'child-added', () => this._queueRebuild());
        this._watch(global.window_group, 'child-removed', () => this._queueRebuild());
        this._watch(global.workspace_manager, 'active-workspace-changed', () => this._queueRebuild());
        this._watch(Main.layoutManager._backgroundGroup, 'child-added', () => this._queueRebuild());
        this._watch(Main.layoutManager._backgroundGroup, 'child-removed', () => this._queueRebuild());
        this._watch(global.stage, 'motion-event', (_actor, event) => {
            if (this._animations()) {
                const [x, y] = event.get_coords();
                for (const entry of this._entries.values()) {
                    entry.effect.light(Math.max(0, Math.min(1, (x - entry.x) / entry.width)),
                        Math.max(0, Math.min(1, (y - entry.y) / entry.height)));
                    entry.plane.queue_redraw();
                }
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this._queueRebuild();
    }

    _watch(object, signal, callback, store = this._signals) {
        if (object)
            store.push([object, object.connect(signal, callback)]);
    }

    _disconnect(signals) {
        for (const [object, id] of signals)
            object.disconnect(id);
        signals.length = 0;
    }

    _potentialSources() {
        const result = [];
        for (const group of [global.window_group, global.top_window_group]) {
            if (!group) continue;
            for (const actor of group.get_children()) {
                const candidates = actor === Main.layoutManager._backgroundGroup ? actor.get_children() : [actor];
                for (const source of candidates)
                    if (!source[INTERNAL]) result.push(source);
            }
        }
        return result;
    }

    _sources() {
        const active = global.workspace_manager.get_active_workspace();
        const sources = this._potentialSources();
        if (sources.length > 256) return [];
        const visible = sources.filter(source => {
            if (!source.mapped || !source.visible || source.width < 1 || source.height < 1) return false;
            const window = source.meta_window ?? source.get_meta_window?.();
            return !window || (!window.minimized && window.located_on_workspace(active));
        });
        return visible.length <= 64 ? visible : [];
    }

    _trackCandidates() {
        const sources = this._potentialSources().slice(0, 256);
        for (const [source, signals] of this._candidates) {
            if (!sources.includes(source)) { this._disconnect(signals); this._candidates.delete(source); }
        }
        for (const source of sources) {
            if (this._candidates.has(source)) continue;
            const signals = [];
            this._candidates.set(source, signals);
            for (const prop of ['mapped','visible'])
                this._watch(source, 'notify::' + prop, () => this._queueRebuild(), signals);
            this._watch(source, 'notify::allocation', () => {
                if (![...this._entries.values()].some(entry => entry.sources.has(source))) this._queueRebuild();
            }, signals);
            const window = source.meta_window ?? source.get_meta_window?.();
            if (window) {
                this._watch(window, 'notify::minimized', () => this._queueRebuild(), signals);
                this._watch(window, 'workspace-changed', () => this._queueRebuild(), signals);
            }
            this._watch(source, 'destroy', () => {
                // Disconnect while the actor still exists, not in the next
                // idle after Mutter has disposed its background actor.
                this._disconnect(signals);
                this._candidates.delete(source);
                this._queueRebuild();
            }, signals);
        }
    }

    _queueRebuild() {
        if (this._rebuildIdle || this._destroyed) return;
        this._rebuildIdle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._rebuildIdle = 0;
            this._rebuild();
            return GLib.SOURCE_REMOVE;
        });
    }

    sync(actor, kind, blurRadius) {
        const target = kind === 'panel' ? Main.panel : actor;
        if (!target.mapped || !this._sources().length) {
            this.remove(actor);
            return false;
        }
        let entry = this._entries.get(actor);
        if (!entry) {
            if (this._entries.size >= MAX_LENSES)
                return false;
            let anchor = target;
            while (anchor.get_parent() && anchor.get_parent() !== Main.uiGroup)
                anchor = anchor.get_parent();
            if (anchor.get_parent() !== Main.uiGroup)
                return false;
            const plane = new Clutter.Actor({name:'livara-liquid-scene', reactive:false, clip_to_allocation:true});
            plane[INTERNAL] = true;
            const blur = new Shell.BlurEffect({mode:Shell.BlurMode.ACTOR});
            plane.add_effect_with_name('livara-scene-softening', blur);
            const effect = new LiquidLensEffect();
            plane.add_effect_with_name('livara-live-refraction', effect);
            entry = {actor, target, plane, blur, effect, kind, sources:new Map(), signals:[], pixels:0};
            this._entries.set(actor, entry);
            Main.uiGroup.insert_child_below(plane, anchor);
            for (let ancestor = target, depth = 0; ancestor && ancestor !== Main.uiGroup && depth < 12;
                ancestor = ancestor.get_parent(), depth++) {
                for (const prop of ['allocation','translation-x','translation-y','scale-x','scale-y','opacity','mapped'])
                    this._watch(ancestor, 'notify::' + prop, () => {
                        if (!target.mapped) this.remove(actor);
                        else if (!this._geometry(entry)) this.remove(actor);
                    }, entry.signals);
            }
            this._rebuildEntry(entry);
        }
        entry.blur.radius = Math.max(0, Math.min(20, blurRadius / 2));
        entry.blur.brightness = 1;
        if (!this._geometry(entry)) {
            this.remove(actor);
            return false;
        }
        if (!actor.has_style_class_name('livara-liquid-surface'))
            actor.add_style_class_name('livara-liquid-surface');
        return true;
    }

    _geometry(entry) {
        if (!this._entries.has(entry.actor) || !entry.target.mapped)
            return false;
        const [x, y] = entry.target.get_transformed_position();
        const [width, height] = entry.target.get_transformed_size();
        const scale = Math.max(1, entry.target.get_resource_scale?.() ?? 1, global.stage.get_resource_scale?.() ?? 1);
        const pixels = Math.ceil(width + PAD * 2) * Math.ceil(height + PAD * 2) * scale * scale;
        const used = [...this._entries.values()].reduce((sum, item) => sum + (item === entry ? 0 : item.pixels), 0);
        if (![x,y,width,height].every(Number.isFinite) || width < 2 || height < 2 ||
            width > 4096 || height > 2160 || used + pixels > MAX_PIXELS)
            return false;
        entry.pixels = pixels;
        entry.x = x; entry.y = y; entry.width = width; entry.height = height;
        entry.plane.set_position(x - PAD, y - PAD);
        entry.plane.set_size(width + PAD * 2, height + PAD * 2);
        entry.plane.opacity = entry.target.get_paint_opacity();
        entry.effect.configure(width + PAD * 2, height + PAD * 2, width, height,
            entry.kind === 'panel' ? Math.min(18, height / 2) : 30, Math.min(14, height * 0.19));
        for (const [source, state] of entry.sources)
            this._place(entry, source, state.clone);
        entry.plane.queue_redraw();
        return true;
    }

    _place(entry, source, clone) {
        const [x,y] = source.get_transformed_position();
        const [width,height] = source.get_transformed_size();
        const valid = [x,y,width,height,entry.x,entry.y].every(Number.isFinite) && width > 0 && height > 0;
        clone.visible = valid;
        if (!valid) return false;
        clone.set_position(x - entry.x + PAD, y - entry.y + PAD);
        clone.set_size(width, height);
        clone.opacity = source.get_paint_opacity();
        return true;
    }

    _rebuildEntry(entry) {
        const sources = this._sources();
        for (const [source, state] of entry.sources) {
            if (!sources.includes(source)) {
                this._disconnect(state.signals);
                state.clone.destroy();
                entry.sources.delete(source);
            }
        }
        let previous = null;
        for (const source of sources) {
            let state = entry.sources.get(source);
            if (!state) {
                const clone = new Clutter.Clone({source, reactive:false});
                state = {clone, signals:[]};
                entry.sources.set(source, state);
                entry.plane.add_child(clone);
                for (const prop of ['allocation','translation-x','translation-y','scale-x','scale-y','opacity'])
                    this._watch(source, 'notify::' + prop, () => this._geometry(entry), state.signals);
                for (const prop of ['visible','mapped'])
                    this._watch(source, 'notify::' + prop, () => this._rebuildEntry(entry), state.signals);
                const window = source.meta_window ?? source.get_meta_window?.();
                if (window) {
                    this._watch(window, 'notify::minimized', () => this._rebuild(), state.signals);
                    this._watch(window, 'workspace-changed', () => this._rebuild(), state.signals);
                }
                this._watch(source, 'destroy', () => {
                    this._disconnect(state.signals);
                    state.clone.destroy();
                    entry.sources.delete(source);
                }, state.signals);
            }
            entry.plane.set_child_above_sibling(state.clone, previous);
            previous = state.clone;
        }
        this._geometry(entry);
    }

    _rebuild() {
        if (this._destroyed) return;
        this._trackCandidates();
        for (const entry of this._entries.values()) this._rebuildEntry(entry);
        this._changed();
    }

    resetLight() {
        for (const entry of this._entries.values()) {
            entry.effect.light(0.5, 0.5);
            entry.plane.queue_redraw();
        }
    }

    remove(actor) {
        const entry = this._entries.get(actor);
        if (!entry)
            return;
        this._entries.delete(actor);
        this._disconnect(entry.signals);
        for (const state of entry.sources.values())
            this._disconnect(state.signals);
        entry.sources.clear();
        actor.remove_style_class_name('livara-liquid-surface');
        entry.plane.remove_effect_by_name('livara-live-refraction');
        entry.plane.remove_effect_by_name('livara-scene-softening');
        entry.effect = entry.blur = null;
        entry.plane.destroy();
    }

    destroy() {
        this._destroyed = true;
        if (this._rebuildIdle) GLib.source_remove(this._rebuildIdle);
        this._rebuildIdle = 0;
        this._disconnect(this._signals);
        for (const signals of this._candidates.values()) this._disconnect(signals);
        this._candidates.clear();
        for (const actor of [...this._entries.keys()])
            this.remove(actor);
    }
}

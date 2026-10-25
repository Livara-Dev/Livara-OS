// SPDX-License-Identifier: GPL-3.0-or-later
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GdkPixbuf from 'gi://GdkPixbuf';
import Cogl from 'gi://Cogl';
import Shell from 'gi://Shell';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import WindowEffects from './windowEffects.js';
import DesktopTools from './desktopTools.js';
import {LiquidBackdrops} from './liquidGlass.js';

const MAX_DEPTH = 8;
const MAX_WATCHED = 1600;
const MAX_SURFACES = 24;
const MAX_RIM_TEXTURE = 512;

export default class LivaraGlass extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._surfaces = new Map();
        this._brands = new Map();
        this._watched = new Map();
        this._pending = new Map();
        this._signals = [];
        try { this._liquid = new LiquidBackdrops(() => this._animations(), () => {
            if (this._material) for (const actor of this._surfaces.keys()) this._syncSurface(actor);
        }); }
        catch (error) { console.warn(`Livara: live refraction unavailable; using background blur: ${error.message}`); }
        this._interfaceSettings = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._accessibilitySettings = new Gio.Settings({schema_id: 'org.gnome.desktop.a11y.interface'});
        this._connect(this._settings, 'changed', () => this._refresh());
        this._connect(this._accessibilitySettings, 'changed::high-contrast', () => this._refresh());
        this._connect(this._interfaceSettings, 'changed::gtk-theme', () => this._refresh());
        this._connect(this._interfaceSettings, 'changed::enable-animations', () => {
            if (!this._animations()) {
                this._liquid?.resetLight();
                this._panelBackground.remove_all_transitions();
                this._panelBackground.opacity = 255;
                for (const actor of this._brands.keys()) {
                    actor.remove_all_transitions();
                    actor.opacity = 255;
                    actor.scale_x = actor.scale_y = 1;
                }
            }
        });
        this._connect(Main.sessionMode, 'updated', () => this._refresh());
        this._connect(Main.overview, 'showing', () => this._refresh());
        this._connect(Main.overview, 'hidden', () => this._refresh());
        // A separate backplate keeps the panel's text and icons sharp. It is a
        // sibling of panelBox, avoiding constraints inside its vertical layout.
        this._panelBackground = new St.Widget({
            style_class: 'livara-panel-background', reactive: false, visible: false,
        });
        Main.uiGroup.insert_child_below(this._panelBackground, Main.layoutManager.panelBox);
        this._panelBackground.add_constraint(new Clutter.BindConstraint({
            source: Main.layoutManager.panelBox, coordinate: Clutter.BindCoordinate.ALL,
        }));
        this._addSurface(this._panelBackground, 'panel');
        this._connect(Main.panel, 'notify::mapped', () => this._refresh());
        this._connect(Main.layoutManager.panelBox, 'notify::visible', () => this._refresh());
        this._windowEffects = new WindowEffects(this._settings, this._interfaceSettings);
        this._windowEffects.enable();
        this._desktopTools = new DesktopTools(this._settings);
        this._desktopTools.enable();
        this._refresh();
        this._queue(Main.uiGroup, 0);
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    _animations() {
        return this._interfaceSettings.get_boolean('enable-animations');
    }

    _refresh() {
        this._radius = Math.max(0, Math.min(60, this._settings.get_int('blur-radius')));
        const highContrast = this._accessibilitySettings.get_boolean('high-contrast') ||
            this._interfaceSettings.get_string('gtk-theme').toLowerCase().includes('highcontrast');
        this._material = this._settings.get_boolean('glass-enabled') && !highContrast &&
            !Main.sessionMode.isLocked && !Main.sessionMode.isGreeter &&
            Main.sessionMode.hasWindows !== false &&
            !Main.overview.visible && !Main.overview.visibleTarget;
        Main.panel[this._material ? 'add_style_class_name' : 'remove_style_class_name']('livara-panel');
        Main.uiGroup[this._material ? 'add_style_class_name' : 'remove_style_class_name']('livara-glass');
        const panelVisible = this._material && Main.panel.mapped && Main.layoutManager.panelBox.visible;
        const reveal = panelVisible && !this._panelBackground.visible;
        this._panelBackground.visible = panelVisible;
        if (reveal && this._animations()) {
            this._panelBackground.opacity = 0;
            this._panelBackground.ease({opacity: 255, duration: 220,
                mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
        } else if (!this._material) {
            this._panelBackground.remove_all_transitions();
            this._panelBackground.opacity = 255;
        }
        for (const actor of this._surfaces.keys())
            this._syncSurface(actor);
    }

    _queue(actor, depth) {
        if (!actor || actor._livaraLiquidInternal || actor === this._panelBackground || depth > MAX_DEPTH)
            return;
        this._pending.set(actor, depth);
        if (this._idle)
            return;
        // Child/style signals coalesce into one finite idle, with no recurring
        // actor-tree timer. New subtrees alone are inspected after startup.
        this._idle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._idle = 0;
            const pending = [...this._pending];
            this._pending.clear();
            for (const [item, itemDepth] of pending)
                this._observe(item, itemDepth);
            return GLib.SOURCE_REMOVE;
        });
    }

    _observe(actor, depth) {
        if (actor._livaraLiquidInternal || actor === this._panelBackground || depth > MAX_DEPTH ||
            actor === global.window_group || actor === global.top_window_group)
            return;
        this._brandLauncher(actor);
        if (actor instanceof St.Icon || actor instanceof St.Label)
            return;
        this._classify(actor);
        if (this._watched.has(actor) || this._watched.size >= MAX_WATCHED)
            return;
        const state = {signals: []};
        this._watched.set(actor, state);
        state.signals.push(actor.connect('child-added', (_parent, child) => this._queue(child, depth + 1)));
        state.signals.push(actor.connect('child-removed', (_parent, child) => this._forgetTree(child)));
        state.signals.push(actor.connect('destroy', () => {
            this._pending.delete(actor);
            this._watched.delete(actor);
            this._removeSurface(actor, false);
        }));
        if (actor instanceof St.Widget) {
            state.signals.push(actor.connect('notify::style-class', () => this._queue(actor, depth)));
        }
        for (const child of actor.get_children())
            this._observe(child, depth + 1);
    }

    _classify(actor) {
        if (actor.has_style_class_name?.('dash-background'))
            this._addSurface(actor, 'dock');
        else if (actor.has_style_class_name?.('popup-menu-content'))
            this._addSurface(actor, 'menu');
        else if (actor.has_style_class_name?.('notification-banner'))
            this._addSurface(actor, 'notification');
        else if (actor.has_style_class_name?.('osd-window'))
            this._addSurface(actor, 'osd');
        else if (actor.has_style_class_name?.('modal-dialog'))
            this._addSurface(actor, 'dialog');
        else if (actor !== this._panelBackground)
            this._removeSurface(actor);
    }

    _forgetTree(actor) {
        this._pending.delete(actor);
        for (const child of actor.get_children())
            this._forgetTree(child);
        this._removeSurface(actor);
        this._unbrand(actor);
        const state = this._watched.get(actor);
        if (state) {
            for (const id of state.signals)
                actor.disconnect(id);
            this._watched.delete(actor);
        }
    }

    _brandLauncher(actor) {
        if (!(actor instanceof St.Icon) || this._brands.has(actor))
            return;
        const name = actor.icon_name ?? '';
        if (!actor.has_style_class_name('show-apps-icon') && !name.startsWith('view-app-grid-ubuntu'))
            return;
        const state = {name: actor.icon_name, gicon: actor.gicon,
            scaleX: actor.scale_x, scaleY: actor.scale_y, opacity: actor.opacity,
            pivot: actor.get_pivot_point()};
        state.destroyed = actor.connect('destroy', () => this._unbrand(actor, false));
        this._brands.set(actor, state);
        actor.icon_name = 'org.livara.Center';
        actor.add_style_class_name('livara-launcher');
        actor.set_pivot_point(0.5, 0.5);
        let button = actor.get_parent();
        for (let i = 0; button && i < 3 && !(button instanceof St.Button); i++)
            button = button.get_parent();
        if (button instanceof St.Button) {
            state.button = button;
            state.hover = button.connect('notify::hover', () => {
                if (this._animations()) {
                    const scale = button.hover ? 1.06 : 1;
                    actor.ease({scale_x: scale, scale_y: scale, duration: 160,
                        mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
                }
            });
        }
        if (actor.mapped && this._animations()) {
            actor.opacity = 0;
            actor.scale_x = actor.scale_y = 0.88;
            actor.ease({opacity: 255, scale_x: 1, scale_y: 1, duration: 260,
                mode: Clutter.AnimationMode.EASE_OUT_CUBIC});
        }
    }

    _unbrand(actor, restore = true) {
        const state = this._brands.get(actor);
        if (!state)
            return;
        actor.disconnect(state.destroyed);
        if (state.button)
            state.button.disconnect(state.hover);
        if (!restore) {
            this._brands.delete(actor);
            return;
        }
        actor.remove_all_transitions();
        actor.remove_style_class_name('livara-launcher');
        actor.icon_name = state.name;
        if (!state.name)
            actor.gicon = state.gicon;
        actor.scale_x = state.scaleX;
        actor.scale_y = state.scaleY;
        actor.opacity = state.opacity;
        actor.set_pivot_point(...state.pivot);
        this._brands.delete(actor);
    }

    _addSurface(actor, kind) {
        if (this._surfaces.has(actor) || this._surfaces.size >= MAX_SURFACES)
            return;
        const state = {kind, signals: [], content: actor.content, gravity: actor.content_gravity};
        this._surfaces.set(actor, state);
        state.signals.push(actor.connect('notify::mapped', () => this._syncSurface(actor)));
        state.signals.push(actor.connect('notify::allocation', () => {
            if (!this._material || !actor.mapped) return;
            if (this._liquid) {
                this._syncSurface(actor);
                if (state.liquid) return;
            }
            if (!state.rim) return;
            const width = Math.round(actor.width), height = Math.round(actor.height);
            if (width === state.width && height === state.height)
                return;
            if (state.resize)
                GLib.source_remove(state.resize);
            // Rasterize highlights only after layout settles, never on each
            // animation frame. Their cached texture has a 512px maximum edge.
            state.resize = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 120, () => {
                state.resize = 0;
                if (this._material && actor.mapped)
                    this._updateRim(actor, state);
                return GLib.SOURCE_REMOVE;
            });
        }));
        state.signals.push(actor.connect('destroy', () => this._removeSurface(actor, false)));
        this._syncSurface(actor);
    }

    _syncSurface(actor) {
        const state = this._surfaces.get(actor);
        if (!state)
            return;
        const visible = this._material && actor.mapped;
        if (visible && !state.content && this._liquid) {
            try { state.liquid = this._liquid.sync(actor, state.kind, this._radius); }
            catch (error) {
                console.warn(`Livara: liquid surface fallback: ${error.message}`);
                this._liquid.remove(actor); state.liquid = false;
            }
            if (state.liquid) {
                if (state.effect) { actor.remove_effect(state.effect); state.effect = null; }
                this._clearRim(actor, state);
                return;
            }
        } else { this._liquid?.remove(actor); state.liquid = false; }
        if (visible && this._radius > 0) {
            if (!state.effect) {
                state.effect = new Shell.BlurEffect({mode: Shell.BlurMode.BACKGROUND});
                actor.add_effect_with_name('livara-glass-blur', state.effect);
            }
            // GNOME 46 uses radius, not the obsolete sigma property.
            state.effect.radius = this._radius;
            // Content plates carry contrast; keep the sampled scene luminous
            // instead of tinting every surface into the same dark purple pane.
            state.effect.brightness = ['menu', 'dialog', 'notification'].includes(state.kind) ? 0.90 : 0.96;
        } else if (state.effect) {
            actor.remove_effect(state.effect);
            state.effect = null;
        }
        if (visible && !state.rim && !state.content)
            this._updateRim(actor, state);
        else if (!visible)
            this._clearRim(actor, state);
    }

    _updateRim(actor, state) {
        if (state.rimFailed)
            return;
        try {
            this._paintRim(actor, state);
        } catch (error) {
            // The CSS material and real blur remain usable if a particular
            // renderer cannot upload the optional reflective texture.
            state.rimFailed = true;
            console.warn(`Livara Glass: optional highlight unavailable: ${error.message}`);
        }
    }

    _paintRim(actor, state) {
        const width = Math.round(actor.width), height = Math.round(actor.height);
        if (width < 2 || height < 2 || state.content)
            return;
        const radius = state.kind === 'panel' ? 0 : Math.min(28, width / 2, height / 2);
        // This original seven-stop reflective artwork adds an optical rim and
        // soft interior highlights. It is a static texture over real compositor
        // blur; it does not displace/refract the desktop's sampled pixels.
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs><linearGradient id="body" x2="0" y2="1">
<stop stop-color="#ffffff" stop-opacity=".26"/>
<stop offset=".08" stop-color="#ded4ff" stop-opacity=".09"/>
<stop offset=".32" stop-color="#b8a3ed" stop-opacity=".018"/>
<stop offset=".5" stop-color="#9074c4" stop-opacity="0"/>
<stop offset=".7" stop-color="#93cbff" stop-opacity=".018"/>
<stop offset=".92" stop-color="#abc5ff" stop-opacity=".075"/>
<stop offset="1" stop-color="#e3deff" stop-opacity=".19"/>
</linearGradient><linearGradient id="edge" x2="1" y2="1">
<stop stop-color="#ffffff" stop-opacity=".72"/>
<stop offset=".22" stop-color="#e4cdff" stop-opacity=".38"/>
<stop offset=".46" stop-color="#8b6eb5" stop-opacity=".06"/>
<stop offset=".68" stop-color="#a5d4ff" stop-opacity=".22"/>
<stop offset="1" stop-color="#f0e3ff" stop-opacity=".48"/>
</linearGradient>
<radialGradient id="lens" cx="0" cy="0" r="1">
<stop stop-color="#ffffff" stop-opacity=".18"/>
<stop offset=".4" stop-color="#dcecff" stop-opacity=".045"/>
<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
</radialGradient>
<radialGradient id="caustic" cx="1" cy="1" r="1">
<stop stop-color="#e8efff" stop-opacity=".12"/>
<stop offset=".25" stop-color="#d4bcff" stop-opacity=".025"/>
<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
</radialGradient></defs>
<rect x=".75" y=".75" width="${width - 1.5}" height="${height - 1.5}" rx="${radius}" fill="url(#body)" stroke="url(#edge)" stroke-width="1.1"/>
<rect x="2" y="2" width="${Math.max(0, width - 4)}" height="${Math.max(0, height - 4)}" rx="${Math.max(0, radius - 1)}" fill="url(#lens)"/>
<rect x="2" y="2" width="${Math.max(0, width - 4)}" height="${Math.max(0, height - 4)}" rx="${Math.max(0, radius - 1)}" fill="url(#caustic)"/>
<rect x="2" y="2" width="${Math.max(0, width - 4)}" height="${Math.max(0, height - 4)}" rx="${Math.max(0, radius - 1)}" fill="none" stroke="#ffffff" stroke-opacity=".055" stroke-width=".7"/>
</svg>`;
        const scale = Math.min(1, MAX_RIM_TEXTURE / Math.max(width, height));
        const loader = GdkPixbuf.PixbufLoader.new_with_type('svg');
        loader.set_size(Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale)));
        loader.write(new TextEncoder().encode(svg));
        loader.close();
        const pixbuf = loader.get_pixbuf();
        const image = new Clutter.Image();
        image.set_data(pixbuf.get_pixels(), Cogl.PixelFormat.RGBA_8888,
            pixbuf.width, pixbuf.height, pixbuf.rowstride);
        state.rim = image;
        state.width = width;
        state.height = height;
        actor.content_gravity = Clutter.ContentGravity.RESIZE_FILL;
        actor.content = image;
    }

    _clearRim(actor, state, restore = true) {
        if (state.resize)
            GLib.source_remove(state.resize);
        state.resize = 0;
        if (state.rim && restore) {
            if (actor.content === state.rim)
                actor.content = state.content;
            actor.content_gravity = state.gravity;
        }
        state.rim = null;
    }

    _removeSurface(actor, restore = true) {
        const state = this._surfaces.get(actor);
        if (!state)
            return;
        this._liquid?.remove(actor);
        for (const id of state.signals)
            actor.disconnect(id);
        if (restore && state.effect)
            actor.remove_effect(state.effect);
        this._clearRim(actor, state, restore);
        this._surfaces.delete(actor);
    }

    disable() {
        this._desktopTools?.disable();this._desktopTools = null;
        this._windowEffects?.disable();
        this._windowEffects = null;
        if (this._idle)
            GLib.source_remove(this._idle);
        this._idle = 0;
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = [];
        for (const [actor, state] of this._watched) {
            for (const id of state.signals)
                actor.disconnect(id);
        }
        this._watched.clear();
        this._pending.clear();
        for (const actor of [...this._surfaces.keys()])
            this._removeSurface(actor);
        for (const actor of [...this._brands.keys()])
            this._unbrand(actor);
        Main.panel.remove_style_class_name('livara-panel');
        Main.uiGroup.remove_style_class_name('livara-glass');
        this._liquid?.destroy(); this._liquid = null;
        this._panelBackground.remove_all_transitions();
        this._panelBackground.destroy();
        this._panelBackground = null;
        this._settings = null;
        this._interfaceSettings = null;
        this._accessibilitySettings = null;
    }
}

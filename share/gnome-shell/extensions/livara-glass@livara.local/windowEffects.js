// SPDX-License-Identifier: GPL-3.0-or-later
// GNOME Shell 46.2 WindowManager's map/destroy bookkeeping is retained. Its
// constructor binds those methods, so replacing the method alone is ineffective.
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const PROPERTIES = ['opacity', 'scale-x', 'scale-y', 'translation-y'];
const MAX_ACTIVE = 12;

function restoreProperty(object, key, descriptor) {
    if (descriptor)
        Object.defineProperty(object, key, descriptor);
    else
        delete object[key];
}

function probeOverride(object, key) {
    const original = object[key];
    if (typeof original !== 'function')
        throw new Error(`Window-manager API is missing: ${key}`);
    const descriptor = Object.getOwnPropertyDescriptor(object, key);
    const probe = () => {};
    try {
        object[key] = probe;
        if (object[key] !== probe)
            throw new Error(`Window-manager API is not replaceable: ${key}`);
    } finally {
        restoreProperty(object, key, descriptor);
    }
}

export default class WindowEffects {
    constructor(settings, interfaceSettings) {
        this._settings = settings;
        this._interface = interfaceSettings;
        this._active = new Map();
        this._signals = [];
        this._blocked = [];
        this._enabled = false;
    }

    enable() {
        this._wm = Main.wm;
        this._shellwm = global.window_manager;
        if (!this._wm || this._wm._shellwm !== this._shellwm ||
            typeof this._wm._shouldAnimateActor !== 'function' ||
            this._wm._mapWindow?.name !== '_mapWindow' || this._wm._destroyWindow?.name !== '_destroyWindow') {
            console.warn('Livara: window effects need the standard GNOME 46 window manager; keeping native behavior.');
            return false;
        }
        this._native = {map: this._wm._mapWindow, destroy: this._wm._destroyWindow};
        try {
            probeOverride(this._wm, '_shouldAnimateActor');
            probeOverride(this._shellwm, 'completed_map');
            probeOverride(this._shellwm, 'completed_destroy');
            const handlers = ['map', 'destroy'].map(signal => ({signal,
                id: GObject.signal_handler_find(this._shellwm, {signalId: signal})}));
            if (handlers.some(item => !item.id))
                throw new Error('Native window-manager signal handler was not found');
            for (const {id} of handlers) {
                GObject.signal_handler_block(this._shellwm, id);
                this._blocked.push(id);
            }
            for (const {signal} of handlers)
                this._connect(this._shellwm, signal, (_shellwm, actor) => this._handle(signal, actor));
            this._connect(this._shellwm, 'kill-window-effects', (_shellwm, actor) => this._finish(actor));
            this._connect(this._settings, 'changed', (_settings, key) => {
                if (key === 'window-animation-style')
                    this._finishAll();
            });
            this._connect(this._interface, 'changed::enable-animations', () => {
                if (!this._interface.get_boolean('enable-animations'))
                    this._finishAll();
            });
            this._connect(Main.overview, 'showing', () => this._finishAll());
            this._connect(Main.sessionMode, 'updated', () => {
                if (Main.sessionMode.isLocked || Main.sessionMode.isGreeter || Main.sessionMode.hasWindows === false)
                    this._finishAll();
            });
            this._enabled = true;
            return true;
        } catch (error) {
            console.warn(`Livara: window effects unavailable: ${error.message}`);
            this.disable();
            return false;
        }
    }

    _connect(object, signal, callback) {
        this._signals.push([object, object.connect(signal, callback)]);
    }

    _normal(actor) {
        const window = actor?.meta_window;
        return window && window.get_window_type() === Meta.WindowType.NORMAL &&
            !window.get_transient_for() && !window.is_attached_dialog() && !window.is_fullscreen();
    }

    _allowed(actor) {
        return this._enabled && this._active.size < MAX_ACTIVE && this._normal(actor) && this._interface.get_boolean('enable-animations') &&
            !Main.sessionMode.isLocked && !Main.sessionMode.isGreeter && Main.sessionMode.hasWindows !== false &&
            !Main.overview.visible && !Main.overview.visibleTarget &&
            ['zoom', 'lift', 'fade'].includes(this._settings.get_string('window-animation-style'));
    }

    _handle(kind, actor) {
        if (!this._normal(actor)) {
            // Dialogs, popups, fullscreen windows and Wayland transients retain
            // GNOME's dimming, sizing, accessibility and animation behavior.
            this._native[kind].call(this._wm, this._shellwm, actor);
            return;
        }
        this._finish(actor);
        const wm = this._wm, shellwm = this._shellwm;
        const key = `completed_${kind}`;
        const originalComplete = shellwm[key];
        const originalShould = wm._shouldAnimateActor;
        const completeDescriptor = Object.getOwnPropertyDescriptor(shellwm, key);
        const shouldDescriptor = Object.getOwnPropertyDescriptor(wm, '_shouldAnimateActor');
        let requested = false, deferred = false, completed = false;
        const complete = () => {
            if (completed)
                return;
            completed = true;
            originalComplete.call(shellwm, actor);
        };
        // GNOME 46.2 calls this predicate and the no-animation completion
        // synchronously, before its first await. Divert only this actor's visual
        // branch; original notify/dimming/disconnection bookkeeping still runs.
        const should = (candidate, types) => {
            const nativeAllowed = originalShould.call(wm, candidate, types);
            if (candidate !== actor)
                return nativeAllowed;
            requested = nativeAllowed && this._allowed(actor);
            return false;
        };
        const completion = candidate => {
            if (candidate !== actor)
                return originalComplete.call(shellwm, candidate);
            if (requested)
                deferred = true;
            else
                complete();
            return undefined;
        };
        let result, invoked = false;
        try {
            wm._shouldAnimateActor = should;
            shellwm[key] = completion;
            invoked = true;
            result = this._native[kind].call(wm, shellwm, actor);
        } catch (error) {
            console.warn(`Livara: ${kind} bookkeeping failed: ${error.message}`);
            if (invoked)
                complete();
        } finally {
            restoreProperty(wm, '_shouldAnimateActor', shouldDescriptor);
            restoreProperty(shellwm, key, completeDescriptor);
        }
        if (!invoked) {
            this.disable();
            this._native[kind].call(wm, shellwm, actor);
            return;
        }
        if (result && typeof result.catch === 'function') {
            result.catch(error => {
                console.warn(`Livara: ${kind} bookkeeping failed: ${error.message}`);
                this._finish(actor);
                complete();
            });
        }
        if (deferred && !completed) {
            try {
                this._start(kind, actor, complete);
            } catch (error) {
                console.warn(`Livara: window transition unavailable: ${error.message}`);
                if (!this._finish(actor))
                    complete();
            }
        }
    }

    _start(kind, actor, complete) {
        const style = this._settings.get_string('window-animation-style');
        const duration = Math.max(80, Math.min(600, this._settings.get_int('window-animation-duration')));
        const state = {kind, complete, done: false, opacity: actor.opacity,
            scaleX: actor.scale_x, scaleY: actor.scale_y, translationY: actor.translation_y,
            pivot: actor.get_pivot_point()};
        this._active.set(actor, state);
        state.destroy = actor.connect('destroy', () => this._finish(actor, true));
        actor.set_pivot_point(0.5, 0.5);
        const target = {opacity: kind === 'map' ? state.opacity : 0, duration,
            mode: kind === 'map' ? Clutter.AnimationMode.EASE_OUT_CUBIC : Clutter.AnimationMode.EASE_IN_QUAD,
            onStopped: () => this._finish(actor)};
        if (style === 'zoom') {
            if (kind === 'map') {
                actor.scale_x = state.scaleX * 0.92;
                actor.scale_y = state.scaleY * 0.92;
            }
            target.scale_x = state.scaleX * (kind === 'map' ? 1 : 0.94);
            target.scale_y = state.scaleY * (kind === 'map' ? 1 : 0.94);
        } else if (style === 'lift') {
            if (kind === 'map')
                actor.translation_y = state.translationY + 18;
            target.translation_y = state.translationY + (kind === 'map' ? 0 : 12);
        }
        if (kind === 'map') {
            actor.opacity = 0;
            actor.show();
        }
        actor.ease(target);
    }

    _finish(actor, destroyed = false) {
        const state = this._active.get(actor);
        if (!state || state.done)
            return false;
        state.done = true;
        this._active.delete(actor);
        try {
            actor.disconnect(state.destroy);
            if (!destroyed) {
            // Mark completion before cancelling transitions: onStopped can run
            // synchronously during removal, and must not complete Mutter twice.
                for (const property of PROPERTIES)
                    actor.remove_transition(property);
                actor.opacity = state.opacity;
                actor.scale_x = state.scaleX;
                actor.scale_y = state.scaleY;
                actor.translation_y = state.translationY;
                actor.set_pivot_point(...state.pivot);
            }
        } catch (error) {
            console.warn(`Livara: restoring a window transition: ${error.message}`);
        } finally {
            state.complete();
        }
        return true;
    }

    _finishAll() {
        for (const actor of [...this._active.keys()])
            this._finish(actor);
    }

    disable() {
        this._enabled = false;
        this._finishAll();
        for (const [object, id] of this._signals)
            object.disconnect(id);
        this._signals = [];
        for (const id of this._blocked) {
            if (GObject.signal_handler_is_connected(this._shellwm, id))
                GObject.signal_handler_unblock(this._shellwm, id);
        }
        this._blocked = [];
    }
}

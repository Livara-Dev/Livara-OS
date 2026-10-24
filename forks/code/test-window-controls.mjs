/* SPDX-License-Identifier: MIT — run with the pinned Node24 toolchain. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseWindowControlsPreferences, WindowControlsController } from './overlay/core/windowControls.ts';

test('traffic-light defaults use left placement, restrained size and the requested three colors', () => {
    assert.deepEqual(parseWindowControlsPreferences(undefined), {
        style: 'trafficlights', position: 'left', size: 14, symbols: 'hover', greenAction: 'fullscreen',
        closeColor: '#ff5f57', minimizeColor: '#febc2e', maximizeColor: '#28c840'
    });
});

test('custom values keep the full eight preferences', () => {
    const preferences = { style: 'native', position: 'right', size: 19, symbols: 'always', greenAction: 'maximize', closeColor: '#112233', minimizeColor: '#abcdef', maximizeColor: '#AABBCC' };
    assert.deepEqual(parseWindowControlsPreferences(preferences), preferences);
});

test('invalid configuration cannot inject CSS or make invisible or oversized control targets', () => {
    const preferences = parseWindowControlsPreferences({ size: Infinity, closeColor: 'url(https://example.test/track)', minimizeColor: '#fff;display:none', maximizeColor: 'transparent', position: 'middle', symbols: 'never' });
    assert.equal(preferences.size, 14);
    assert.equal(preferences.closeColor, '#ff5f57');
    assert.equal(preferences.minimizeColor, '#febc2e');
    assert.equal(preferences.maximizeColor, '#28c840');
    assert.equal(preferences.position, 'left');
    assert.equal(preferences.symbols, 'hover');
    assert.equal(parseWindowControlsPreferences({ size: -1 }).size, 10);
    assert.equal(parseWindowControlsPreferences({ size: 999 }).size, 22);
    assert.equal(parseWindowControlsPreferences({ size: 14.6 }).size, 15);
});

test('rebuilt titlebars regain controls, removed listeners are released and refresh settles', async () => {
    let observe, disconnected = false;
    class Button {
        constructor() { this.attrs = new Map(); this.listeners = new Map(); this.isConnected = true; }
        hasAttribute(name) { return this.attrs.has(name); }
        setAttribute(name, value) { this.attrs.set(name, value); }
        addEventListener(name, listener, capture = false) { this.listeners.set(`${name}:${capture}`, listener); }
        removeEventListener(name, listener, capture = false) { this.listeners.delete(`${name}:${capture}`); }
        click() { this.listeners.get('click:true')?.({ shiftKey: false, preventDefault() {}, stopImmediatePropagation() {} }); }
    }
    const root = {
        classList: { toggle() {} }, setAttribute() {}, style: { setProperty() {} }
    };
    const target = { prepend(group) { group.parentElement = this; }, append(group) { group.parentElement = this; } };
    const titlebar = { querySelector() { return target; } };
    let appendCount = 0;
    const group = {
        nodeType: 1, parentElement: target, buttons: {}, children: [],
        querySelector(selector) { return this.buttons[selector]; },
        closest() { return titlebar; },
        append(button) { appendCount++; this.children = this.children.filter(child => child !== button); this.children.push(button); }
    };
    const replaceButtons = () => {
        for (const button of group.children) { button.isConnected = false; }
        const close = new Button(), min = new Button(), max = new Button();
        group.buttons = { '.window-close': close, '.window-minimize': min, '.window-max-restore': max };
        group.children = [min, max, close];
        return [close, min, max];
    };
    const first = replaceButtons();
    let queries = 0, fullscreen = 0;
    const document = {
        documentElement: root,
        querySelectorAll() { queries++; return [group]; },
        defaultView: { MutationObserver: class {
            constructor(callback) { observe = callback; }
            observe() {}
            disconnect() { disconnected = true; }
        } }
    };
    const controller = new WindowControlsController(document, () => fullscreen++);
    controller.apply(parseWindowControlsPreferences());
    assert.deepEqual(group.children, first);
    first[2].click(); assert.equal(fullscreen, 1);
    assert.equal(first[0].attrs.get('role'), 'button');
    const second = replaceButtons();
    const change = [{ target: { nodeType: 1, closest: () => titlebar }, addedNodes: [], removedNodes: [] }];
    observe(change); observe(change); // Several layout mutations batch once.
    await Promise.resolve();
    assert.equal(queries, 2);
    assert.deepEqual(group.children, second);
    assert.equal(first[0].listeners.size, 0);
    assert.equal(first[2].listeners.size, 0);
    second[2].click(); assert.equal(fullscreen, 2);
    const moves = appendCount;
    observe(change); await Promise.resolve();
    assert.equal(appendCount, moves); // Applying a stable layout does not mutate it again.
    observe([{ target: { nodeType: 1, closest: () => null }, addedNodes: [], removedNodes: [] }]);
    await Promise.resolve(); assert.equal(queries, 3); // Editor content does not trigger a titlebar scan.
    controller.dispose();
    assert.equal(disconnected, true);
    assert.equal(second[2].listeners.size, 0);
    observe(change); await Promise.resolve(); assert.equal(queries, 3);
});

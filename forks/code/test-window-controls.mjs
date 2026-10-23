/* SPDX-License-Identifier: MIT — run with the pinned Node24 toolchain. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseWindowControlsPreferences } from './overlay/core/windowControls.ts';

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

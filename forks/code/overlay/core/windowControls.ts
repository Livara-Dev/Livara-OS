/* SPDX-License-Identifier: MIT */
export interface WindowControlsPreferences {
    style: 'trafficlights' | 'native';
    position: 'left' | 'right';
    size: number;
    symbols: 'hover' | 'always';
    greenAction: 'fullscreen' | 'maximize';
    closeColor: string;
    minimizeColor: string;
    maximizeColor: string;
}

export function parseWindowControlsPreferences(value: unknown): WindowControlsPreferences {
    const input = value && typeof value === 'object' ? value as Record<string, unknown> : {};
    const color = (key: string, fallback: string): string => {
        const v = input[key];
        return typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v) ? v : fallback;
    };
    const rawSize = input['size'];
    return {
        style: input['style'] === 'native' ? 'native' : 'trafficlights',
        position: input['position'] === 'right' ? 'right' : 'left',
        size: typeof rawSize === 'number' && Number.isFinite(rawSize) ? Math.min(22, Math.max(10, Math.round(rawSize))) : 14,
        symbols: input['symbols'] === 'always' ? 'always' : 'hover',
        greenAction: input['greenAction'] === 'maximize' ? 'maximize' : 'fullscreen',
        closeColor: color('closeColor', '#ff5f57'),
        minimizeColor: color('minimizeColor', '#febc2e'),
        maximizeColor: color('maximizeColor', '#28c840')
    };
}

/** Restyles and moves the existing native-host controls; never replaces their actions. */
export class WindowControlsController {
    private readonly document: Document;
    private readonly fullscreen: () => void;
    private readonly keys = new Map<HTMLElement, (event: KeyboardEvent) => void>();
    private readonly clicks = new Map<HTMLElement, (event: MouseEvent) => void>();
    private greenAction: 'fullscreen' | 'maximize' = 'fullscreen';

    constructor(document: Document, fullscreen: () => void) { this.document = document; this.fullscreen = fullscreen; }

    apply(preferences: WindowControlsPreferences): void {
        const root = this.document.documentElement;
        this.greenAction = preferences.style === 'trafficlights' ? preferences.greenAction : 'maximize';
        root.classList.toggle('livara-traffic-lights', preferences.style === 'trafficlights');
        root.setAttribute('data-livara-control-symbols', preferences.symbols);
        root.style.setProperty('--livara-control-size', `${preferences.size}px`);
        root.style.setProperty('--livara-control-close', preferences.closeColor);
        root.style.setProperty('--livara-control-minimize', preferences.minimizeColor);
        root.style.setProperty('--livara-control-maximize', preferences.maximizeColor);
        for (const group of this.document.querySelectorAll<HTMLElement>('.monaco-workbench .part.titlebar .window-controls-container:not(.wco-enabled)')) {
            const close = group.querySelector<HTMLElement>('.window-close');
            const minimize = group.querySelector<HTMLElement>('.window-minimize');
            const maximize = group.querySelector<HTMLElement>('.window-max-restore');
            if (!close || !minimize || !maximize) { continue; }
            const titlebar = group.closest('.titlebar-container');
            const target = titlebar?.querySelector(`:scope > .titlebar-${preferences.position}`);
            if (target && group.parentElement !== target) {
                if (preferences.position === 'left') { target.prepend(group); }
                else { target.append(group); }
            }
            const order = preferences.style === 'trafficlights' ? [close, minimize, maximize] : [minimize, maximize, close];
            for (const button of order) { group.append(button); }
            for (const [button, label] of [[close, 'Close window'], [minimize, 'Minimize window'], [maximize, 'Maximize or restore window']] as const) {
                if (!button.hasAttribute('role')) { button.setAttribute('role', 'button'); }
                const fullscreen = button === maximize && this.greenAction === 'fullscreen';
                button.setAttribute('aria-label', fullscreen ? 'Toggle full screen' : label);
                button.title = fullscreen ? 'Toggle full screen · Shift-click to maximize or restore' : button === maximize ? `${label} · F11 for full screen` : label;
                button.tabIndex = 0;
                if (!this.keys.has(button)) {
                    const key = (event: KeyboardEvent) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            event.stopPropagation();
                            if (event.shiftKey && this.document.defaultView) {
                                button.dispatchEvent(new this.document.defaultView.MouseEvent('click', { bubbles: true, cancelable: true, shiftKey: true }));
                            } else { button.click(); }
                        }
                    };
                    button.addEventListener('keydown', key);
                    this.keys.set(button, key);
                }
            }
            if (!this.clicks.has(maximize)) {
                const click = (event: MouseEvent) => {
                    if (this.greenAction === 'fullscreen' && !event.shiftKey) {
                        event.preventDefault();
                        event.stopImmediatePropagation();
                        this.fullscreen();
                    }
                };
                // Capture runs before the existing native-host maximize listener.
                maximize.addEventListener('click', click, true);
                this.clicks.set(maximize, click);
            }
        }
    }

    dispose(): void {
        for (const [button, listener] of this.keys) { button.removeEventListener('keydown', listener); }
        for (const [button, listener] of this.clicks) { button.removeEventListener('click', listener, true); }
        this.keys.clear();
        this.clicks.clear();
    }
}

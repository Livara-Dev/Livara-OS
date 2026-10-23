/* SPDX-License-Identifier: MIT
 * Livara's compiled workbench contribution. Upstream VS Code remains MIT licensed.
 */
import { FileAccess } from '../../../../base/common/network.js';
import { mainWindow } from '../../../../base/browser/window.js';
import { Disposable } from '../../../../base/common/lifecycle.js';
import { Registry } from '../../../../platform/registry/common/platform.js';
import { Extensions as ConfigurationExtensions, IConfigurationRegistry, ConfigurationScope } from '../../../../platform/configuration/common/configurationRegistry.js';
import { IConfigurationService } from '../../../../platform/configuration/common/configuration.js';
import { ICommandService } from '../../../../platform/commands/common/commands.js';
import { registerWorkbenchContribution2, WorkbenchPhase } from '../../../common/contributions.js';
import { IStatusbarService, StatusbarAlignment } from '../../../services/statusbar/browser/statusbar.js';
import { parseWindowControlsPreferences, WindowControlsController } from './windowControls.js';
import './livara.css';

Registry.as<IConfigurationRegistry>(ConfigurationExtensions.Configuration).registerConfiguration({
    id: 'livara', title: 'Livara', type: 'object',
    properties: {
        'livara.windowControls.style': {
            type: 'string', enum: ['trafficlights', 'native'], default: 'trafficlights', scope: ConfigurationScope.APPLICATION,
            enumDescriptions: ['Colored Livara traffic lights.', 'Standard workbench buttons. OS-owned controls are available with window.controlsStyle or a native title bar.'],
            description: 'Appearance of the existing window buttons in a custom title bar. Uses their real close, minimize and maximize actions.'
        },
        'livara.windowControls.position': { type: 'string', enum: ['left', 'right'], default: 'left', scope: ConfigurationScope.APPLICATION, description: 'Position of custom title-bar buttons. Native overlay controls keep their OS placement.' },
        'livara.windowControls.size': { type: 'integer', minimum: 10, maximum: 22, default: 14, scope: ConfigurationScope.APPLICATION, description: 'Traffic-light diameter in pixels. Buttons retain larger pointer and keyboard targets.' },
        'livara.windowControls.symbols': { type: 'string', enum: ['hover', 'always'], default: 'hover', scope: ConfigurationScope.APPLICATION, description: 'Show button symbols on hover/keyboard focus, or all the time.' },
        'livara.windowControls.greenAction': { type: 'string', enum: ['fullscreen', 'maximize'], default: 'fullscreen', scope: ConfigurationScope.APPLICATION, description: 'Green traffic-light action. Shift-click always maximizes/restores. F11 also toggles full screen.' },
        'livara.windowControls.closeColor': { type: 'string', pattern: '^#[0-9a-fA-F]{6}$', default: '#ff5f57', scope: ConfigurationScope.APPLICATION, description: 'Close traffic-light color (#RRGGBB).' },
        'livara.windowControls.minimizeColor': { type: 'string', pattern: '^#[0-9a-fA-F]{6}$', default: '#febc2e', scope: ConfigurationScope.APPLICATION, description: 'Minimize traffic-light color (#RRGGBB).' },
        'livara.windowControls.maximizeColor': { type: 'string', pattern: '^#[0-9a-fA-F]{6}$', default: '#28c840', scope: ConfigurationScope.APPLICATION, description: 'Maximize/restore traffic-light color (#RRGGBB). Use F11 for full screen.' }
    }
});

Registry.as<IConfigurationRegistry>(ConfigurationExtensions.Configuration).registerDefaultConfigurations([{
    source: 'Livara Code',
    overrides: {
        'workbench.colorTheme': 'Livara AMOLED',
        'workbench.iconTheme': 'livara-files',
        'workbench.startupEditor': 'none',
        'workbench.tips.enabled': false,
        'workbench.enableExperiments': false,
        'workbench.activityBar.location': 'default',
        'workbench.editor.tabSizing': 'shrink',
        'workbench.tree.indent': 18,
        'workbench.list.smoothScrolling': true,
        'window.titleBarStyle': 'custom',
        'window.controlsStyle': 'custom',
        'window.title': '${dirty}${activeEditorShort}${separator}${rootName}${separator}Livara Code',
        'window.autoDetectColorScheme': false,
        'editor.fontFamily': "'Livara Mono', 'Livara Persian', 'Noto Sans', 'DejaVu Sans Mono', monospace",
        'editor.fontSize': 14,
        'editor.fontLigatures': false,
        'editor.smoothScrolling': true,
        'editor.cursorBlinking': 'smooth',
        'editor.cursorSmoothCaretAnimation': 'explicit',
        'editor.bracketPairColorization.enabled': true,
        'editor.guides.bracketPairs': 'active',
        'editor.padding.top': 14,
        'editor.padding.bottom': 14,
        'editor.minimap.enabled': true,
        'terminal.integrated.fontFamily': "'Livara Mono', 'Livara Persian', 'Noto Sans', 'DejaVu Sans Mono', monospace",
        'terminal.integrated.fontSize': 13,
        'terminal.integrated.defaultProfile.linux': 'Livara',
        'terminal.integrated.profiles.linux': {
            'Livara': { path: '/bin/bash', args: ['--rcfile', '/usr/share/livara/terminal/livara.bash', '-i'], icon: 'terminal-bash', color: 'terminal.ansiMagenta' },
            'Bash': { path: '/bin/bash', icon: 'terminal-bash' }
        },
        'telemetry.telemetryLevel': 'off',
        'telemetry.enableTelemetry': false,
        'telemetry.enableCrashReporter': false,
        'extensions.autoUpdate': false,
        'extensions.autoCheckUpdates': false,
        'update.mode': 'none',
        'chat.disableAIFeatures': true,
        'security.workspace.trust.enabled': true,
        'security.workspace.trust.startupPrompt': 'once',
        'files.hotExit': 'onExitAndWindowClose'
    }
}]);

class LivaraWorkbench extends Disposable {
    static readonly ID = 'workbench.contrib.livara';
    constructor(@IStatusbarService statusbar: IStatusbarService, @IConfigurationService configuration: IConfigurationService, @ICommandService commands: ICommandService) {
        super();
        // This distribution has no bundled cloud AI provider.
        statusbar.updateEntryVisibility('chat.statusBarEntry', false);
        const controls = this._register(new WindowControlsController(mainWindow.document, () => { void commands.executeCommand('workbench.action.toggleFullScreen'); }));
        const updateControls = () => controls.apply(parseWindowControlsPreferences(configuration.getValue('livara.windowControls')));
        updateControls();
        this._register(configuration.onDidChangeConfiguration(event => {
            if (event.affectsConfiguration('livara.windowControls')) { updateControls(); }
        }));
        for (const family of ['Sans', 'Mono', 'Persian']) {
            for (const [style, weight] of [['Regular', '400'], ['SemiBold', '600']]) {
                const uri = FileAccess.asBrowserUri(`vs/livara/fonts/Livara${family}-${style}.ttf`).toString(true);
                const face = new FontFace(`Livara ${family}`, `url("${uri}")`, { weight });
                face.load().then(loaded => mainWindow.document.fonts.add(loaded)).catch(() => undefined);
            }
        }
        this._register(statusbar.addEntry({
            name: 'Livara Code',
            text: '$(sparkle) LIVARA',
            ariaLabel: 'Livara Code commands',
            tooltip: 'Livara Code · Open the command palette',
            command: 'workbench.action.showCommands'
        }, 'livara.workbench.brand', StatusbarAlignment.LEFT, 10000));
    }
}
registerWorkbenchContribution2(LivaraWorkbench.ID, LivaraWorkbench, WorkbenchPhase.AfterRestored);

#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply Livara's product, compiled workbench and bundled extension to pinned OSS source."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((HERE / 'upstream.json').read_text())


def product_configuration(original: dict) -> dict:
    product = dict(original)
    product.update({
        'nameShort': 'Livara Code', 'nameLong': 'Livara Code', 'applicationName': 'livara-code',
        'dataFolderName': '.livara-code', 'sharedDataFolderName': '.livara-code-shared',
        'serverApplicationName': 'livara-code-server', 'serverDataFolderName': '.livara-code-server',
        'tunnelApplicationName': 'livara-code-tunnel', 'urlProtocol': 'livara-code',
        'linuxDesktopName': 'org.livara.Code', 'linuxIconName': 'org.livara.Code',
        'win32DirName': 'Livara Code', 'win32NameVersion': 'Livara Code',
        'win32RegValueName': 'LivaraCode', 'win32AppUserModelId': 'Livara.Code',
        'win32ShellNameShort': 'Livara Code', 'win32MutexName': 'livaracode',
        'win32TunnelServiceMutex': 'livara-code-tunnelservice', 'win32TunnelMutex': 'livara-code-tunnel',
        'darwinBundleIdentifier': 'org.livara.Code',
        'quality': 'stable', 'enableTelemetry': False, 'experimentsEnabled': False,
        'extensionsGallery': {
            'serviceUrl': 'https://open-vsx.org/vscode/gallery',
            'itemUrl': 'https://open-vsx.org/extension',
            'resourceUrlTemplate': 'https://open-vsx.org/vscode/unpkg/{publisher}/{name}/{version}/{path}'
        },
        'configurationSync.store': None,
        'webviewContentExternalBaseUrlTemplate': None,
        'livaraUpstreamVersion': PIN['version'], 'livaraUpstreamCommit': PIN['commit']
    })
    for key in ('defaultChatAgent', 'defaultChatProvider', 'aiConfig', 'updateUrl', 'downloadUrl', 'releaseNotesUrl', 'reportIssueUrl', 'crashReporter', 'aiKey', 'ariaKey', 'enableASARIntegrityValidation', 'chatEntitlementUrl', 'configurationSync.store', 'webviewContentExternalBaseUrlTemplate'):
        product.pop(key, None)
    # Keep genuine upstream license/debugger metadata. Do not impersonate a Microsoft distribution.
    for key in ('win32x64AppId', 'win32arm64AppId', 'win32x64UserAppId', 'win32arm64UserAppId'):
        product.pop(key, None)
    return product


def replace_visible_brand(text: str) -> str:
    result = []
    for line in text.splitlines(keepends=True):
        if 'copyright' not in line.casefold() and 'licensed under' not in line.casefold():
            for old in ('Visual Studio Code', 'VS Code', 'Code - OSS', 'Code OSS'):
                line = line.replace(old, 'Livara Code')
            line = line.replace('Zen Mode', 'Focus Mode').replace('Zen mode', 'Focus mode')
        result.append(line)
    return ''.join(result)


def refresh_inline_script_hashes(original: str, changed: str) -> str:
    """Preserve restrictive CSP hashes when branding changes an inline script."""
    scripts = r'<script\b[^>]*>(.*?)</script\s*>'
    before = re.findall(scripts, original, re.DOTALL | re.IGNORECASE)
    after = re.findall(scripts, changed, re.DOTALL | re.IGNORECASE)
    if len(before) != len(after):
        raise ValueError('Branding unexpectedly changed the HTML script structure.')
    for old, new in zip(before, after):
        old_hash = 'sha256-' + base64.b64encode(hashlib.sha256(old.encode()).digest()).decode()
        new_hash = 'sha256-' + base64.b64encode(hashlib.sha256(new.encode()).digest()).decode()
        changed = changed.replace(old_hash, new_hash)
    return changed


def window_controls_default_plans(source: Path, *, refresh: bool = False):
    """Set Linux defaults before Electron creates its very first window.

    Renderer-only default registrations happen too late for the native main
    process. Patch the shared accessor and matching schema, preserving explicit
    user choices and all non-Linux platform defaults. Guard both pinned files
    before the caller writes any source or product metadata.
    """
    shared = source / 'src/vs/platform/window/common/window.ts'
    schema = source / 'src/vs/workbench/electron-browser/desktop.contribution.ts'
    shared_text, schema_text = shared.read_text(), schema.read_text()
    if shared_text.count('return TitlebarStyle.CUSTOM; // default to custom on all OS') != 1:
        raise ValueError('Upstream titlebar default changed; review Linux startup controls.')
    titlebar_schema = "'window.titleBarStyle': {\n\t\t\t\t'type': 'string',\n\t\t\t\t'enum': ['native', 'custom'],\n\t\t\t\t'default': 'custom',"
    if schema_text.count(titlebar_schema) != 1:
        raise ValueError('Upstream titlebar schema changed; review Linux startup controls.')
    original_function = '''export function getWindowControlsStyle(configurationService: IConfigurationService): WindowControlsStyle {
\tif (isWeb || isMacintosh || getTitleBarStyle(configurationService) === TitlebarStyle.NATIVE) {
\t\treturn WindowControlsStyle.NATIVE; // only supported on Windows/Linux desktop with custom titlebar
\t}

\tconst configuration = configurationService.getValue<IWindowSettings | undefined>('window');
\tconst style = configuration?.controlsStyle;
\tif (style === WindowControlsStyle.CUSTOM || style === WindowControlsStyle.HIDDEN) {
\t\treturn style;
\t}

\treturn WindowControlsStyle.NATIVE; // default to native on all OS
}'''
    patched_function = original_function.replace(
        'style === WindowControlsStyle.CUSTOM || style === WindowControlsStyle.HIDDEN',
        'style === WindowControlsStyle.NATIVE || style === WindowControlsStyle.CUSTOM || style === WindowControlsStyle.HIDDEN'
    ).replace('return WindowControlsStyle.NATIVE; // default to native on all OS',
              'return isLinux ? WindowControlsStyle.CUSTOM : WindowControlsStyle.NATIVE; // Livara: main-process Linux default before the renderer starts')
    original_import = "import { isMacintosh, isNative, isTahoeOrNewer, isWeb } from '../../../base/common/platform.js';"
    patched_import = original_import.replace('{ isMacintosh,', '{ isLinux, isMacintosh,')
    original_schema = "'window.controlsStyle': {\n\t\t\t\t'type': 'string',\n\t\t\t\t'enum': ['native', 'custom', 'hidden'],\n\t\t\t\t'default': 'native',"
    patched_schema = original_schema.replace("'default': 'native'", "'default': isLinux ? 'custom' : 'native'")
    plans = []
    for path, text, replacements in ((shared, shared_text, ((original_import, patched_import), (original_function, patched_function))),
                                      (schema, schema_text, ((original_schema, patched_schema),))):
        for original, patched in replacements:
            if refresh and text.count(patched) == 1 and original not in text:
                continue
            if text.count(original) != 1 or patched in text:
                raise ValueError('Upstream window-controls defaults changed; review the pinned Linux startup patch.')
            text = text.replace(original, patched)
        plans.append((path, text))
    return plans


def apply(source: Path, project: Path = ROOT, *, refresh: bool = False) -> dict:
    source = source.resolve(strict=True)
    package_path = source / 'package.json'
    package = json.loads(package_path.read_text())
    expected_name = 'livara-code-source' if refresh else 'code-oss-dev'
    if refresh:
        previous = json.loads((source / 'livara-source.json').read_text())
        if previous['upstream']['commit'] != PIN['commit']:
            raise ValueError('Cannot refresh a different upstream source revision.')
    if package.get('version') != PIN['version'] or package.get('name') != expected_name:
        raise ValueError('Livara Code patches require the exact pinned pristine upstream version.')
    main_path = source / 'src/vs/workbench/workbench.desktop.main.ts'
    main = main_path.read_text()
    anchor = "import './workbench.common.main.js';"
    if main.count(anchor) != 1 or (not refresh and "contrib/livara/" in main):
        raise ValueError('Unexpected desktop entry point; refusing to apply branding partially.')
    logo = project / 'artwork/livara-code.png'
    if not logo.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('The Livara Code PNG icon is missing or invalid.')
    window_defaults = window_controls_default_plans(source, refresh=refresh)
    # All public app identity comes from product.json; technical module/API IDs are preserved.
    product_path = source / 'product.json'
    product = product_configuration(json.loads(product_path.read_text()))
    product_path.write_text(json.dumps(product, indent=2) + '\n')
    package['name'] = 'livara-code-source'
    package['author'] = {'name': 'Livara contributors; original work by Microsoft contributors'}
    package_path.write_text(json.dumps(package, indent=2) + '\n')
    for path, text in window_defaults:
        path.write_text(text)
    if "contrib/livara/" not in main:
        main_path.write_text(main.replace(anchor, anchor + "\nimport './contrib/livara/browser/livara.contribution.js';"))
    core_target = source / 'src/vs/workbench/contrib/livara/browser'
    shutil.copytree(HERE / 'overlay/core', core_target, dirs_exist_ok=refresh)
    # Upstream account onboarding asserts defaultChatAgent at module load. Keep
    # its injected service but replace the external-account flow with a local no-op.
    onboarding = source / 'src/vs/workbench/contrib/welcomeOnboarding/browser/welcomeOnboarding.contribution.ts'
    onboarding.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / 'overlay/onboarding/welcomeOnboarding.contribution.ts', onboarding)
    onboarding.chmod(0o644)
    # Recent upstream also constructs its default account service unconditionally.
    # Without a configured account backend this remains a resolved, local-only
    # service: no provider is registered and sign-in requests return no account.
    accounts = source / 'src/vs/workbench/services/accounts/browser/defaultAccount.ts'
    if accounts.is_file():
        account_text = accounts.read_text()
        local_marker = '// Livara: a local workspace needs no account backend.'
        if local_marker not in account_text:
            account_patches = {
                'function toDefaultAccountConfig(defaultChatAgent: IDefaultChatAgent): IDefaultAccountConfig {': '''function toDefaultAccountConfig(defaultChatAgent: IDefaultChatAgent | undefined): IDefaultAccountConfig {
\t// Livara: a local workspace needs no account backend.
\tif (!defaultChatAgent) {
\t\treturn { preferredExtensions: [], authenticationProvider: {
\t\t\tdefault: { id: 'livara-local', name: 'Local workspace' },
\t\t\tenterprise: { id: 'livara-local', name: 'Local workspace' },
\t\t\tenterpriseProviderConfig: '', scopes: []
\t\t}, entitlementUrl: '', tokenEntitlementUrl: '', mcpRegistryDataUrl: '', managedSettingsUrl: '' };
\t}''',
                'this.defaultAccountConfig = toDefaultAccountConfig(productService.defaultChatAgent);': '''this.defaultAccountConfig = toDefaultAccountConfig(productService.defaultChatAgent);
\t\tif (!productService.defaultChatAgent) { this.initBarrier.open(); }''',
                'const defaultAccountProvider = this._register(instantiationService.createInstance(DefaultAccountProvider, toDefaultAccountConfig(productService.defaultChatAgent)));': '''if (!productService.defaultChatAgent) { return; }
\t\tconst defaultAccountProvider = this._register(instantiationService.createInstance(DefaultAccountProvider, toDefaultAccountConfig(productService.defaultChatAgent)));'''
            }
            for original, changed in account_patches.items():
                if account_text.count(original) != 1:
                    raise ValueError('Upstream account service changed; review its local-account guards.')
                account_text = account_text.replace(original, changed)
            accounts.write_text(account_text)
    extension_target = source / 'extensions/livara-workbench'
    shutil.copytree(HERE / 'overlay/extension', extension_target, dirs_exist_ok=refresh)
    (extension_target / 'media').mkdir(exist_ok=refresh)
    shutil.copyfile(logo, extension_target / 'media/livara-code.png')
    # Source checkouts may use umask077; packaged static application files must be readable by desktop users.
    for public_root in (core_target, extension_target):
        public_root.chmod(0o755)
        for public_path in public_root.rglob('*'):
            if not public_path.is_symlink():
                public_path.chmod(0o755 if public_path.is_dir() else 0o644)
    for relative in ('resources/linux/code.png', 'resources/server/code-512.png', 'resources/server/code-192.png'):
        shutil.copyfile(logo, source / relative)
    # Embedded images are self-contained and accepted by Electron's workbench CSS.
    encoded = base64.b64encode(logo.read_bytes()).decode('ascii')
    compiled_css = core_target / 'livara.css'
    compiled_css.write_text(compiled_css.read_text().replace('@@LIVARA_ICON_DATA@@', 'data:image/png;base64,' + encoded))
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1024 1024"><image width="1024" height="1024" xlink:href="data:image/png;base64,{encoded}"/></svg>\n'
    for relative in ('src/vs/workbench/browser/media/code-icon.svg', 'src/vs/sessions/browser/media/vscode-icon.svg', 'extensions/github-authentication/media/code-icon.svg', 'extensions/npm/images/code.svg', *[str(path.relative_to(source)) for path in (source / 'src/vs').rglob('letterpress*.svg')], 'src/vs/sessions/browser/media/sessions-logo-light.svg', 'src/vs/sessions/browser/media/sessions-logo-dark.svg'):
        path = source / relative
        if path.exists():
            path.write_text(svg)
    # These are first-party visible strings. Lower-case vscode API/module identifiers stay intact.
    branded_files = 0
    for base in ('src', 'extensions'):
        for directory, names, files in os.walk(source / base, followlinks=False):
            names[:] = [name for name in names if name not in ('node_modules', '.git', 'out', 'dist') and not (Path(directory) / name).is_symlink()]
            for name in files:
                path = Path(directory) / name
                if path.suffix not in ('.ts', '.js', '.json', '.html') or not path.is_file() or path.is_symlink():
                    continue
                if path.stat().st_size > 3_000_000:
                    continue
                text = path.read_text(encoding='utf-8')
                changed = replace_visible_brand(text)
                if path.suffix == '.html' and changed != text:
                    changed = refresh_inline_script_hashes(text, changed)
                if changed != text:
                    path.write_text(changed)
                    branded_files += 1
    # An archive has no Git HEAD; use its locked source date without a misleading fatal Git warning.
    date_path = source / 'build/lib/date.ts'
    if date_path.is_file():
        date_text = date_path.read_text()
        date_anchor = 'export function getGitCommitDate(): string {'
        if 'LIVARA_SOURCE_DATE' not in date_text:
            if date_text.count(date_anchor) != 1:
                raise ValueError('Upstream build date helper changed; review its source-date patch.')
            date_path.write_text(date_text.replace(date_anchor, date_anchor + "\n\tconst livaraDate = process.env['LIVARA_SOURCE_DATE'];\n\tif (livaraDate) { return new Date(livaraDate).toISOString(); }"))
    # Respect the build's explicit parallelism budget, including npm's nested extension installs.
    postinstall = source / 'build/npm/postinstall.ts'
    install_text = postinstall.read_text()
    concurrency = 'const concurrency = Math.min(os.cpus().length, 8);'
    replacement = "const concurrency = Math.min(os.cpus().length, Math.max(1, Math.min(16, Number(process.env['LIVARA_BUILD_JOBS']) || 2)));"
    if install_text.count(concurrency) == 1:
        postinstall.write_text(install_text.replace(concurrency, replacement))
    elif install_text.count(replacement) != 1:
        raise ValueError('Upstream dependency installer changed; review the concurrency patch.')
    recipe_files = sorted(path for path in HERE.rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    report = {
        'product': 'Livara Code', 'upstream': PIN,
        'branded_source_files': branded_files,
        'recipes': {str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest() for path in recipe_files},
        'icon_sha256': hashlib.sha256(logo.read_bytes()).hexdigest(),
        'features': ['compiled-workbench-chrome', 'compiled-defaults', 'local-onboarding-service', 'livara-welcome', 'amoled-theme', 'livara-file-icons', 'open-vsx', 'telemetry-off', 'workspace-trust-on'],
        'built': False
    }
    (source / 'livara-source.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--project', type=Path, default=ROOT)
    parser.add_argument('--refresh', action='store_true', help='Refresh an already-verified Livara development checkout')
    args = parser.parse_args()
    report = apply(args.source, args.project, refresh=args.refresh)
    print(json.dumps({'product': report['product'], 'upstream': PIN['commit'], 'branded_source_files': report['branded_source_files']}))

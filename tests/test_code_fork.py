"""Livara's actual upstream editor recipe and source transformation checks."""
import importlib.util
import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('livara_code_patch', ROOT / 'forks/code/apply.py')
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)


class CodeFork(unittest.TestCase):
    def test_source_and_toolchain_are_content_pinned(self):
        pin = PATCH.PIN
        self.assertRegex(pin['commit'], r'^[0-9a-f]{40}$')
        self.assertTrue(pin['source_url'].endswith(pin['commit']))
        for field in ('source_sha256', 'node_sha256'):
            self.assertRegex(pin[field], r'^[0-9a-f]{64}$')
        self.assertTrue(pin['node_url'].endswith('linux-x64.tar.xz'))
        self.assertEqual(pin['artifact'], 'livara-code-linux-x64.tar.xz')

    def test_product_is_independent_and_retains_real_notices(self):
        original = {'nameShort':'Code - OSS','licenseName':'MIT','licenseUrl':'https://github.com/microsoft/vscode/blob/main/LICENSE.txt','builtInExtensions':[{'repo':'https://github.com/microsoft/vscode-js-debug','sha256':'a'*64}], 'defaultChatAgent':{'provider':'Microsoft'}, 'updateUrl':'https://update.code.visualstudio.com'}
        product = PATCH.product_configuration(original)
        self.assertEqual(product['nameShort'], 'Livara Code')
        self.assertEqual(product['applicationName'], 'livara-code')
        self.assertEqual(product['linuxDesktopName'], 'org.livara.Code')
        self.assertFalse(product['enableTelemetry'])
        self.assertNotIn('defaultChatAgent', product)
        self.assertNotIn('updateUrl', product)
        self.assertEqual(product['builtInExtensions'], original['builtInExtensions'])
        self.assertEqual(product['licenseUrl'], original['licenseUrl'])
        self.assertEqual(product['extensionsGallery']['serviceUrl'], 'https://open-vsx.org/vscode/gallery')
        self.assertEqual(original['nameShort'], 'Code - OSS')

    def test_visible_text_branding_preserves_legal_and_api_ids(self):
        source = '// Copyright Microsoft Visual Studio Code\nimport * as vscode from "vscode";\nconst t="Visual Studio Code / VS Code / Code - OSS";\n'
        result = PATCH.replace_visible_brand(source)
        self.assertIn('Copyright Microsoft Visual Studio Code', result)
        self.assertIn('import * as vscode from "vscode"', result)
        self.assertIn('"Livara Code / Livara Code / Livara Code"', result)

    def test_webview_inline_script_csp_still_authenticates_branded_script(self):
        script='\nthrow new Error("Visual Studio Code API");\n'
        digest=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        original=f'''<meta http-equiv="Content-Security-Policy" content="script-src 'sha256-{digest}' 'self'"><script type="module">{script}</script>'''
        changed=PATCH.refresh_inline_script_hashes(original,PATCH.replace_visible_brand(original))
        updated=re.search(r'<script[^>]*>(.*?)</script>',changed,re.S).group(1)
        wanted=base64.b64encode(hashlib.sha256(updated.encode()).digest()).decode()
        self.assertIn('sha256-'+wanted,changed)
        self.assertNotIn('sha256-'+digest,changed)
        self.assertNotIn('unsafe-inline',changed)
        self.assertIn('Livara Code API',changed)

    def fixture(self, root):
        files = {'package.json':json.dumps({'name':'code-oss-dev','version':PATCH.PIN['version'],'license':'MIT'}),'product.json':json.dumps({'nameShort':'Code - OSS','licenseName':'MIT'}),'src/vs/workbench/workbench.desktop.main.ts':"import './workbench.common.main.js';\n",'src/example.ts':'const welcome="Visual Studio Code";\n','build/npm/postinstall.ts':'const concurrency = Math.min(os.cpus().length, 8);\n'}
        for name, text in files.items():
            path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
        accounts=root/'src/vs/workbench/services/accounts/browser/defaultAccount.ts'
        accounts.parent.mkdir(parents=True,exist_ok=True)
        accounts.write_text('function toDefaultAccountConfig(defaultChatAgent: IDefaultChatAgent): IDefaultAccountConfig {\n}\nthis.defaultAccountConfig = toDefaultAccountConfig(productService.defaultChatAgent);\nconst defaultAccountProvider = this._register(instantiationService.createInstance(DefaultAccountProvider, toDefaultAccountConfig(productService.defaultChatAgent)));\n')
        for fixture, relative in (('code-window-defaults.ts', 'src/vs/platform/window/common/window.ts'),
                                  ('code-desktop-defaults.ts', 'src/vs/workbench/electron-browser/desktop.contribution.ts')):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'tests/fixtures' / fixture, path)
        for name in ('resources/linux','resources/server'):
            (root/name).mkdir(parents=True)

    def test_source_transformation_adds_compiled_core_and_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp); self.fixture(source)
            report=PATCH.apply(source, ROOT)
            self.assertFalse(report['built'])
            self.assertIn('compiled-workbench-chrome',report['features'])
            self.assertIn("./contrib/livara/browser/livara.contribution.js",(source/'src/vs/workbench/workbench.desktop.main.ts').read_text())
            self.assertTrue((source/'src/vs/workbench/contrib/livara/browser/livara.css').is_file())
            self.assertIn('Livara Code',(source/'src/example.ts').read_text())
            self.assertEqual(json.loads((source/'product.json').read_text())['applicationName'],'livara-code')
            self.assertEqual((source/'resources/linux/code.png').read_bytes(),(ROOT/'artwork/livara-code.png').read_bytes())
            self.assertTrue((source/'extensions/livara-workbench/extension.js').is_file())
            onboarding=(source/'src/vs/workbench/contrib/welcomeOnboarding/browser/welcomeOnboarding.contribution.ts').read_text()
            self.assertIn('registerSingleton(IOnboardingService, LivaraOnboarding', onboarding)
            self.assertIn('Event.None', onboarding)
            self.assertNotIn('onboardingVariationA', onboarding)
            self.assertNotIn('defaultChatAgent', onboarding)
            accounts=(source/'src/vs/workbench/services/accounts/browser/defaultAccount.ts').read_text()
            self.assertIn('if (!defaultChatAgent)', accounts)
            self.assertIn('if (!productService.defaultChatAgent) { this.initBarrier.open(); }', accounts)
            self.assertIn('if (!productService.defaultChatAgent) { return; }', accounts)
            self.assertEqual((source/'extensions/livara-workbench/extension.js').stat().st_mode & 0o777, 0o644)
            self.assertEqual((source/'extensions/livara-workbench').stat().st_mode & 0o777, 0o755)
            with self.assertRaises(ValueError):
                PATCH.apply(source, ROOT)

    def test_unknown_upstream_is_rejected_before_any_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp); self.fixture(source)
            package=source/'package.json'; package.write_text('{"version":"0.0.0","name":"other"}')
            original=(source/'product.json').read_bytes()
            with self.assertRaises(ValueError): PATCH.apply(source, ROOT)
            self.assertEqual((source/'product.json').read_bytes(), original)

    @unittest.skipUnless(shutil.which('node'), 'Node24 is required to execute patched TypeScript accessors')
    def test_first_linux_window_has_custom_controls_and_explicit_choices_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp); self.fixture(source)
            for path, text in PATCH.window_controls_default_plans(source):
                # Replace only the fixture's platform import with test bindings;
                # execute the transformed upstream functions, not a Python model.
                text = re.sub(r"import \{[^\n]+\} from '[^\n]+platform.js';",
                              'const { isLinux, isMacintosh, isNative, isTahoeOrNewer, isWeb } = globalThis.__livaraTestPlatform;', text)
                path.write_text(text)
            shared = (source / 'src/vs/platform/window/common/window.ts').as_uri()
            schema = (source / 'src/vs/workbench/electron-browser/desktop.contribution.ts').as_uri()
            script = r'''
import assert from 'node:assert/strict';
for (const platform of ['linux', 'windows', 'mac', 'web']) {
    globalThis.__livaraTestPlatform = { isLinux: platform === 'linux', isMacintosh: platform === 'mac', isWeb: platform === 'web' };
    const api = await import(SHARED + '?' + platform);
    const service = value => ({ getValue: () => value });
    assert.equal(api.getTitleBarStyle(service(undefined)), 'custom');
    assert.equal(api.getWindowControlsStyle(service(undefined)), platform === 'linux' ? 'custom' : 'native');
    for (const choice of ['native', 'custom', 'hidden']) {
        assert.equal(api.getWindowControlsStyle(service({ controlsStyle: choice })),
            ['linux', 'windows'].includes(platform) ? choice : 'native');
    }
    assert.equal(api.getWindowControlsStyle(service({ titleBarStyle: 'native', controlsStyle: 'custom' })), 'native');
    const { schemas } = await import(SCHEMA + '?' + platform);
    assert.equal(schemas['window.controlsStyle'].default, platform === 'linux' ? 'custom' : 'native');
    assert.equal(schemas['window.titleBarStyle'].default, 'custom');
}
'''.replace('SHARED', json.dumps(shared)).replace('SCHEMA', json.dumps(schema))
            result = subprocess.run(['node', '--input-type=module', '-e', script], text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_window_default_source_drift_is_rejected_before_product_changes(self):
        for relative, old, changed in (
            ('src/vs/platform/window/common/window.ts', 'return TitlebarStyle.CUSTOM; // default to custom on all OS', 'return TitlebarStyle.NATIVE; // upstream changed'),
            ('src/vs/platform/window/common/window.ts', 'style === WindowControlsStyle.HIDDEN', 'style === WindowControlsStyle.CUSTOM'),
            ('src/vs/workbench/electron-browser/desktop.contribution.ts', "'default': 'native'", "'default': 'hidden'"),
        ):
            with self.subTest(relative=relative, changed=changed), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp); self.fixture(source)
                target = source / relative; target.write_text(target.read_text().replace(old, changed))
                previous = (source / 'product.json').read_bytes()
                with self.assertRaisesRegex(ValueError, 'Upstream'):
                    PATCH.apply(source, ROOT)
                self.assertEqual((source / 'product.json').read_bytes(), previous)

    def test_window_default_refresh_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp); self.fixture(source)
            for path, text in PATCH.window_controls_default_plans(source): path.write_text(text)
            before = {path: path.read_text() for path, _ in PATCH.window_controls_default_plans(source, refresh=True)}
            self.assertEqual(dict(PATCH.window_controls_default_plans(source, refresh=True)), before)

    def test_amoled_and_real_command_entrypoints(self):
        theme=json.loads((ROOT/'forks/code/overlay/extension/themes/livara-amoled.json').read_text())
        self.assertEqual(theme['colors']['editor.background'],'#000000')
        self.assertEqual(theme['colors']['terminal.background'],'#000000')
        package=json.loads((ROOT/'forks/code/overlay/extension/package.json').read_text())
        commands={item['command'] for item in package['contributes']['commands']}
        for name in ('welcome','notes','focusStart','todos','hashFile','formatJSON','compareClipboard','inventory','newProject'):
            self.assertIn('livara.'+name,commands)
        script=(ROOT/'forks/code/overlay/extension/extension.js').read_text()
        self.assertIn('enableScripts: false', script)
        self.assertNotIn('--no-sandbox',(ROOT/'scripts/build-code.sh').read_text())
        self.assertNotIn('marketplace.visualstudio.com',json.dumps(PATCH.product_configuration({})))


if __name__ == '__main__': unittest.main()

from __future__ import annotations

import hashlib
import base64
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from livara import app_updates


class AppResourceUpdates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.opt, self.payload, self.backup = (self.root / name for name in ('opt', 'payload', 'backup'))
        self.app = self.opt / 'livara-browser'
        (self.app / 'browser').mkdir(parents=True)
        (self.payload / 'browser').mkdir(parents=True)
        (self.payload / 'code').mkdir()
        (self.payload / 'manifest.json').write_text(json.dumps({'version': '0.1.1', 'browser_commit': 'browser-pin', 'code_commit': 'code-pin'}))
        self.binary = b'original executable'
        (self.app / 'livara-browser').write_bytes(self.binary)
        (self.app / 'livara-build.json').write_text(json.dumps({'upstream': {'commit': 'browser-pin'}, 'binary_sha256': hashlib.sha256(self.binary).hexdigest()}))
        for name in app_updates.BROWSER_RESOURCES:
            (self.payload / 'browser' / name).write_text('new ' + name)
        for name in app_updates.BROWSER_LOCALES:
            path = self.payload / 'browser/locales/en-US' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('label = Restored localization')
        self.jar = self.app / 'browser/omni.ja'
        with zipfile.ZipFile(self.jar, 'w') as jar:
            for name in app_updates.BROWSER_RESOURCES:
                jar.writestr('chrome/browser/content/browser/livara/' + name, 'old ' + name)
            jar.writestr('engine-owned-resource', b'preserve this')
            jar.writestr('jsloader/cache', b'obsolete bytecode')

    def refresh(self):
        return app_updates.refresh(opt=self.opt, payload=self.payload, backup=self.backup)

    def code(self):
        app = self.opt / 'livara-code/resources/app'
        (app / 'out/vs/workbench').mkdir(parents=True)
        (app / 'livara-build.json').write_text(json.dumps({'upstream': {'commit': 'code-pin'}, 'distribution': 'Livara Code'}))
        css = app / 'out/vs/workbench/workbench.desktop.main.css'
        css.write_text('/* original compiled CSS */')
        checksum = base64.b64encode(hashlib.sha256(css.read_bytes()).digest()).decode().rstrip('=')
        (app / 'product.json').write_text(json.dumps({'checksums': {'vs/workbench/workbench.desktop.main.css': checksum, 'other': 'preserved'}, 'nameShort': 'Livara Code'}))
        (self.payload / 'code/livara.css').write_text('.monaco-workbench { color: white; }')
        return css

    def test_updates_owned_resources_preserves_engine_and_is_repeatable(self):
        original = self.jar.read_bytes()
        css = self.code()
        self.assertEqual([result['status'] for result in self.refresh()], ['updated', 'updated'])
        with zipfile.ZipFile(self.jar) as jar:
            self.assertEqual(jar.read('engine-owned-resource'), b'preserve this')
            self.assertNotIn('jsloader/cache', jar.namelist())
            self.assertEqual(jar.read('chrome/browser/content/browser/livara/start.css'), b'new start.css')
            for name in app_updates.BROWSER_LOCALES:
                self.assertEqual(jar.read('localization/en-US/' + name), b'label = Restored localization')
        self.assertEqual((self.app / 'livara-browser').read_bytes(), self.binary)
        self.assertIn('/* original compiled CSS */', css.read_text())
        product = json.loads((css.parents[3] / 'product.json').read_text())
        self.assertEqual(product['checksums']['vs/workbench/workbench.desktop.main.css'], base64.b64encode(hashlib.sha256(css.read_bytes()).digest()).decode().rstrip('='))
        self.assertEqual(product['checksums']['other'], 'preserved')
        self.assertEqual([result['status'] for result in self.refresh()], ['current', 'current'])
        self.assertIn(original, [path.read_bytes() for path in self.backup.iterdir()])

    def test_mismatched_app_prevents_partial_update(self):
        original = self.jar.read_bytes()
        self.code()
        identity = self.opt / 'livara-code/resources/app/livara-build.json'
        identity.write_text('{"upstream":{"commit":"different"}}')
        with self.assertRaisesRegex(ValueError, 'different source build'):
            self.refresh()
        self.assertEqual(self.jar.read_bytes(), original)
        self.assertFalse(self.backup.exists())

    def test_failed_second_write_rolls_back_browser(self):
        original = self.jar.read_bytes()
        css = self.code()
        write = app_updates.atomic_write
        def fail_code(path, data):
            if path == css:
                raise OSError('fixture: full disk')
            return write(path, data)
        with patch.object(app_updates, 'atomic_write', side_effect=fail_code):
            with self.assertRaisesRegex(OSError, 'full disk'):
                self.refresh()
        self.assertEqual(self.jar.read_bytes(), original)

    def test_audit_record_failure_rolls_back_browser(self):
        original = self.jar.read_bytes()
        write = app_updates.atomic_write
        def fail_record(path, data):
            if path == self.backup / 'latest.json':
                raise OSError('fixture: audit write failed')
            return write(path, data)
        with patch.object(app_updates, 'atomic_write', side_effect=fail_record):
            with self.assertRaisesRegex(OSError, 'audit write failed'):
                self.refresh()
        self.assertEqual(self.jar.read_bytes(), original)

    def test_symlink_and_modified_executable_are_rejected(self):
        (self.app / 'livara-browser').write_bytes(b'modified')
        with self.assertRaisesRegex(ValueError, 'executable'):
            self.refresh()
        (self.app / 'livara-browser').write_bytes(self.binary)
        saved = self.jar.with_suffix('.original')
        self.jar.rename(saved)
        self.jar.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            self.refresh()

    def test_code_integrity_failure_preserves_all_resources(self):
        original = self.jar.read_bytes()
        css = self.code()
        css.write_text('locally modified code css')
        with self.assertRaisesRegex(ValueError, 'original integrity checksum'):
            self.refresh()
        self.assertEqual(self.jar.read_bytes(), original)
        self.assertEqual(css.read_text(), 'locally modified code css')

    def test_matching_compiled_code_package_is_not_modified(self):
        css = self.code()
        identity = self.opt / 'livara-code/resources/app/livara-build.json'
        value = json.loads(identity.read_text())
        value['desktop_package_version'] = '0.1.1'
        identity.write_text(json.dumps(value))
        before = css.read_bytes()
        result = self.refresh()
        self.assertEqual(result[1]['status'], 'current')
        self.assertEqual(css.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

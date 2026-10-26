"""Verify fresh builds and incremental updates share the shipping planner."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from livara.app_updates import BROWSER_RESOURCES, BROWSER_LOCALES, browser_source_plan, atomic_write

ROOT = Path(__file__).resolve().parents[1]


class BrowserResourceUpdate(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / 'livara-browser'
        (self.app / 'browser').mkdir(parents=True)
        self.binary = b'original native binary'
        (self.app / 'livara-browser').write_bytes(self.binary)
        pin = json.loads((ROOT / 'forks/browser/upstream.json').read_text())['commit']
        (self.app / 'livara-build.json').write_text(json.dumps({
            'upstream': {'commit': pin}, 'binary_sha256': hashlib.sha256(self.binary).hexdigest()}))
        self.jar = self.app / 'browser/omni.ja'
        with zipfile.ZipFile(self.jar, 'w') as archive:
            for name in BROWSER_RESOURCES:
                archive.writestr('chrome/browser/content/browser/livara/' + name, 'old resource')
            archive.writestr('localization/en-US/browser/browserContext.ftl', 'upstream = Preserved')
            archive.writestr('jsloader/stale-bytecode', 'obsolete')

    def test_complete_resources_restore_localization_without_changing_native_files(self):
        plans = browser_source_plan(self.app, ROOT)
        self.assertEqual(len(plans), 1)
        for path, _old, fresh in plans:
            atomic_write(path, fresh)
        with zipfile.ZipFile(self.jar) as archive:
            for name in BROWSER_RESOURCES:
                self.assertEqual(archive.read('chrome/browser/content/browser/livara/' + name),
                                 (ROOT / 'forks/browser/overlay/src/livara' / name).read_bytes())
            for name in BROWSER_LOCALES:
                self.assertEqual(archive.read('localization/en-US/' + name),
                                 (ROOT / 'forks/browser/locales/en-US' / name).read_bytes())
            self.assertEqual(archive.read('localization/en-US/browser/browserContext.ftl'), b'upstream = Preserved')
            self.assertNotIn('jsloader/stale-bytecode', archive.namelist())
            self.assertIsNone(archive.testzip())
        self.assertEqual((self.app / 'livara-browser').read_bytes(), self.binary)
        self.assertEqual(browser_source_plan(self.app, ROOT), [])

    def test_missing_resource_refuses_update_before_any_archive_write(self):
        with zipfile.ZipFile(self.jar, 'w') as archive:
            archive.writestr('unrelated', 'preserved')
        original = self.jar.read_bytes()
        with self.assertRaisesRegex(ValueError, 'exactly one copy'):
            browser_source_plan(self.app, ROOT)
        self.assertEqual(self.jar.read_bytes(), original)

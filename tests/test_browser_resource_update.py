import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('resource_update',ROOT/'scripts/refresh-browser-chrome.py');update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)


class BrowserResourceUpdate(unittest.TestCase):
    def test_only_livara_script_changes_and_generated_bytecode_is_dropped(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar=root/'omni.ja';resource=root/'LivaraUI.js';resource.write_bytes(b'new Livara source')
            with zipfile.ZipFile(jar,'w') as z:
                z.writestr('chrome/browser/content/browser/livara/LivaraUI.js',b'old Livara source')
                z.writestr('chrome/browser/content/browser/browser.xhtml',b'unchanged browser entry')
                z.writestr('jsloader/generated-cache',b'obsolete bytecode')
            report=update.update_jar(jar,resource)
            with zipfile.ZipFile(jar) as z:
                self.assertEqual(z.read(report['path']),resource.read_bytes())
                self.assertEqual(z.read('chrome/browser/content/browser/browser.xhtml'),b'unchanged browser entry')
                self.assertNotIn('jsloader/generated-cache',z.namelist());self.assertIsNone(z.testzip())
            before=jar.read_bytes();self.assertFalse(update.update_jar(jar,resource)['changed']);self.assertEqual(jar.read_bytes(),before)

    def test_missing_or_ambiguous_resource_does_not_rewrite_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jar=root/'omni.ja';resource=root/'LivaraUI.js';resource.write_bytes(b'new')
            with zipfile.ZipFile(jar,'w') as z:z.writestr('unrelated',b'preserved')
            previous=jar.read_bytes();self.assertIsNone(update.update_jar(jar,resource));self.assertEqual(jar.read_bytes(),previous)
            with zipfile.ZipFile(jar,'w') as z:
                z.writestr('one/livara/LivaraUI.js',b'a');z.writestr('two/livara/LivaraUI.js',b'b')
            previous=jar.read_bytes()
            with self.assertRaisesRegex(ValueError,'Ambiguous'):update.update_jar(jar,resource)
            self.assertEqual(jar.read_bytes(),previous)

if __name__=='__main__':unittest.main()

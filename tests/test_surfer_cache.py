import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('surfer_cache',ROOT/'forks/browser/prepare-surfer-cache.py');cache=importlib.util.module_from_spec(spec);spec.loader.exec_module(cache)
class SurferCache(unittest.TestCase):
    def fixture(self,root):
        folder=root/'node_modules/@zen-browser/surfer';(folder/'dist/commands/download').mkdir(parents=True)
        (folder/'package.json').write_text(json.dumps({'version':'1.14.9'}));path=folder/'dist/commands/download/firefox.js';path.write_text('function download() {\n'+cache.ORIGINAL+'\n}\n');return path
    def test_guard_added_once_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.fixture(root);self.assertTrue(cache.prepare(root,'1.14.9'));original=path.read_bytes()
            self.assertIn('existsSync',path.read_text());self.assertFalse(cache.prepare(root,'1.14.9'));self.assertEqual(path.read_bytes(),original)
    def test_changed_source_or_version_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.fixture(root);original=path.read_bytes()
            with self.assertRaises(ValueError):cache.prepare(root,'99.0.0')
            self.assertEqual(path.read_bytes(),original)
            path.write_text('unknown downloader')
            with self.assertRaises(ValueError):cache.prepare(root,'1.14.9')
            self.assertEqual(path.read_text(),'unknown downloader')
if __name__=='__main__':unittest.main()

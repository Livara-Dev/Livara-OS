import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'scripts/package-iso-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
class ReleaseTests(unittest.TestCase):
    def test_split_join_restores_exact_iso_and_verifies_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);iso=root/'livara-test.iso';data=bytes(range(256))*40;iso.write_bytes(data)
            result=release.package(iso,root/'release',limit=3000)
            self.assertEqual(len(result['parts']),4)
            self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
            subprocess.run(['bash',str(root/'release/Join-Livara-ISO.sh')],check=True,capture_output=True)
            self.assertEqual((root/'release'/iso.name).read_bytes(),data)
            self.assertIn(b'\r\n',(root/'release/Join-Livara-ISO.bat').read_bytes())
    def test_corrupt_part_does_not_produce_iso(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);iso=root/'livara-test.iso';iso.write_bytes(b'fixture'*100)
            result=release.package(iso,root/'release',limit=300)
            (root/'release'/result['parts'][0]['name']).write_bytes(b'bad')
            result=subprocess.run(['bash',str(root/'release/Join-Livara-ISO.sh')],capture_output=True)
            self.assertNotEqual(result.returncode,0);self.assertFalse((root/'release'/iso.name).exists())
    def test_small_iso_is_single_asset_and_existing_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);iso=root/'livara-test.iso';iso.write_bytes(b'fixture')
            result=release.package(iso,root/'release',limit=100)
            self.assertEqual((root/'release'/iso.name).read_bytes(),b'fixture');self.assertEqual(len(result['parts']),1)
            with self.assertRaises(ValueError):release.package(iso,root/'release',limit=100)
if __name__=='__main__':unittest.main()

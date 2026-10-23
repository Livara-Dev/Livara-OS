"""Regression tests for native-header network/integrity failures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('headers',ROOT/'scripts/prepare-code-headers.py');headers=importlib.util.module_from_spec(spec);spec.loader.exec_module(headers)
class HeaderTests(unittest.TestCase):
    def entry(self,version='43.7.7',payload=b'verified fixture'):
        return {'version':version,'url':f'https://artifacts.electronjs.org/headers/dist/v{version}/node-v{version}-headers.tar.gz','sha256':hashlib.sha256(payload).hexdigest()}
    def fixture(self,root):
        for folder,version in [('', '43.7.7'),('build','22.22.1'),('remote','24.21.0')]:
            path=root/folder/'.npmrc';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(f'target="{version}"\n')
    def test_all_actual_pinned_targets_and_official_https(self):
        manifest=json.loads((ROOT/'forks/code/native-headers.json').read_text());headers.validate_manifest(manifest)
        self.assertEqual({e['version'] for e in manifest},{'43.7.7','24.18.0','24.22.1','22.22.1'})
        for item in [{**self.entry(),'url':'http://nodejs.org/test'}, {**self.entry(),'url':'https://evil.invalid/a'}, {**self.entry(),'sha256':'bad'}]:
            with self.assertRaises(ValueError):headers.validate_manifest([item])
    def test_changed_checkout_target_fails_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);run=Mock()
            with self.assertRaises(ValueError):headers.prepare([self.entry()],root,root/'cache','v24.18.0',Path('/gyp.js'),run)
            run.assert_not_called()
            self.assertEqual(headers.required_versions(root,'v24.18.0'),{'43.7.7','24.18.0','24.21.0','22.22.1'})
    def test_checksum_failure_never_installs_or_keeps_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def bad_download(argv,check):Path(argv[argv.index('--output')+1]).write_bytes(b'truncated network response')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):headers.download(self.entry(),root,bad_download)
            self.assertEqual(list(root.iterdir()),[])
    def test_verified_cache_skips_network_and_corruption_redownloads(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);entry=self.entry();path=root/'node-v43.7.7-headers.tar.gz';path.write_bytes(b'verified fixture')
            run=Mock();self.assertEqual(headers.download(entry,root,run),path);run.assert_not_called()
            path.write_bytes(b'corrupt')
            def download(argv,check):
                self.assertIn('--retry-all-errors',argv);self.assertIn('--proto-redir',argv)
                Path(argv[argv.index('--output')+1]).write_bytes(b'verified fixture')
            self.assertEqual(headers.download(entry,root,download).read_bytes(),b'verified fixture')
    def test_missing_or_ambiguous_npm_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.fixture(root);(root/'.npmrc').write_text('target="43.7.7"\ntarget="1.0.0"\n')
            with self.assertRaises(ValueError):headers.required_versions(root,'24.18.0')

if __name__=='__main__':unittest.main()

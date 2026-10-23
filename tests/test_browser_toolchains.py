import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('browser_toolchains',ROOT/'forks/browser/prepare-toolchains.py')
tools=importlib.util.module_from_spec(spec);spec.loader.exec_module(tools)


class BrowserToolchains(unittest.TestCase):
    def fixture(self):
        data=b'compiler fixture, never shipped as a real compiler'
        item=dict(tools.manifest(),sha256=hashlib.sha256(data).hexdigest(),size=len(data))
        cot=json.dumps({'taskId':item['task_id'],'artifacts':{item['artifact']:{'sha256':item['sha256']}}}).encode()
        item['chain_of_trust_sha256']=hashlib.sha256(cot).hexdigest()
        return item,data,cot

    def test_verified_cache_works_without_any_network(self):
        item,data,cot=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);archive,provenance=tools.cached_paths(state,item)
            archive.parent.mkdir();provenance.parent.mkdir();archive.write_bytes(data);provenance.write_bytes(cot)
            with patch.object(tools,'preflight',side_effect=AssertionError('No network permitted')):
                tools.prepare(state,item)
            self.assertEqual(archive.read_bytes(),data)

    def test_corrupt_provenance_is_rejected_without_network_or_replacement(self):
        item,data,cot=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);archive,provenance=tools.cached_paths(state,item)
            archive.parent.mkdir();provenance.parent.mkdir();archive.write_bytes(data);provenance.write_bytes(cot+b'changed')
            with patch.object(tools,'preflight',side_effect=AssertionError('No network permitted')):
                with self.assertRaisesRegex(ValueError,'checksum'):tools.prepare(state,item)
            self.assertEqual(archive.read_bytes(),data)

    def test_corrupt_download_cannot_replace_existing_cache(self):
        item,data,cot=self.fixture()
        def wrong_download(command,**kwargs):Path(command[command.index('--output')+1]).write_bytes(b'wrong')
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);archive,_=tools.cached_paths(state,item);archive.parent.mkdir();archive.write_bytes(b'previous invalid cache')
            with patch.object(tools,'preflight',return_value=cot):
                with self.assertRaisesRegex(ValueError,'checksum'):tools.prepare(state,item,run=wrong_download)
            self.assertEqual(archive.read_bytes(),b'previous invalid cache')
            self.assertFalse(list(archive.parent.glob('.livara-clang-*')))

    def test_persistent_403_has_bounded_attempts_and_useful_error(self):
        calls=[]
        def blocked(url,*args):
            calls.append(url);raise urllib.error.HTTPError(url,403,'Forbidden',None,None)
        with patch.object(tools.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'before source downloads/compilation'):
                tools.request_official(tools.urls(tools.manifest(),'public/chain-of-trust.json'),1024,fetch=blocked)
        self.assertEqual(len(calls),4)

    def test_patch_is_scoped_idempotent_and_rejects_changed_upstream(self):
        item=tools.manifest()
        with tempfile.TemporaryDirectory() as folder:
            engine=Path(folder);path=engine/'python/mozbuild/mozbuild/artifact_commands.py';path.parent.mkdir(parents=True)
            path.write_text('def test():\n    if True:\n        if True:\n            if True:\n'+tools.ANCHOR+'\n')
            tools.patch(engine,item);first=path.read_bytes();ast.parse(path.read_text());tools.patch(engine,item)
            self.assertEqual(path.read_bytes(),first)
            self.assertIn(item['task_id'],path.read_text());self.assertIn('hashlib.sha256(raw_cot)',path.read_text())
            path.write_text('changed upstream')
            with self.assertRaisesRegex(ValueError,'downloader changed'):tools.patch(engine,item)
            self.assertEqual(path.read_text(),'changed upstream')

    def test_preflight_runs_before_long_builds(self):
        windows=(ROOT/'scripts/windows-build.sh').read_text()
        self.assertLess(windows.index('prepare-toolchains.py --check'),windows.index('bash scripts/build-code.sh /project/dist/forks'))
        browser=(ROOT/'forks/browser/build-source.sh').read_text()
        self.assertLess(browser.index('prepare-toolchains.py" --state'),browser.index('git clone'))
        self.assertLess(browser.index('--engine "$PWD"'),browser.index('./mach --no-interactive bootstrap'))

if __name__=='__main__':unittest.main()

"""Offline official-launch, file-preservation and artifact-verification tests."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


official = module('official_tor', ROOT / 'share/livara/browser/official_tor.py')
preparer = module('prepare_official_tor', ROOT / 'scripts/prepare-tor-browser.py')

LAUNCHER = '''#!/usr/bin/env python3
import json, os, pathlib, sys
base=pathlib.Path(__file__).parent
capture={'args':sys.argv[1:],'cwd':os.getcwd(),'launcher':str(pathlib.Path(__file__).resolve()),'environment':{key:value for key,value in os.environ.items() if key.startswith(('LIVARA_TOR_','MOZ_DISABLE_'))}}
pathlib.Path(os.environ['OFFICIAL_TOR_TEST_OUTPUT']).write_text(json.dumps(capture))
raise SystemExit(int(os.environ.get('OFFICIAL_TOR_TEST_EXIT','0')))
'''


class OfficialTor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='livara-official-tor-test-')
        self.root = Path(self.temp.name)
        self.base = self.root / 'immutable-tor-browser'
        (self.base / 'Browser/fonts').mkdir(parents=True)
        (self.base / 'Browser/start-tor-browser').write_text(LAUNCHER)
        (self.base / 'Browser/start-tor-browser').chmod(0o700)
        (self.base / 'Browser/firefox').write_text('#!/bin/sh\nexec "$0.real" "$@"\n')
        (self.base / 'Browser/firefox').chmod(0o700)
        header = bytearray(64)
        header[:6] = b'\x7fELF\x02\x01'
        header[18:20] = struct.pack('<H', 62)
        (self.base / 'Browser/firefox.real').write_bytes(header)
        (self.base / 'Browser/firefox.real').chmod(0o700)
        (self.base / 'Browser/fonts/fonts.conf').write_text('<fontconfig><dir prefix="cwd">fonts</dir></fontconfig>')
        (self.base / 'Browser/fonts/bundled.ttf').write_bytes(b'official-font-bytes')
        self.files = self.root / 'files.json'
        entries = []
        for filename in sorted(self.base.rglob('*')):
            info = filename.lstat()
            entry = {'path': filename.relative_to(self.base).as_posix(), 'mode': stat.S_IMODE(info.st_mode),
                     'type': 'directory' if filename.is_dir() else 'file'}
            if filename.is_file():
                entry.update(size=info.st_size, sha256=hashlib.sha256(filename.read_bytes()).hexdigest())
            entries.append(entry)
        self.entries = entries
        self.files.write_text(json.dumps({'schema': 1, 'archive_root': 'tor-browser', 'entries': entries}))
        self.pin = {'schema': 1, 'version': '15.0.26', 'primary_fingerprint': official.PRIMARY,
                    'sha256': '1' * 64, 'assets': {'files.json': hashlib.sha256(self.files.read_bytes()).hexdigest()}}
        self.manifest = self.root / 'upstream.json'
        self.manifest.write_text(json.dumps(self.pin))
        self.data = self.root / 'private-user-data'
        self.capture = self.root / 'capture.json'
        self.environment = patch.dict(os.environ, {'OFFICIAL_TOR_TEST_OUTPUT': str(self.capture), 'OFFICIAL_TOR_TEST_EXIT': '0'})
        self.environment.start()
        self.regular_user = patch.object(official, '_root_user', return_value=False)
        self.regular_user.start()

    def tearDown(self):
        self.regular_user.stop()
        self.environment.stop()
        self.temp.cleanup()

    def run_browser(self, urls=None, **options):
        with contextlib.redirect_stderr(io.StringIO()):
            return official.run_tor_browser(urls or [], base_directory=self.base, data_directory=self.data,
                                            manifest_path=self.manifest, files_manifest_path=self.files, **options)

    def test_copy_preserves_official_files_exec_fonts_and_only_passes_urls(self):
        os.environ['MOZ_DISABLE_CONTENT_SANDBOX'] = '1'
        os.environ['LIVARA_TOR_SOCKS_PORT'] = '9999'
        self.assertEqual(self.run_browser(['https://example.org/']), 0)
        copy = self.data / self.pin['version'] / 'tor-browser'
        capture = json.loads(self.capture.read_text())
        self.assertEqual(capture['args'], ['https://example.org/'])
        self.assertEqual(Path(capture['cwd']), copy / 'Browser')
        self.assertEqual(capture['environment'], {})
        for entry in self.entries:
            if entry['type'] == 'file':
                original, cloned = self.base / entry['path'], copy / entry['path']
                self.assertEqual(cloned.read_bytes(), original.read_bytes())
                self.assertEqual(stat.S_IMODE(cloned.stat().st_mode), stat.S_IMODE(original.stat().st_mode))
        self.assertEqual(stat.S_IMODE(self.data.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(copy.parent.stat().st_mode), 0o700)
        self.assertFalse((copy / 'Browser/user.js').exists())
        self.assertTrue((copy.parent / '.livara-origin.json').is_file())

    def test_existing_official_updates_and_profiles_are_never_overwritten(self):
        self.assertEqual(self.run_browser(), 0)
        copy = self.data / self.pin['version'] / 'tor-browser'
        profile = copy / 'Browser/TorBrowser/Data/Browser/profile.default'
        profile.mkdir(parents=True)
        (profile / 'prefs.js').write_text('official-user-profile-data')
        (copy / 'Browser/firefox.real').write_bytes(b'official-updater-replaced-this-file')
        self.assertEqual(self.run_browser(['https://example.org/next']), 0)
        self.assertEqual((copy / 'Browser/firefox.real').read_bytes(), b'official-updater-replaced-this-file')
        self.assertEqual((profile / 'prefs.js').read_text(), 'official-user-profile-data')
        self.assertEqual((self.base / 'Browser/firefox.real').read_bytes()[:4], b'\x7fELF')

    def test_shared_read_permissions_allowed_but_altered_baseline_is_refused(self):
        for filename in self.base.rglob('*'):
            if filename.is_file():
                filename.chmod(0o755 if filename.stat().st_mode & 0o100 else 0o644)
            elif filename.is_dir(): filename.chmod(0o755)
        self.assertEqual(self.run_browser(), 0)
        shutil.rmtree(self.data)
        (self.base / 'Browser/fonts/fonts.conf').write_text('injected-system-fonts')
        self.assertEqual(self.run_browser(), 1)
        self.assertFalse((self.data / self.pin['version']).exists())

    def test_copy_is_checked_before_atomic_promotion(self):
        original = official.shutil.copytree
        def corrupted(source, target, *args, **options):
            result = original(source, target, *args, **options)
            if Path(target).name == 'tor-browser':
                (Path(target) / 'Browser/fonts/bundled.ttf').write_bytes(b'corrupt')
            return result
        with patch.object(official.shutil, 'copytree', side_effect=corrupted):
            self.assertEqual(self.run_browser(), 1)
        self.assertFalse((self.data / self.pin['version']).exists())
        self.assertEqual(sorted(path.name for path in self.data.iterdir()), ['.15.0.26.copy.lock'])

    def test_symlink_user_storage_and_existing_origin_conflicts_refused(self):
        self.data.mkdir()
        outside = self.root / 'outside'
        outside.mkdir()
        (self.data / self.pin['version']).symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.run_browser(), 1)
        self.assertEqual(list(outside.iterdir()), [])
        (self.data / self.pin['version']).unlink()
        self.assertEqual(self.run_browser(), 0)
        marker = self.data / self.pin['version'] / '.livara-origin.json'
        marker.write_text(json.dumps({'baseline_version': '15.0.26', 'archive_sha256': 'different'}))
        self.assertEqual(self.run_browser(), 1)
        self.assertIn('different', marker.read_text())

    def test_root_custom_arguments_and_non_web_urls_refused(self):
        with patch.object(official, '_root_user', return_value=True):
            self.assertEqual(self.run_browser(), 2)
        for urls, options in [(['file:///etc/passwd'], {}), (['javascript:alert(1)'], {}),
                              (['https://example.org\n--profile=x'], {}), (['--no-sandbox'], {}),
                              ([], {'browser_args': ['--profile=/tmp/zen-profile']})]:
            with self.subTest(urls=urls): self.assertEqual(self.run_browser(urls, **options), 1)
        self.assertFalse(self.data.exists())
        self.assertFalse(self.capture.exists())

    def test_valid_v3_onion_checksum_and_bad_or_retired_addresses(self):
        key = bytes(range(32)); version = b'\x03'
        service = base64.b32encode(key + hashlib.sha3_256(b'.onion checksum' + key + version).digest()[:2] + version).decode().lower()
        url = f'http://subdomain.{service}.onion/path'
        self.assertEqual(official.validate_urls([url]), [url])
        self.assertEqual(self.run_browser([url]), 0)
        for invalid in ['http://abcdefghijklmnop.onion', f'http://{service[:-1]}a.onion']:
            with self.assertRaises(ValueError): official.validate_urls([invalid])

    def test_official_exit_code_is_preserved(self):
        os.environ['OFFICIAL_TOR_TEST_EXIT'] = '7'
        self.assertEqual(self.run_browser(), 7)

    def test_archive_member_and_elf_file_preservation_guards(self):
        archive = self.root / 'fixture.tar.xz'
        with tarfile.open(archive, 'w:xz') as bundle:
            bundle.add(self.base, arcname='tor-browser')
        report = preparer.verify_archive(archive, self.root)
        self.assertEqual(report['elf_machine'], 'AMD64')
        self.assertEqual(report['members'], len(self.entries))
        (self.base / 'Browser/firefox.real').write_bytes(b'not-an-ELF')
        with tarfile.open(archive, 'w:xz') as bundle: bundle.add(self.base, arcname='tor-browser')
        with self.assertRaises(ValueError): preparer.verify_archive(archive, self.root)
        for path in ['../outside', '/tor-browser/outside', 'tor-browser/../outside']:
            with self.assertRaises(ValueError): preparer.safe_member(tarfile.TarInfo(path))
        alias = tarfile.TarInfo('tor-browser/Browser/unsafe'); alias.type = tarfile.SYMTYPE; alias.linkname = '../../../outside'
        with self.assertRaises(ValueError): preparer.safe_member(alias)

    def test_pinned_assets_and_checksum_tampering_detected_offline(self):
        pin = self.root / 'pin'
        shutil.copytree(ROOT / 'forks/tor', pin)
        (pin / 'bundle.sig.asc').write_text('tampered signature')
        with self.assertRaises(ValueError): preparer.check_pin(pin)
        archive = self.root / 'bad.tar.xz'; archive.write_bytes(b'not official')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            preparer.verify_signature(archive, ROOT / 'forks/tor', {'sha256': '0' * 64})

    @unittest.skipUnless(shutil.which('gpg'), 'gnupg is required for the build pin check')
    def test_real_official_primary_key_fingerprint(self):
        self.assertEqual(preparer.key_fingerprint(ROOT / 'forks/tor/tor-browser-developers.asc', shutil.which('gpg')), official.PRIMARY)


if __name__ == '__main__':
    unittest.main()

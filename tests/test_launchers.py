"""Check application argument forwarding and the live-image archive boundary."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from livara import code_launcher

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_livara_forks', ROOT / 'build/install-forks.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class CodeLauncher(unittest.TestCase):
    def test_argument_array_is_forwarded_without_shell_or_sandbox_bypass(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / 'livara-code'
            binary.write_text('#!/bin/sh\n')
            binary.chmod(0o755)
            args = ['--wait', str(Path(tmp) / 'a $(touch marker).py')]
            with patch.object(code_launcher, 'BINARY', binary), patch.object(code_launcher.os, 'execv') as execute:
                self.assertEqual(code_launcher.main(args), 0)
                execute.assert_called_once_with(str(binary), [str(binary), *args])
            self.assertFalse((Path(tmp) / 'marker').exists())

    def test_missing_application_reports_a_build_instruction(self):
        stream = io.StringIO()
        with patch.object(code_launcher, 'BINARY', Path('/nonexistent/livara-code')), contextlib.redirect_stderr(stream):
            self.assertEqual(code_launcher.main([]), 127)
        self.assertIn('Build-Livara.bat', stream.getvalue())


class ForkArchiveBoundary(unittest.TestCase):
    def item(self, name, kind=tarfile.REGTYPE, link=''):
        entry = tarfile.TarInfo(name)
        entry.type, entry.linkname = kind, link
        return entry

    def test_expected_tree_and_internal_links_are_accepted(self):
        installer.validate_members([self.item('livara-code', tarfile.DIRTYPE), self.item('livara-code/livara-code'), self.item('livara-code/bin/app', tarfile.SYMTYPE, '../livara-code')], 'livara-code')

    def test_escaping_paths_links_and_special_files_are_rejected(self):
        for entry in [self.item('/etc/host.conf'), self.item('livara-code/../../oops'), self.item('other/app'), self.item('livara-code/a', tarfile.SYMTYPE, '../../outside'), self.item('livara-code/a', tarfile.SYMTYPE, '/etc/passwd'), self.item('livara-code/device', tarfile.CHRTYPE)]:
            with self.subTest(name=entry.name, kind=entry.type), self.assertRaises(ValueError):
                installer.validate_members([entry], 'livara-code')

    def test_only_amd64_elf_can_enter_the_live_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / 'app'
            header = bytearray(20)
            header[:6] = b'\x7fELF\x02\x01'
            header[18:20] = (62).to_bytes(2, 'little')
            binary.write_bytes(header)
            installer.validate_elf(binary)
            for changed in ((4, 1), (18, 183)):
                invalid = header.copy(); invalid[changed[0]] = changed[1]
                binary.write_bytes(invalid)
                with self.assertRaises(ValueError): installer.validate_elf(binary)
            binary.write_text('#!/bin/sh\n')
            with self.assertRaises(ValueError): installer.validate_elf(binary)

    def test_private_build_modes_become_readable_without_changing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / 'source/livara-browser'
            source.mkdir(parents=True, mode=0o700)
            header = bytearray(20)
            header[:6] = b'\x7fELF\x02\x01'
            header[18:20] = (62).to_bytes(2, 'little')
            binary = source / 'livara-browser'
            binary.write_bytes(header); binary.chmod(0o700)
            resource = source / 'chrome.css'
            resource.write_text('body { color: purple; }'); resource.chmod(0o600)
            archive = workspace / 'livara-browser-linux-x64.tar.xz'
            with tarfile.open(archive, 'w:xz') as output:
                output.add(source, arcname='livara-browser')
            apps = {'browser': ('livara-browser-linux-x64.tar.xz', 'livara-browser', 'livara-browser')}
            with patch.object(installer, 'APPS', apps), contextlib.redirect_stdout(io.StringIO()):
                installer.install(workspace, workspace / 'installed')
            installed = workspace / 'installed/livara-browser'
            self.assertEqual(installed.stat().st_mode & 0o777, 0o755)
            self.assertEqual((installed / 'chrome.css').stat().st_mode & 0o777, 0o644)
            self.assertEqual((installed / 'livara-browser').stat().st_mode & 0o777, 0o755)
            self.assertEqual((installed / 'chrome.css').read_bytes(), resource.read_bytes())
            self.assertEqual((installed / 'livara-browser').read_bytes(), bytes(header))

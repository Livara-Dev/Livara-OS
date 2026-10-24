"""Packaging boundaries; executable runtime behavior is checked in Code CI."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('code_update', ROOT / 'scripts/package-code-update.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


@unittest.skipUnless(shutil.which('dpkg-deb'), 'Debian packaging tools required')
class CodeUpdatePackage(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / 'source/livara-code'
        (self.app / 'bin').mkdir(parents=True)
        (self.app / 'resources/app/out/vs/workbench').mkdir(parents=True)
        (self.app / 'livara-code').write_bytes(b'\x7fELFpackaging-fixture-only')
        (self.app / 'livara-code').chmod(0o755)
        (self.app / 'bin/livara-code').write_text('#!/bin/sh\nexit 0\n')
        (self.app / 'bin/livara-code').chmod(0o755)
        (self.app / 'resources/app/out/vs/workbench/workbench.desktop.main.js').write_text('/* packaging fixture */')
        (self.app / 'resources/app/out/vs/workbench/workbench.desktop.main.css').write_text('/* packaging fixture */')
        (self.app / 'resources/app/product.json').write_text('{}')
        self.manifest = {'upstream': json.loads((ROOT / 'forks/code/upstream.json').read_text()),
                         'built': True, 'distribution': 'Livara Code', 'build_target': 'vscode-linux-x64-min',
                         'recipes': {name: packager.sha256(ROOT / 'forks/code' / name) for name in
                                     ('overlay/core/windowControls.ts', 'overlay/core/livara.css', 'overlay/core/livara.contribution.ts')}}

    def archive(self):
        (self.app / 'resources/app/livara-build.json').write_text(json.dumps(self.manifest))
        archive = self.root / 'livara-code-linux-x64.tar.xz'
        with tarfile.open(archive, 'w:xz') as output:
            output.add(self.app, arcname='livara-code')
        Path(str(archive) + '.sha256').write_text(packager.sha256(archive) + '  ' + archive.name + '\n')
        return archive

    def test_package_owns_only_opt_and_records_compiled_source_version(self):
        package = packager.build(self.archive(), self.root / 'output')
        self.assertEqual(subprocess.check_output(['dpkg-deb', '-f', str(package), 'Package'], text=True).strip(), 'livara-code')
        data = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(package)])
        with tarfile.open(fileobj=io.BytesIO(data)) as contents:
            self.assertTrue(all(member.name == '.' or member.name.startswith('./opt') for member in contents))
            self.assertTrue(all((member.uid, member.gid) == (0, 0) for member in contents))
            report = json.load(contents.extractfile('./opt/livara-code/resources/app/livara-build.json'))
            self.assertEqual(report['desktop_package_version'], packager.__version__)
            self.assertEqual(contents.getmember('./opt/livara-code/livara-code').mode, 0o755)

    def test_stale_compiled_controller_is_rejected(self):
        self.manifest['recipes']['overlay/core/windowControls.ts'] = 'old-source-hash'
        with self.assertRaisesRegex(ValueError, 'current source fix'):
            packager.build(self.archive(), self.root / 'output')

    def test_check_only_validates_without_creating_installable_package(self):
        result = packager.build(self.archive(), self.root / 'output', check_only=True)
        self.assertIsNone(result)
        self.assertEqual(list((self.root / 'output').glob('*.deb')), [])

    def test_modified_archive_is_rejected_before_packaging(self):
        archive = self.archive()
        archive.write_bytes(archive.read_bytes() + b'modified')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            packager.build(archive, self.root / 'output')


if __name__ == '__main__':
    unittest.main()

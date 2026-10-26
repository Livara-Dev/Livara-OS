from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from livara import boot


class BootRefresh(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'proc').mkdir()
        (self.root / 'boot/grub').mkdir(parents=True)
        (self.root / 'proc/cmdline').write_text('root=UUID=example quiet splash')
        (self.root / 'proc/mounts').write_text('/dev/mapper/root / ext4 rw 0 0\n')
        (self.root / 'boot/grub/grub.cfg').write_text('existing boot menu')
        self.run = Mock()

    def test_installed_system_regenerates_grub_without_replacing_main_configuration(self):
        result = boot.refresh(root=self.root, runner=self.run, command='/usr/sbin/update-grub')
        self.run.assert_called_once_with(['/usr/sbin/update-grub'], check=True, timeout=180)
        self.assertIn('auto-boot enabled', result)
        self.assertEqual((self.root / 'boot/grub/grub.cfg').read_text(), 'existing boot menu')

    def test_live_media_and_overlay_never_rewrite_boot_files(self):
        for cmdline, mounts in (('boot=casper', '/dev/sda / ext4 rw 0 0'),
                                ('quiet', 'overlay / overlay rw 0 0')):
            (self.root / 'proc/cmdline').write_text(cmdline)
            (self.root / 'proc/mounts').write_text(mounts)
            self.assertIn('read-only', boot.refresh(root=self.root, runner=self.run))
        self.run.assert_not_called()

    def test_absent_grub_is_not_created_and_failed_generation_is_reported(self):
        self.run.side_effect = subprocess.CalledProcessError(1, 'update-grub')
        with self.assertRaises(subprocess.CalledProcessError):
            boot.refresh(root=self.root, runner=self.run, command='update-grub')
        (self.root / 'boot/grub/grub.cfg').unlink()
        self.run.reset_mock()
        self.assertIn('No installed GRUB', boot.refresh(root=self.root, runner=self.run))
        self.run.assert_not_called()

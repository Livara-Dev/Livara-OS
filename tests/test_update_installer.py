"""The downloaded installer must explain incomplete downloads and fail closed."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desktop_update_builder", ROOT / "scripts/package-desktop-update.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class InstallerFeedback(unittest.TestCase):
    def run_installer(self, files):
        with tempfile.TemporaryDirectory(prefix="livara installer ") as temporary:
            root = Path(temporary)
            script = root / "Install-Livara-Update.sh"
            script.write_text(builder.installer_script("desktop.deb", "code.deb"))
            for name, data in files.items():
                (root / name).write_bytes(data)
            subprocess.run(["bash", "-n", str(script)], check=True)
            return subprocess.run(["bash", str(script)], cwd="/tmp", capture_output=True, text=True)

    def test_script_only_explains_the_missing_package(self):
        result = self.run_installer({})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checking downloaded files", result.stdout)
        self.assertIn("Missing or unreadable file: desktop.deb", result.stderr)
        self.assertIn("releases/tag/desktop-v", result.stderr)

    def test_missing_checksums_are_reported_before_installation(self):
        result = self.run_installer({"desktop.deb": b"fixture"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing or unreadable file: SHA256SUMS", result.stderr)
        self.assertNotIn("Installing the update", result.stdout)

    def test_corrupted_package_reports_failure_and_does_not_install(self):
        checksum = hashlib.sha256(b"original").hexdigest().encode() + b"  desktop.deb\n"
        result = self.run_installer({"desktop.deb": b"corrupted", "SHA256SUMS": checksum})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertIn("Update stopped at line", result.stderr)
        self.assertNotIn("Installing the update", result.stdout)

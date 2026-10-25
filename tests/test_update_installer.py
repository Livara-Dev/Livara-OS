"""The downloaded installer must explain incomplete downloads and fail closed."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desktop_update_builder", ROOT / "scripts/package-desktop-update.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class InstallerFeedback(unittest.TestCase):
    def test_bundle_extracts_all_required_files_into_one_versioned_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = ["desktop.deb", "code.deb", "Install-Livara-Update.sh", "README.txt", "update-manifest.json"]
            for name in names:
                (root / name).write_bytes(("release payload " + name).encode())
            (root / "SHA256SUMS").write_text("".join(hashlib.sha256((root / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in names))
            bundle = builder.bundle_update(root, names)
            with zipfile.ZipFile(bundle) as archive:
                self.assertIsNone(archive.testzip())
                prefix = f"Livara-Halo-{builder.__version__}-Update/"
                self.assertEqual(set(archive.namelist()), {prefix + name for name in (*names, "SHA256SUMS")})
                archive.extractall(root / "extracted")
            folder = root / "extracted" / prefix
            result = subprocess.run(["sha256sum", "--check", "SHA256SUMS"], cwd=folder, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

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

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from livara import core
from livara.cli import main


class Workspaces(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def new_case(self):
        return core.create_case("lab-review", self.root)

    def test_private_case_and_refuse_overwrite(self):
        case = self.new_case()
        self.assertEqual(case.stat().st_mode & 0o777, 0o700)
        self.assertTrue((case / "evidence").is_dir())
        self.assertTrue((case / "reports").is_dir())
        self.assertEqual(json.loads((case / "case.json").read_text())["name"], "lab-review")
        with self.assertRaises(FileExistsError):
            self.new_case()

    def test_traversal_and_shell_characters_rejected(self):
        for name in ("../escape", "/tmp/escape", "a/b", "", "a;touch bad", "$(touch bad)", "a" * 65):
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.create_case(name, self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_case_manifest_detects_modified_missing_and_added(self):
        case = self.new_case()
        (case / "evidence" / "modified.bin").write_bytes(b"original")
        (case / "evidence" / "missing.bin").write_bytes(b"keep me")
        core.seal_case(case)
        self.assertTrue(core.verify_case(case)["ok"])
        (case / "evidence" / "modified.bin").write_bytes(b"changed")
        (case / "evidence" / "missing.bin").unlink()
        (case / "evidence" / "added.bin").write_bytes(b"new")
        report = core.verify_case(case)
        self.assertFalse(report["ok"])
        self.assertEqual(report["changed"], ["evidence/modified.bin"])
        self.assertEqual(report["missing"], ["evidence/missing.bin"])
        self.assertEqual(report["added"], ["evidence/added.bin"])

    def test_dotfiles_are_included_in_manifest(self):
        case = self.new_case()
        (case / "evidence" / ".livara-important").write_bytes(b"evidence")
        self.assertIn("evidence/.livara-important", core.seal_case(case)["files"])

    def test_symlinks_and_special_files_are_rejected(self):
        case = self.new_case()
        link = case / "evidence" / "external"
        link.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "Symbolic links"):
            core.seal_case(case)
        link.unlink()
        os.mkfifo(case / "evidence" / "pipe")
        with self.assertRaisesRegex(ValueError, "special file"):
            core.seal_case(case)

    def test_manifest_does_not_allow_external_paths(self):
        case = self.new_case()
        manifest = core.seal_case(case)
        manifest["files"]["../outside"] = "0" * 64
        (case / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "Invalid path"):
            core.verify_case(case)

    def test_malformed_metadata_and_manifest_fail_cleanly(self):
        case = self.new_case()
        (case / "manifest.json").write_text("[]")
        with self.assertRaises(ValueError):
            core.verify_case(case)
        (case / "case.json").write_text("[]")
        with self.assertRaises(ValueError):
            core.require_case(case)


class FileVerification(unittest.TestCase):
    def test_sha256_streaming_and_mismatch_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "with spaces.bin"
            target.write_bytes(b"Livara" * 300000)
            expected = hashlib.sha256(target.read_bytes()).hexdigest()
            self.assertEqual(core.verify_file(target, expected.upper()), (expected, True))
            self.assertEqual(core.verify_file(target, "0" * 64), (expected, False))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["verify", str(target), "--sha256", "0" * 64]), 1)
                self.assertEqual(main(["verify", str(target), "--sha256", expected]), 0)
            with self.assertRaises(ValueError):
                core.verify_file(target, "invalid")


class Toolbox(unittest.TestCase):
    def test_no_shell_interpolation_and_only_workspace_is_mounted(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "has spaces; $(echo test)"
            command = core.toolbox_run_command("web", ["printf", "$(id); touch /tmp/side-effect"], workspace)
            self.assertEqual(command[-2:], ["printf", "$(id); touch /tmp/side-effect"])
            self.assertIn("--cap-drop=ALL", command)
            self.assertIn("--read-only", command)
            self.assertIn("--security-opt=no-new-privileges", command)
            self.assertEqual(command.count("--mount"), 1)
            self.assertIn(f"type=bind,source={workspace},destination=/work", command)
            self.assertNotIn("--privileged", command)
            self.assertNotIn("--network=host", command)
            self.assertIn("localhost/livara-kali:0.1.0-web", command)

    def test_invalid_profile_and_ambiguous_mount_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                core.toolbox_run_command("core;echo bad", [], Path(directory))
            with self.assertRaises(ValueError):
                core.toolbox_run_command("core", [], Path(directory) / "a,b")

    def test_bundled_image_load_and_refresh(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, "DATA_DIR", Path(directory)):
            toolbox = Path(directory) / "toolbox"
            toolbox.mkdir()
            (toolbox / "Containerfile").write_text("FROM kalilinux/kali-rolling")
            (toolbox / "kali-core.tar.gz").touch()
            self.assertEqual(core.toolbox_setup_command("core")[:2], ["podman", "load"])
            command = core.toolbox_setup_command("core", refresh=True)
            self.assertEqual(command[:2], ["podman", "build"])
            self.assertIn("LIVARA_PROFILE=core", command)

    def test_persistent_storage_is_shared_by_setup_and_run(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            storage = Path(directory) / "disk with spaces; $(literal)"
            self.assertEqual(core.configure_toolbox_storage(storage), storage)
            self.assertEqual(core.toolbox_storage(), storage)
            with patch.object(core, "DATA_DIR", Path(__file__).resolve().parents[1] / "share/livara"):
                setup = core.toolbox_setup_command("full")
            run = core.toolbox_run_command("full", ["bash"], Path(directory) / "workspace")
            self.assertEqual(setup[:3], ["podman", "--root", str(storage)])
            self.assertEqual(run[:3], setup[:3])
            self.assertIn("LIVARA_PROFILE=full", setup)
            self.assertEqual(run[-2:], ["localhost/livara-kali:0.1.0-full", "bash"])
            self.assertEqual(core.toolbox_config().stat().st_mode & 0o777, 0o600)

    def test_full_catalog_storage_refuses_live_ram_filesystem(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            with patch.object(core, "read_text", return_value="boot=casper"), patch.object(core, "run_capture", return_value="overlay"):
                with self.assertRaisesRegex(ValueError, "persistent disk"):
                    core.configure_toolbox_storage(Path(directory) / "storage")
            self.assertFalse(core.toolbox_config().exists())


class SystemObservations(unittest.TestCase):
    def test_missing_firewall_privileges_are_unknown(self):
        with patch.object(core, "run_capture", return_value=None):
            firewall = next(item for item in core.shield_report() if item["name"] == "Host firewall")
            self.assertEqual(firewall["state"], "unknown")

    def test_os_release_is_parsed_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "os-release"
            target.write_text('NAME="Livara OS"\nID=livara\nX="$(touch /tmp/nope)"\n')
            self.assertEqual(core.os_info(target)["NAME"], "Livara OS")
            self.assertEqual(core.os_info(target)["X"], "$(touch /tmp/nope)")

    def test_json_status_contains_actual_system_fields(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["status", "--json"]), 0)
        status = json.loads(output.getvalue())
        self.assertEqual(status["kernel"], os.uname().release)
        self.assertGreater(status["disk_total"], 0)
        self.assertIsInstance(status["interfaces"], list)


class DebianPackaging(unittest.TestCase):
    @unittest.skipUnless(shutil.which("dpkg-deb"), "Debian packaging tools are not installed")
    def test_package_permissions_and_root_ownership(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["bash", str(project / "packaging/build-deb.sh"), directory], check=True, capture_output=True)
            from livara import __version__
            package = Path(directory) / f"livara-desktop_{__version__}_all.deb"
            archive = subprocess.run(["dpkg-deb", "--fsys-tarfile", str(package)], check=True, capture_output=True).stdout
            with tarfile.open(fileobj=io.BytesIO(archive)) as files:
                root = files.getmember(".")
                self.assertEqual(root.mode, 0o755)
                self.assertEqual(files.getmember("./usr/bin/livara").mode, 0o755)
                self.assertEqual(files.getmember("./usr/lib/python3/dist-packages/livara/core.py").mode, 0o644)
                for member in files.getmembers():
                    self.assertEqual((member.uid, member.gid), (0, 0))
                    self.assertNotIn("..", Path(member.name).parts)


if __name__ == "__main__":
    unittest.main()


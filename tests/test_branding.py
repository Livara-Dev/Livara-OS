import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("livara_branding", PROJECT / "share/livara/branding/apply-branding.py")
branding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(branding)


class Branding(unittest.TestCase):
    def test_named_assets_and_safe_alias_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "usr/share/livara/logo.png"
            png.parent.mkdir(parents=True)
            png.write_bytes(b"new-logo")
            svg = root / "usr/share/icons/hicolor/scalable/apps/org.livara.Center.svg"
            svg.parent.mkdir(parents=True)
            svg.write_bytes(b"<svg>Livara</svg>")
            target = root / "outside.svg"
            target.write_bytes(b"must stay untouched")
            alias = root / "usr/share/icons/Yaru/scalable/actions/view-app-grid-ubuntu-symbolic.svg"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(target)
            pro = root / "usr/share/software-properties/ubuntu-pro-logo.svg"
            pro.parent.mkdir(parents=True)
            pro.write_bytes(b"old-commercial-logo")
            notices = root / "usr/share/doc/original/copyright"
            notices.parent.mkdir(parents=True)
            notices.write_bytes(b"Original copyright preserved")
            branding.apply(root, refresh_caches=False, renderer=lambda *args: b"png")
            self.assertFalse(alias.is_symlink())
            self.assertEqual(alias.read_bytes(), svg.read_bytes())
            self.assertEqual(target.read_bytes(), b"must stay untouched")
            self.assertEqual(pro.read_bytes(), branding.EMPTY_SVG)
            self.assertEqual(notices.read_bytes(), b"Original copyright preserved")
            self.assertTrue(branding.audit(root)["ok"])
            alias.write_bytes(b"old logo restored")
            self.assertFalse(branding.audit(root)["ok"])

    def test_rebuilt_icon_cache_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "usr/share/icons/Yaru/icon-theme.cache"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"rebuilt Livara graphics")
            report = root / branding.REPORT
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps({"schema": 1, "replacements": [], "icon_caches": [
                {"path": cache.relative_to(root).as_posix(),
                 "sha256": branding.hashlib.sha256(cache.read_bytes()).hexdigest()}
            ]}))
            self.assertTrue(branding.audit(root)["ok"])
            cache.write_bytes(b"restored stale distribution graphics")
            self.assertFalse(branding.audit(root)["ok"])

    def test_png_canvas_is_bounded_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "logo.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", 260, 91))
            self.assertEqual(branding.png_bounds(path), (260, 91))
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", 9999999, 91))
            self.assertEqual(branding.png_bounds(path), (256, 256))

    def test_terminal_prompt_treats_directory_text_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            cwd = root / "$(touch OWNED)"
            cwd.mkdir()
            script = PROJECT / "share/livara/terminal/livara.bash"
            command = 'source "$1"; false; __livara_prompt; printf "%s\\n" "${PS1@P}"; shopt -q promptvars && exit 9; exit 0'
            result = subprocess.run(["bash", "--noprofile", "--norc", "-ic", command, "livara", str(script)],
                                    env={"HOME": str(home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color"},
                                    cwd=cwd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("exit 1", result.stdout)
            self.assertFalse((cwd / "OWNED").exists())


if __name__ == "__main__":
    unittest.main()

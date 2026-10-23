import tempfile
from pathlib import Path
import unittest

from livara import window_style


class WindowStyle(unittest.TestCase):
    def test_defaults_and_css_versions(self):
        values = window_style.normalized_values()
        self.assertEqual(values["window-button-style"], "traffic-lights")
        for version in (3, 4):
            css = window_style.css_for_values(values, version)
            for color in ("#ff5f57", "#febc2e", "#28c840"):
                self.assertIn(color, css)
            self.assertIn("min-width: 14px", css)
            self.assertIn(".livara-window-controls", css)
        self.assertIn("-gtk-icon-size:", window_style.css_for_values(values, 4))
        self.assertNotIn("-gtk-icon-size:", window_style.css_for_values(values, 3))

    def test_invalid_css_inputs_are_rejected(self):
        for values in ({"window-close-color": "red; } window {color:red"}, {"window-button-size": 9}, {"window-button-size": True}, {"window-button-size": 23}, {"window-button-symbols": "false"}, {"window-green-action": "shell"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                window_style.css_for_values(values)

    def test_managed_edit_preserves_user_css_and_is_reversible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for version in (3, 4):
                path = root / f"gtk-{version}.0/gtk.css"
                path.parent.mkdir()
                path.write_text("/* my existing theme */\nwindow { color: #c3c3c3; }")
                path.chmod(0o640)
            original = (root / "gtk-4.0/gtk.css").read_text()
            changed = window_style.apply_user_style({}, root)
            self.assertEqual(len(changed), 2)
            content = (root / "gtk-4.0/gtk.css").read_text()
            self.assertTrue(content.startswith(original))
            self.assertEqual(content.count(window_style.BEGIN), 1)
            self.assertEqual((root / "gtk-4.0/gtk.css").stat().st_mode & 0o777, 0o640)
            self.assertEqual(window_style.apply_user_style({}, root), [])
            window_style.apply_user_style({"window-close-color": "#112233", "window-button-size": 20}, root)
            content = (root / "gtk-4.0/gtk.css").read_text()
            self.assertEqual(content.count(window_style.BEGIN), 1)
            self.assertIn("#112233", content)
            window_style.apply_user_style({"window-button-style": "default"}, root)
            self.assertEqual((root / "gtk-4.0/gtk.css").read_text(), original)

    def test_invalid_marker_or_symlink_leaves_both_files_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "gtk-3.0/gtk.css"
            second = root / "gtk-4.0/gtk.css"
            first.parent.mkdir(); second.parent.mkdir()
            first.write_text("user gtk3 css")
            second.write_text(window_style.BEGIN + "\nunknown partial block")
            with self.assertRaises(ValueError):
                window_style.apply_user_style({}, root)
            self.assertEqual(first.read_text(), "user gtk3 css")
            second.unlink(); second.symlink_to(first)
            with self.assertRaises(ValueError):
                window_style.apply_user_style({}, root)
            self.assertTrue(second.is_symlink())
            self.assertEqual(first.read_text(), "user gtk3 css")

    def test_default_style_does_not_create_empty_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(window_style.apply_user_style({"window-button-style": "default"}, root), [])
            self.assertFalse((root / "gtk-4.0/gtk.css").exists())


if __name__ == "__main__":
    unittest.main()

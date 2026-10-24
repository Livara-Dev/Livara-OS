"""Login refresh applies installed preferences rather than resetting the user."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from livara import session, window_style


class SessionAppearance(unittest.TestCase):
    def test_existing_accounts_get_gtk_controls_without_changing_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            css = base / "gtk-4.0/gtk.css"
            css.parent.mkdir()
            css.write_text("/* user's theme */\n")
            values = {**window_style.DEFAULTS, "window-close-color": "#112233"}
            with patch.object(session.desktop, "settings_for", return_value=object()), \
                 patch.object(session.desktop, "window_style_values", return_value=values), \
                 patch.object(session.desktop, "write_setting") as write:
                self.assertEqual(len(session.refresh(config_home=base)), 2)
                self.assertEqual(session.refresh(config_home=base), [])
                write.assert_not_called()
            self.assertTrue(css.read_text().startswith("/* user's theme */\n"))
            self.assertIn("#112233", css.read_text())

    def test_missing_schema_does_not_create_default_user_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(session.desktop, "settings_for", return_value=None):
                with self.assertRaisesRegex(ValueError, "schemas are unavailable"):
                    session.refresh(config_home=Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_standard_controls_removes_managed_block_and_preserves_user_css(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            window_style.apply_user_style({}, base)
            css = base / "gtk-3.0/gtk.css"
            css.write_text("/* custom */\n" + css.read_text())
            values = {**window_style.DEFAULTS, "window-button-style": "default"}
            with patch.object(session.desktop, "settings_for", return_value=object()), \
                 patch.object(session.desktop, "window_style_values", return_value=values):
                session.refresh(config_home=base)
            self.assertEqual(css.read_text(), "/* custom */\n")

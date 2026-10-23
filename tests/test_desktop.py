"""Boundaries for user-controlled CSS values and desktop settings integration."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from livara import desktop


class WindowPreferences(unittest.TestCase):
    def test_colors_are_normalized_and_css_injection_never_persists(self):
        for key in desktop.WINDOW_COLOR_KEYS:
            with self.subTest(key=key), patch.object(desktop, "write_setting") as write, patch.object(desktop, "apply_window_style") as apply:
                desktop.set_option(key, "#A1B2C3")
                write.assert_called_once_with("org.livara.desktop", key, "#a1b2c3")
                apply.assert_called_once_with()
            for invalid in ("red", "#fff", "#ffffff00", "#ffffff; } window { opacity:0", "url(file:///tmp/a)", "#ff00gg", None):
                with self.subTest(key=key, invalid=invalid), patch.object(desktop, "write_setting") as write:
                    with self.assertRaises(ValueError):
                        desktop.set_option(key, invalid)
                    write.assert_not_called()

    def test_button_and_animation_values_are_bounded_before_writing(self):
        invalid = (("window-button-size", 9), ("window-button-size", 23), ("window-button-size", True),
                   ("window-animation-duration", 79), ("window-animation-duration", 601), ("window-animation-duration", 220.0),
                   ("window-button-style", "fake-native"), ("window-green-action", "execute"),
                   ("window-animation-style", "unbounded"), ("window-button-symbols", "false"))
        for name, value in invalid:
            with self.subTest(name=name, value=value), patch.object(desktop, "write_setting") as write:
                with self.assertRaises(ValueError):
                    desktop.set_option(name, value)
                write.assert_not_called()
        for name, value in desktop.WINDOW_DEFAULTS.items():
            self.assertEqual(desktop.validate_window_value(name, value), value)

    def test_style_snapshot_recovers_from_missing_or_invalid_old_settings(self):
        values = {"window-button-size": 1000, "window-close-color": "#fff;bad", "window-buttons": ":minimize,maximize,close", "window-green-action": "maximize"}
        with patch.object(desktop, "read_option", side_effect=lambda key: values.get(key)):
            result = desktop.window_style_values()
        self.assertEqual(result["window-button-size"], 14)
        self.assertEqual(result["window-close-color"], "#ff5f57")
        self.assertEqual(result["window-green-action"], "maximize")
        self.assertEqual(result["window-buttons"], ":minimize,maximize,close")
        self.assertEqual(set(result), {*desktop.WINDOW_STYLE_KEYS, "window-buttons"})

    def test_old_schema_missing_a_new_key_returns_unavailable(self):
        settings = MagicMock()
        settings.props.settings_schema.has_key.return_value = False
        with patch.object(desktop, "settings_for", return_value=settings):
            self.assertIsNone(desktop.read_option("window-button-style"))
        settings.get_value.assert_not_called()

    def test_button_side_applies_style_but_animation_does_not_rewrite_css(self):
        with patch.object(desktop, "write_setting") as write, patch.object(desktop, "apply_window_style") as apply:
            desktop.set_option("window-buttons", ":minimize,maximize,close")
            write.assert_called_once_with("org.gnome.desktop.wm.preferences", "button-layout", ":minimize,maximize,close")
            apply.assert_called_once_with()
        with patch.object(desktop, "write_setting") as write, patch.object(desktop, "apply_window_style") as apply:
            desktop.set_option("window-animation-style", "off")
            write.assert_called_once_with("org.livara.desktop", "window-animation-style", "off")
            apply.assert_not_called()

    def test_reset_restores_only_window_preferences(self):
        with patch.object(desktop, "write_setting") as write, patch.object(desktop, "apply_window_style") as apply:
            desktop.reset_window_preferences()
        settings = {(call.args[0], call.args[1]): call.args[2] for call in write.call_args_list}
        self.assertEqual(settings[("org.livara.desktop", "window-green-action")], "fullscreen")
        self.assertEqual(settings[("org.livara.desktop", "window-animation-duration")], 220)
        self.assertEqual(settings[("org.gnome.desktop.wm.preferences", "button-layout")], "close,minimize,maximize:")
        self.assertNotIn(("org.gnome.desktop.interface", "enable-animations"), settings)
        self.assertNotIn(("org.livara.desktop", "glass-enabled"), settings)
        apply.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

"""Global appearance reaches native windows without transparent text surfaces."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from livara import materials


class NativeMaterials(unittest.TestCase):
    def style(self):
        style = materials._LiveMaterials.__new__(materials._LiveMaterials)
        style.accent_override = None
        style.provider = Mock()
        manager = Mock()
        style.Adw = SimpleNamespace(StyleManager=SimpleNamespace(get_default=lambda: manager),
                                    ColorScheme=SimpleNamespace(FORCE_DARK="dark", FORCE_LIGHT="light"))
        return style, manager

    def test_global_light_mode_updates_native_scheme_and_readable_surfaces(self):
        style, manager = self.style()
        values = {"appearance": "light", "accent": "purple", "glass-enabled": True, "animations": True}
        with patch("livara.desktop.read_option", side_effect=values.get):
            style.refresh()
        manager.set_color_scheme.assert_called_once_with("light")
        css = style.provider.load_from_data.call_args.args[0].decode()
        self.assertIn("background-color: #f3f1f8", css)
        self.assertIn("color: #242032", css)
        self.assertNotIn("opacity:", css.split("window,", 1)[1].split("headerbar", 1)[0])

    def test_glass_and_motion_switches_remove_expensive_decoration(self):
        style, manager = self.style()
        values = {"appearance": "dark", "glass-enabled": False, "animations": False}
        with patch("livara.desktop.read_option", side_effect=values.get):
            style.changed(None, "glass-enabled")
        manager.set_color_scheme.assert_called_once_with("dark")
        css = style.provider.load_from_data.call_args.args[0].decode()
        self.assertIn("background-image: none", css)
        self.assertIn("box-shadow: none", css)
        self.assertIn("background-color 0ms", css)
        self.assertNotIn("backdrop-filter", css)

    def test_css_values_cannot_inject_rules(self):
        for value in (None, "red", "#fff", "#c5a3ff; opacity:0", "url(file:///secret)"):
            with self.assertRaises(ValueError):
                materials.css(accent=value)

    def test_explicit_app_accent_survives_global_appearance_changes(self):
        style, manager = self.style()
        style.accent_override = "#8dcaff"
        with patch("livara.desktop.read_option", side_effect={"appearance":"light", "accent":"purple"}.get):
            style.refresh()
        generated = style.provider.load_from_data.call_args.args[0].decode()
        self.assertIn("@define-color accent_bg_color #8dcaff", generated)
        manager.set_color_scheme.assert_called_once_with("light")


if __name__ == "__main__":
    unittest.main()

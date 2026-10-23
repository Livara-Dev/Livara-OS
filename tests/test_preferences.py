"""Settings catalog validation, inert preset storage and scoped application."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from livara import desktop, preferences


class CatalogTests(unittest.TestCase):
    def test_catalog_matches_actual_gnome46_schema_audit(self):
        audit = json.loads((Path(__file__).resolve().parents[1] / "docs/preferences-schema-audit.json").read_text())
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["errors"], [])
        evidence = {row["name"]: row for row in audit["rows"]}
        native_types = {"bool": ("b",), "choice": ("s",), "font": ("s",), "color": ("s",), "image": ("s",), "strv": ("as",), "int": ("i", "u"), "float": ("d",)}
        self.assertEqual(set(evidence), set(preferences.BY_NAME))
        for spec in preferences.CATALOG:
            row = evidence[spec["name"]]
            self.assertEqual((spec["schema"], spec["key"]), (row["schema"], row["key"]), spec["name"])
            self.assertIn(row["type"], native_types[spec["kind"]], spec["name"])
            for value, _label in spec.get("choices", []):
                self.assertIn(value, row["declared_values_checked"], spec["name"])

    def test_catalog_covers_unique_real_options_and_safe_types(self):
        self.assertGreaterEqual(len(preferences.CATALOG), 90)
        self.assertEqual(set(desktop.OPTIONS), set(preferences.BY_NAME))
        for spec in preferences.CATALOG:
            self.assertIn(spec["section"], {"appearance", "windows", "dock", "typography", "workspaces", "privacy", "input", "display"})
            self.assertIn(spec["kind"], {"bool", "choice", "int", "float", "font", "color", "image", "strv"})
            self.assertTrue(spec["title"] and spec["description"])
            self.assertTrue(spec["schema"].startswith("org."))
        with patch.object(desktop, "settings_for", return_value=None):
            self.assertTrue(all(not row["available"] and not row["writable"] for row in desktop.preference_metadata()))

    def test_values_are_typed_bounded_and_support_persian_joining(self):
        cases = [("keyboard-delay", True), ("keyboard-delay", 99), ("mouse-speed", float("nan")),
                 ("mouse-speed", float("inf")), ("text-scale", 10 ** 400), ("night-light-temperature", 999),
                 ("night-light-from", 25), ("focus-mode", "shell"), ("window-close-color", "red;}"),
                 ("cursor-theme", "../../themes"), ("interface-font", "bad\nfont"),
                 ("wallpaper-image", "https://example.com/wall.png"), ("workspace-names", ["bad\x00name"])]
        for name, value in cases:
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                preferences.validate_value(name, value)
        self.assertEqual(preferences.validate_value("workspace-names", "Code; پژوهش‌های من"), ["Code", "پژوهش‌های من"])
        self.assertEqual(preferences.validate_value("window-close-color", "#A1B2C3"), "#a1b2c3")
        self.assertEqual(preferences.validate_value("interface-font", "Livara Persian Semi-Bold 13"), "Livara Persian Semi-Bold 13")


class PresetStoreTests(unittest.TestCase):
    def test_private_crud_and_independent_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = preferences.PresetStore(Path(temporary))
            values = {"accent": "sage", "interface-font": "Livara Persian 12", "workspace-names": ["پژوهش‌های من"]}
            store.save("  فضای من  ", values)
            values["workspace-names"].append("outside")
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.directory.stat().st_mode & 0o777, 0o700)
            listed = store.list()
            self.assertEqual(listed["فضای من"]["workspace-names"], ["پژوهش‌های من"])
            listed["فضای من"]["workspace-names"].append("also outside")
            self.assertEqual(len(store.list()["فضای من"]["workspace-names"]), 1)
            created = json.loads(store.path.read_text())["presets"]["فضای من"]["created_at"]
            store.rename("فضای من", "تمرکز")
            self.assertEqual(json.loads(store.path.read_text())["presets"]["تمرکز"]["created_at"], created)
            store.save("Second", {"appearance": "light"})
            with self.assertRaises(ValueError):
                store.rename("تمرکز", "Second")
            store.delete("تمرکز")
            self.assertEqual(store.list(), {"Second": {"appearance": "light"}})

    def test_invalid_names_values_and_tampered_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = preferences.PresetStore(Path(temporary))
            for name in ("", "../other", "a/b", "a\\b", "bad\nname", "x" * 65):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    store.save(name, {"accent": "purple"})
            for values in ({"command": "sh"}, {"keyboard-delay": -1}, {"mouse-speed": float("nan")}):
                with self.assertRaises(ValueError):
                    store.save("Bad", values)
            store.save("Good", {"accent": "purple"})
            for content in ('{"schema":1,"schema":1,"presets":{}}', '{"schema":1,"presets":{"Bad":{"values":{"command":"sh"},"created_at":"x","updated_at":"x"}}}', "[" * 2000):
                store.path.write_text(content)
                with self.assertRaises(ValueError):
                    store.save("New", {"accent": "sage"})
                self.assertEqual(store.path.read_text(), content)

    def test_symlinks_and_interrupted_atomic_replacement_do_not_touch_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_text("keep me")
            store = preferences.PresetStore(root / "config")
            store.directory.mkdir(parents=True)
            store.path.symlink_to(target)
            with self.assertRaises(ValueError):
                store.save("Test", {"accent": "sage"})
            self.assertEqual(target.read_text(), "keep me")
            store.path.unlink()
            store.save("Before", {"accent": "purple"})
            original = store.path.read_bytes()
            with patch.object(preferences.os, "replace", side_effect=OSError("fixture interrupted")), self.assertRaises(OSError):
                store.save("After", {"accent": "sage"})
            self.assertEqual(store.path.read_bytes(), original)
            self.assertFalse(list(store.directory.glob(".appearance-presets-*")))

    def test_default_snapshot_has_visual_scope_and_preserves_motion_off(self):
        keys = set(desktop.APPEARANCE_PRESET_KEYS)
        self.assertTrue({"interface-font", "window-green-action", "wallpaper-image", "cursor-theme"} <= keys)
        self.assertFalse({"animations", "mouse-left-handed", "touchpad-send-events", "keyboard-repeat", "screen-lock", "notification-banners", "night-light"} & keys)
        with tempfile.TemporaryDirectory() as temporary, patch.object(desktop, "read_option", side_effect=lambda key: {"accent": "sage", "window-button-size": 999}.get(key)):
            desktop.save_custom_preset("Look", config_home=Path(temporary))
            self.assertEqual(desktop.list_custom_presets(config_home=Path(temporary)), {"Look": {"accent": "sage"}})


class DesktopBatchTests(unittest.TestCase):
    class Variant:
        def __init__(self, value): self.value = value
        def unpack(self): return self.value

    class Settings:
        def __init__(self, values, defaults):
            self.values, self.defaults = values, defaults
            self.props = type("Props", (), {"settings_schema": self})()
        def has_key(self, key): return key in self.defaults
        def get_user_value(self, key): return DesktopBatchTests.Variant(self.values[key]) if key in self.values else None
        def get_value(self, key): return DesktopBatchTests.Variant(self.values.get(key, self.defaults[key]))
        def get_default_value(self, key): return DesktopBatchTests.Variant(self.defaults[key])
        def set_value(self, key, value): self.values[key] = value.unpack(); return True
        def reset(self, key): self.values.pop(key, None)

    def fixture(self):
        schemas = {}
        for name in ("accent", "appearance", "wallpaper", "dock-size", "animations", "interface-font", "window-close-color"):
            schema, key = desktop.OPTIONS[name]
            if schema not in schemas:
                schemas[schema] = self.Settings({}, {})
            schemas[schema].defaults[key] = {"accent": "purple", "appearance": "dark", "wallpaper": "glass", "dock-size": 48, "animations": True, "interface-font": "Livara Sans 11", "window-close-color": "#ff5f57"}[name]
        schemas[desktop.OPTIONS["animations"][0]].values["enable-animations"] = False
        def setting(schema): return schemas.get(schema)
        def prepare(schema, key, value): return schemas[schema], self.Variant(value)
        def write(schema, key, value): schemas[schema].values[key] = value
        return schemas, setting, prepare, write

    def test_batch_preserves_reduced_motion_and_applies_wallpaper_last(self):
        schemas, settings, prepare, write = self.fixture()
        order = []
        with patch.object(desktop, "settings_for", side_effect=settings), patch.object(desktop, "prepare_setting", side_effect=prepare), patch.object(desktop, "write_setting", side_effect=write), patch.object(desktop, "apply_palette", side_effect=lambda **kw: order.append("palette")), patch.object(desktop, "validate_wallpaper_image", return_value=Path("/tmp/image.png")), patch.object(desktop, "set_wallpaper_image", side_effect=lambda value: order.append("image")):
            background = self.Settings({}, {"picture-uri": ""})
            schemas["org.gnome.desktop.background"] = background
            result = desktop._apply_options({"accent": "sage", "wallpaper-image": "/tmp/image.png", "animations": True})
        self.assertEqual(order, ["palette", "image"])
        self.assertEqual(result["unavailable"], ["animations"])
        self.assertFalse(schemas[desktop.OPTIONS["animations"][0]].values["enable-animations"])

    def test_write_failure_restores_previous_user_overrides_and_unset_values(self):
        schemas, settings, prepare, _write = self.fixture()
        schemas["org.livara.desktop"].values["accent"] = "blue"
        def write(schema, key, value):
            if key == "font-name": raise ValueError("fixture refuses font")
            schemas[schema].values[key] = value
        with patch.object(desktop, "settings_for", side_effect=settings), patch.object(desktop, "prepare_setting", side_effect=prepare), patch.object(desktop, "write_setting", side_effect=write):
            with self.assertRaisesRegex(ValueError, "previous preferences were restored"):
                desktop._apply_options({"accent": "sage", "interface-font": "Livara Persian 12"})
        self.assertEqual(schemas["org.livara.desktop"].values, {"accent": "blue"})
        self.assertNotIn("font-name", schemas[desktop.OPTIONS["interface-font"][0]].values)

    def test_reset_is_limited_to_named_preferences(self):
        schemas, settings, prepare, _write = self.fixture()
        schemas["org.livara.desktop"].values.update(accent="sage", appearance="light")
        with patch.object(desktop, "settings_for", side_effect=settings), patch.object(desktop, "prepare_setting", side_effect=prepare), patch.object(desktop, "apply_palette"):
            desktop.reset_options(["accent"])
        self.assertEqual(schemas["org.livara.desktop"].values, {"appearance": "light"})
        self.assertFalse(schemas[desktop.OPTIONS["animations"][0]].values["enable-animations"])

    def test_dock_fixed_mode_tracks_both_hiding_preferences(self):
        schemas, settings, prepare, write = self.fixture()
        schema = "org.gnome.shell.extensions.dash-to-dock"
        dock = schemas[schema]
        dock.defaults.update({"autohide": False, "intellihide": False, "dock-fixed": True})
        with patch.object(desktop, "settings_for", side_effect=settings), patch.object(desktop, "prepare_setting", side_effect=prepare), patch.object(desktop, "write_setting", side_effect=write):
            desktop.set_option("dock-autohide", True)
            self.assertFalse(dock.values["dock-fixed"])
            desktop.set_option("dock-intellihide", True)
            desktop.set_option("dock-autohide", False)
            self.assertFalse(dock.values["dock-fixed"])
            desktop.set_option("dock-intellihide", False)
            self.assertTrue(dock.values["dock-fixed"])
            desktop._apply_options({"dock-autohide": False, "dock-intellihide": True})
            self.assertFalse(dock.values["dock-fixed"])
            desktop.reset_options(["dock-autohide", "dock-intellihide"])
            self.assertTrue(dock.values["dock-fixed"])

    def test_failed_preset_restores_derived_dock_mode_and_original_user_state(self):
        schemas, settings, prepare, write = self.fixture()
        dock = schemas["org.gnome.shell.extensions.dash-to-dock"]
        dock.defaults.update({"autohide": False, "intellihide": False, "dock-fixed": True})
        dock.values.update({"autohide": False, "dock-fixed": True})
        original = dict(dock.values)
        with patch.object(desktop, "settings_for", side_effect=settings), patch.object(desktop, "prepare_setting", side_effect=prepare), patch.object(desktop, "write_setting", side_effect=write), patch.object(desktop, "apply_palette", side_effect=ValueError("fixture palette failure")):
            with self.assertRaisesRegex(ValueError, "previous preferences were restored"):
                desktop._apply_options({"dock-autohide": True, "appearance": "light"})
        self.assertEqual(dock.values, original)
        self.assertNotIn("intellihide", dock.values)


class WallpaperTests(unittest.TestCase):
    PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXioAAAAASUVORK5CYII=")

    def test_local_images_and_file_uris_validate_without_downloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "My wallpaper.png"
            path.write_bytes(self.PNG)
            self.assertEqual(desktop.validate_wallpaper_image(str(path)), path)
            self.assertEqual(desktop.validate_wallpaper_image(path.as_uri()), path)
            self.assertEqual(desktop._local_wallpaper_path(path.as_uri()), str(path))
            for value in ("https://example.com/picture.png", "file://remote/path.png", str(path.parent), str(path) + ".missing"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    desktop.validate_wallpaper_image(value)
            path.write_text("not an image")
            with self.assertRaises(ValueError): desktop.validate_wallpaper_image(str(path))

    def test_palette_change_preserves_custom_background(self):
        with patch.object(desktop, "read_option", side_effect=lambda key: {"accent": "sage", "appearance": "dark", "wallpaper": "glass"}[key]), patch.object(desktop, "write_setting") as write, patch.object(desktop, "set_wallpaper_image") as image:
            desktop.apply_palette()
        self.assertEqual(write.call_count, 3)
        image.assert_not_called()


if __name__ == "__main__":
    unittest.main()

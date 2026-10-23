"""Icon overrides preserve launcher semantics, updates and user-owned files."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from livara.app_icons import App, IconManager, desktop_id, replace_icon, search_apps, render_icon, _local_resource

DESKTOP = b'''[Desktop Entry]\nType=Application\nName=Files\nName[fa]=Files Persian\nExec=files --new-window %U\nDBusActivatable=true\nStartupWMClass=Files\nIcon=old-files\nIcon[fa]=old-local\nActions=New;\n\n[Desktop Action New]\nName=New window\nExec=files --new-window\nIcon=action-icon\n'''
PNG = b"\x89PNG\r\n\x1a\nexample-test-bytes"


class AppIconTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "system.desktop";self.source.write_bytes(DESKTOP)
        self.manager = IconManager(self.base / "user")
        self.app = App("org.livara.Settings.desktop", "Settings", str(self.source))
        self.cache = patch.object(self.manager, "refresh_cache");self.cache.start();self.addCleanup(self.cache.stop)

    def apply(self, png=PNG):
        return self.manager.apply(self.app, self.base / "chosen.png", renderer=lambda path: png)

    def test_changes_only_main_icon_including_localized_icons(self):
        result = replace_icon(DESKTOP, "/home/user/My icons/a.png")
        self.assertIn(b"Icon=/home/user/My icons/a.png\n", result)
        self.assertNotIn(b"Icon[fa]", result)
        self.assertIn(b"Icon=action-icon", result)
        for line in (b"Exec=files --new-window %U", b"DBusActivatable=true", b"StartupWMClass=Files", b"Name[fa]=Files Persian", b"Actions=New;"):
            self.assertIn(line, result)

    def test_icon_insert_and_crlf_and_duplicate_main_section(self):
        self.assertIn(b"Icon=x\r\n[Desktop Action", replace_icon(b"[Desktop Entry]\r\nName=X\r\n[Desktop Action A]\r\nIcon=action\r\n", "x"))
        self.assertTrue(replace_icon(b"[Desktop Entry]\nName=X", "x").endswith(b"\nIcon=x\n"))
        with self.assertRaises(ValueError): replace_icon(b"[Desktop Entry]\n[Desktop Entry]\n", "x")

    def test_default_app_override_restores_upstream_and_preserves_commands(self):
        asset = self.apply();target, folder, state = self.manager.paths(self.app.id)
        self.assertEqual(asset.read_bytes(), PNG)
        self.assertEqual(self.source.read_bytes(), DESKTOP)
        self.assertIn(b"Exec=files --new-window %U", target.read_bytes())
        self.assertTrue(self.manager.customized(self.app.id))
        self.assertEqual(state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertTrue(self.manager.restore(self.app.id))
        self.assertFalse(target.exists());self.assertFalse(self.manager.customized(self.app.id))
        self.assertFalse(self.manager.restore(self.app.id))

    def test_original_user_override_is_restored_byte_for_byte(self):
        target, _, _ = self.manager.paths(self.app.id);target.parent.mkdir(parents=True)
        custom = DESKTOP.replace(b"files --new-window %U", b"files --my-options %U")
        target.write_bytes(custom)
        self.apply();self.apply(PNG + b"new")
        self.manager.restore(self.app.id)
        self.assertEqual(target.read_bytes(), custom)

    def test_reapply_uses_updated_system_launcher_and_unique_asset_path(self):
        first = self.apply()
        changed = DESKTOP.replace(b"files --new-window %U", b"new-files --updated %U")
        self.source.write_bytes(changed)
        second = self.apply(PNG + b"new image")
        self.assertNotEqual(first, second);self.assertFalse(first.exists())
        self.assertIn(b"new-files --updated %U", self.manager.paths(self.app.id)[0].read_bytes())

    def test_external_edits_are_not_overwritten_or_restored(self):
        self.apply();target, _, _ = self.manager.paths(self.app.id)
        data = target.read_bytes() + b"# important user change\n";target.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "edited outside"): self.apply()
        with self.assertRaisesRegex(ValueError, "edited outside"): self.manager.restore(self.app.id)
        self.assertEqual(target.read_bytes(), data)

    def test_unsafe_ids_and_links_never_replace_other_files(self):
        for name in ("../../x.desktop", "/tmp/x.desktop", "x\\evil.desktop", "x\nIcon=x.desktop", ".desktop"):
            with self.assertRaises(ValueError): desktop_id(name)
        self.assertEqual(desktop_id("ماشین حساب.desktop"), "ماشین حساب.desktop")
        target, _, _ = self.manager.paths(self.app.id);target.parent.mkdir(parents=True)
        other = self.base / "other";other.write_bytes(DESKTOP);target.symlink_to(other)
        with self.assertRaises(OSError): self.apply()
        self.assertEqual(other.read_bytes(), DESKTOP)

    def test_write_failure_rolls_back_previous_launcher_and_state(self):
        self.apply();target, _, state = self.manager.paths(self.app.id)
        before, record = target.read_bytes(), state.read_bytes()
        real = self.manager._atomic
        def fail_once(path, data, mode=0o600):
            if path == target and data != before: raise OSError("simulated full disk")
            return real(path, data, mode)
        with patch.object(self.manager, "_atomic", side_effect=fail_once):
            with self.assertRaises(OSError): self.apply(PNG + b"different")
        self.assertEqual(target.read_bytes(), before);self.assertEqual(state.read_bytes(), record)

    def test_corrupt_state_is_preserved(self):
        self.apply();_, _, state = self.manager.paths(self.app.id)
        state.write_text('{"bad":true}')
        with self.assertRaises(ValueError): self.manager.restore(self.app.id)
        self.assertEqual(state.read_text(), '{"bad":true}')

    def test_pending_apply_or_restore_can_be_recovered(self):
        self.apply();target, _, state = self.manager.paths(self.app.id)
        record = json.loads(state.read_bytes());record["desktop_hashes"].append(None)
        state.write_text(json.dumps(record));target.unlink()
        self.assertTrue(self.manager.restore(self.app.id))

    def test_search_unicode_and_hidden_launchers(self):
        apps = [self.app, App("x.desktop", "ماشین حساب", "x", visible=False)]
        self.assertEqual(search_apps(apps, "settings livara"), [self.app])
        self.assertEqual(search_apps(apps, "ماشین"), [])
        self.assertEqual(search_apps(apps, "ماشین", include_hidden=True), [apps[1]])

    def test_external_svg_is_rejected_before_loading_gi(self):
        for data in (b'<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/passwd"/></svg>',
                     b'<!DOCTYPE svg><svg/>',b'<svg><style>@import "https://example.com/a.css";</style></svg>',
                     b'<svg><path fill="url(https://example.com/a.svg)"/></svg>',b'\x1f\x8bcompressed-svg'):
            file = self.base / "icon.png";file.write_bytes(data)
            with self.assertRaises(ValueError): render_icon(file)

    def test_inline_raster_svg_resources_are_self_contained(self):
        self.assertTrue(_local_resource("#gradient"))
        self.assertTrue(_local_resource("data:image/png;base64," + base64.b64encode(PNG).decode()))
        for value in ("file:///tmp/icon.png", "https://example.com/a.png", "data:image/svg+xml;base64,PHN2Zy8+", "data:text/html;base64,eA==", "data:image/png;base64,!!!!"):
            self.assertFalse(_local_resource(value))

    def test_flatpak_snap_and_dbus_commands_remain_exact(self):
        for command in (b'flatpak run --branch=stable --command=app org.example.App @@u %U @@', b'env BAMF_DESKTOP_FILE_HINT=/var/lib/snapd/desktop/applications/app.desktop /snap/bin/app %U'):
            before = DESKTOP.replace(b"files --new-window %U", command)
            after = replace_icon(before, "/home/user/icon.png")
            self.assertIn(b"Exec=" + command, after)
            self.assertIn(b"DBusActivatable=true", after)


if __name__ == "__main__": unittest.main()

import base64
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from livara import studio


class StudioTools(unittest.TestCase):
    def run_json(self, name, text, option=""):
        return json.loads(studio.run_tool(name, text, option))

    def test_registry_has_distinct_reachable_tools(self):
        identifiers = [tool["id"] for tool in studio.TOOLS]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertGreaterEqual(len(identifiers), 21)
        for tool in studio.TOOLS:
            if tool["input_kind"] == "text" and tool["id"] != "jwt":
                with self.subTest(tool=tool["id"]):
                    self.assertIsInstance(studio.run_tool(tool["id"], tool["sample"], tool["option_default"]), str)

    def test_unicode_reports_codepoints_not_invented_grapheme_count(self):
        report = self.run_json("unicode", "e\u0301 👋")
        self.assertEqual(report["code_points"], 4)
        self.assertEqual(report["utf8_bytes"], 8)
        self.assertFalse(report["normalized_nfc"])
        self.assertEqual(report["first_128_unique_characters"][1]["code_point"], "U+0301")

    def test_encoding_roundtrips_and_invalid_data(self):
        value = "Livara / café 👋"
        for tool in ("base64", "html", "urlencode"):
            encoded = studio.run_tool(tool, value, "encode")
            self.assertEqual(studio.run_tool(tool, encoded, "decode"), value)
        for tool, value in (("base64", "not*base64"), ("urlencode", "%GG"), ("base64", "/w==")):
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                studio.run_tool(tool, value, "decode")

    def test_text_cleanup_and_diff(self):
        self.assertEqual(studio.run_tool("cleanup", " z \na\nz\n\n", "trim,nonempty,deduplicate,sort"), "a\nz")
        diff = studio.run_tool("diff", "same\nbefore\n", "same\nafter\n")
        self.assertIn("-before", diff)
        self.assertIn("+after", diff)

    def test_strict_json_toml_and_csv(self):
        self.assertEqual(self.run_json("json", '{"b":2,"a":1}'), {"a": 1, "b": 2})
        for value in ('{"value":NaN}', '{"x":Infinity}', '{"x":1e999}'):
            with self.assertRaises(ValueError):
                studio.run_tool("json", value)
        self.assertEqual(self.run_json("toml", '[project]\nname="Livara"')["project"]["name"], "Livara")
        rows = self.run_json("csv", 'name,note\nLivara,"a,b"\n', "to-json")
        self.assertEqual(rows, [{"name": "Livara", "note": "a,b"}])
        csv_text = studio.run_tool("csv", json.dumps(rows), "from-json")
        self.assertEqual(self.run_json("csv", csv_text, "to-json"), rows)
        for value in ("name,name\na,b", "name,note\nonefield"):
            with self.assertRaises(ValueError):
                studio.run_tool("csv", value, "to-json")
        with self.assertRaises(ValueError):
            studio.run_tool("csv", '[{"nested":{}}]', "from-json")

    def test_jwt_is_explicitly_unverified(self):
        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
        token = encode({"alg": "none"}) + "." + encode({"sub": "research"}) + "."
        result = self.run_json("jwt", token)
        self.assertFalse(result["signature_verified"])
        self.assertEqual(result["payload"]["sub"], "research")
        with self.assertRaises(ValueError):
            studio.run_tool("jwt", "a.b")

    def test_regex_is_bounded_and_isolated(self):
        result = self.run_json("regex", "case 42 and 17", r"\d+")
        self.assertEqual([match["match"] for match in result["matches"]], ["42", "17"])
        with self.assertRaises(ValueError):
            studio.run_tool("regex", "text", "[")
        with self.assertRaisesRegex(ValueError, "time limit|resource limit"):
            studio.run_tool("regex", "a" * 4000 + "!", r"^(a+)+$")
        with self.assertRaises(ValueError):
            studio.run_tool("regex", "a" * 20001, "a")

    def test_calculator_does_not_execute_python_and_limits_cost(self):
        self.assertEqual(studio.run_tool("calculator", "sqrt(144) + 2**8"), "268.0")
        for expression in ("__import__('os').getcwd()", "(1).__class__", "[1,2]", "True", "2**999999", "1e999", "round(1, ndigits=2)"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                studio.run_tool("calculator", expression)
        self.assertAlmostEqual(float(studio.run_tool("calculator", "sin(pi/2)")), 1)

    def test_generators_and_conversion_validation(self):
        password = studio.run_tool("password", "32", "letters").splitlines()[0]
        self.assertEqual(len(password), 32)
        self.assertTrue(password.isascii() and password.isalpha())
        identifiers = studio.run_tool("uuid", "5").splitlines()
        self.assertEqual(len(set(identifiers)), 5)
        self.assertIn("= 32 F", studio.run_tool("units", "0", "C -> F"))
        self.assertIn("= 1024 MiB", studio.run_tool("units", "1", "GiB -> MiB"))
        for name, text, option in (("password", "7", "all"), ("uuid", "1000", ""), ("units", "-1", "K -> C"), ("units", "nan", "m -> km"), ("units", "1", "kg -> m")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                studio.run_tool(name, text, option)

    def test_time_network_and_domain_tools_are_local_calculations(self):
        time = self.run_json("time", "1970-01-01T00:00:00")
        self.assertEqual(time["unix_seconds"], 0)
        self.assertEqual(self.run_json("time", "0")["utc"], "1970-01-01T00:00:00+00:00")
        subnet = self.run_json("subnet", "192.168.1.17/24")
        self.assertEqual(subnet["network"], "192.168.1.0/24")
        self.assertEqual(subnet["last_host"], "192.168.1.254")
        subnet6 = self.run_json("subnet", "2001:db8::/64")
        self.assertEqual(subnet6["address_count"], 2**64)
        url = self.run_json("urlparts", "https://user:secret@example.org:8443/path?a=1&a=2")
        self.assertEqual(url["port"], 8443)
        self.assertNotIn("secret", json.dumps(url))
        self.assertEqual(url["query_fields"], [["a", "1"], ["a", "2"]])
        self.assertEqual(self.run_json("idna", "münich.example")["ascii"], "xn--mnich-kva.example")

    def test_colors_and_contrast_follow_srgb_formula(self):
        self.assertEqual(self.run_json("color", "#abc")["rgb"], [170, 187, 204])
        contrast = self.run_json("contrast", "#000000 #ffffff")
        self.assertEqual(contrast["ratio"], 21)
        self.assertTrue(contrast["AAA_normal_text"])
        with self.assertRaises(ValueError):
            studio.run_tool("color", "rgb(256,0,0)")

    def test_tool_limits_and_unknown_identifier(self):
        with self.assertRaises(ValueError):
            studio.run_tool("not-a-tool", "")
        with self.assertRaises(ValueError):
            studio.run_tool("unicode", "a" * (studio.MAX_TEXT + 1))


class StudioFiles(unittest.TestCase):
    def test_inventory_duplicates_metadata_and_tail_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.txt").write_text("same content\n")
            (root / "second.txt").write_text("same content\n")
            (root / "other.log").write_text("one\ntwo\nthree\n")
            (root / "linked.txt").symlink_to(root / "first.txt")
            before = {path.name: path.lstat().st_mtime_ns for path in root.iterdir()}
            report = json.loads(studio.run_tool("inventory", str(root)))
            self.assertEqual(report["regular_files"], 3)
            self.assertEqual(report["symlinks_and_special_files_skipped"], 1)
            duplicate = json.loads(studio.run_tool("duplicates", str(root)))
            self.assertEqual(duplicate["duplicate_groups"][0]["paths"], ["first.txt", "second.txt"])
            metadata = json.loads(studio.run_tool("fileinfo", str(root / "first.txt")))
            self.assertEqual(metadata["bytes"], 13)
            self.assertIn("metadata_changed_utc", metadata)
            self.assertEqual(studio.run_tool("logtail", str(root / "other.log"), "2"), "two\nthree")
            self.assertEqual(before, {path.name: path.lstat().st_mtime_ns for path in root.iterdir()})
            with self.assertRaises(ValueError):
                studio.run_tool("fileinfo", str(root / "linked.txt"))

    def test_scans_fail_explicitly_at_resource_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a", "b"):
                (root / name).write_bytes(b"12345")
            with patch.object(studio, "MAX_FILES", 1), self.assertRaisesRegex(ValueError, "file limit"):
                studio.run_tool("inventory", str(root))
            with patch.object(studio, "MAX_SCAN_BYTES", 5), self.assertRaisesRegex(ValueError, "read budget"):
                studio.run_tool("duplicates", str(root))

    def test_file_paths_keep_literal_spaces_and_shell_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / " report ; $(literal) .log "
            path.write_text("ordinary text\n")
            self.assertEqual(studio.run_tool("logtail", str(path), "1"), "ordinary text")
            self.assertEqual(json.loads(studio.run_tool("fileinfo", str(path)))["bytes"], 14)


class StudioPrivateStorage(unittest.TestCase):
    def test_notes_private_create_update_search_archive_and_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            store = studio.NoteStore(Path(directory) / "notes")
            identifier = store.save("Research", "A private observation")
            self.assertEqual(stat.S_IMODE(store.root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((store.root / (identifier + ".json")).stat().st_mode), 0o600)
            self.assertEqual(store.list_notes("OBSERVATION")[0]["id"], identifier)
            store.save("Updated", "New notes", identifier)
            self.assertEqual(store.read(identifier)["title"], "Updated")
            store.archive(identifier)
            self.assertEqual(store.list_notes(), [])
            self.assertTrue((store.root / "archive" / (identifier + ".json")).exists())
            store.restore(identifier)
            self.assertEqual(store.read(identifier)["body"], "New notes")
            for value in ("../outside", "a/b", "", "a" * 31):
                with self.assertRaises(ValueError):
                    store.read(value)

    def test_note_symlinks_and_oversized_records_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = studio.NoteStore(root / "notes")
            identifier = "a" * 32
            (store.root / (identifier + ".json")).symlink_to(root / "outside")
            with self.assertRaises(ValueError):
                store.save("Title", "body", identifier)
            with self.assertRaises(ValueError):
                store.save("Title", "👋" * 100000)

    def test_focus_history_private_and_validated(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_DATA_HOME": directory}):
            self.assertEqual(studio.focus_history(), [])
            studio.record_focus(60, "Read notes")
            studio.record_focus(120, "Review")
            history = studio.focus_history(1)
            self.assertEqual(history[0]["label"], "Review")
            path = studio.studio_directory() / "focus.jsonl"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(ValueError):
                studio.record_focus(True, "No")
            with self.assertRaises(ValueError):
                studio.record_focus(0, "No")


if __name__ == "__main__":
    unittest.main()

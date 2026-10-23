import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from livara.web import BookmarkStore, browser_paths, ensure_new_destination, normalize_address, safe_download_name


class Addresses(unittest.TestCase):
    def test_addresses_search_and_local_sites(self):
        self.assertEqual(normalize_address("example.com/a b"), "https://duckduckgo.com/?q=example.com%2Fa+b")
        self.assertEqual(normalize_address("example.com:8080/test"), "https://example.com:8080/test")
        self.assertEqual(normalize_address("localhost:8080/test"), "http://localhost:8080/test")
        self.assertEqual(normalize_address("[::1]:8080/a"), "http://[::1]:8080/a")
        self.assertEqual(normalize_address("HTTPS://EXAMPLE.COM/a?q=1"), "https://example.com/a?q=1")
        self.assertEqual(normalize_address("hello & world"), "https://duckduckgo.com/?q=hello+%26+world")
        self.assertEqual(normalize_address("münich.example"), "https://xn--mnich-kva.example")
        self.assertEqual(normalize_address(""), "about:blank")

    def test_unsafe_protocols_and_credentials_rejected(self):
        for value in ("javascript:alert(1)", "data:text/html,hello", "file:///etc/passwd", "ftp://example.com", "javascript :alert(1)", "https://user:pass@example.com", "https://example.com:99999", "https://example.com/\nsecret"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_address(value)

    def test_download_names_and_overwrite_protection(self):
        self.assertEqual(safe_download_name("../../report.txt"), "report.txt")
        self.assertEqual(safe_download_name(r"C:\secret\report.pdf"), "report.pdf")
        self.assertEqual(safe_download_name(".."), "download")
        self.assertEqual(safe_download_name("CON.txt"), "_CON.txt")
        self.assertNotIn("\n", safe_download_name("a\nb.txt"))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "new.txt"
            self.assertEqual(ensure_new_destination(path), path)
            path.write_text("existing")
            with self.assertRaises(ValueError):
                ensure_new_destination(path)


class Bookmarks(unittest.TestCase):
    def test_atomic_private_storage_and_deduplication(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private/bookmarks.json"
            store = BookmarkStore(path)
            store.add("First", "https://example.com")
            store.add("Renamed", "https://example.com")
            self.assertEqual(store.list(), [{"title": "Renamed", "url": "https://example.com"}])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            store.remove("https://example.com")
            self.assertEqual(store.list(), [])

    def test_malformed_or_unsafe_records_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bookmarks.json"
            original = json.dumps({"schema": 1, "bookmarks": [{"title": "Bad", "url": "javascript:alert(1)"}]})
            path.write_text(original)
            with self.assertRaises(ValueError):
                BookmarkStore(path).add("Good", "https://example.com")
            self.assertEqual(path.read_text(), original)
            path.write_text("not json")
            with self.assertRaises(ValueError):
                BookmarkStore(path).list()
            self.assertEqual(path.read_text(), "not json")

    def test_chat_and_browser_profiles_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"XDG_DATA_HOME": temporary + "/data", "XDG_CACHE_HOME": temporary + "/cache"}):
            browser = browser_paths()
            chat = browser_paths(chat=True)
            self.assertNotEqual(browser, chat)
            self.assertEqual(browser[0].stat().st_mode & 0o777, 0o700)
            self.assertTrue(chat[0].name == "chat")

from __future__ import annotations

import unittest

from livara.settings_ui import catalog_sections, matching_preferences, search_text


class SettingsSearch(unittest.TestCase):
    def setUp(self):
        self.catalog = [
            {"name": "interface-font", "title": "Interface font", "description": "Choose a family and size", "section": "typography", "keywords": ["text", "readability"]},
            {"name": "dock-size", "title": "Dock icon size", "description": "Make space for your apps", "section": "dock"},
            {"name": "window-close-color", "title": "Close color", "description": "Traffic-light palette", "section": "windows"},
            {"name": "wallpaper-image", "title": "Your wallpaper", "description": "Choose a photo", "section": "appearance"},
            {"name": "custom-accent", "title": "Café accent", "description": "Color", "section": "appearance"},
        ]

    def test_empty_search_preserves_stable_catalog_order(self):
        self.assertEqual(matching_preferences(self.catalog, " \t "), self.catalog)
        self.assertEqual(matching_preferences(self.catalog, "", "dock"), [self.catalog[1]])

    def test_search_matches_all_words_across_metadata_and_category(self):
        self.assertEqual(matching_preferences(self.catalog, "TEXT family"), [self.catalog[0]])
        self.assertEqual(matching_preferences(self.catalog, "type size"), [self.catalog[0]])
        self.assertEqual(matching_preferences(self.catalog, "dock size"), [self.catalog[1]])
        self.assertEqual(matching_preferences(self.catalog, "color windows"), [self.catalog[2]])
        self.assertEqual(matching_preferences(self.catalog, "photo"), [self.catalog[3]])

    def test_unicode_and_regex_characters_are_literal_search_data(self):
        self.assertEqual(search_text("ＣＡＦÉ"), "cafe")
        self.assertEqual(matching_preferences(self.catalog, "cafe"), [self.catalog[4]])
        self.assertEqual(matching_preferences(self.catalog, ".*"), [])
        self.assertEqual(matching_preferences(self.catalog, "[font]"), [])
        self.assertEqual(matching_preferences(self.catalog, "nothing matches"), [])

    def test_unknown_sections_are_preserved_after_primary_sections(self):
        catalog = self.catalog + [{"name": "future", "section": "future-device"}]
        self.assertEqual(catalog_sections(catalog), ["appearance", "windows", "dock", "typography", "future-device"])
        self.assertEqual(catalog_sections([]), [])

    def test_search_does_not_mutate_canonical_metadata(self):
        snapshot = [dict(item) for item in self.catalog]
        matching_preferences(self.catalog, "color")
        self.assertEqual(self.catalog, snapshot)


if __name__ == "__main__":
    unittest.main()

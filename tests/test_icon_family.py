"""Launcher icons must resolve to distinct self-contained vector artwork."""
import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("app_icon_builder", ROOT / "scripts/build-app-icons.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class IconFamily(unittest.TestCase):
    def test_every_livara_launcher_has_its_own_icon(self):
        seen = set()
        for path in (ROOT / "share/applications").glob("org.livara.*.desktop"):
            value = next(line[5:] for line in path.read_text().splitlines() if line.startswith("Icon="))
            self.assertTrue(value.startswith("org.livara."), path.name)
            self.assertNotIn(value, seen, path.name)
            seen.add(value)
            self.assertTrue((ROOT / "artwork" / (value + ".svg")).is_file(), value)
        self.assertEqual(len(seen), 13)

    def test_vectors_are_reproducible_accessible_and_self_contained(self):
        geometries = set()
        for name, (accent, tint, title, geometry) in builder.ICONS.items():
            path = ROOT / "artwork" / f"org.livara.{name}.svg"
            self.assertEqual(path.read_text(), builder.render(name, accent, tint, title, geometry))
            root = ET.fromstring(path.read_text())
            self.assertEqual(root.get("viewBox"), "0 0 256 256")
            self.assertEqual(root.find("{http://www.w3.org/2000/svg}title").text, title)
            self.assertNotIn("data:", path.read_text())
            for element in root.iter():
                self.assertNotIn("href", element.attrib)
            self.assertNotIn(geometry, geometries)
            geometries.add(geometry)


if __name__ == "__main__":
    unittest.main()

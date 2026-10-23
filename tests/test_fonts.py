"""The original Livara fonts remain editable, valid and predictable to rebuild."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

try:
    from fontTools.ttLib import TTFont
except ImportError:
    TTFont = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(TTFont is None, "Install python3-fonttools to validate editable Livara fonts")
class LivaraFonts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("livara_font_builder", ROOT / "scripts/build-fonts.py")
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def face(self, family="Sans", style="Regular"):
        return TTFont(ROOT / "fonts/ttf" / f"Livara{family}-{style}.ttf", checkChecksums=2)

    def test_names_licenses_and_complete_latin_coverage(self):
        required = set(range(32, 127)) | set(range(160, 256))
        for family in ("Sans", "Mono"):
            for style, weight in (("Regular", 400), ("SemiBold", 600)):
                with self.face(family, style) as font:
                    self.assertEqual(font["name"].getDebugName(16), "Livara " + family)
                    self.assertEqual(font["name"].getDebugName(17), style)
                    self.assertEqual(font["OS/2"].usWeightClass, weight)
                    self.assertEqual(font["OS/2"].fsType, 0)
                    self.assertIn("SIL Open Font License", font["name"].getDebugName(13))
                    self.assertTrue(required.issubset(font.getBestCmap()))
                    self.assertIn(0x20AC, font.getBestCmap())
                    self.assertGreaterEqual(len(font.getBestCmap()), 204)
                    self.assertNotIn(".notdef", {font.getBestCmap()[point] for point in required})

    def test_mono_is_fixed_pitch_and_sans_is_proportional(self):
        with self.face("Mono") as font:
            self.assertEqual({advance for advance, _ in font["hmtx"].metrics.values()}, {650})
            self.assertTrue(font["post"].isFixedPitch)
            self.assertNotIn("GPOS", font)
        with self.face() as font:
            self.assertGreater(len({advance for advance, _ in font["hmtx"].metrics.values()}), 12)
            self.assertFalse(font["post"].isFixedPitch)
            self.assertIn("GPOS", font)

    def test_semibold_uses_distinct_larger_outlines(self):
        with self.face() as regular, self.face(style="SemiBold") as semibold:
            self.assertEqual(regular["hmtx"].metrics["A"][0], semibold["hmtx"].metrics["A"][0])
            self.assertLess(semibold["glyf"]["A"].xMin, regular["glyf"]["A"].xMin)
            self.assertGreater(semibold["glyf"]["A"].xMax, regular["glyf"]["A"].xMax)
            self.assertNotEqual(regular["glyf"]["A"].coordinates, semibold["glyf"]["A"].coordinates)

    def test_round_counters_and_accent_descenders_are_real_outlines(self):
        with self.face() as font:
            letter = font["glyf"]["o"]
            self.assertEqual(letter.numberOfContours, 2)
            points, ends, _flags = letter.getCoordinates(font["glyf"])
            areas = []
            start = 0
            for end in ends:
                contour = points[start:end + 1]
                areas.append(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(contour, [*contour[1:], contour[0]])))
                start = end + 1
            self.assertLess(areas[0] * areas[1], 0, "The inner counter must wind opposite the outer outline")
            cmap = font.getBestCmap()
            self.assertGreater(font["glyf"][cmap[ord("Á")]].yMax, font["glyf"]["A"].yMax)
            self.assertLess(font["glyf"][cmap[ord("ç")]].yMin, -100)

    def test_rebuilding_ufo_is_byte_reproducible(self):
        source = ROOT / "fonts/sources/LivaraSans-Regular.ufo"
        committed = ROOT / "fonts/ttf/LivaraSans-Regular.ttf"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "roundtrip.ttf"
            self.builder.compile_ufo(source, output)
            self.assertEqual(output.read_bytes(), committed.read_bytes())

    def test_manual_ufo_edits_enter_font_and_remain_in_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            source = temporary / "Editable.ufo"
            shutil.copytree(ROOT / "fonts/sources/LivaraSans-Regular.ufo", source)
            from fontTools.ufoLib import UFOReader
            reader = UFOReader(source)
            glyphset = reader.getGlyphSet()
            filename = glyphset.contents["A"]
            reader.close()
            glif = source / "glyphs" / filename
            tree = ET.parse(glif)
            tree.getroot().find("advance").set("width", "675")
            first_point = tree.getroot().find("outline/contour/point")
            first_point.set("x", str(float(first_point.get("x")) + 12))
            tree.write(glif, encoding="UTF-8", xml_declaration=True)
            before = hashlib.sha256(glif.read_bytes()).hexdigest()
            output = temporary / "edited.ttf"
            self.builder.compile_ufo(source, output)
            self.assertEqual(hashlib.sha256(glif.read_bytes()).hexdigest(), before)
            with TTFont(output) as font:
                self.assertEqual(font["hmtx"].metrics["A"][0], 675)
                with self.face() as original:
                    self.assertNotEqual(font["glyf"]["A"].coordinates, original["glyf"]["A"].coordinates)


@unittest.skipIf(TTFont is None, "Install python3-fonttools to validate Livara Persian")
class LivaraPersianFonts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("livara_persian_builder", ROOT / "scripts/build-fonts.py")
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def test_pinned_sources_copyright_and_retained_shaping(self):
        self.builder.verify_vazirmatn_sources(ROOT / "fonts")
        required = {ord(c) for c in "زبان فارسی عربی پ چ ژ گ ک ی ۰۱۲۳۴۵۶۷۸۹ َُِّْ"}
        with TTFont(ROOT / "fonts/vendor/vazirmatn/Vazirmatn-Variable.ttf") as original:
            copyright_notice = original["name"].getDebugName(0)
            for style, weight in (("Regular", 400), ("SemiBold", 600)):
                with TTFont(ROOT / "fonts/ttf" / f"LivaraPersian-{style}.ttf", checkChecksums=2) as font:
                    self.assertEqual(font["name"].getDebugName(16), "Livara Persian")
                    self.assertEqual(font["name"].getDebugName(0), copyright_notice)
                    self.assertIn("SIL Open Font License", font["name"].getDebugName(13))
                    self.assertEqual(font["OS/2"].usWeightClass, weight)
                    self.assertTrue(required.issubset(font.getBestCmap()))
                    self.assertGreaterEqual(font["maxp"].numGlyphs, 1333)
                    self.assertGreaterEqual(len(font["GSUB"].table.LookupList.Lookup), 37)
                    self.assertGreaterEqual(len(font["GPOS"].table.LookupList.Lookup), 18)
                    cmap = font.getBestCmap()
                    self.assertNotEqual(cmap[0x06CC], cmap[0x064A], "Persian Yeh and Arabic Yeh must remain distinct")
                    self.assertNotEqual(cmap[0x06A9], cmap[0x0643], "Persian Kaf and Arabic Kaf must remain distinct")

    def test_editable_persian_ttx_roundtrip_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "persian.ttf"
            self.builder.compile_persian(ROOT / "fonts/sources/LivaraPersian-Regular.ttx", output)
            self.assertEqual(output.read_bytes(), (ROOT / "fonts/ttf/LivaraPersian-Regular.ttf").read_bytes())

    def shape(self, filename, text):
        try:
            import uharfbuzz as hb
        except ImportError:
            hb = None
        if hb is not None:
            face = hb.Face(Path(filename).read_bytes())
            font = hb.Font(face)
            buffer = hb.Buffer()
            buffer.add_str(text)
            buffer.direction, buffer.script, buffer.language = "rtl", "arab", "fa"
            hb.shape(font, buffer)
            return [{"g": info.codepoint, "ax": position.x_advance, "dx": position.x_offset, "dy": position.y_offset} for info, position in zip(buffer.glyph_infos, buffer.glyph_positions)]
        executable = shutil.which("hb-shape")
        if executable:
            import json
            import subprocess
            result = subprocess.run([executable, str(filename), text, "--direction=rtl", "--script=arab", "--language=fa", "--no-glyph-names", "--output-format=json"], capture_output=True, text=True, check=True, timeout=10)
            return json.loads(result.stdout)
        self.skipTest("Actual RTL shaping requires uharfbuzz or libharfbuzz-bin (hb-shape)")

    def test_harfbuzz_persian_joining_ligatures_zwnj_and_marks(self):
        for style in ("Regular", "SemiBold"):
            filename = ROOT / "fonts/ttf" / f"LivaraPersian-{style}.ttf"
            with TTFont(filename) as font:
                cmap = font.getBestCmap()
                nominal = [font.getGlyphID(cmap[ord(c)]) for c in reversed("فارسی")]
            joined = self.shape(filename, "فارسی")
            self.assertTrue(joined)
            self.assertNotIn(0, [entry["g"] for entry in joined], "A Persian sample must not contain .notdef")
            self.assertNotEqual([entry["g"] for entry in joined], nominal, "Arabic contextual GSUB substitutions must execute")
            self.assertEqual(len(self.shape(filename, "لا")), 1, "Lam-Alef ligature must shape")
            connected = [entry["g"] for entry in self.shape(filename, "میروم") if entry["ax"]]
            separated = [entry["g"] for entry in self.shape(filename, "می\u200cروم") if entry["ax"]]
            self.assertNotEqual(connected, separated, "ZWNJ must prevent joining at the requested position")
            marked = self.shape(filename, "سَلَام")
            self.assertTrue(any(entry["ax"] == 0 and (entry["dx"] or entry["dy"]) for entry in marked), "GPOS must position Arabic marks")

#!/usr/bin/env python3
"""Build original Livara fonts from editable UFOs, or regenerate from design.json.

Requires fontTools. Default compilation preserves user-edited UFO/GLIF sources.
--regenerate deliberately redraws them from Livara's geometric design model.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
from types import SimpleNamespace
import unicodedata

from fontTools.agl import UV2AGL
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.pointPen import SegmentToPointPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path
from fontTools.ufoLib import UFOReader, UFOWriter

ROOT = Path(__file__).resolve().parents[1]
FONT_ROOT = ROOT / "fonts"
MODEL_PATH = FONT_ROOT / "sources/design.json"
FAMILIES = ("Livara Sans", "Livara Mono")
WEIGHTS = (("Regular", 400), ("SemiBold", 600))
SAMPLE_STEP = 17


def glyph_name(character: str) -> str:
    if character == ".notdef":
        return character
    point = ord(character)
    return UV2AGL.get(point, f"uni{point:04X}" if point <= 0xFFFF else f"u{point:X}")


def midpoint(first, second):
    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)


def vector(start, end):
    x, y = end[0] - start[0], end[1] - start[1]
    length = math.hypot(x, y)
    return (x / length, y / length) if length else (1, 0)


def sample_path(source):
    recorder = RecordingPen()
    parse_path(source, recorder)
    paths, points = [], []
    for command, values in recorder.value:
        if command == "moveTo":
            if points:
                paths.append((points, False))
            points = [values[0]]
        elif command == "lineTo":
            start, end = points[-1], values[0]
            count = max(1, math.ceil(math.dist(start, end) / SAMPLE_STEP))
            points.extend((start[0] + (end[0] - start[0]) * t / count, start[1] + (end[1] - start[1]) * t / count) for t in range(1, count + 1))
        elif command in ("curveTo", "qCurveTo"):
            start = points[-1]
            controls = [start, *values]
            distance = sum(math.dist(a, b) for a, b in zip(controls, controls[1:]))
            count = max(8, math.ceil(distance / SAMPLE_STEP))
            for index in range(1, count + 1):
                t = index / count
                work = list(controls)
                while len(work) > 1:
                    work = [(a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t) for a, b in zip(work, work[1:])]
                points.append(work[0])
        elif command == "closePath":
            # Closing straight segments need samples as well, preserving their
            # join shape when the outline is fitted with quadratic splines.
            start, end = points[-1], points[0]
            count = max(1, math.ceil(math.dist(start, end) / SAMPLE_STEP))
            points.extend((start[0] + (end[0] - start[0]) * t / count, start[1] + (end[1] - start[1]) * t / count) for t in range(1, count))
            if len(points) > 1 and math.dist(points[-1], points[0]) < .001:
                points.pop()
            paths.append((points, True))
            points = []
        elif command == "endPath":
            if points:
                paths.append((points, False))
            points = []
    if points:
        paths.append((points, False))
    return paths


def contour(pen, points):
    if len(points) < 3:
        return
    # All spline control points are original computed geometry, not outlines
    # borrowed from another typeface. Short quadratic spans smooth the offsets.
    beginning = midpoint(points[-1], points[0])
    pen.moveTo(beginning)
    pen.qCurveTo(*points, beginning)
    pen.closePath()


def stroke(pen, points, closed, width):
    half = width / 2
    normals = []
    for index, point in enumerate(points):
        previous = points[index - 1] if index or closed else point
        following = points[(index + 1) % len(points)] if index + 1 < len(points) or closed else point
        before, after = vector(previous, point), vector(point, following)
        if index == 0 and not closed:
            before = after
        if index == len(points) - 1 and not closed:
            after = before
        nx, ny = -before[1] - after[1], before[0] + after[0]
        length = math.hypot(nx, ny)
        if length < 0.0001:
            nx, ny = -after[1], after[0]
        else:
            nx, ny = nx / length, ny / length
        denominator = max(.5, nx * -after[1] + ny * after[0])
        normals.append((nx * half / denominator, ny * half / denominator))
    left = [(p[0] + n[0], p[1] + n[1]) for p, n in zip(points, normals)]
    right = [(p[0] - n[0], p[1] - n[1]) for p, n in zip(points, normals)]
    if closed:
        contour(pen, left)
        contour(pen, right[::-1])
        return
    end, last = points[-1], normals[-1]
    angle = math.atan2(last[1], last[0])
    end_cap = [(end[0] + half * math.cos(angle - math.pi * index / 12), end[1] + half * math.sin(angle - math.pi * index / 12)) for index in range(1, 12)]
    start, first = points[0], normals[0]
    angle = math.atan2(-first[1], -first[0])
    start_cap = [(start[0] + half * math.cos(angle - math.pi * index / 12), start[1] + half * math.sin(angle - math.pi * index / 12)) for index in range(1, 12)]
    contour(pen, [*left, *end_cap, *right[::-1], *start_cap])


def disc(pen, x, y, radius):
    contour(pen, [(x + radius * math.cos(-index * math.tau / 32), y + radius * math.sin(-index * math.tau / 32)) for index in range(32)])


def accent_definition(mark, width, top):
    middle = width / 2
    if mark == "\u0300":
        return {"paths": [f"M{middle - 70} {top + 165} L{middle + 30} {top + 80}"]}
    if mark == "\u0301":
        return {"paths": [f"M{middle - 30} {top + 80} L{middle + 70} {top + 165}"]}
    if mark == "\u0302":
        return {"paths": [f"M{middle - 105} {top + 80} L{middle} {top + 175} L{middle + 105} {top + 80}"]}
    if mark == "\u0303":
        return {"paths": [f"M{middle - 130} {top + 110} C{middle - 50} {top + 225} {middle + 50} {top + 5} {middle + 130} {top + 125}"]}
    if mark == "\u0308":
        return {"dots": [[middle - 95, top + 135, 32], [middle + 95, top + 135, 32]]}
    if mark == "\u030a":
        return {"paths": [f"M{middle} {top + 205} C{middle - 105} {top + 205} {middle - 105} {top + 55} {middle} {top + 55} C{middle + 105} {top + 55} {middle + 105} {top + 205} {middle} {top + 205} Z"]}
    if mark == "\u0327":
        return {"paths": [f"M{middle} -20 Q{middle + 125} -95 {middle + 10} -165 L{middle - 60} -165"]}
    raise ValueError(f"Unsupported accent {mark!r}")


def catalog(model):
    glyphs = dict(model["glyphs"])
    for point in range(0xA0, 0x100):
        character = chr(point)
        if character in glyphs:
            continue
        decomposed = unicodedata.normalize("NFD", character)
        if len(decomposed) == 2 and decomposed[0] in glyphs:
            base, mark = decomposed
            glyphs[character] = {"advance": glyphs[base]["advance"], "accent_base": base, "accent": accent_definition(mark, glyphs[base]["advance"], model["cap_height"] if base.isupper() else model["x_height"])}
        else:
            raise ValueError(f"Missing original design for U+{point:04X}")
    return glyphs


def outline(character, glyphs, width):
    definition = glyphs[character]
    pen = RecordingPen()
    def draw(definition, destination):
        for path in definition.get("paths", []):
            for points, closed in sample_path(path):
                stroke(destination, points, closed, width)
        for x, y, radius in definition.get("dots", []):
            disc(destination, x, y, radius * width / 60)
    if "accent_base" in definition:
        base = outline(definition["accent_base"], glyphs, width)
        base.replay(pen)
        draw(definition["accent"], pen)
    else:
        draw(definition, pen)
        for base, x, y, sx, sy in definition.get("components", []):
            outline(base, glyphs, width).replay(TransformPen(pen, (sx, 0, 0, sy, x, y)))
    return pen


def generate_sources(font_root=FONT_ROOT):
    model = json.loads((font_root / "sources/design.json").read_text())
    glyphs = catalog(model)
    order = [".notdef", *sorted((c for c in glyphs if c != ".notdef"), key=ord)]
    for family in FAMILIES:
        mono = family.endswith("Mono")
        for style, weight in WEIGHTS:
            directory = font_root / "sources" / f"{family.replace(' ', '')}-{style}.ufo"
            if directory.exists():
                shutil.rmtree(directory)
            writer = UFOWriter(directory, formatVersion=3)
            info = SimpleNamespace(familyName=family, styleName=style, styleMapFamilyName=family if weight == 400 else family + " " + style,
                styleMapStyleName="regular", unitsPerEm=model["units_per_em"], ascender=model["ascender"], descender=model["descender"],
                capHeight=model["cap_height"], xHeight=model["x_height"], copyright=model["copyright"],
                versionMajor=1, versionMinor=0, openTypeOS2WeightClass=weight, postscriptIsFixedPitch=mono,
                openTypeNameLicense="This Font Software is licensed under the SIL Open Font License, Version 1.1.",
                openTypeNameLicenseURL="https://openfontlicense.org", openTypeOS2VendorID="LVRA")
            writer.writeInfo(info)
            writer.writeLib({"public.glyphOrder": [glyph_name(c) for c in order], "org.livara.source": "Original editable Livara geometric design, sources/design.json"})
            kerning = {} if mono else {(glyph_name(a), glyph_name(b)): value for pair, value in model["kerning"].items() for a, b in [pair.split(" ")]}
            writer.writeKerning(kerning)
            glyphset = writer.getGlyphSet()
            stroke_width = model["stroke_regular" if weight == 400 else "stroke_semibold"]
            for character in order:
                definition = glyphs[character]
                drawing = outline(character, glyphs, stroke_width)
                advance = definition["advance"] + model.get("tracking", 0)
                if mono:
                    scaling = min(1, (model["mono_advance"] - 100) / max(1, advance - 100))
                    moved = RecordingPen()
                    drawing.replay(TransformPen(moved, (scaling, 0, 0, 1, (model["mono_advance"] - advance * scaling) / 2, 0)))
                    drawing, advance = moved, model["mono_advance"]
                    if character == "I":
                        # The coding face distinguishes capital I from l and 1.
                        for path in ("M145 720 L505 720", "M145 0 L505 0"):
                            for points, closed in sample_path(path):
                                stroke(drawing, points, closed, stroke_width)
                metadata = SimpleNamespace(width=advance, height=0, unicodes=[] if character == ".notdef" else [ord(character)], note="Original Livara outline. Edit points directly or regenerate from design.json.")
                glyphset.writeGlyph(glyph_name(character), metadata, lambda pointpen, drawing=drawing: drawing.replay(SegmentToPointPen(pointpen)), formatVersion=2)
            glyphset.writeContents()
            writer.writeLayerContents()
            writer.close()
    # Small centerline SVG sources are an additional easily edited design view.
    svg_dir = font_root / "sources/svg"
    svg_dir.mkdir(exist_ok=True)
    import html
    for character, definition in model["glyphs"].items():
        if character == ".notdef":
            continue
        paths = ''.join(f'<path d="{html.escape(path, quote=True)}"/>' for path in definition.get("paths", []))
        dots = ''.join(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="#16101f" stroke="none"/>' for x, y, radius in definition.get("dots", []))
        (svg_dir / f"U{ord(character):04X}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {definition["advance"]} 1240"><g transform="translate(0 960) scale(1 -1)" fill="none" stroke="#16101f" stroke-width="{model["stroke_regular"]}" stroke-linecap="round" stroke-linejoin="round">{paths}{dots}</g></svg>\n')
    print(f"Generated editable UFO and SVG sources for {len(glyphs) - 1} characters in four original font faces.")


def compile_ufo(source: Path, output: Path):
    reader = UFOReader(source)
    info = SimpleNamespace()
    reader.readInfo(info)
    glyphset = reader.getGlyphSet()
    lib = reader.readLib()
    preferred = lib.get("public.glyphOrder", [])
    available = set(glyphset.keys())
    order = [".notdef", *[name for name in preferred if name != ".notdef" and name in available], *sorted(available - set(preferred) - {".notdef"})]
    glyph_data, metrics, cmap = {}, {}, {}
    for name in order:
        metadata = SimpleNamespace()
        glyphset.readGlyph(name, metadata)
        pen = TTGlyphPen(glyphset)
        glyphset[name].draw(pen)
        glyph = pen.glyph()
        if glyph.numberOfContours > 0:
            # Outlined strokes may overlap at joins. TrueType's overlap flag
            # requests normal non-zero winding treatment in rasterizers.
            glyph.flags[0] |= 0x40
        glyph_data[name] = glyph
        if glyph.numberOfContours:
            glyph.recalcBounds(None)
            bearing = glyph.xMin
        else:
            bearing = 0
        metrics[name] = (round(metadata.width), bearing)
        for point in getattr(metadata, "unicodes", []):
            cmap[point] = name
    builder = FontBuilder(info.unitsPerEm, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyph_data)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=info.ascender, descent=info.descender, lineGap=0)
    style = info.styleName
    family = info.familyName
    postscript = family.replace(" ", "") + "-" + style
    builder.setupNameTable({"familyName": family, "styleName": style, "uniqueFontIdentifier": f"Livara: {postscript}: 1.000", "fullName": family + " " + style,
        "psName": postscript, "version": "Version 1.000", "copyright": info.copyright,
        "licenseDescription": info.openTypeNameLicense, "licenseInfoURL": info.openTypeNameLicenseURL,
        "typographicFamily": family, "typographicSubfamily": style, "manufacturer": "Livara OS contributors", "designer": "Livara OS contributors"})
    builder.setupOS2(sTypoAscender=info.ascender, sTypoDescender=info.descender, sTypoLineGap=0,
        usWinAscent=max(info.ascender, 1000), usWinDescent=max(-info.descender, 280),
        sxHeight=info.xHeight, sCapHeight=info.capHeight, usWeightClass=info.openTypeOS2WeightClass,
        usWidthClass=5, achVendID="LVRA", fsSelection=0x40 if style == "Regular" else 0,
        fsType=0, sFamilyClass=0x0800)
    builder.setupPost(isFixedPitch=info.postscriptIsFixedPitch)
    builder.setupMaxp()
    # Fixed timestamp makes rebuilds deterministic and prevents workspace dates
    # from changing identical font binaries.
    builder.font["head"].created = builder.font["head"].modified = 3406620153
    builder.font.recalcTimestamp = False
    kerning = reader.readKerning()
    if kerning:
        features = "languagesystem DFLT dflt; languagesystem latn dflt; feature kern {\n"
        features += "\n".join(f"pos {a} {b} {value};" for (a, b), value in sorted(kerning.items()))
        features += "\n} kern;\n"
        addOpenTypeFeaturesFromString(builder.font, features)
    output.parent.mkdir(parents=True, exist_ok=True)
    builder.save(output)
    output.chmod(0o644)
    reader.close()
    print(f"Built {output.name}: {len(cmap)} encoded characters, {len(order)} glyphs.")


def verify_vazirmatn_sources(root: Path):
    """Validate immutable, attributed upstream inputs before preparing a derivative."""
    import hashlib
    vendor = root / "vendor/vazirmatn"
    manifest = json.loads((vendor / "upstream.json").read_text())
    for entry in manifest["files"]:
        payload = (vendor / entry["local_path"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("Vazirmatn input differs from its pinned source: " + entry["local_path"])
    return vendor


def prepare_persian_sources(root: Path):
    """Explicitly recreate editable renamed faces from the verified OFL upstream."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    vendor = verify_vazirmatn_sources(root)
    for style, weight in WEIGHTS:
        font = TTFont(vendor / "Vazirmatn-Variable.ttf")
        instantiateVariableFont(font, {"wght": weight}, inplace=True, optimize=True)
        names = {1: "Livara Persian", 2: style, 3: "Livara: LivaraPersian-" + style + ": Vazirmatn 33.003 derivative 1.000",
                 4: "Livara Persian " + style, 6: "LivaraPersian-" + style,
                 16: "Livara Persian", 17: style, 25: "LivaraPersian"}
        for record in font["name"].names:
            if record.nameID in names:
                record.string = names[record.nameID].encode(record.getEncoding())
        for identifier, value in names.items():
            font["name"].setName(value, identifier, 3, 1, 0x409)
        # Copyright and license name records intentionally remain upstream.
        font["name"].setName("Livara adaptation of Vazirmatn by Saber Rastikerdar and contributors. Shaping tables retained.", 10, 3, 1, 0x409)
        font["OS/2"].usWeightClass = weight
        font["head"].created = font["head"].modified = 3406620153
        font.recalcTimestamp = False
        path = root / "sources" / f"LivaraPersian-{style}.ttx"
        font.saveXML(path)
        font.close()
        print(f"Prepared editable {path.name} from pinned Vazirmatn 33.003.")


def compile_persian(source: Path, output: Path):
    """Compile user-editable full-table XML without reconstructing Arabic shaping."""
    from fontTools.ttLib import TTFont
    font = TTFont(recalcTimestamp=False)
    font.importXML(source)
    if not {"GSUB", "GPOS", "GDEF"}.issubset(font.keys()):
        raise ValueError("Livara Persian requires its original OpenType shaping tables")
    if font["name"].getDebugName(16) != "Livara Persian":
        raise ValueError("Persian derivative must retain its distinct Livara Persian family name")
    font.recalcTimestamp = False
    output.parent.mkdir(parents=True, exist_ok=True)
    font.save(output)
    output.chmod(0o644)
    print(f"Built {output.name}: {len(font.getBestCmap())} encoded characters; Arabic/Persian GSUB/GPOS retained.")
    font.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regenerate", action="store_true", help="redraw original Latin UFOs from design.json; overwrites their outline edits")
    parser.add_argument("--prepare-persian", action="store_true", help="recreate Persian TTX sources from pinned Vazirmatn; overwrites Persian XML edits")
    parser.add_argument("--font-root", type=Path, default=FONT_ROOT, help="font tree, useful for isolated tests")
    options = parser.parse_args()
    root = options.font_root.resolve()
    if options.regenerate:
        generate_sources(root)
    if options.prepare_persian:
        prepare_persian_sources(root)
    for family in FAMILIES:
        for style, _weight in WEIGHTS:
            name = family.replace(" ", "") + "-" + style
            source = root / "sources" / f"{name}.ufo"
            if not source.is_dir():
                parser.error(f"Missing editable source {source}; run --regenerate to create it")
            compile_ufo(source, root / "ttf" / f"{name}.ttf")
    for style, _weight in WEIGHTS:
        name = "LivaraPersian-" + style
        source = root / "sources" / (name + ".ttx")
        if not source.is_file():
            parser.error(f"Missing editable Persian source {source}; run --prepare-persian to create it")
        compile_persian(source, root / "ttf" / (name + ".ttf"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

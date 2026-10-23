# Pinned Vazirmatn upstream

These unmodified upstream files come from [rastikerdar/vazirmatn](https://github.com/rastikerdar/vazirmatn), release **v33.003**. The annotated tag object is `f68f7bc5dd1d046bd6a5a2bda355bd6d430e807a`; its peeled source commit is **`83629f877e8f084cc07b47030b5d3a0ff06c76ec`**. `upstream.json` records each immutable raw-source URL and SHA-256 digest.

Vazirmatn is the work of Saber Rastikerdar and its contributors. Its original copyright and [SIL OFL1.1](OFL.txt) are retained. The original Thin/Regular/Black FontForge SFD masters and official variable TTF are supplied as editable/reference upstream sources. `UPSTREAM-README.md` is the original project documentation.

**Livara Persian** is a renamed Vazirmatn-derived family. Its actual glyph design and OpenType Arabic/Persian shaping come from Vazirmatn; they are not claimed as original Livara Sans/Mono work. The derivative's Regular/SemiBold full-table editable TTX sources are in `fonts/sources/`; the compiled distribution faces are in `fonts/ttf/`.

Default `python3 scripts/build-fonts.py` compiles those existing editable TTX sources and preserves edits. `--prepare-persian` explicitly reinstances weights400/600 from this pinned official variable input and replaces the two derivative TTX files; its source verification checks every vendored file against the manifest.

The build keeps the original GSUB/GPOS/GDEF tables, Persian Yeh/Kaf, contextual forms, ligatures, zero-width non-joiner behavior, and mark positioning. It changes family/product identifiers to avoid font-name conflicts. Keep this license and attribution with derivative fonts.

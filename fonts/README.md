# Livara type

**Livara Sans** and **Livara Mono** are original rounded geometric typefaces made for this project. Their letterforms are drawn from the editable geometric model in `sources/design.json`; no existing font outlines are renamed or traced. Each family has **Regular (400)** and **SemiBold (600)** faces.

Compiled fonts are in `ttf/`. The complete editable UFO3/GLIF outline sources are in `sources/*.ufo/`. Per-character SVG centerline drawings in `sources/svg/` provide an additional vector design view. The specimen in `specimens/livara-type-specimen.png` is rendered with these actual TTFs.

See [editing and rebuilding](../docs/fonts.md). This font software is licensed under **SIL OFL 1.1**; keep [OFL.txt](OFL.txt) with redistributed copies. No Reserved Font Names are declared, so the OFL does not force you to rename your own modified versions.

**Livara Persian** adds Regular/SemiBold faces derived from the OFL-licensed **Vazirmatn** by Saber Rastikerdar and contributors, with the original contextual Arabic/Persian shaping retained. These faces are explicitly derivatives, not original Livara geometric designs. Their full-table editable TTX sources are in `sources/`, and pinned official variable/SFD source files plus their separate license are in `vendor/vazirmatn/`. Default rebuild now compiles all **six** faces while preserving UFO/TTX edits. See the Persian specimen in `specimens/livara-persian-specimen.png`.

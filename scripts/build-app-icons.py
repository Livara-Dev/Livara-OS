#!/usr/bin/env python3
"""Build Livara's distinct, self-contained vector app icon family.

The OS identity mark is preserved. These original launcher symbols use a shared
optical frame and application-specific glyphs; no third-party artwork is used.
"""
from pathlib import Path
import html

ROOT = Path(__file__).resolve().parents[1]
# name: (accent, deep tint, accessible title, original glyph geometry)
ICONS = {
    "Center": ("#a9a0ff", "#4c3ea1", "Livara Control Center", '<rect x="66" y="66" width="53" height="53" rx="15"/><rect x="137" y="66" width="53" height="32" rx="12"/><rect x="66" y="137" width="53" height="53" rx="15"/><rect x="137" y="116" width="53" height="74" rx="15"/>'),
    "Settings": ("#b6c5ff", "#435ca2", "Livara Settings", '<path d="M69 83h118M69 128h118M69 173h118" fill="none" stroke="url(#glyph)" stroke-width="12" stroke-linecap="round"/><rect x="91" y="67" width="22" height="32" rx="10"/><rect x="146" y="112" width="22" height="32" rx="10"/><rect x="101" y="157" width="22" height="32" rx="10"/>'),
    "Monitor": ("#73edcb", "#146f74", "Livara Task Manager", '<rect x="59" y="67" width="138" height="113" rx="22" fill="none" stroke="url(#glyph)" stroke-width="9"/><path d="M71 131h24l16-33 26 60 17-33h31" fill="none" stroke="url(#glyph)" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/><path d="M106 198h44" stroke="url(#glyph)" stroke-width="9" stroke-linecap="round"/>'),
    "Studio": ("#ffc09c", "#a14f7a", "Livara Studio", '<path d="m130 62 54 54-49 68-47 2-18-18 2-47Z" fill="none" stroke="url(#glyph)" stroke-width="10" stroke-linejoin="round"/><path d="m89 167 37-37" stroke="url(#glyph)" stroke-width="9" stroke-linecap="round"/><circle cx="134" cy="122" r="13"/><path d="m145 58 43 43" stroke="url(#glyph)" stroke-width="12" stroke-linecap="round"/>'),
    "Browser": ("#83cfff", "#3b58a3", "Livara Browser", '<circle cx="128" cy="128" r="61" fill="none" stroke="url(#glyph)" stroke-width="9"/><ellipse cx="128" cy="128" rx="27" ry="61" fill="none" stroke="url(#glyph)" stroke-width="7"/><path d="M69 128h118M79 95h98M79 161h98" fill="none" stroke="url(#glyph)" stroke-width="7" stroke-linecap="round"/>'),
    "Code": ("#c1a2ff", "#6945b1", "Livara Code", '<path d="m100 86-43 42 43 42m56-84 43 42-43 42m-17-98-22 115" fill="none" stroke="url(#glyph)" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>'),
    "Chat": ("#e5a5ff", "#8c49aa", "Livara Chat", '<path d="M174 85h9a22 22 0 0 1 22 22v43a22 22 0 0 1-22 22h-8l-23 20v-20h-33" fill="none" stroke="url(#glyph)" stroke-width="8" stroke-linejoin="round"/><path d="M73 64h76a23 23 0 0 1 23 23v37a23 23 0 0 1-23 23h-39l-34 24v-24h-3a23 23 0 0 1-23-23V87a23 23 0 0 1 23-23Z"/><circle cx="86" cy="106" r="6" fill="#624b8b"/><circle cx="111" cy="106" r="6" fill="#624b8b"/><circle cx="136" cy="106" r="6" fill="#624b8b"/>'),
    "Terminal": ("#a6f0c9", "#36796c", "Livara Terminal", '<rect x="54" y="65" width="148" height="126" rx="22" fill="none" stroke="url(#glyph)" stroke-width="9"/><path d="m79 104 29 24-29 24m49 4h43" fill="none" stroke="url(#glyph)" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>'),
    "Essentials": ("#ffe3a2", "#997548", "Livara Essentials", '<path d="M126 58c9 43 24 59 69 70-45 10-60 26-69 69-10-43-25-59-69-69 44-11 59-27 69-70Z"/><path d="m184 54 4 14 14 4-14 4-4 14-4-14-14-4 14-4Z"/>'),
    "Graphics": ("#91e4fb", "#347291", "Livara Graphics", '<rect x="77" y="77" width="102" height="102" rx="20" fill="none" stroke="url(#glyph)" stroke-width="10"/><rect x="103" y="103" width="50" height="50" rx="10"/><path d="M101 58v19m27-19v19m27-19v19M101 179v19m27-19v19m27-19v19M58 101h19m-19 27h19m-19 27h19m102-54h19m-19 27h19m-19 27h19" stroke="url(#glyph)" stroke-width="8" stroke-linecap="round"/>'),
    "Palette": ("#f4add8", "#9b477e", "Livara Palette", '<circle cx="114" cy="112" r="43" fill="none" stroke="url(#glyph)" stroke-width="12"/><path d="m146 145 42 43" stroke="url(#glyph)" stroke-width="16" stroke-linecap="round"/><path d="M114 89v46m-23-23h46" stroke="url(#glyph)" stroke-width="7" stroke-linecap="round"/>'),
    "Install": ("#a5c8ff", "#42619e", "Install Livara OS", '<path d="M128 59v91m-31-31 31 31 31-31M67 151v25a17 17 0 0 0 17 17h88a17 17 0 0 0 17-17v-25" fill="none" stroke="url(#glyph)" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>'),
    "Toolbox": ("#ffb1a8", "#a04f6d", "Livara Kali Toolbox", '<rect x="57" y="99" width="142" height="90" rx="19" fill="none" stroke="url(#glyph)" stroke-width="10"/><path d="M99 99V82a14 14 0 0 1 14-14h30a14 14 0 0 1 14 14v17M60 133h136" fill="none" stroke="url(#glyph)" stroke-width="9"/><rect x="116" y="120" width="24" height="30" rx="8"/>'),
}


def render(name, accent, tint, title, geometry):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" role="img" aria-labelledby="title">
<title id="title">{html.escape(title)}</title>
<defs>
 <linearGradient id="body" x1="0" y1="0" x2="0.8" y2="1">
  <stop stop-color="{accent}"/><stop offset=".43" stop-color="{tint}"/><stop offset="1" stop-color="#211c3c"/>
 </linearGradient>
 <radialGradient id="caustic" cx=".18" cy=".06" r="1">
  <stop stop-color="#fff" stop-opacity=".65"/><stop offset=".44" stop-color="{accent}" stop-opacity=".12"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
 </radialGradient>
 <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">
  <stop stop-color="#fff" stop-opacity=".95"/><stop offset=".42" stop-color="#fff" stop-opacity=".14"/><stop offset=".73" stop-color="{accent}" stop-opacity=".32"/><stop offset="1" stop-color="#fff" stop-opacity=".65"/>
 </linearGradient>
 <linearGradient id="glyph" x1="0" y1="0" x2=".4" y2="1">
  <stop stop-color="#fff"/><stop offset="1" stop-color="{accent}"/>
 </linearGradient>
</defs>
<rect x="18" y="22" width="220" height="220" rx="57" fill="#09081b" opacity=".14"/>
<rect x="18" y="16" width="220" height="220" rx="57" fill="url(#body)"/>
<rect x="19" y="17" width="218" height="218" rx="56" fill="url(#caustic)" stroke="url(#rim)" stroke-width="2"/>
<rect x="25" y="23" width="206" height="206" rx="50" fill="none" stroke="#fff" stroke-opacity=".11"/>
<path d="M44 59a38 38 0 0 1 34-24h100" fill="none" stroke="#fff" stroke-width="3" stroke-opacity=".32" stroke-linecap="round"/>
<path d="M77 218h100a38 38 0 0 0 34-23" fill="none" stroke="{accent}" stroke-width="4" stroke-opacity=".45" stroke-linecap="round"/>
<g fill="url(#glyph)">{geometry}</g>
</svg>
'''


def main():
    for name, (accent, tint, title, geometry) in ICONS.items():
        (ROOT / "artwork" / f"org.livara.{name}.svg").write_text(render(name, accent, tint, title, geometry), encoding="utf-8")
    print(f"Generated {len(ICONS)} distinct Livara application icons.")


if __name__ == "__main__":
    main()

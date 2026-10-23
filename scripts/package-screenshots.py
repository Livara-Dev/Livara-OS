#!/usr/bin/env python3
"""Package genuine capture files as an offline gallery and full-resolution ZIP.

Pixels are copied unchanged. The catalog records what each capture establishes;
uncaptured components stay explicitly listed rather than receiving mock images.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def png_info(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        raise ValueError(f'Capture must be an original PNG: {path}')
    return struct.unpack('>II', header[16:24])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'docs/screenshots/catalog.json')
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    captures = []
    names = set()
    for entry in catalog['captures']:
        source = (ROOT / entry['path']).resolve()
        if not source.is_relative_to(ROOT) or not source.is_file():
            raise ValueError(f'Missing capture: {entry["path"]}')
        if source.name.casefold() in names:
            raise ValueError(f'Duplicate screenshot filename: {source.name}')
        names.add(source.name.casefold())
        width, height = png_info(source)
        captures.append({**entry, 'source': source, 'width': width, 'height': height,
                         'bytes': source.read_bytes()})
    if not captures:
        raise ValueError('The gallery needs real screenshots')
    escape = html.escape
    cards = []
    for index, entry in enumerate(captures):
        uri = 'data:image/png;base64,' + base64.b64encode(entry['bytes']).decode('ascii')
        title, context = escape(entry['title']), escape(entry['context'])
        cards.append(f'''<article data-section="{escape(entry['section'], quote=True)}">
<button class="capture" type="button" data-index="{index}" aria-label="View {title}"><img loading="lazy" src="{uri}" alt="{title}" width="{entry['width']}" height="{entry['height']}"></button>
<div class="caption"><small>{escape(entry['section'])} · {entry['width']} × {entry['height']}</small><h2>{title}</h2><p>{context}</p><a class="download" href="#" download="{escape(entry['source'].name, quote=True)}">Download original PNG</a></div></article>''')
    script = '''const cards=[...document.querySelectorAll('article')], dialog=document.querySelector('dialog');
document.querySelectorAll('.capture').forEach(button=>button.addEventListener('click',()=>{
 const card=button.closest('article'); dialog.querySelector('img').src=card.querySelector('img').src;
 dialog.querySelector('img').alt=card.querySelector('h2').textContent;
 dialog.querySelector('p').textContent=card.querySelector('h2').textContent;dialog.showModal();
}));
document.querySelectorAll('.download').forEach(link=>link.addEventListener('click',()=>{link.href=link.closest('article').querySelector('img').src}));
dialog.querySelector('button').addEventListener('click',()=>dialog.close());
dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});
document.querySelector('select').addEventListener('change',event=>cards.forEach(card=>{card.hidden=event.target.value!=='All'&&card.dataset.section!==event.target.value}));'''
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    options = ''.join(f'<option>{escape(value)}</option>' for value in ['All', *dict.fromkeys(entry['section'] for entry in captures)])
    unavailable = ''.join(f'<li>{escape(value)}</li>' for value in catalog.get('not_captured', []))
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'">
<title>Livara OS · Actual screenshot gallery</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#07050b;color:#f1e9fa;font:16px system-ui,sans-serif}}main{{max-width:1560px;margin:auto;padding:36px}}header{{padding:12px 0 28px;max-width:1050px}}h1{{font-size:clamp(30px,5vw,58px);letter-spacing:-2px;margin:10px 0}}p,li{{color:#c0afcf;line-height:1.6}}small{{color:#caa0ff}}select,button{{font:inherit}}select{{padding:10px 16px;background:#1a1027;color:#eee;border:1px solid #78529d;border-radius:10px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:24px}}article{{border:1px solid #39264b;border-radius:18px;background:#100a18;overflow:hidden}}article[hidden]{{display:none}}.capture{{padding:0;border:0;background:#000;display:block;width:100%;cursor:zoom-in}}.capture img{{width:100%;height:auto;display:block}}.caption{{padding:20px}}h2{{font-size:20px;margin:8px 0}}a{{color:#d3a6ff}}.limits{{margin:36px 0;padding:22px;border:1px solid #39264b;border-radius:16px}}dialog{{max-width:98vw;max-height:98vh;background:#0b0710;color:#eee;border:1px solid #9668c6;border-radius:12px;padding:16px}}dialog::backdrop{{background:#000d}}dialog img{{display:block;max-width:94vw;max-height:82vh;width:auto;height:auto}}dialog button{{float:right;padding:8px 16px;cursor:pointer}}dialog p{{margin:8px 0}}footer{{color:#b09ac5;padding:24px 0}}
</style></head><body><main><header><small>LIVARA OS / REAL CAPTURES</small><h1>Explore Livara.</h1><p>{escape(catalog['description'])}</p><p>{len(captures)} full-resolution captures. Click an image to enlarge it; the gallery works offline.</p><label>Show <select aria-label="Screenshot section">{options}</select></label></header><div class="grid">{''.join(cards)}</div>
<section class="limits"><h2>Capture limits</h2><ul>{unavailable}</ul></section><footer>Original PNG pixels are unchanged. Captions distinguish native application tests, nested desktop previews, and font specimens.</footer></main><dialog><button type="button">Close</button><p></p><img alt=""></dialog><script>{script}</script></body></html>'''
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    gallery = output / 'livara-os-screenshot-gallery.html'
    gallery.write_text(document, encoding='utf-8'); gallery.chmod(0o644)
    archive = output / 'livara-os-screenshots.zip'
    archive_document = document
    for entry in captures:
        uri = 'data:image/png;base64,' + base64.b64encode(entry['bytes']).decode('ascii')
        archive_document = archive_document.replace(uri, 'images/' + entry['source'].name)
    archive_document = archive_document.replace("img-src data:;", "img-src 'self' data:;")
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        package.writestr('livara-screenshots/index.html', archive_document)
        packaged_catalog = {**catalog, 'captures': [
            {**entry, 'archive_path': 'images/' + capture['source'].name,
             'width': capture['width'], 'height': capture['height'],
             'sha256': hashlib.sha256(capture['bytes']).hexdigest()}
            for entry, capture in zip(catalog['captures'], captures)
        ]}
        package.writestr('livara-screenshots/catalog.json', json.dumps(packaged_catalog, indent=2) + '\n')
        for entry in captures:
            package.writestr('livara-screenshots/images/' + entry['source'].name, entry['bytes'])
    archive.chmod(0o644)
    for path in (gallery, archive):
        checksum = path.with_name(path.name + '.sha256')
        checksum.write_text(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n')
        checksum.chmod(0o644)
    print(f'Packaged {len(captures)} original captures: {gallery} and {archive}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

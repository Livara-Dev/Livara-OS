#!/usr/bin/env python3
"""Check rendered refraction, live movement/content and sharp foreground text."""
import argparse
import json
from pathlib import Path
import re

from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
log = (args.output / 'compositor.log').read_text()
if re.search(r'(?:Gjs|Clutter|GLib-GObject)-CRITICAL|JS ERROR', log):
    raise SystemExit('Compositor emitted a critical diagnostic; inspect compositor.log')
report = json.loads((args.output / 'production.json').read_text())
if report.get('status') != 'passed':
    raise SystemExit(f'Compositor test failed: {report}')
images = {name: Image.open(args.output / f'{name}.png').convert('RGB')
          for name in ('flat', 'refracted', 'live', 'updated')}
crop = (220, 200, 620, 360)
comparisons = [('flat', 'refracted'), ('refracted', 'live'), ('live', 'updated')]
metrics = {}
for before, after in comparisons:
    changed = sum(max(abs(a - b) for a, b in zip(p, q)) > 8
                  for p, q in zip(images[before].crop(crop).getdata(),
                                  images[after].crop(crop).getdata()))
    if changed < 1000:
        raise SystemExit(f'No convincing optical/live change: {before} → {after}: {changed}')
    metrics[f'{before}_to_{after}_changed_pixels'] = changed

# Interior white glyph pixels exclude antialiased edges that legitimately
# blend with the changing background. The foreground never enters the lens.
text_crop = (250, 250, 600, 300)
masks = {name: [min(pixel) >= 245 for pixel in image.crop(text_crop).getdata()]
         for name, image in images.items()}
white = sum(masks['flat'])
if white < 100:
    raise SystemExit('Foreground label missing or unreadable')
for name, mask in masks.items():
    if mask != masks['flat']:
        raise SystemExit(f'Foreground glyphs moved or warped in {name}')
metrics['unchanged_white_glyph_pixels'] = white
report['pixels'] = metrics
(args.output / 'verified.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

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
def fail(message):
    # Also visible through GitHub's check annotations when artifact storage is
    # unavailable. Include only this renderer's own bounded diagnostics.
    print('::error title=Liquid glass renderer::' + str(message).replace('\n', ' '))
    raise SystemExit(message)

log = (args.output / 'compositor.log').read_text()
if re.search(r'(?:Gjs|Clutter|GLib-GObject)-CRITICAL|JS ERROR', log):
    fail('Compositor emitted a critical diagnostic; inspect compositor.log')
report = json.loads((args.output / 'production.json').read_text())
if report.get('status') != 'passed':
    fail(f'Compositor test failed: {report}')
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
        fail(f'No convincing optical/live change: {before} → {after}: {changed}')
    metrics[f'{before}_to_{after}_changed_pixels'] = changed

# A hysteresis band excludes antialiased edges that blend with the changing
# underlayer. Moving a bright core outside the original silhouette still fails.
# Exact single-threshold masks incorrectly reject one-level RGB rounding.
text_crop = (250, 250, 600, 300)
values = {name: [min(pixel) for pixel in image.crop(text_crop).getdata()]
         for name, image in images.items()}
white = sum(value >= 250 for value in values['flat'])
if white < 100:
    fail('Foreground label missing or unreadable')
for name, current in values.items():
    displaced = sum((a >= 250 and b < 245) or (b >= 250 and a < 245)
                    for a,b in zip(values['flat'], current))
    if displaced:
        fail(f'Foreground glyphs moved or warped in {name}: {displaced} core pixels')
metrics['stable_bright_glyph_pixels'] = white
report['pixels'] = metrics
(args.output / 'verified.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))

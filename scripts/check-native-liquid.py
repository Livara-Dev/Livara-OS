#!/usr/bin/env python3
"""Verify actual native app refraction, live scene content and sharp text."""
import argparse
import json
from pathlib import Path
import re
from PIL import Image

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('output',type=Path)
args=parser.parse_args();out=args.output
report=json.loads((out/'native.json').read_text())
assert report['status']=='passed',report
log=(out/'compositor.log').read_text()
assert not re.search(r'(?:Gjs|Clutter|GLib-GObject|libmutter)-CRITICAL|JS ERROR',log),'Inspect compositor.log'
f=report['frame'];crop=(f['x'],f['y'],f['x']+f['width'],f['y']+f['height'])
images={name:Image.open(out/f'native-{name}.png').convert('RGB') for name in ('flat','refracted','live','updated')}
metrics={}
for a,b in [('flat','refracted'),('refracted','live'),('live','updated')]:
 count=sum(max(abs(x-y) for x,y in zip(p,q))>8 for p,q in zip(images[a].crop(crop).getdata(),images[b].crop(crop).getdata()))
 assert count>2000,(a,b,count)
 metrics[a+'_to_'+b]=count
text=(f['x']+300,f['y']+94,f['x']+710,f['y']+136)
masks={name:[min(pixel)>=238 for pixel in image.crop(text).getdata()] for name,image in images.items()}
white=sum(masks['flat']);assert white>300,white
for name,mask in masks.items():
 changed=sum(a!=b for a,b in zip(masks['flat'],mask))
 assert changed<=max(2,white*.005),(name,changed,white)
 metrics['glyph_changes_'+name]=changed
metrics['foreground_pixels']=white
report['pixels']=metrics
(out/'native-verified.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))

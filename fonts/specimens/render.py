#!/usr/bin/env python3
"""Render the original fonts for visual review; requires Pillow."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
root=Path(__file__).resolve().parents[1]
image=Image.new('RGB',(1500,1570),'#07040b');draw=ImageDraw.Draw(image)
def line(text,size,y,weight='Regular',color='#eee4fa',family='Sans'):
 font=ImageFont.truetype(str(root/'ttf'/f'Livara{family}-{weight}.ttf'),size)
 draw.text((80,y),text,font=font,fill=color)
line('LIVARA SANS',24,55,'SemiBold','#b984f5')
line('A little curiosity.',78,115,'SemiBold')
line('A clearer perspective.',78,215)
line('Original shapes. Editable sources. Yours to change.',32,345,color='#baa7ca')
line('ABCDEFGHIJKLMNOPQRSTUVWXYZ',38,450)
line('abcdefghijklmnopqrstuvwxyz',44,525)
line('0123456789  & @ # % / < > { } [ ]',42,610)
line('ÀÁÂÃÄÅ Æ Ç ÈÉÊË ÌÍÎÏ Ð Ñ ÒÓÔÕÖ Ø ÙÚÛÜ Ý Þ ß',28,710)
line('àáâãäå æ ç èéêë ìíîï ð ñ òóôõö ø ùúûü ý þ ÿ',30,770)
line('“Choose your own way…”  € £ ¥  ± × ÷  ← → ↑ ↓',32,840)
line('The quick brown fox jumps over the lazy dog.',27,960)
line('Pack my box with five dozen liquor jugs.',23,1015)
line('A modern desktop with a little more room for your ideas.',19,1062)
line('LIVARA MONO',24,1150,'SemiBold','#b984f5')
line('const theme = { glass: true, accent: "purple" };',26,1220,family='Mono')
line('for (let line = 0; line < 20; line++) {',26,1270,family='Mono')
line('  console.log(`Welcome to Livara ${line}`);',26,1320,color='#bb9ee0',family='Mono')
line('}',26,1370,family='Mono')
line('Regular 400 / SemiBold 600 · Original OFL 1.1 typefaces',23,1470,color='#a693b6')
image.save(root/'specimens/livara-type-specimen.png')

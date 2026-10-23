#!/usr/bin/env python3
"""Render the actual Vazirmatn-derived Livara Persian with Pillow/RAQM."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, features

root = Path(__file__).resolve().parents[1]
if not features.check('raqm'):
    raise SystemExit('Pillow must have RAQM/HarfBuzz support for genuine RTL shaping')
image = Image.new('RGB', (1500, 1100), '#07040b')
draw = ImageDraw.Draw(image)
latin = lambda size, weight='Regular': ImageFont.truetype(str(root/'ttf'/f'LivaraSans-{weight}.ttf'), size)
persian = lambda size, weight='Regular': ImageFont.truetype(str(root/'ttf'/f'LivaraPersian-{weight}.ttf'), size, layout_engine=ImageFont.Layout.RAQM)
draw.text((85, 50), 'LIVARA PERSIAN', font=latin(27, 'SemiBold'), fill='#bd88f5')
draw.text((85, 105), 'A Vazirmatn adaptation with its shaping intact.', font=latin(28), fill='#ac99bf')
rows = [
    ('لیوارا، پنجره‌ای رو به آینده', 70, 210, 'SemiBold', '#f1e7fb'),
    ('زیبایی در جزئیات است.', 62, 340, 'Regular', '#eadff5'),
    ('متن فارسیِ خوانا، آرام و زیبا.', 42, 490, 'Regular', '#c9b5dc'),
    ('می‌توانیم بنویسیم؛ با نیم‌فاصله و نشانه‌های درست.', 37, 585, 'Regular', '#c9b5dc'),
    ('پژوهش، گرافیک، کدنویسی و امنیت', 39, 680, 'SemiBold', '#e6d4f7'),
    ('۰۱۲۳۴۵۶۷۸۹ — ی ک پ چ ژ گ', 39, 775, 'Regular', '#c9b5dc'),
    ('العربية: جمالٌ في التفاصيل', 37, 865, 'Regular', '#c9b5dc'),
]
for text, size, y, style, color in rows:
    draw.text((1410, y), text, font=persian(size, style), fill=color, anchor='ra', direction='rtl', language='fa')
draw.text((85, 1000), 'Vazirmatn by Saber Rastikerdar and contributors · SIL OFL 1.1', font=latin(24), fill='#ac99bf')
image.save(root/'specimens/livara-persian-specimen.png')

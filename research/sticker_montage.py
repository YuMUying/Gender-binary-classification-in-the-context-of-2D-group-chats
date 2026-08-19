# -*- coding: utf-8 -*-
"""sticker_montage.py — 把 Top-200 贴纸拼成带编号的网格图（10 张 x20 格）"""
import os
from PIL import Image, ImageDraw, ImageFont

SRC = 'data/sticker_tags'
OUT = 'research/sticker_sheets'
os.makedirs(OUT, exist_ok=True)

files = sorted(f for f in os.listdir(SRC) if f.startswith('rank_'))
print(f'贴纸文件: {len(files)} 个')

CELL = 260
COLS, ROWS = 5, 4
PER = COLS * ROWS

def load(fn):
    im = Image.open(os.path.join(SRC, fn))
    im.seek(0)
    im = im.convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert('RGB')
    im.thumbnail((CELL - 30, CELL - 30))
    return im

try:
    font = ImageFont.truetype('arial.ttf', 22)
except Exception:
    font = ImageFont.load_default()

sheets = []
for s in range(0, len(files), PER):
    batch = files[s:s + PER]
    sheet = Image.new('RGB', (COLS * CELL, ROWS * CELL), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    for i, fn in enumerate(batch):
        col, row = i % COLS, i // COLS
        x, y = col * CELL, row * CELL
        try:
            im = load(fn)
            sheet.paste(im, (x + (CELL - im.width) // 2, y + (CELL - im.height) // 2))
        except Exception as e:
            print(f'  {fn} 读取失败: {e}')
        rank = fn.replace('rank_', '').split('.')[0]
        d.rectangle([x + 4, y + 4, x + 64, y + 32], fill=(220, 40, 40))
        d.text((x + 10, y + 6), f'#{rank}', fill=(255, 255, 255), font=font)
        d.rectangle([x, y, x + CELL - 1, y + CELL - 1], outline=(180, 180, 180))
    out = os.path.join(OUT, f'sheet_{s // PER + 1:02d}.png')
    sheet.save(out)
    sheets.append(out)
    print(f'  {out} ({len(batch)} 格)')
print(f'共 {len(sheets)} 张拼图')

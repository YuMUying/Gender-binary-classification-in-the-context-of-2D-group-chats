# -*- coding: utf-8 -*-
"""review_prep.py — 抽查准备：自检抽样 + 生成标签对照图册 HTML"""
import csv
import json
import os
import random

# 1) 自检：v2 标签 vs gpt-5.5 描述 一致性抽样
desc = {}
for l in open('research/sticker_desc.jsonl', encoding='utf-8'):
    l = l.strip()
    if l:
        d = json.loads(l)
        desc[d['rank']] = d['desc']

tags = {}
with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r.get('emotion'):
            tags[r['rank']] = r

print('=== 自检抽样（标签 vs 描述）===')
random.seed(7)
sample = random.sample(sorted(tags, key=int)[:200], 8) if len(tags) >= 200 else list(tags)[:8]
for rk in sample:
    t = tags[rk]
    d = desc.get(int(rk), {})
    print(f'rank {rk}: [{t["emotion"]}|{t["style"]}|涩{t["ero"]}|梗{t["meme"]}|萌{t["moe"]}]')
    print(f'  描述: {d.get("overall", "?")}')
    print(f'  表情: {d.get("emotion", "?")[:50]}')

# 2) 生成图册 HTML
IMG_TOP = '../data/sticker_tags'
rows_top = [tags[r] for r in sorted(tags, key=lambda x: (x != 'LT', int(x) if x.isdigit() else 0))]
html = ['<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">',
        '<title>贴纸标签抽查图册</title>',
        '<style>body{font-family:sans-serif;margin:20px;background:#f7f7f7}',
        '.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}',
        '.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}',
        '.card img{width:100%;height:140px;object-fit:contain;background:#eee;border-radius:4px}',
        '.card h4{margin:6px 0 2px;font-size:13px}',
        '.tag{display:inline-block;background:#eef4ff;border:1px solid #c8d8f0;border-radius:10px;padding:1px 8px;margin:2px;font-size:12px}',
        '.ero1{background:#ffeef0;border-color:#f0b8c0}.meme{background:#fff8e6;border-color:#e8d48a}',
        '.meta{font-size:11px;color:#888;margin-top:4px}',
        'h2{font-size:16px;margin:24px 0 8px}</style></head><body>',
        '<h1>贴纸标签抽查图册（v2 分级）</h1>',
        '<p>共 <b id="cnt"></b> 条。情绪10类｜画风｜涩情0-3｜文字梗｜萌系。请重点看情绪标签是否贴切，涩情≥1 的用红色边框标出。</p>']

n = 0
for r in tags.values():
    rk = r['rank']
    is_lt = rk == 'LT'
    img = ''
    if not is_lt:
        fn = os.path.join(IMG_TOP, f'rank_{int(rk):03d}.gif')
        if os.path.exists(fn):
            img = f'<img src="{fn}" loading="lazy">'
    ero_cls = ' ero1' if str(r['ero']) != '0' else ''
    meme_cls = ' meme' if r['meme'] == '有' else ''
    title = f"#{rk}（使用{r['count']}次）" + (f'｜官方名:{r["summary"]}' if r['summary'] else '')
    tags_html = (f'<span class="tag">{r["emotion"]}</span>'
                 f'<span class="tag">{r["style"]}</span>'
                 f'<span class="tag{ero_cls}">涩情{r["ero"]}</span>'
                 f'<span class="tag{meme_cls}">文字梗:{r["meme"]}</span>'
                 f'<span class="tag">萌系:{r["moe"]}</span>')
    desc_p = f'<div class="meta">{r["desc_content"]}</div>' if r.get('desc_content') else ''
    html.append(f'<div class="card">{img}<h4>{title}</h4><div>{tags_html}</div>{desc_p}</div>')
    n += 1

html.append('</div></body></html>')
page = ''.join(html).replace('<div class="grid">', f'<div class="grid" id="g">', 1)
page = page.replace('<h1>贴纸标签抽查图册（v2 分级）</h1>',
                    f'<h1>贴纸标签抽查图册（v2 分级）</h1>\n<div class="grid">')
page = page.replace('<b id="cnt"></b>', f'<b id="cnt">{n}</b>')
with open('research/sticker_review.html', 'w', encoding='utf-8') as f:
    f.write(page)
print(f'\n[完成] 图册已生成: research/sticker_review.html（{n} 条）')

# -*- coding: utf-8 -*-
"""desc_analysis.py — 分析 gpt-5.5 自由描述，统计真实维度分布"""
import json
import re
from collections import Counter

recs = [json.loads(l) for l in open('research/sticker_desc.jsonl', encoding='utf-8') if l.strip()]
print(f'描述数: {len(recs)}')

STYLE_KEYS = ['Q版', '正常比例', '抽象', '扭曲', '像素', '真人', '拟人', '厚涂', '线稿', '水彩', '赛璐璐', '大头', '简笔', '火柴人', '表情包素材', '3D']
EMO_KEYS = ['害羞', '发呆', '装傻', '坏笑', '疲惫', '无语', '得意', '生气', '哭', '撒娇', '嫌弃', '委屈', '惊讶', '兴奋', '开心', '笑', '嘲讽', '无奈', '困', '冒汗', '流汗', '黑线', '白眼', '虚弱', '抓狂', '崩溃', '求饶', '装可爱', '高冷', '认真', '卖萌']
ERO_KEYS = ['涩', '色气', '色情', '性暗示', '情欲', '露骨', '擦边', '乳', '腿', '泳装', '内衣', '诱惑', '媚']
TEXT_KEYS = ['文字', '字', '文案', '台词', '标语', '字幕']

style_c = Counter(); emo_c = Counter(); ero_c = Counter(); text_c = Counter()
samples_style = Counter(); samples_emo = Counter()
erotic_list = []
for r in recs:
    d = r.get('desc') or {}
    s = json.dumps(d, ensure_ascii=False)
    for k in STYLE_KEYS:
        if k in s:
            style_c[k] += 1
            if style_c[k] <= 3:
                samples_style[k] += r['rank']
    for k in EMO_KEYS:
        if k in s:
            emo_c[k] += 1
            if emo_c[k] <= 3:
                samples_emo[k] += r['rank']
    ero = d.get('erotic') or ''
    if ero and '否' not in ero:
        erotic_list.append((r['rank'], ero[:40]))
        ero_c['是'] += 1
    else:
        ero_c['否'] += 1
    txt = d.get('text') or ''
    if txt and txt != '无':
        text_c['有文字'] += 1
        if text_c['有文字'] <= 8:
            text_c[f'样例{r["rank"]}'] = txt[:40]

print('\n=== 画风关键词频次（含样例rank）===')
for k, c in style_c.most_common():
    print(f'  {k}: {c}  (例: rank {samples_style.get(k, "")})')
print('\n=== 情绪关键词频次 ===')
for k, c in emo_c.most_common(25):
    print(f'  {k}: {c}  (例: rank {samples_emo.get(k, "")})')
print(f'\n=== 涩情标记 ===')
print(f'  是: {ero_c["是"]} / 否: {ero_c["否"]}')
for rank, e in erotic_list[:10]:
    print(f'  rank {rank}: {e}')
print(f'\n=== 有文字贴纸: {text_c["有文字"]} ===')
for k, v in text_c.items():
    if isinstance(v, str):
        print(f'  {k}: {v}')

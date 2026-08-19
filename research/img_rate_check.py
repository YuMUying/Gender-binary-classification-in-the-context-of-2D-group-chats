# -*- coding: utf-8 -*-
"""img_rate_check.py — 已标注用户：贴纸/图片覆盖率 vs 模型误判

问题：贴纸覆盖率高的用户，文本通道信息稀薄，是否更容易误判？
指标：image_rate（含图消息占比）、纯占位消息占比、平均有效字数
"""
import csv
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
    labels[r['user_id']] = r['gender']

import re
CJK = re.compile(r'[\u4e00-\u9fff]')
stats = {}
for r in conn.execute("SELECT user_id, raw_json, text FROM messages WHERE raw_json IS NOT NULL"):
    uid = r['user_id']
    if uid not in labels:
        continue
    s = stats.setdefault(uid, {'n': 0, 'img': 0, 'pure': 0, 'chars': 0})
    s['n'] += 1
    try:
        j = json.loads(r['raw_json'])
        has_img = any(isinstance(x, dict) and x.get('type') in ('image', 'market_face') for x in (j.get('message') or []))
    except Exception:
        has_img = False
    if has_img:
        s['img'] += 1
    txt = r['text'] or ''
    if not CJK.search(txt.replace('[图片', '').replace('[表情', '')):
        s['pure'] += 1
    else:
        s['chars'] += len(txt)
conn.close()

scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

print(f'{"QQ":<12}{"性别":<4}{"消息":<6}{"图率":<7}{"纯占位率":<9}{"均字/条":<8}{"P(女)":<7}{"预测":<7}正确')
rows = []
for uid, g in labels.items():
    s = stats.get(uid)
    sc = scores.get(uid)
    if not s or not sc:
        continue
    img_rate = s['img'] / s['n']
    pure_rate = s['pure'] / s['n']
    avg_chars = s['chars'] / max(s['n'] - s['pure'], 1)
    p = float(sc['prob_female_mean'])
    ok = sc['correct'] == '1'
    rows.append((uid, g, s['n'], img_rate, pure_rate, avg_chars, p, ok))
    print(f'{uid:<12}{g:<4}{s["n"]:<6}{img_rate:<7.2f}{pure_rate:<9.2f}{avg_chars:<8.1f}{p:<7.3f}{sc["predicted"]:<7}{"✓" if ok else "✗"}')

wrong = [r for r in rows if not r[7]]
right = [r for r in rows if r[7]]
import statistics
print(f'\n=== 误判组 vs 正确组 ===')
for name, grp in [('误判', wrong), ('正确', right)]:
    if not grp:
        continue
    print(f'{name} ({len(grp)}人): 图率均值={statistics.mean(r[3] for r in grp):.3f} 纯占位率={statistics.mean(r[4] for r in grp):.3f} 均字={statistics.mean(r[5] for r in grp):.1f}')
# 图率>=0.3的用户
hi = [r for r in rows if r[3] >= 0.3]
print(f'\n=== 高图率(>=0.3)用户 {len(hi)} 人 ===')
for r in hi:
    print(f'  {r[0]} {r[1]} 图率={r[3]:.2f} P(女)={r[6]:.3f} {"✗误判" if not r[7] else "✓"}')

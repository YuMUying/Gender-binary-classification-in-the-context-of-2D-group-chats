# -*- coding: utf-8 -*-
"""validate_disagree2.py — 干净四模型（v9a/b/c+v7）冲突指数验证（64 标注用户）"""
import csv
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
conn.close()

scores = {}
with open('outputs/score-v7-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        scores[int(r['user_id'])] = r

multi = {}
with open('outputs/score-multi-v9.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        multi[int(r['user_id'])] = r

rows = []
for uid, g in labels.items():
    s = scores.get(uid)
    m = multi.get(uid)
    if not s or not m:
        continue
    correct = s['predicted'] == g
    rows.append({
        'uid': uid, 'label': g, 'pred': s['predicted'], 'correct': correct,
        'flip': int(m.get('flip_count', 0)), 'bstd': float(m.get('boundary_std', 0) or 0),
        'disagree': m.get('disagreement', '低'),
        'vm': m.get('votes_male'), 'vf': m.get('votes_female'),
    })

n = len(rows)
err = [r for r in rows if not r['correct']]
print(f'已标注用户: {n}，v7 错误: {len(err)}（{len(err)/n:.1%}）\n')

for name, pred in [
    ('翻案≥1', lambda r: r['flip'] >= 1),
    ('翻案=0', lambda r: r['flip'] == 0),
    ('翻案≥2', lambda r: r['flip'] >= 2),
    ('分歧=高', lambda r: r['disagree'] == '高'),
    ('分歧=低', lambda r: r['disagree'] == '低'),
    ('票型分裂(2:2或1:3)', lambda r: r['vm'] != r['vf'] and (r['vm'] == 2 or r['vf'] == 2)),
    ('票型全一致(4:0)', lambda r: r['vm'] == 4 or r['vf'] == 4),
]:
    grp = [r for r in rows if pred(r)]
    if grp:
        e = sum(1 for r in grp if not r['correct'])
        print(f'{name}: {len(grp)} 人，错误 {e}（{e/len(grp):.1%}）')

print('\n=== v7 错误用户的四模型票型 ===')
for r in err:
    print(f'  {r["uid"]} 真={r["label"]} 预={r["pred"]} 票={r["vm"]}男{r["vf"]}女 翻案={r["flip"]} 分歧={r["disagree"]}')

# -*- coding: utf-8 -*-
"""merge_flip.py — 把 v6v7 翻案标记合并进标定参考包"""
import csv
import json

# v6/v7 翻案用户
flips = set()
rows = list(csv.DictReader(open('outputs/score-multi.csv', encoding='utf-8')))
thr6 = json.load(open('models/bert-v6/metrics.json', encoding='utf-8')).get('threshold', 0.5)
thr7 = json.load(open('models/bert-v7/metrics.json', encoding='utf-8')).get('threshold', 0.5)
for r in rows:
    p6, p7 = r.get('p_bert-v6'), r.get('p_bert-v7')
    if not p6 or not p7:
        continue
    pred6 = 'female' if float(p6) >= thr6 else 'male'
    pred7 = 'female' if float(p7) >= thr7 else 'male'
    if pred6 != pred7:
        flips.add(int(r['user_id']))
print(f'v6v7 翻案用户: {len(flips)}')

# 读参考包 md 和 csv，合并标记
md_path = 'outputs/标定参考包.md'
lines = open(md_path, encoding='utf-8').read().split('\n')
out = []
for line in lines:
    if line.startswith('| ') and 'v6v7' not in line:
        uid = line.split('|')[1].strip()
        if uid.isdigit() and int(uid) in flips:
            # 在提示列追加翻案标记（最后一列）
            cols = line.split('|')
            cols[-2] = cols[-2].strip() + '；v6v7翻案'
            line = '|'.join(cols)
    out.append(line)
open(md_path, 'w', encoding='utf-8').write('\n'.join(out))

csv_path = 'outputs/标定参考包.csv'
rows2 = list(csv.DictReader(open(csv_path, encoding='utf-8')))
fieldnames = list(rows2[0].keys()) + ['v6v7翻案']
with open(csv_path, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for r in rows2:
        r['v6v7翻案'] = '是' if int(r['QQ号']) in flips else ''
        w.writerow(r)
print(f'[完成] 已合并 {len(flips)} 个翻案标记 → 标定参考包.md/.csv')

# -*- coding: utf-8 -*-
"""merge_flip2.py — 用四模型翻案（v9a/b/c+v7，各模型自身阈值）替换参考包里的 v6v7 翻案列"""
import csv

flips = {}
with open('outputs/score-multi-v10.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        flips[int(r['user_id'])] = (int(r['flip_count']), f"{r['votes_male']}男{r['votes_female']}女", r['disagreement'])

# 更新 md
md = open('outputs/标定参考包.md', encoding='utf-8').read()
md = md.replace('v6v7翻案', '四模型翻案')
lines = md.split('\n')
out = []
for line in lines:
    if line.startswith('| ') and not line.startswith('| QQ'):
        uid = line.split('|')[1].strip()
        if uid.isdigit() and int(uid) in flips:
            f, vote, dis = flips[int(uid)]
            if f >= 1:
                cols = line.split('|')
                tag = f'四模型翻案×{f}({vote})'
                if '四模型翻案' in cols[-2]:
                    cols[-2] = cols[-2].strip()
                else:
                    cols[-2] = cols[-2].strip() + '；' + tag
                line = '|'.join(cols)
    out.append(line)
open('outputs/标定参考包.md', 'w', encoding='utf-8').write('\n'.join(out))

# 更新 csv：替换 v6v7翻案 列
rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
fn = [c for c in rows[0].keys() if c != 'v6v7翻案'] + ['四模型翻案', '票型']
with open('outputs/标定参考包.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fn)
    w.writeheader()
    for r in rows:
        uid = int(r['QQ号'])
        f, vote, dis = flips.get(uid, (0, '', '低'))
        r['四模型翻案'] = f if f >= 1 else ''
        r['票型'] = vote
        r.pop('v6v7翻案', None)
        w.writerow(r)
print(f'[完成] 参考包已更新（{sum(1 for v in flips.values() if v[0] >= 1)} 个翻案用户标记）')


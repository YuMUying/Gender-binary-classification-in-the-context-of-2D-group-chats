# -*- coding: utf-8 -*-
"""compare_v10_vs_multi.py — bert-v10 vs bert-v10-multi 对比分析"""
import csv
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}

def load(path):
    d = {}
    try:
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                d[int(r['user_id'])] = r
    except Exception as e:
        print(f'载入失败 {path}: {e}')
    return d

v10 = load('outputs/score-v10-all.csv')
v10m = load('outputs/score-v10-multi-all.csv')
print(f'v10: {len(v10)} 用户 | v10-multi: {len(v10m)} 用户')

common = set(v10) & set(v10m)
print(f'共同用户: {len(common)}')

# 整体对比（已标注用户）
known = [u for u in common if u in labels]
ok10 = sum(1 for u in known if v10[u]['predicted'] == labels[u])
okm = sum(1 for u in known if v10m[u]['predicted'] == labels[u])
print(f'\n=== 已标注用户一致率 ===')
print(f'v10: {ok10}/{len(known)} | v10-multi: {okm}/{len(known)}')

# 预测分歧用户
diff = [u for u in common if v10[u]['predicted'] != v10m[u]['predicted']]
print(f'\n=== 两模型预测分歧用户: {len(diff)} ===')
for u in diff[:30]:
    nick = conn.execute("SELECT MAX(nickname) n FROM messages WHERE user_id=?", (u,)).fetchone()['n']
    print(f'  {u} | {str(nick)[:10]} | 标注={labels.get(u, "未标注")} | v10={v10[u]["predicted"]}({v10[u]["prob_female_mean"]}) → v10m={v10m[u]["predicted"]}({v10m[u]["prob_female_mean"]})')

# 极端用户（图率>30%）对比
print(f'\n=== 极端用户（图率>30%，已标注）上的对比 ===')
import json
from collections import Counter
stats = {}
for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json IS NOT NULL"):
    uid = r['user_id']
    if uid not in common or uid not in labels:
        continue
    s = stats.setdefault(uid, {'n': 0, 'img': 0})
    s['n'] += 1
    try:
        j = json.loads(r['raw_json'])
        msgs = j.get('message') or []
        if isinstance(msgs, dict):
            msgs = [msgs]
        for seg in msgs:
            if isinstance(seg, dict) and seg.get('type') == 'image':
                s['img'] += 1
    except Exception:
        pass

ext = [(u, s) for u, s in stats.items() if s['n'] >= 30 and s['img'] / s['n'] >= 0.3]
ext.sort(key=lambda x: -x[1]['img'] / x[1]['n'])
print(f'高图率已标注用户: {len(ext)}')
ok10e = okme = 0
for u, s in ext:
    r10 = v10[u]['predicted'] == labels[u]
    rm = v10m[u]['predicted'] == labels[u]
    ok10e += r10
    okme += rm
    mark = '✓' if r10 == rm else 'Δ'
    print(f'  {u} | {labels[u]} | 图率={s["img"]/s["n"]:.2f} | v10={v10[u]["predicted"]}({v10[u]["prob_female_mean"]}) v10m={v10m[u]["predicted"]}({v10m[u]["prob_female_mean"]}) {mark}')
print(f'高图率用户一致率: v10 {ok10e}/{len(ext)} | v10-multi {okme}/{len(ext)}')
conn.close()

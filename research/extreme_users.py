# -*- coding: utf-8 -*-
"""extreme_users.py — 极端用户画像：图片/贴纸覆盖率过高的用户"""
import csv
import json
import sqlite3
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}

tags = {}
with open('outputs/贴纸标签v2.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r.get('url') and r.get('emotion'):
            tags[r['url']] = r

# 每用户：消息数、图片数、贴纸数、主要贴纸情感
stats = {}
for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json IS NOT NULL"):
    uid = r['user_id']
    s = stats.setdefault(uid, {'n_msg': 0, 'n_img': 0, 'n_tag': 0, 'em': Counter(), 'img_text': 0})
    s['n_msg'] += 1
    try:
        j = json.loads(r['raw_json'])
        msgs = j.get('message') or []
        if isinstance(msgs, dict):
            msgs = [msgs]
        for seg in msgs:
            if isinstance(seg, dict) and seg.get('type') == 'image':
                url = (seg.get('data') or {}).get('url') or ''
                s['n_img'] += 1
                t = tags.get(url)
                if t:
                    s['n_tag'] += 1
                    em = t.get('emotion') or ''
                    if em:
                        s['em'][em] += 1
    except Exception:
        pass

# 按图率排序，找极端用户（图率 > 0.3）
ext = []
for uid, s in stats.items():
    if s['n_msg'] < 30:
        continue
    rate = s['n_img'] / s['n_msg']
    if rate >= 0.3:
        ext.append((uid, s, rate))

ext.sort(key=lambda x: -x[2])
print(f'图率>=30% 的用户: {len(ext)}')
print(f'\n=== 极端用户列表（图率>=30%）===')
for uid, s, rate in ext[:30]:
    total_em = sum(s['em'].values())
    top = s['em'].most_common(2)
    lbl = labels.get(uid, '未标注')
    nick = conn.execute("SELECT MAX(nickname) n FROM messages WHERE user_id=?", (uid,)).fetchone()['n']
    print(f'  {uid} | {str(nick)[:10]} | {lbl} | 消息{s["n_msg"]} 图率={rate:.2f} 贴纸标签={total_em} 主要情感={top}')

# 图率最高的 5 个已标注用户的贴纸情感 vs 性别
print(f'\n=== 已标注高图率用户（图率>=20%）===')
cnt = 0
for uid, s, rate in sorted(((uid, s, s['n_img']/s['n_msg']) for uid, s in stats.items() if s['n_msg'] >= 30 and uid in labels), key=lambda x: -x[2]):
    if rate < 0.2:
        break
    cnt += 1
    total_em = sum(s['em'].values())
    top = s['em'].most_common(2)
    print(f'  {uid} | {labels[uid]} | 图率={rate:.2f} | 贴纸标签={total_em} | {top}')
print(f'共 {cnt} 人')
conn.close()

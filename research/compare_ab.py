# -*- coding: utf-8 -*-
"""compare_ab.py — v10 vs v10-synth vs v10-wb 三模型评估对比"""
import csv
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
nick = {}
for r in conn.execute("SELECT user_id, MAX(nickname) n FROM messages GROUP BY user_id"):
    nick[r['user_id']] = r['n']

MODELS = {
    'v10': 'outputs/score-v10-all.csv',
    'v10-synth': 'outputs/score-v10-synth-all.csv',
    'v10-wb': 'outputs/score-v10-wb-all.csv',
    'v10-synth-yandere': 'outputs/score-v10-synth-yandere-all.csv',
    'v10-all': 'outputs/score-v10-all-all.csv',
}

data = {}
for name, path in MODELS.items():
    d = {}
    try:
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                d[int(r['user_id'])] = r
    except Exception as e:
        print(f'{name}: 载入失败 {e}')
    data[name] = d

print('=== 全库已知标签一致率 ===')
for name, d in data.items():
    if not d:
        continue
    known = [u for u in d if u in labels]
    ok = sum(1 for u in known if d[u]['predicted'] == labels[u])
    # 按性别分开
    m_ok = sum(1 for u in known if labels[u] == 'male' and d[u]['predicted'] == 'male')
    m_n = sum(1 for u in known if labels[u] == 'male')
    f_ok = sum(1 for u in known if labels[u] == 'female' and d[u]['predicted'] == 'female')
    f_n = sum(1 for u in known if labels[u] == 'female')
    print(f'  {name}: {ok}/{len(known)} ({ok/max(len(known),1)*100:.1f}%) | 男 {m_ok}/{m_n} | 女 {f_ok}/{f_n}')

# 已知 hard case（女判男历史）
print('\n=== 历史 hard case 用户预测 ===')
hard = [u for u in labels if labels[u] == 'female']
for u in sorted(hard, key=lambda x: -int(data['v10'].get(x, {}).get('n_messages', 0) or 0)):
    row = f'  {u} | {str(nick.get(u, ""))[:10]} | {labels[u]}'
    for name, d in data.items():
        if u in d:
            row += f' | {name}={d[u]["predicted"]}({d[u]["prob_female_mean"]})'
    print(row)

# 极端用户（图率>30%）
print('\n=== 高图率已标注用户对比 ===')
import json
stats = {}
for r in conn.execute("SELECT user_id, raw_json FROM messages WHERE raw_json IS NOT NULL"):
    uid = r['user_id']
    if uid not in labels:
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
print(f'高图率用户: {len(ext)}')
for u, s in sorted(ext, key=lambda x: -x[1]['img'] / x[1]['n'])[:15]:
    row = f'  {u} | {labels[u]} | 图率={s["img"]/s["n"]:.2f}'
    for name, d in data.items():
        if u in d:
            row += f' | {name}={d[u]["predicted"]}({d[u]["prob_female_mean"]})'
    print(row)
conn.close()

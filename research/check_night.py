# -*- coding: utf-8 -*-
"""check_night.py — 深夜活跃度性别区分度 + 284256062 消息构成"""
import sqlite3
import re
from collections import Counter

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 已标注用户（含刚标注的 3202322974=female, 2498419003=male）
labels = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
print(f'已标注: {Counter(labels.values())}')

# 1) 284256062 消息构成
print('\n=== 284256062 消息构成 ===')
r = conn.execute("SELECT COUNT(*) c FROM messages WHERE user_id=284256062").fetchone()
print(f'总消息: {r["c"]}')
samples = conn.execute("SELECT text FROM messages WHERE user_id=284256062 LIMIT 20").fetchall()
ph = 0; txt = 0
for row in conn.execute("SELECT text FROM messages WHERE user_id=284256062"):
    t = row['text'] or ''
    if re.match(r'^\[.*\]$', t.strip()) or '[图片' in t or '[表情' in t:
        ph += 1
    else:
        txt += 1
print(f'占位符类: {ph} | 有文本: {txt}')
for s in samples[:10]:
    print('  ', repr(s['text'][:60]))

# 2) 深夜活跃度（0-6点消息占比）按性别
print('\n=== 深夜活跃度(0-6点占比) 按性别 ===')
night = {}
for r in conn.execute("""
    SELECT user_id, 
           SUM(CASE WHEN strftime('%H', time, 'unixepoch', '+8 hours') IN ('00','01','02','03','04','05') THEN 1 ELSE 0 END) night,
           COUNT(*) c
    FROM messages WHERE user_id IN ({}) AND LENGTH(text) > 4
    GROUP BY user_id""".format(','.join(str(u) for u in labels))):
    uid = r['user_id']
    if r['c'] >= 50:
        night[uid] = r['night'] / r['c']

m_n = [v for u, v in night.items() if labels[u] == 'male']
f_n = [v for u, v in night.items() if labels[u] == 'female']
import statistics
def desc(x):
    return f'n={len(x)} 均值={statistics.mean(x):.3f} 中位={statistics.median(x):.3f}' if x else 'n=0'
print('男 深夜占比:', desc(m_n))
print('女 深夜占比:', desc(f_n))
# 深夜活跃 top
print('\n深夜占比 Top10 用户:')
for u, v in sorted(night.items(), key=lambda x: -x[1])[:10]:
    print(f'  {u} | {labels[u]} | 深夜占比={v:.3f}')

# 3) 深夜消息的文本风格差异（男女在深夜 vs 白天的粗口率）
print('\n=== 深夜 vs 白天 粗口率（按性别）===')
curse = re.compile(r'卧槽|我操|我草|妈的|他妈的|草泥马|淦|草了')
for g in ('male', 'female'):
    day_c = day_n = night_c = night_n = 0
    for r in conn.execute("""
        SELECT strftime('%H', time, 'unixepoch', '+8 hours') h, text FROM messages 
        WHERE user_id IN ({}) AND LENGTH(text) > 4""".format(','.join(str(u) for u in labels if labels[u] == g))):
        if r['h'] in ('00','01','02','03','04','05'):
            night_n += 1
            if curse.search(r['text'] or ''): night_c += 1
        else:
            day_n += 1
            if curse.search(r['text'] or ''): day_c += 1
    print(f'{g}: 白天粗口率={day_c/max(day_n,1):.4f} ({day_c}/{day_n}) | 深夜粗口率={night_c/max(night_n,1):.4f} ({night_c}/{night_n})')
conn.close()

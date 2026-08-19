# -*- coding: utf-8 -*-
"""check_missing2.py — 深入验证：导出消息是否真在库内"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 表结构
for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'"):
    print('TABLE:', r[0])
for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='messages'"):
    print('IDX:', r[0], '|', r[1])

# 群1 最早/最晚
r = conn.execute("SELECT MIN(time) mn, MAX(time) mx, COUNT(*) c FROM messages WHERE scene='group' AND peer_id=826904606").fetchone()
print(f'群1: min={datetime.fromtimestamp(r["mn"], cst) if r["mn"] else None} max={datetime.fromtimestamp(r["mx"], cst) if r["mx"] else None} count={r["c"]}')

# 导出批次
data = json.load(open(r'C:\Users\Lenovo\.qq-chat-exporter\exports\group_826904606_20260818_213447.json', encoding='utf-8'))
msgs = data['messages']
m = msgs[0]
mid = str(m['id'])
t_ms = m['timestamp']
print(f'样例消息: id={mid} time={datetime.fromtimestamp(t_ms/1000, cst)} sender_uin={m["sender"].get("uin")}')

# 1) 该 id 是否在库
hit = conn.execute('SELECT COUNT(*) c FROM messages WHERE message_id=?', (mid,)).fetchone()['c']
print(f'样例 id 在库: {hit}')
# 2) 该 id 是否以其它形式存在
for pat in (mid, int(mid), f'{int(mid):x}'):
    hit = conn.execute('SELECT COUNT(*) c FROM messages WHERE message_id=?', (str(pat),)).fetchone()['c']
    if hit:
        print(f'  id 变体 {str(pat)[:20]} 命中 {hit}')

# 3) 同发送者同时刻是否有库内消息
lo = t_ms/1000 - 5; hi = t_ms/1000 + 5
rows = conn.execute('SELECT message_id, user_id, time, substr(text,1,60) t FROM messages WHERE scene="group" AND peer_id=826904606 AND time BETWEEN ? AND ? AND user_id=?',
                    (lo, hi, m['sender']['uin'])).fetchall()
print(f'同人±5s 库内消息: {len(rows)}')
for r in rows:
    print('   ', r['message_id'][:25], r['user_id'], datetime.fromtimestamp(r['time'], cst), r['t'])

# 4) 全部 1031 条 id 在库命中数
ids = [str(x['id']) for x in msgs]
hit_all = conn.execute(f'SELECT COUNT(*) c FROM messages WHERE message_id IN ({",".join("?" for _ in ids)})', ids).fetchone()['c']
print(f'1031 条导出 id 中库内已有: {hit_all}')

# 5) 该窗口时间(11:32~23:32)库内消息数
lo2 = t_ms/1000
hi2 = lo2 + 12*3600
n = conn.execute('SELECT COUNT(*) c FROM messages WHERE scene="group" AND peer_id=826904606 AND time BETWEEN ? AND ?', (lo2, hi2)).fetchone()['c']
print(f'导出批次时间窗口内库内消息数: {n}')
conn.close()

# -*- coding: utf-8 -*-
"""check_missing.py — 验证缺失区前提：导出批次的消息 id 是否真不在库里"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 群1 最早时间
r = conn.execute("SELECT MIN(time) mn, COUNT(*) c FROM messages WHERE scene='group' AND peer_id=826904606").fetchone()
from datetime import datetime, timezone, timedelta
cst = timezone(timedelta(hours=8))
print(f'群1 库内最早: {datetime.fromtimestamp(r["mn"], cst)} | 消息数: {r["c"]}')

# 导出批次的消息 id 抽查
data = json.load(open(r'C:\Users\Lenovo\.qq-chat-exporter\exports\group_826904606_20260818_213447.json', encoding='utf-8'))
msgs = data.get('messages') or []
print(f'导出批次消息数: {len(msgs)}')
sample = msgs[0]
mid = str(sample.get('id') or '')
t = sample.get('timestamp') or sample.get('time') or 0
print(f'样例: id={mid} time={datetime.fromtimestamp(t, cst) if t else "?"}')
hit = conn.execute('SELECT COUNT(*) c FROM messages WHERE message_id=?', (mid,)).fetchone()['c']
print(f'  该 id 在库中: {hit} 条')
# 时间范围内的库内消息数
if t:
    lo = t - 3600
    hi = t + 3600
    n = conn.execute('SELECT COUNT(*) c FROM messages WHERE scene="group" AND peer_id=826904606 AND time BETWEEN ? AND ?', (lo, hi)).fetchone()['c']
    print(f'  该消息时间±1h 内库内群1消息: {n} 条')
# 全部导出 id 的命中率
ids = [str(m.get('id') or '') for m in msgs if m.get('id')]
ph = ','.join('?' for _ in ids[:500])
if len(ids) > 500:
    c1 = conn.execute(f'SELECT COUNT(*) c FROM messages WHERE message_id IN ({ph})', ids[:500]).fetchone()['c']
    print(f'前500个id中库内已有: {c1}')
else:
    c1 = conn.execute(f'SELECT COUNT(*) c FROM messages WHERE message_id IN ({ph})', ids).fetchone()['c']
    print(f'全部{len(ids)}个id中库内已有: {c1}')
conn.close()

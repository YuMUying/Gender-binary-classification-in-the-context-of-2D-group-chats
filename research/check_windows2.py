# -*- coding: utf-8 -*-
import sqlite3, json
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('--- DB message_seq 抽查（群1） ---')
for r in conn.execute("SELECT message_seq, typeof(message_seq) t, time, substr(text,1,30) txt FROM messages WHERE scene='group' AND peer_id=826904606 AND message_seq IS NOT NULL LIMIT 5"):
    print(dict(r))

print('--- 导出文件 seq 抽查 ---')
data = json.load(open(r'C:\Users\Lenovo\.qq-chat-exporter\exports\group_826904606_20260818_213447.json', encoding='utf-8'))
for m in data['messages'][:3]:
    print({'id': m['id'], 'seq': m['seq'], 'time': m['time'], 'sender_uin': m['sender'].get('uin')})

# 已知区窗口
print('--- 已知区窗口（每4000条）前5个 ---')
rows = conn.execute("SELECT time FROM messages WHERE scene='group' AND peer_id=826904606 AND time>0 ORDER BY time").fetchall()
times = [r['time'] for r in rows]
n_win = (len(times) + 3999) // 4000
print(f'总消息数: {len(times)}, 4000条/批 → {n_win} 批')
for i in range(min(5, n_win)):
    chunk = times[i*4000:(i+1)*4000]
    print(f'批{i}: {datetime.fromtimestamp(chunk[0], cst)} ~ {datetime.fromtimestamp(chunk[-1], cst)} ({len(chunk)}条, 窗口{(chunk[-1]-chunk[0])/3600:.1f}h)')

# seq 重复性检查：DB 里 message_seq 是否唯一
dup = conn.execute("SELECT message_seq, COUNT(*) c FROM messages WHERE scene='group' AND peer_id=826904606 AND message_seq IS NOT NULL GROUP BY message_seq HAVING c>1 LIMIT 3").fetchall()
print('--- DB seq 重复样例:', [dict(d) for d in dup])
conn.close()

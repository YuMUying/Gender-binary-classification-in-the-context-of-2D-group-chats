# -*- coding: utf-8 -*-
"""audit_envelopes.py — 全量审计：每个信封展开状态 + 消息归属"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

HAPPY_START = 1786937400
HAPPY_END = 1786940100

rows = conn.execute("""
    SELECT forward_id, envelope_time, fetched_at, content_raw FROM forwards 
    WHERE envelope_user=2633083674 ORDER BY envelope_time""").fetchall()

print(f'信封总数: {len(rows)}')
fwd_total = conn.execute("SELECT COUNT(*) FROM messages WHERE source='forward'").fetchone()[0]
print(f'messages 表 source=forward 总数: {fwd_total}')

# 每个信封：内容消息数、入库命中数
total_happy = 0   # HAPPY 窗口信封中 1094950020 消息数
total_other = 0   # 其他窗口信封中 1094950020 消息数
happy_in_db = 0   # 这些消息在 messages 表（source=forward）的数量
other_in_db = 0

for r in rows:
    try:
        j = json.loads(r['content_raw'])
        msgs = j.get('messages') or []
        is_happy = r['envelope_time'] and HAPPY_START <= r['envelope_time'] <= HAPPY_END
        n109 = sum(1 for m in msgs if str(m.get('user_id')) == '1094950020')
        if is_happy:
            total_happy += n109
        else:
            total_other += n109
        # 检查 messages 表命中：取该信封 1094950020 消息的 real_id
        ids = [m.get('real_id') or m.get('message_id') for m in msgs if str(m.get('user_id')) == '1094950020' and (m.get('real_id') or m.get('message_id'))]
        if ids:
            ph = ','.join('?' for _ in ids[:400])
            n = conn.execute(f"SELECT COUNT(*) FROM messages WHERE source='forward' AND message_id IN ({ph})", ids[:400]).fetchone()[0]
            if is_happy:
                happy_in_db += n
            else:
                other_in_db += n
        et = datetime.fromtimestamp(r['envelope_time'] or 0, cst)
        ft = datetime.fromtimestamp(r['fetched_at'] or 0, cst) if r['fetched_at'] else None
        print(f'  fwd={str(r["forward_id"])[:22]} | 信封={et.strftime("%m-%d %H:%M")} | 抓取={ft.strftime("%m-%d %H:%M") if ft else "?"} | 109消息={n109} | {"HAPPY窗口" if is_happy else "合疯窗口"}')
    except Exception as e:
        print(f'  fwd={str(r["forward_id"])[:22]} 解析失败: {e}')

print(f'\nHAPPY 窗口 1094950020 消息(内容): {total_happy} | 入库命中(前400): {happy_in_db}')
print(f'合疯窗口 1094950020 消息(内容): {total_other} | 入库命中(前400): {other_in_db}')
conn.close()

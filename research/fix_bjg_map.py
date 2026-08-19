# -*- coding: utf-8 -*-
"""fix_bjg_map.py — 纠正映射：合疯信封改回，仅白驹过隙信封归 3615168664"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

def ids_of_envelopes(start, end):
    rows = conn.execute("""
        SELECT forward_id, envelope_time, content_raw FROM forwards 
        WHERE envelope_user=2633083674 AND envelope_time BETWEEN ? AND ?""", (start, end)).fetchall()
    ids = set()
    for r in rows:
        try:
            j = json.loads(r['content_raw'])
            for m in (j.get('messages') or []):
                if str(m.get('user_id')) != '1094950020':
                    continue
                mid = m.get('real_id') or m.get('message_id')
                if mid is not None:
                    ids.add(mid)
        except Exception:
            pass
    return ids

def remap(ids, to_uid, to_nick, from_uids=(1046636617, 3615168664, 1094950020)):
    total = 0
    for i in range(0, len(ids), 400):
        chunk = list(ids)[i:i+400]
        ph = ','.join('?' for _ in chunk)
        cur = conn.execute(f"""
            UPDATE messages SET user_id=?, nickname=?
            WHERE source='forward' AND user_id IN ({','.join('?' for _ in from_uids)}) AND message_id IN ({ph})""",
            [to_uid, to_nick, *from_uids, *chunk])
        total += cur.rowcount
    return total

# 1) 合疯窗口（8-19 01:12-01:20）→ 改回 1046636617
hefeng = ids_of_envelopes(1787069400, 1787072700)   # 8-19 01:10 ~ 01:25
print(f'合疯窗口信封消息 id: {len(hefeng)}')
n1 = remap(hefeng, 1046636617, '合疯')
print(f'改回合疯: {n1} 条')

# 2) 白驹过隙窗口（8-18 17:30-18:00 + 8-19 10:00-10:10）→ 3615168664
bjg1 = ids_of_envelopes(1787031000, 1787032800)   # 8-18 17:30 ~ 18:00
bjg2 = ids_of_envelopes(1787083200, 1787086200)   # 8-19 10:00 ~ 10:10
bjg = bjg1 | bjg2
print(f'白驹过隙窗口信封消息 id: {len(bjg)}（17:30段{len(bjg1)} + 10:00段{len(bjg2)}）')
n2 = remap(bjg, 3615168664, '白驹过隙')
print(f'映射到白驹过隙: {n2} 条')
conn.commit()

# 验证
for uid, name in ((1046636617, '合疯'), (3615168664, '白驹过隙')):
    r = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (uid,)).fetchone()
    print(f'{name}({uid}) 总消息: {r[0]}')
# 残留占位符检查
r = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=1094950020").fetchone()
print(f'占位符 1094950020 剩余: {r[0]}')
conn.close()

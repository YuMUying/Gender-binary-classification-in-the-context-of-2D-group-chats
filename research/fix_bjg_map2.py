# -*- coding: utf-8 -*-
"""fix_bjg_map2.py — 用 forward_id 前缀精确分组纠正"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

def ids_of(envelope_prefix):
    rows = conn.execute("""
        SELECT content_raw FROM forwards 
        WHERE envelope_user=2633083674 AND forward_id LIKE ?""", (envelope_prefix + '%',)).fetchall()
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

def remap(ids, to_uid, to_nick):
    total = 0
    for i in range(0, len(ids), 400):
        chunk = list(ids)[i:i+400]
        ph = ','.join('?' for _ in chunk)
        cur = conn.execute(f"""
            UPDATE messages SET user_id=?, nickname=?
            WHERE source='forward' AND user_id IN (1094950020, 1046636617, 3615168664) AND message_id IN ({ph})""",
            [to_uid, to_nick, *chunk])
        total += cur.rowcount
    return total

# 合疯：7675425464671617xxx（8-19 01:12-01:20）
hefeng = ids_of('7675425464671617')
print(f'合疯信封 id: {len(hefeng)}')
n1 = remap(hefeng, 1046636617, '合疯')
print(f'改回合疯: {n1}')

# 白驹过隙：7675550606991033221（8-18 17:42）+ 7675557xxx（8-19 10:01-10:04）
bjg = ids_of('7675550606991033221') | ids_of('7675557')
print(f'白驹过隙信封 id: {len(bjg)}')
n2 = remap(bjg, 3615168664, '白驹过隙')
print(f'映射白驹过隙: {n2}')
conn.commit()

for uid, name in ((1046636617, '合疯'), (3615168664, '白驹过隙')):
    r = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=?", (uid,)).fetchone()
    print(f'{name}({uid}) 总消息: {r[0]}')
r = conn.execute("SELECT COUNT(*) FROM messages WHERE user_id=1094950020").fetchone()
print(f'占位符剩余: {r[0]}')
conn.close()

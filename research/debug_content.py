# -*- coding: utf-8 -*-
"""debug_content.py — 查看 content_raw 原始结构"""
import json
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

# 取 HAPPY 窗口第一个信封和最后一个
r1 = conn.execute("SELECT * FROM forwards WHERE envelope_user=2633083674 ORDER BY envelope_time LIMIT 1").fetchone()
r2 = conn.execute("SELECT * FROM forwards WHERE envelope_user=2633083674 ORDER BY envelope_time DESC LIMIT 1").fetchone()

for label, r in (('最早信封', r1), ('最新信封', r2)):
    print(f'=== {label}: fwd={r["forward_id"]} env_time={r["envelope_time"]} ===')
    print('content_raw 前 600 字符:')
    print((r['content_raw'] or '')[:600])
    try:
        j = json.loads(r['content_raw'])
        print('顶层 keys:', list(j.keys()) if isinstance(j, dict) else type(j))
        msgs = j.get('messages') if isinstance(j, dict) else j
        print(f'messages 数: {len(msgs) if isinstance(msgs, list) else "?"}')
        if isinstance(msgs, list) and msgs:
            m = msgs[0]
            print('首条消息 keys:', list(m.keys()) if isinstance(m, dict) else type(m))
            print('首条 user_id:', repr(m.get('user_id')), '| sender:', m.get('sender'))
    except Exception as e:
        print('解析失败:', e)
    print()
conn.close()

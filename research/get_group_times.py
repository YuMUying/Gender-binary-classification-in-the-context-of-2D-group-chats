# -*- coding: utf-8 -*-
"""get_group_times.py — 输出某群全部消息时间（unix秒，空格分隔）供 batcher 使用"""
import sqlite3
import sys

group = int(sys.argv[1]) if len(sys.argv) > 1 else 826904606
conn = sqlite3.connect('data/qqchat.db')
times = [r[0] for r in conn.execute(
    "SELECT time FROM messages WHERE scene='group' AND peer_id=? AND time > 0 ORDER BY time", (group,))]
conn.close()
print(' '.join(str(t) for t in times))

# -*- coding: utf-8 -*-
"""try_read_ntmsg.py — 尝试读取 NTQQ 本地消息库"""
import sqlite3

p = r'C:\Users\Lenovo\Documents\Tencent Files\2740088195\nt_qq\nt_db\nt_msg.db'
try:
    conn = sqlite3.connect(p)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print('读取成功! 表:', tables[:40])
    conn.close()
except Exception as e:
    print('读取失败:', type(e).__name__, str(e)[:300])
    # 检查文件头
    with open(p, 'rb') as f:
        head = f.read(64)
    print('文件头:', head[:32])

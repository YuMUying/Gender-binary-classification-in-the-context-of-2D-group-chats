# -*- coding: utf-8 -*-
"""declare_debug.py — 检查常见性别自述表述的实际出现量"""
import sqlite3

conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
patterns = [
    '我是男的', '我是男生', '我是男人', '我是男的啊', '我是个男的',
    '我是女生', '我是女的', '我是妹子', '我是小萝莉', '我是萝莉',
    '我前女友', '我前男友', '我女朋友', '我男朋友',
    '性别男', '性别女', '性别:男', '性别：女',
    '本直男', '老娘', '爷们', '大老爷们', '我是gay', '我是les',
    '我是个女生', '我是个男的', '我是个大老爷们',
]
for p in patterns:
    c = conn.execute("SELECT COUNT(*) c FROM messages WHERE text LIKE ?", (f'%{p}%',)).fetchone()['c']
    if c:
        print(f'{p}: {c}')
conn.close()

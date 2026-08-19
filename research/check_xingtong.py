# -*- coding: utf-8 -*-
"""check_xingtong.py — 星瞳 2049014399 全部证据"""
import csv
import sqlite3
from datetime import datetime, timezone, timedelta

cst = timezone(timedelta(hours=8))
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row

print('=== 参考包数据 ===')
with open('outputs/标定参考包.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if int(r['QQ号']) == 2049014399:
            for k, v in r.items():
                print(f'  {k}: {v}')
            break

print('\n=== v10 预测 ===')
with open('outputs/score-v10-all.csv', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if int(r['user_id']) == 2049014399:
            for k, v in r.items():
                print(f'  {k}: {v}')
            break

print('\n=== 网络性别（profile_genders）===')
for r in conn.execute("SELECT * FROM profile_genders WHERE user_id=2049014399"):
    print(' ', dict(r))

print('\n=== 性别自述检测（gender_declare）===')
try:
    for r in conn.execute("SELECT * FROM gender_declarations WHERE user_id=2049014399"):
        print(' ', dict(r))
except Exception as e:
    print('  无 gender_declarations 表或查询失败:', e)

print('\n=== 发言抽样（最近 15 条有效文本）===')
for r in conn.execute("""
    SELECT time, text FROM messages WHERE user_id=2049014399 AND LENGTH(text) >= 4 
    AND text NOT LIKE '[%' ORDER BY time DESC LIMIT 15"""):
    t = datetime.fromtimestamp(r['time'], cst)
    print(f'  {t.strftime("%m-%d %H:%M")} | {r["text"][:60]}')

print('\n=== 深夜占比 ===')
r = conn.execute("""
    SELECT COUNT(*) c, SUM(CASE WHEN strftime('%H', time, 'unixepoch', '+8 hours') IN ('00','01','02','03','04','05') THEN 1 ELSE 0 END) n
    FROM messages WHERE user_id=2049014399""").fetchone()
print(f'  深夜: {r["n"]}/{r["c"]} = {r["n"]/max(r["c"],1):.2f}')
conn.close()

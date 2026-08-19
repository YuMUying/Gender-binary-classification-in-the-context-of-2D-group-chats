# -*- coding: utf-8 -*-
"""today_stats.py — 今日落地数据统计"""
import csv
import json
import os
import sqlite3

print('=== 1. 数据库消息 ===')
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
for r in conn.execute("SELECT scene, source, COUNT(*) c FROM messages GROUP BY scene, source ORDER BY c DESC"):
    print(f'  {r["scene"]}/{r["source"]}: {r["c"]:,}')
total = conn.execute("SELECT COUNT(*) c FROM messages").fetchone()['c']
print(f'  messages 总数: {total:,}')
labels = conn.execute("SELECT COUNT(*) c FROM speaker_labels WHERE gender IN ('male','female')").fetchone()['c']
print(f'  有效标注: {labels} 人')
conn.close()

print('\n=== 2. 贴纸标签表 ===')
rows = list(csv.DictReader(open('outputs/贴纸标签v2.csv', encoding='utf-8')))
from collections import Counter
c = Counter(r['rank'][:2] for r in rows)
print(f'  总行数: {len(rows)}（Top200={c["1"]+c["2"]+c["3"]+c["4"]+c["5"]+c["6"]+c["7"]+c["8"]+c["9"]}  LT={c["LT"]}  HV={c["HV"]}  HB={c["HB"]}）')

print('\n=== 3. 本地收割图片 ===')
for d in ('data/media/harvest', 'data/media/qce-harvest'):
    if os.path.isdir(d):
        n = len(os.listdir(d))
        sz = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) / 1e6
        print(f'  {d}: {n} 张, {sz:.0f} MB')
n_res = len(os.listdir(r'C:\Users\Lenovo\.qq-chat-exporter\resources\images')) if os.path.isdir(r'C:\Users\Lenovo\.qq-chat-exporter\resources\images') else 0
print(f'  qce资源目录: {n_res} 张')

print('\n=== 4. 模型与标签数据 ===')
print('  erotic-bert 模型: 存在' if os.path.isdir('models/erotic-bert') else '  缺失')
n_erotic = sum(1 for l in open('research/erotic_labels.jsonl', encoding='utf-8') if l.strip())
print(f'  涩情标签: {n_erotic} 条')
n_decl = sum(1 for l in open('research/gender_declare_labels.jsonl', encoding='utf-8') if l.strip())
print(f'  自述标签: {n_decl} 条')
n_ava = sum(1 for l in open('research/avatar_desc.jsonl', encoding='utf-8') if l.strip())
print(f'  头像描述: {n_ava} 条')
n_avf = len(os.listdir('data/avatars')) if os.path.isdir('data/avatars') else 0
print(f'  头像文件: {n_avf} 张')
n_prof = conn = sqlite3.connect('data/qqchat.db'); n = conn.execute('SELECT COUNT(*) c FROM profile_details').fetchone()['c']; conn.close()
print(f'  主页详情: {n} 人')

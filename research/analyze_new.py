# -*- coding: utf-8 -*-
"""analyze_new.py — 新参考包分析：女性候选 + 指数变化"""
import csv
import sqlite3

rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
print(f'参考包共 {len(rows)} 人')

# 已标注对照
conn = sqlite3.connect('data/qqchat.db')
conn.row_factory = sqlite3.Row
labeled = {r['user_id']: r['gender'] for r in conn.execute(
    "SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')")}
conn.close()

# P(女) 高 + 样本充足
cand = [r for r in rows if float(r['P(女)']) >= 0.5 and int(r['消息数']) >= 100]
cand.sort(key=lambda r: -float(r['P(女)']))
print(f'\n=== P(女)>=0.5 且样本>=100 的未标注女性候选: {len(cand)} 人 ===')
for r in cand[:25]:
    print(f"{r['QQ号']} | {r['昵称'][:12]} | {r['消息数']}条 | P(女)={r['P(女)']} | {r['模型结论']}/{r['置信度']} | "
          f"翻案={r.get('四模型翻案','')} {r.get('票型','')} | MSI={r.get('男侧证据指数','')} RI={r.get('复核指数','')} | {r['提示'][:36]}")

# 强候选：P(女) 高且 MSI 低（无男侧冲突）
strong = [r for r in cand if float(r.get('男侧证据指数') or 0) < 35]
print(f'\n=== 其中 MSI<35（无男侧冲突，最可能为女）: {len(strong)} 人 ===')
for r in strong[:15]:
    print(f"{r['QQ号']} | {r['昵称'][:12]} | {r['消息数']}条 | P(女)={r['P(女)']} | 票型={r.get('票型','')} | RI={r.get('复核指数','')}")

# 高翻案用户（指数变化关注点）
print('\n=== 翻案>=2 的未标注用户 ===')
fl = [r for r in rows if str(r.get('四模型翻案','')).replace('四模型翻案×','').isdigit() and int(str(r.get('四模型翻案','')).replace('四模型翻案×','')) >= 2]
for r in fl[:15]:
    print(f"{r['QQ号']} | {r['昵称'][:12]} | {r['消息数']}条 | P(女)={r['P(女)']} | {r.get('四模型翻案','')} {r.get('票型','')} | MSI={r.get('男侧证据指数','')} RI={r.get('复核指数','')}")

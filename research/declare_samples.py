# -*- coding: utf-8 -*-
"""declare_samples.py — 查看自述判定样本"""
import json

recs = [json.loads(l) for l in open('research/gender_declare_labels.jsonl', encoding='utf-8') if l.strip()]
print(f'共 {len(recs)} 条')
for r in recs[:20]:
    print(f'{r["user_id"]} 自述={r["declared"]} 事实={r["factual"]} conf={r["conf"]} | {r["text"][:40]!r} | {r.get("reason","")[:40]}')

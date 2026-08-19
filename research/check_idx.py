# -*- coding: utf-8 -*-
"""check_idx.py — 抽查综合指数"""
import csv

rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
rows.sort(key=lambda r: -(float(r['复核指数']) + float(r['男侧证据指数'])))
print('按 MSI+RI 总分排序 top10:')
for r in rows[:10]:
    p = r['P(女)']
    print(f'  {r["QQ号"]} {r["昵称"]}: MSI={r["男侧证据指数"]} RI={r["复核指数"]} P(女)={p} 提示={r["综合提示"]}')
print()
ri_hi = [r for r in rows if float(r['复核指数']) >= 50]
print(f'RI>=50 必复核: {len(ri_hi)} 人')
for r in ri_hi:
    print(f'  {r["QQ号"]} {r["昵称"]}: RI={r["复核指数"]} MSI={r["男侧证据指数"]} P(女)={r["P(女)"]}')

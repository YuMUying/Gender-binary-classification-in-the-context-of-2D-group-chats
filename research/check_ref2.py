# -*- coding: utf-8 -*-
"""check_ref2.py — 抽查参考包翻案标记"""
import csv

rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
flip = [r for r in rows if r.get('四模型翻案')]
print(f'参考包内翻案用户: {len(flip)}')
for r in flip[:8]:
    print(f'  {r["QQ号"]} {r["昵称"]}: 翻案x{r["四模型翻案"]} 票型={r["票型"]} P(女)={r["P(女)"]} 提示={r["提示"][:30]}')

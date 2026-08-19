# -*- coding: utf-8 -*-
"""check_speech.py — 抽查话语指数在参考包中的效果"""
import csv

rows = list(csv.DictReader(open('outputs/标定参考包.csv', encoding='utf-8')))
tips = [r for r in rows if r.get('话语提示')]
print(f'触发话语提示的用户: {len(tips)} 人')
for r in sorted(tips, key=lambda x: -float(x['话语指数']))[:12]:
    print(f'  {r["QQ号"]} {r["昵称"]}: 指数={r["话语指数"]} (性发泄{r["性发泄率"]}/粗口{r["粗口率"]}/叫爹{r["叫爹率"]}) 提示={r["话语提示"]} P(女)={r["P(女)"]}')
print()
print('=== 高指数用户的 P(女) 分布（看是否与判女冲突）===')
for r in sorted(rows, key=lambda x: -float(x['话语指数']))[:10]:
    print(f'  {r["QQ号"]} {r["昵称"]}: 指数={r["话语指数"]} P(女)={r["P(女)"]} 结论={r["模型结论"]}')

# -*- coding: utf-8 -*-
"""inspect_export.py — 打印 qce 导出 JSON 的真实结构"""
import json

p = r'C:\Users\Lenovo\.qq-chat-exporter\exports\group_826904606_20260818_213447.json'
data = json.load(open(p, encoding='utf-8'))
print('顶层 keys:', list(data.keys()))
msgs = data.get('messages') or []
print('消息数:', len(msgs))
m = msgs[0]
print('单条消息 keys:', list(m.keys()))
for k, v in m.items():
    vs = str(v)
    print(f'  {k}: {type(v).__name__} = {vs[:200]}')
print('\n--- 第二条 ---')
m2 = msgs[1]
for k, v in m2.items():
    vs = str(v)
    print(f'  {k}: {type(v).__name__} = {vs[:200]}')

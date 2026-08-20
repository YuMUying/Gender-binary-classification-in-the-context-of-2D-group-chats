# -*- coding: utf-8 -*-
"""xnn_integrate.py — 把 XNN 男娘指数 + LGBT 指数并入标定参考包 CSV/MD

从 outputs/xnn_index.csv（男娘）+ outputs/lgbt_index.csv（小众性取向）读取，
按 QQ号 合并进 标定参考包.csv，新增列: 男娘指数, 男娘提示, 小众性取向指数
"""
import csv

xnn_map = {}
with open("outputs/xnn_index.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            xnn_map[int(row["QQ号"])] = float(row["XNN男娘指数"])
        except (ValueError, KeyError):
            continue

lgbt_map = {}
with open("outputs/lgbt_index.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            lgbt_map[int(row["QQ号"])] = float(row["LGBT小众性取向指数"])
        except (ValueError, KeyError):
            continue

def xnn_tip(v):
    if v >= 80:
        return "男娘信号强（男娘/女装话题+稀有萌系词密集）"
    if v >= 60:
        return "男娘信号中"
    if v >= 45:
        return "男娘信号弱"
    return ""

def lgbt_tip(v):
    if v >= 80:
        return "小众性取向信号强（百合/BL/耽美话题密集）"
    if v >= 60:
        return "小众性取向信号中"
    if v >= 45:
        return "小众性取向信号弱"
    return ""

rows = list(csv.DictReader(open("outputs/标定参考包.csv", encoding="utf-8")))
fn = list(rows[0].keys()) + ["男娘指数", "男娘提示", "小众性取向指数", "小众性取向提示"]
with open("outputs/标定参考包.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fn)
    w.writeheader()
    for r in rows:
        uid = int(r["QQ号"])
        x = xnn_map.get(uid)
        l = lgbt_map.get(uid)
        r["男娘指数"] = f"{x:.0f}" if x is not None else ""
        r["男娘提示"] = xnn_tip(x) if x is not None else ""
        r["小众性取向指数"] = f"{l:.0f}" if l is not None else ""
        r["小众性取向提示"] = lgbt_tip(l) if l is not None else ""
        w.writerow(r)

n_xnn = sum(1 for r in rows if r["男娘指数"])
n_lgbt = sum(1 for r in rows if r["小众性取向指数"])
print(f"[完成] 标定参考包.csv 已更新（男娘指数 {n_xnn}/{len(rows)}，小众性取向 {n_lgbt}/{len(rows)}）")

md = open("outputs/标定参考包.md", encoding="utf-8").read()
if "男娘指数（XNN" not in md:
    md += '''
## 男娘指数（XNN，v4 独立）
- **男娘话题**（女装/伪娘/男娘/药娘/丝袜/小裙子/jk/lo裙/白丝/黑丝/穿裙/女装大佬）× 2.5
- **稀有萌系**（qwq/QAQ/TAT/叭/诶嘿/Orz/OvO/OwO/嘤嘤/呜呜/捏~）× 3.0
- **自称女性**（人家/咱家/本小姐/伦家/奴家/妾身/本宫/小妹）× 1.3
- 0-100 连续分；样本 <300 条自动降权
- 定位：男娘相关信号强度（供人工参考；"谈论男娘"与"自身是男娘"需人工甄别）

## 小众性取向指数（LGBT，v4 独立）
- **百合/BL**（百合/gl向/耽美/同人女/嗑cp/磕cp/bl向/bl文/同人文）× 2.2
- **同性恋话题**（南通/基佬/弯了/弯的/gay/男同/给子/txl/通讯录/出柜）× 1.5
- 独立于男娘指数（男娘话题 ≠ 小众性取向，两者分开评估）
'''
    open("outputs/标定参考包.md", "w", encoding="utf-8").write(md)
    print("[完成] 标定参考包.md 已追加 XNN/LGBT 说明")

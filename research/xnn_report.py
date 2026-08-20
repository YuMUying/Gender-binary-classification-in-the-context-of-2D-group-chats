# -*- coding: utf-8 -*-
"""xnn_report.py — 生成 XNN 男娘指数 + LGBT 指数报告"""
import csv
import sqlite3
from datetime import datetime

xnn = {}
with open("outputs/xnn_index.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            xnn[int(row["QQ号"])] = (int(row["消息数"]), float(row["XNN男娘指数"]))
        except (ValueError, KeyError):
            continue

lgbt = {}
with open("outputs/lgbt_index.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            lgbt[int(row["QQ号"])] = (int(row["消息数"]), float(row["LGBT小众性取向指数"]))
        except (ValueError, KeyError):
            continue

conn = sqlite3.connect("data/qqchat.db")
conn.row_factory = sqlite3.Row
labels = {}
for r in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
    labels[r["user_id"]] = r["orientation"]
conn.close()

lines = []
lines.append("# XNN 男娘指数 + LGBT 小众性取向指数报告（v4）")
lines.append("")
lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append("")
lines.append("## 方法")
lines.append("")
lines.append("**双指数分离**（男娘 ≠ 小众性取向，独立评估）：")
lines.append("")
lines.append("| 指数 | 特征 | 权重依据 |")
lines.append("|---|---|---|")
lines.append("| **XNN 男娘** | 男娘话题(女装/伪娘/男娘/丝袜/小裙子/jk/lo裙/白丝/黑丝) ×2.5 + 稀有萌系(qwq/QAQ/叭/诶嘿/呜呜) ×3.0 + 自称女性(人家/本小姐/伦家) ×1.3 | 词级区分度 1.8~2.7× |")
lines.append("| **LGBT 小众性取向** | 百合/BL(百合/耽美/同人女/嗑cp) ×2.2 + 同性恋话题(南通/基佬/弯了/gay) ×1.5 | 百合BL 2.2× 区分；南通梗人人用降权 |")
lines.append("")
lines.append("指数 = 100·sigmoid(加权分)，样本 <300 条自动降权向 50 收缩。")
lines.append("")
lines.append("## 真实 orientation 用户对照")
lines.append("")
lines.append("| QQ号 | 标签 | 消息数 | XNN男娘 | LGBT小众 |")
lines.append("|---|---|---|---|---|")
ranked_x = sorted(xnn.items(), key=lambda kv: -kv[1][1])
for uid, (n, x) in ranked_x:
    if uid in labels:
        l = lgbt.get(uid, (0, 0))[1]
        lines.append(f"| {uid} | {labels[uid]} | {n} | {x:.0f} | {l:.0f} |")
lines.append("")
lines.append("> 男娘指数高 ≠ 小众性取向高（如 375569635 男娘 26/LGBT 0；2633083674 男娘 42/LGBT 100），两者独立。")
lines.append("")
lines.append("## XNN 男娘指数 TOP 20（未标注）")
lines.append("")
lines.append("| 排名 | QQ号 | 消息数 | XNN |")
lines.append("|---|---|---|---|")
rank = 1
for uid, (n, x) in ranked_x:
    if uid in labels:
        continue
    lines.append(f"| {rank} | {uid} | {n} | {x:.0f} |")
    rank += 1
    if rank > 20:
        break
lines.append("")
lines.append("## LGBT 指数 TOP 15（未标注）")
lines.append("")
lines.append("| 排名 | QQ号 | 消息数 | LGBT |")
lines.append("|---|---|---|---|")
rank = 1
for uid, (n, l) in sorted(lgbt.items(), key=lambda kv: -kv[1][1]):
    if uid in labels:
        continue
    lines.append(f"| {rank} | {uid} | {n} | {l:.0f} |")
    rank += 1
    if rank > 15:
        break
lines.append("")
lines.append("## 文件")
lines.append("")
lines.append("- `outputs/xnn_index.csv` — 772 人男娘指数")
lines.append("- `outputs/lgbt_index.csv` — 772 人小众性取向指数")
lines.append("- 参考包 `标定参考包.csv` — 已并入双指数列")

with open("outputs/XNN报告.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("[完成] outputs/XNN报告.md")

# -*- coding: utf-8 -*-
"""构建带伪标签的 FOI 训练集（伪标签用户按软标签 0.6 加入）"""
import csv
import json
import sqlite3

# 伪标签候选（统计 FOI>=50, 消息>=300, 未标注）
PSEUDO = {2865728637: 0.6, 2159492514: 0.6, 3969964584: 0.6, 3236380896: 0.6}
PSEUDO_SOFT = 0.6

conn = sqlite3.connect("data/qqchat.db")
conn.row_factory = sqlite3.Row

def rows_for_user(uid, cap=2000):
    return [dict(r) for r in conn.execute("""
        SELECT user_id, peer_id AS group_id, time, text, CAST(message_id AS TEXT) AS message_id, nickname, card
        FROM messages WHERE user_id=? AND scene IN ('group','private') AND LENGTH(text)>=2
        ORDER BY time ASC""", (uid,)).fetchall()][:cap]

# 生成伪标签样本行（label='foi', soft=0.6, pseudo=true）
lines = []
for uid, soft in PSEUDO.items():
    for r in rows_for_user(uid):
        row = {
            "text": r["text"], "user_id": r["user_id"], "group_id": r["group_id"],
            "time": r["time"], "label": "foi", "soft": soft, "pseudo": True,
        }
        if r.get("nickname") is not None:
            row["nickname"] = r["nickname"]
        if r.get("card"):
            row["card"] = r["card"]
        lines.append(json.dumps(row, ensure_ascii=False))
print(f"伪标签样本: {len(lines)} 行（{len(PSEUDO)} 用户, soft={PSEUDO_SOFT}）")

with open("data/foi-pseudo.jsonl", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("已写出 data/foi-pseudo.jsonl")
conn.close()

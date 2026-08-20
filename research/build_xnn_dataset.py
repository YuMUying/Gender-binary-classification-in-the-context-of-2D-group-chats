# -*- coding: utf-8 -*-
"""构建 XNN 训练集：真实男娘 + 大规模伪标签（统计XNN>=50 & n>=100）+ 正常男
每用户采样 cap=500 条（轻量训练）"""
import collections
import csv
import json
import sqlite3

PSEUDO_THR = 50
PSEUDO_MIN_N = 100
CAP = 500

xnn_map = {}
with open("outputs/xnn_index.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            xnn_map[int(row["QQ号"])] = (int(row["消息数"]), float(row["XNN男娘指数"]))
        except (ValueError, KeyError):
            continue

conn = sqlite3.connect("data/qqchat.db")
conn.row_factory = sqlite3.Row

# 真实阳性（男娘相关，排除纯同性恋）
pos_real = {}
for r in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
    if r["orientation"] != "同性恋":
        pos_real[r["user_id"]] = r["orientation"]

# 伪标签候选
labeled = set(r["user_id"] for r in conn.execute("SELECT user_id FROM speaker_labels WHERE gender IN ('male','female')"))
pseudo = {}
for u, (n, x) in xnn_map.items():
    if u not in labeled and x >= PSEUDO_THR and n >= PSEUDO_MIN_N:
        pseudo[u] = x

# 正常男
normal_male = set(r["user_id"] for r in conn.execute("SELECT user_id FROM speaker_labels WHERE gender='male'")) - set(pos_real)

print(f"真实阳性: {len(pos_real)} 人")
print(f"伪标签: {len(pseudo)} 人（XNN>={PSEUDO_THR}, n>={PSEUDO_MIN_N}）")
print(f"正常男: {len(normal_male)} 人")


def rows_for_user(uid, cap=CAP):
    return [dict(r) for r in conn.execute("""
        SELECT user_id, peer_id AS group_id, time, text, CAST(message_id AS TEXT) AS message_id, nickname, card
        FROM messages WHERE user_id=? AND scene IN ('group','private') AND LENGTH(text)>=2
        ORDER BY time ASC""", (uid,)).fetchall()][:cap]


def build_row(r, label, extra=None):
    row = {"text": r["text"], "user_id": r["user_id"], "group_id": r["group_id"], "time": r["time"], "label": label}
    if r.get("nickname") is not None:
        row["nickname"] = r["nickname"]
    if r.get("card"):
        row["card"] = r["card"]
    if extra:
        row.update(extra)
    return row


lines = []
for uid in pos_real:
    for r in rows_for_user(uid):
        lines.append(json.dumps(build_row(r, "foi"), ensure_ascii=False))
for uid, x in pseudo.items():
    for r in rows_for_user(uid):
        lines.append(json.dumps(build_row(r, "foi", {"pseudo": True, "soft": 0.6}), ensure_ascii=False))
for uid in normal_male:
    for r in rows_for_user(uid):
        lines.append(json.dumps(build_row(r, "normal"), ensure_ascii=False))

with open("data/xnn-train.jsonl", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

cnt = collections.Counter()
for line in lines:
    d = json.loads(line)
    if d.get("pseudo"):
        cnt["foi_pseudo"] += 1
    else:
        cnt[d["label"]] += 1
print(f"\n训练集: {len(lines)} 行")
print(f"  真实阳性: {cnt.get('foi', 0)} 行")
print(f"  伪标签: {cnt.get('foi_pseudo', 0)} 行")
print(f"  正常男: {cnt.get('normal', 0)} 行")
print("已写出 data/xnn-train.jsonl")
conn.close()

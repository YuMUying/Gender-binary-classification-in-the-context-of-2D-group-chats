# -*- coding: utf-8 -*-
"""foi_mix.py — FOI 混合指数：统计特征指数 × 0.4 + BERT 概率指数 × 0.6

输入：
  outputs/foi_index.csv    统计特征 FOI（v3，词级区分度）
  outputs/foi_pred.csv     BERT 概率（foi_predict.py 输出，含 p_mean / foi_index）
输出：
  outputs/foi_final.csv    混合指数（0-100）+ 置信区间 + 消息数 + 标签对照
"""
import csv

STAT_W = 0.4   # 统计特征权重
BERT_W = 0.6   # BERT 训练结果权重（用户要求：权重更倾向于训练结果）

def load_csv(path):
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[int(row["QQ号"] if "QQ号" in row else row["user_id"])] = row
    except FileNotFoundError:
        pass
    return out

stat_map = load_csv("outputs/foi_index.csv")
bert_map = load_csv("outputs/foi_pred.csv")

all_uids = set(stat_map) | set(bert_map)
rows_out = []
for uid in all_uids:
    s = stat_map.get(uid)
    b = bert_map.get(uid)
    # 统计指数（0-100）归一化
    stat_foi = float(s["FOI指数"]) if s and s.get("FOI指数") else None
    # BERT 概率指数：p_mean → 0-100（0.2→0, 0.8→100）
    bert_foi = None
    if b:
        p = float(b["p_mean"])
        bert_foi = 100 * max(0, min(1, (p - 0.2) / 0.6))
    # 混合：两者都有 → 加权；只有其一 → 用其本身（缺 BERT 时统计为主）
    if stat_foi is not None and bert_foi is not None:
        mix = STAT_W * stat_foi + BERT_W * bert_foi
        src = "both"
    elif bert_foi is not None:
        mix = bert_foi
        src = "bert"
    elif stat_foi is not None:
        mix = stat_foi
        src = "stat"
    else:
        continue
    n_msgs = int(b["n_messages"]) if b else (int(s["消息数"]) if s else 0)
    ci = float(b["ci95"]) if b and b.get("ci95") else None
    # 置信区间映射到指数单位（ci95 是概率 CI，×100/0.6）
    ci_foi = 100 * ci / 0.6 if ci else None
    rows_out.append({
        "user_id": uid, "n_messages": n_msgs,
        "stat_foi": round(stat_foi, 1) if stat_foi is not None else "",
        "bert_foi": round(bert_foi, 1) if bert_foi is not None else "",
        "foi_index": round(mix, 1),
        "ci95_foi": round(ci_foi, 1) if ci_foi else "",
        "source": src,
        "orientation": b.get("orientation", "") if b else (s.get("FOI提示", "") if s else ""),
    })

rows_out.sort(key=lambda r: -r["foi_index"])
with open("outputs/foi_final.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["user_id", "n_messages", "stat_foi", "bert_foi",
                                      "foi_index", "ci95_foi", "source", "orientation"])
    w.writeheader()
    for r in rows_out:
        w.writerow(r)
print(f"[完成] outputs/foi_final.csv（{len(rows_out)} 人）")
print("\n=== 混合指数 TOP 20 ===")
for r in rows_out[:20]:
    print(f"  {r['user_id']} n={r['n_messages']} stat={r['stat_foi']} bert={r['bert_foi']} "
          f"FOI={r['foi_index']} [{r['source']}] {r['orientation']}")

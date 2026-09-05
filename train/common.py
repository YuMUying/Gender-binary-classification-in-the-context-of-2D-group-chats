# -*- coding: utf-8 -*-
"""训练侧共用工具：数据加载、文本组装、用户级评估、阈值校准"""
import csv
import json
import os
from collections import defaultdict

LABEL_MAP = {"male": 0, "female": 1}
ID2LABEL = {0: "male", 1: "female"}


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def prepare_text(row, use_nickname=False, use_context=False, use_avatar=False, use_profile=False):
    """组装一条样本的输入文本（与导出格式对应）"""
    parts = []
    if use_avatar and row.get("avatar_desc"):
        parts.append(f"[头像:{row['avatar_desc']}]")
    if use_profile and row.get("profile_meta"):
        parts.append(f"[主页:{row['profile_meta']}]")
    if use_nickname:
        meta = []
        if row.get("nickname"):
            meta.append(str(row["nickname"]))
        if row.get("card"):
            meta.append(str(row["card"]))
        if meta:
            parts.append("[" + "/".join(meta) + "]")
    if use_context:
        before = row.get("before") or []
        after = row.get("after") or []
        ctx = before + [row.get("text", "")] + after
        parts.append("\n".join(ctx))
    else:
        parts.append(row.get("text", ""))
    return "\n".join(parts).strip()


def user_level_report(user_ids, y_true, y_score, threshold=0.5):
    """用户级聚合评估：每人分数=其消息分数的均值；标签=该人多数标签"""
    users = defaultdict(lambda: {"scores": [], "label": None})
    for uid, y, s in zip(user_ids, y_true, y_score):
        users[uid]["scores"].append(s)
        if users[uid]["label"] is None:
            users[uid]["label"] = y
    rows = []
    for uid, d in users.items():
        score = sum(d["scores"]) / len(d["scores"])
        rows.append({
            "user_id": uid,
            "true": ID2LABEL[d["label"]],
            "score": round(score, 4),
            "pred": ID2LABEL[1 if score >= threshold else 0],
            "n_msgs": len(d["scores"]),
        })
    rows.sort(key=lambda r: -r["n_msgs"])
    correct = sum(1 for r in rows if r["pred"] == r["true"])
    return {"rows": rows, "accuracy": correct / len(rows) if rows else 0.0,
            "n_users": len(rows), "correct": correct}


def message_metrics(y_true, y_pred, y_score):
    from sklearn.metrics import (accuracy_score, precision_recall_fscore_support,
                                 roc_auc_score, average_precision_score)
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=[0, 1], zero_division=0)
    out = {
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": float((f1[0] + f1[1]) / 2),
        "male_precision": p[0], "male_recall": r[0], "male_f1": f1[0],
        "female_precision": p[1], "female_recall": r[1], "female_f1": f1[1],
    }
    if len(set(y_true)) == 2:
        out["pr_auc"] = float(average_precision_score(y_true, y_score))
        out["roc_auc"] = float(roc_auc_score(y_true, y_score))
    return out


def best_threshold_by_users(user_ids, y_true, y_score, lo=0.05, hi=0.95, step=0.01):
    """在验证集上按用户级准确率/宏观表现选阈值"""
    best_t, best_acc, best_rows = 0.5, -1, None
    for t in [round(lo + i * step, 3) for i in range(int((hi - lo) / step) + 1)]:
        rep = user_level_report(user_ids, y_true, y_score, threshold=t)
        if rep["accuracy"] > best_acc:
            best_acc, best_t, best_rows = rep["accuracy"], t, rep
    return best_t, best_acc, best_rows


def write_user_csv(path, report_rows):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["user_id", "true", "pred", "score", "n_msgs"])
        w.writeheader()
        for r in report_rows:
            w.writerow(r)


def print_report(tag, msg_metrics, user_report):
    print(f"\n===== {tag} =====")
    if msg_metrics:
        print(f"[消息级] acc={msg_metrics['accuracy']:.4f} macroF1={msg_metrics['macro_f1']:.4f} "
              f"女recall={msg_metrics['female_recall']:.4f} 女F1={msg_metrics['female_f1']:.4f}")
        if "pr_auc" in msg_metrics:
            print(f"          PR-AUC={msg_metrics['pr_auc']:.4f} ROC-AUC={msg_metrics['roc_auc']:.4f}")
    print(f"[用户级] {user_report['correct']}/{user_report['n_users']} 人正确 "
          f"(acc={user_report['accuracy']:.4f})")
    wrong = [r for r in user_report["rows"] if r["pred"] != r["true"]]
    if wrong:
        print("错分用户（建议用 export-context.js 复核其发言，可能是标签问题）:")
        for r in wrong:
            print(f"  QQ {r['user_id']}  真={r['true']} 预={r['pred']} 分数={r['score']} 条数={r['n_msgs']}")

# -*- coding: utf-8 -*-
"""基线模型：TF-IDF + 逻辑回归

两种模式：
  --mode message : 逐条消息分类（每消息一个样本），评估时聚合到用户级
  --mode user    : 按人聚合（每人全部发言拼成一个文档），直接用户级分类

用法：
  python train/baseline_tfidf.py --train data/train.jsonl --val data/val.jsonl --mode message
  python train/baseline_tfidf.py --train data/train.jsonl --val data/val.jsonl --mode user
"""
import argparse
import json
import os
import random
from collections import defaultdict

from common import (LABEL_MAP, ID2LABEL, load_jsonl, prepare_text,
                    message_metrics, user_level_report, best_threshold_by_users,
                    write_user_csv, print_report)


def aug_text(text, method, rng):
    """少数类文本增广（基线仅支持 dup / eda；ctx 回退为 dup）"""
    if method in ("dup", "ctx"):
        return text
    if method == "eda" and len(text) > 4:
        chars = list(text)
        if rng.random() < 0.5:
            for _ in range(rng.randint(1, 2)):
                if len(chars) > 2:
                    del chars[rng.randrange(len(chars))]
        else:
            i = rng.randrange(len(chars) - 1)
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        return "".join(chars)
    return text


def oversample_arrays(X, y, u, method, k, seed=42):
    """对 label=1 样本扩增（返回新数组）"""
    if not method or method == "none" or k <= 1.0:
        return X, y, u
    rng = random.Random(seed)
    ex_x, ex_y, ex_u = [], [], []
    for i in range(len(y)):
        if y[i] != 1:
            continue
        copies = int(k) - 1 + (1 if rng.random() < (k - int(k)) else 0)
        for _ in range(copies):
            ex_x.append(aug_text(X[i], method, rng))
            ex_y.append(1)
            ex_u.append(u[i])
    print(f"[过采样] {method} x{k}: 少数类样本 {sum(1 for v in y if v == 1)} → {sum(1 for v in y if v == 1) + len(ex_x)}")
    return X + ex_x, y + ex_y, u + ex_u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/train.jsonl")
    ap.add_argument("--extra-train", default="", help="追加的合成/增广训练数据（逗号分隔）")
    ap.add_argument("--val", default="data/val.jsonl")
    ap.add_argument("--mode", default="message", choices=["message", "user"])
    ap.add_argument("--use-nickname", action="store_true", help="文本前拼接 [昵称/群名片]")
    ap.add_argument("--use-context", action="store_true", help="使用导出时的 before/after 上下文")
    ap.add_argument("--oversample", default="none", choices=["none", "dup", "eda", "ctx"],
                    help="少数类(female)过采样: dup=复制 / eda=字符级扰动 / ctx=等价dup")
    ap.add_argument("--oversample-k", type=float, default=2.0, help="少数类扩增倍数")
    ap.add_argument("--min-df", type=int, default=3)
    ap.add_argument("--max-features", type=int, default=100000)
    ap.add_argument("--top-k", type=int, default=30, help="输出最性别化的词数量")
    ap.add_argument("--out-dir", default="outputs")
    args = ap.parse_args()

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    train_rows = load_jsonl(args.train)
    for extra_path in [p.strip() for p in args.extra_train.split(",") if p.strip()]:
        if os.path.exists(extra_path):
            extra = load_jsonl(extra_path)
            print(f"[数据] 追加合成样本 {extra_path}: {len(extra)} 条（仅训练集）")
            train_rows = train_rows + extra
    val_rows = load_jsonl(args.val) if os.path.exists(args.val) else []
    if not train_rows:
        raise SystemExit("训练集为空：请先采集数据并 export-dataset.js --mode train")

    os.makedirs(args.out_dir, exist_ok=True)

    X_train, y_train, u_train = [], [], []
    for r in train_rows:
        X_train.append(prepare_text(r, args.use_nickname, args.use_context))
        y_train.append(LABEL_MAP[r["label"]])
        u_train.append(r["user_id"])
    X_val, y_val, u_val = [], [], []
    for r in val_rows:
        X_val.append(prepare_text(r, args.use_nickname, args.use_context))
        y_val.append(LABEL_MAP[r["label"]])
        u_val.append(r["user_id"])

    if args.mode == "user":
        # 按人聚合：每人一个文档
        def agg(rows):
            docs, ys, us = defaultdict(list), {}, []
            for r in rows:
                docs[r["user_id"]].append(prepare_text(r, args.use_nickname, args.use_context))
                ys[r["user_id"]] = LABEL_MAP[r["label"]]
            for uid in docs:
                us.append((uid, "\n".join(docs[uid]), ys[uid]))
            return us
        tr = agg(train_rows)
        va = agg(val_rows) if val_rows else []
        X_train = [x[1] for x in tr]; y_train = [x[2] for x in tr]; u_train = [x[0] for x in tr]
        X_train, y_train, u_train = oversample_arrays(X_train, y_train, u_train, args.oversample, args.oversample_k)
        if va:
            X_val = [x[1] for x in va]; y_val = [x[2] for x in va]; u_val = [x[0] for x in va]
        print(f"[baseline user模式] 训练用户 {len(tr)} 人，验证用户 {len(va)} 人")

    X_train, y_train, u_train = oversample_arrays(X_train, y_train, u_train, args.oversample, args.oversample_k)

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 4),
                          min_df=args.min_df, max_features=args.max_features)
    Xt = vec.fit_transform(X_train)
    clf = LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0)
    clf.fit(Xt, y_train)

    # 性别化词汇（LR 权重最高的词）
    coefs = sorted(zip(vec.get_feature_names_out(), clf.coef_[0]), key=lambda x: -x[1])
    top_female = coefs[:args.top_k]
    top_male = sorted(coefs, key=lambda x: x[1])[:args.top_k]
    terms_path = os.path.join(args.out_dir, "baseline-terms.txt")
    with open(terms_path, "w", encoding="utf-8") as f:
        f.write("最像女生的词/字: " + " ".join(w for w, _ in top_female) + "\n")
        f.write("最像男生的词/字: " + " ".join(w for w, _ in top_male) + "\n")
    print(f"性别化词表已保存: {terms_path}（女: {' '.join(w for w,_ in top_female[:15])}）")

    if args.mode == "user" and va:
        y_pred = clf.predict(vec.transform(X_val)).tolist()
        y_score = clf.predict_proba(vec.transform(X_val))[:, 1].tolist()
        rep = user_level_report(u_val, y_val, y_score)
        print_report("baseline(user模式)", None, rep)
        write_user_csv(os.path.join(args.out_dir, "baseline-users.csv"), rep["rows"])
        return

    if not val_rows:
        print("未提供 val.jsonl，跳过评估（建议 export-dataset.js --split-by-user 生成）")
        return

    y_pred = clf.predict(vec.transform(X_val)).tolist()
    y_score = clf.predict_proba(vec.transform(X_val))[:, 1].tolist()
    m = message_metrics(y_val, y_pred, y_score)
    t, acc, rep = best_threshold_by_users(u_val, y_val, y_score)
    rep2 = user_level_report(u_val, y_val, y_score, threshold=t)
    print_report("baseline(message模式)", m, rep2)
    print(f"[校准] 最优用户级阈值={t:.2f} (acc={acc:.4f})")
    write_user_csv(os.path.join(args.out_dir, "baseline-users.csv"), rep2["rows"])


if __name__ == "__main__":
    main()

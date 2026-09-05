# -*- coding: utf-8 -*-
"""三分类(style_class)训练变体: male=0 / soft_male=1 / female=2

基于 train_bert.py（v16 二分类管线）复制改造；二分类管线保持不动（生产 bert-v10-wb-fix）。
- num_labels=3, 行级 weight 字段照常生效（外部数据 w0.6）
- 评估: 用户级 argmax + 每类准确率 + 混淆矩阵（无阈值概念）
- --user-weight 用户均衡采样照常

用法:
  python train/train_bert3.py --train trainsets/gender-v17-train.jsonl \
      --val trainsets/gender-v17-val.jsonl --out-dir models/bert-v17-3class \
      --epochs 4 --user-weight --use-nickname --batch 32 --seed 7
"""
import argparse
import json
import os
import time
import random
from collections import defaultdict, Counter

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler

from common import load_jsonl, prepare_text

LABEL3 = {"male": 0, "soft_male": 1, "female": 2}
ID2L3 = {0: "male", 1: "soft_male", 2: "female"}


class ChatDataset3(Dataset):
    def __init__(self, rows, tokenizer, max_len, use_nickname, use_context, user_doc, user_doc_chars,
                 oversample="none", oversample_k=2.0, aug_seed=42, user2idx_override=None):
        self.samples = []          # (uid, text, label, raw_row|None)
        self.user_msg_count = defaultdict(int)
        self.user_ids = set()
        for r in rows:
            if r.get("label") not in LABEL3:
                continue
            self.user_msg_count[r["user_id"]] += 1
            self.user_ids.add(r["user_id"])
        self.user2idx = user2idx_override if user2idx_override is not None else \
            {u: i for i, u in enumerate(sorted(self.user_ids))}

        if user_doc:
            docs = defaultdict(list)
            user_label = {}
            for r in rows:
                if r.get("label") not in LABEL3:
                    continue
                docs[r["user_id"]].append(prepare_text(r, use_nickname, use_context))
                user_label[r["user_id"]] = LABEL3[r["label"]]
            for uid, lines in docs.items():
                buf, n = [], 0
                for line in lines:
                    buf.append(line)
                    n += len(line)
                    if n >= user_doc_chars:
                        self.samples.append((uid, "\n".join(buf), user_label[uid], None))
                        buf, n = [], 0
                if buf:
                    self.samples.append((uid, "\n".join(buf), user_label[uid], None))
        else:
            for r in rows:
                if r.get("label") not in LABEL3:
                    continue
                self.samples.append((r["user_id"], prepare_text(r, use_nickname, use_context),
                                     LABEL3[r["label"]], r))

        # 少数类过采样：只作用于 female(y=2)（默认不启用，user-weight 已均衡）
        if oversample and oversample != "none" and oversample_k > 1.0:
            rng = random.Random(aug_seed)
            minority = [s for s in self.samples if s[2] == 2]
            extra = []
            for uid, text, y, row in minority:
                copies = int(oversample_k) - 1 + (1 if rng.random() < (oversample_k - int(oversample_k)) else 0)
                for _ in range(copies):
                    extra.append((uid, text, y, row))
            self.samples.extend(extra)
            print(f"[过采样] female x{oversample_k}: {len(minority)} → {len(minority) + len(extra)}")

        self.tokenizer = tokenizer
        self.max_len = max_len
        # 预tokenize: 批量一次性编码(Rust fast tokenizer批模式), 训练期直接查表
        # 消除每epoch重复tokenize(4轮60万次 → 15万次×1)
        print(f"[预tokenize] 批量编码{len(self.samples)}条...", flush=True)
        _t0 = time.time()
        texts = [s[1] for s in self.samples]
        _enc = self.tokenizer(texts, max_length=self.max_len, truncation=True,
                              padding="max_length", return_tensors="np")
        self.enc_ids = _enc["input_ids"].astype(np.int64)
        self.enc_mask = _enc["attention_mask"].astype(np.int64)
        print(f"[预tokenize] 完成 ({time.time() - _t0:.0f}s)", flush=True)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        uid, text, y, row = self.samples[i]
        try:
            w = float(row.get('weight', 1.0) or 1.0)
        except (TypeError, ValueError, AttributeError):
            w = 1.0   # doc 模式样本无 row 字典
        return {
            "input_ids": torch.from_numpy(self.enc_ids[i]),
            "attention_mask": torch.from_numpy(self.enc_mask[i]),
            "label": y,
            "user_idx": self.user2idx.get(uid, -1),
            "uid": uid,
            "weight": w,
        }


def user_report(uids, ys, P):
    """用户级: 平均概率 → argmax。返回 (acc, per_class, confusion, rows)"""
    agg = defaultdict(lambda: [None, np.zeros(3)])
    for u, y, p in zip(uids, ys, P):
        agg[u][0] = y
        agg[u][1] += p
    rows = []
    for u, (y, s) in sorted(agg.items()):
        pred = int(s.argmax())
        rows.append((u, y, pred, (s / max(1e-9, s.sum())).tolist()))
    acc = sum(1 for _, y, pr, _ in rows if y == pr) / max(1, len(rows))
    # 二元折叠(2026-09-04用户裁决): SM在acc层归入M — 本项目最终目标=性别二分, soft是风格不是性别
    # 女性准确率 = 真F判F; 男性准确率 = 真M/SM 判 male或soft_male(非F)
    f_true = [r for r in rows if r[1] == 2]
    m_true = [r for r in rows if r[1] in (0, 1)]
    bin_f = sum(1 for r in f_true if r[2] == 2) / max(1, len(f_true))
    bin_m = sum(1 for r in m_true if r[2] != 2) / max(1, len(m_true))
    bin_acc = (bin_f * len(f_true) + bin_m * len(m_true)) / max(1, len(rows))
    per = {}
    for c in range(3):
        t = [r for r in rows if r[1] == c]
        hit = sum(1 for r in t if r[2] == c)
        per[ID2L3[c]] = {"users": len(t), "acc": round(hit / max(1, len(t)), 3)}
    conf = Counter((ID2L3[y], ID2L3[p]) for _, y, p, _ in rows)
    per["binary_female"] = {"users": len(f_true), "acc": round(bin_f, 3)}
    per["binary_male"] = {"users": len(m_true), "acc": round(bin_m, 3)}
    per["binary_acc"] = round(bin_acc, 3)
    return acc, per, conf, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/train.jsonl")
    ap.add_argument("--val", default="data/val.jsonl")
    ap.add_argument("--model", default="hfl/chinese-roberta-wwm-ext")
    ap.add_argument("--out-dir", default="models/bert-v17-3class")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--max-len", type=int, default=128)
    ap.add_argument("--label-smoothing", type=float, default=0.0)
    ap.add_argument("--user-weight", action="store_true")
    ap.add_argument("--user-doc", action="store_true")
    ap.add_argument("--user-doc-chars", type=int, default=400)
    ap.add_argument("--oversample", default="none", choices=["none", "dup"])
    ap.add_argument("--oversample-k", type=float, default=2.0)
    ap.add_argument("--alpha-mult", default="1,1,1", help="三类alpha乘子 male,soft_male,female")
    ap.add_argument("--use-nickname", action="store_true")
    ap.add_argument("--use-context", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--resume", action="store_true", help="从out_dir/last.pt恢复训练")
    args = ap.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device}")

    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    train_rows = load_jsonl(args.train)
    val_rows = load_jsonl(args.val) if os.path.exists(args.val) else []
    if not train_rows:
        raise SystemExit("训练集为空")
    tr_users = {r["user_id"] for r in train_rows if r.get("label") in LABEL3}
    va_users = {r["user_id"] for r in val_rows if r.get("label") in LABEL3}
    if tr_users & va_users:
        raise SystemExit("错误：train/val 存在同一 QQ 号（数据泄漏）")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    base = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=3)

    ds_train = ChatDataset3(train_rows, tokenizer, args.max_len, args.use_nickname, args.use_context,
                            args.user_doc, args.user_doc_chars, args.oversample, args.oversample_k, args.seed)
    ds_val = ChatDataset3(val_rows, tokenizer, args.max_len, args.use_nickname, args.use_context,
                          args.user_doc, args.user_doc_chars,
                          user2idx_override=ds_train.user2idx) if val_rows else None

    sampler = None
    if args.user_weight:
        weights = [(1.0 / max(1, ds_train.user_msg_count[u])) for u, _, y, _ in ds_train.samples]
        sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)

    loader = DataLoader(ds_train, batch_size=args.batch, shuffle=sampler is None, sampler=sampler)
    loader_val = DataLoader(ds_val, batch_size=args.batch) if ds_val else None

    model = base.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    start_epoch = 0
    if args.resume:
        last_pt = os.path.join(args.out_dir, "last.pt")
        if os.path.exists(last_pt):
            ck = torch.load(last_pt, map_location=device, weights_only=False)
            model.load_state_dict(ck["state"])
            optimizer.load_state_dict(ck["optimizer"])
            random.setstate(ck["py_rng"])
            np.random.set_state(ck["np_rng"])
            torch.set_rng_state(ck["torch_rng"].cpu())
            start_epoch = ck["epoch"]
            print(f"[resume] 从 epoch {start_epoch} 恢复 (out_dir/last.pt)")
        else:
            print(f"[resume] 未找到 last.pt, 从头训练")

    n_cls = Counter(y for _, _, y, _ in ds_train.samples)
    N = sum(n_cls.values())
    class_alpha = torch.tensor([N / (3 * max(1, n_cls[c])) for c in range(3)], dtype=torch.float32).to(device)
    _am = [float(x) for x in args.alpha_mult.split(',')]
    class_alpha = class_alpha * torch.tensor(_am, dtype=torch.float32).to(device)
    print(f'[alpha-mult] {_am}')
    print(f"[数据] 训练样本 {len(ds_train)} " +
          " / ".join(f"{ID2L3[c]}={n_cls[c]}" for c in range(3)) +
          f"，验证 {len(ds_val) if ds_val else 0}")
    print(f"[类别权重 alpha] {[round(x, 2) for x in class_alpha.tolist()]}")

    os.makedirs(args.out_dir, exist_ok=True)
    best_user_acc, best_epoch, best_state = -1, -1, None

    for epoch in range(start_epoch, args.epochs):
        model.train()
        total = 0.0
        for step, batch in enumerate(loader):
            input_ids = batch["input_ids"].to(device)
            mask = batch["attention_mask"].to(device)
            y = batch["label"].to(device)
            sample_w = batch["weight"].to(device)
            logits = model(input_ids, mask).logits
            ce = nn.functional.cross_entropy(logits, y, weight=class_alpha,
                                             label_smoothing=args.label_smoothing, reduction="none")
            loss = (ce * sample_w).mean()
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += loss.item()
        print(f"[epoch {epoch+1}] loss={total/max(1,step+1):.4f}", flush=True)

        if loader_val:
            model.eval()
            ys, Ps, uids = [], [], []
            with torch.no_grad():
                for batch in loader_val:
                    logits = model(batch["input_ids"].to(device), batch["attention_mask"].to(device)).logits
                    P = torch.softmax(logits, dim=1)
                    ys += batch["label"].tolist()
                    Ps.append(P.cpu().numpy())
                    uids += batch["uid"].tolist()
            Pm = np.concatenate(Ps)
            m_pred = Pm.argmax(1)
            m_acc = float((np.array(ys) == m_pred).mean())
            acc, per, conf, rows = user_report(uids, ys, Pm)
            print(f"  [val] 消息级acc={m_acc:.4f} | 用户级acc={acc:.4f}")
            for c in range(3):
                k = ID2L3[c]
                print(f"    {k:<10} {per[k]['users']:>2}人 acc={per[k]['acc']:.3f}")
            top_conf = conf.most_common(6)
            print(f"    混淆top: {[(f'{a}→{b}', n) for (a, b), n in top_conf]}")
            print(f"    [二元裁决] 女性准确率={per['binary_female']['acc']:.3f}({per['binary_female']['users']}人) 男性准确率(含SM)={per['binary_male']['acc']:.3f}({per['binary_male']['users']}人) 综合={per['binary_acc']:.3f}")
            for u, y, pr, probs in rows:
                mark = " " if y == pr else "X"
                print(f"      [{mark}] {u} {ID2L3[y]:>9s} -> {ID2L3[pr]:<9s} P=[{probs[0]:.3f}/{probs[1]:.3f}/{probs[2]:.3f}]")
            # 断点: 每epoch存完整训练状态(权重+优化器+rng), 支持--resume续训
            torch.save({"state": model.state_dict(), "optimizer": optimizer.state_dict(),
                        "epoch": epoch + 1, "py_rng": random.getstate(), "np_rng": np.random.get_state(),
                        "torch_rng": torch.get_rng_state()},
                       os.path.join(args.out_dir, "last.pt"))
            if acc > best_user_acc:
                best_user_acc, best_epoch = acc, epoch + 1
                torch.save({"state": model.state_dict(), "user2idx": ds_train.user2idx,
                            "use_nickname": args.use_nickname, "use_context": args.use_context,
                            "model_name": args.model, "labels": LABEL3, "task": "style_class_3"},
                           os.path.join(args.out_dir, "model.pt"))
                with open(os.path.join(args.out_dir, "users.csv"), "w", encoding="utf-8") as f:
                    f.write("user_id,true,pred,p_male,p_soft_male,p_female\n")
                    for u, y, pr, s in rows:
                        f.write(f"{u},{ID2L3[y]},{ID2L3[pr]},{s[0]:.4f},{s[1]:.4f},{s[2]:.4f}\n")
                with open(os.path.join(args.out_dir, "metrics.json"), "w", encoding="utf-8") as f:
                    json.dump({"best_epoch": best_epoch, "user_accuracy": acc, "per_class": per,
                               "message_acc": m_acc, "confusion": {f"{a}->{b}": n for (a, b), n in top_conf}},
                              f, ensure_ascii=False, indent=2)
                print(f"  [保存] epoch {epoch+1} 为用户级最优 (acc={acc:.4f})")

    tokenizer.save_pretrained(args.out_dir)
    model.config.save_pretrained(args.out_dir)
    print(f"\n完成。最优 epoch={best_epoch}，用户级准确率={best_user_acc:.4f}")


if __name__ == "__main__":
    main()


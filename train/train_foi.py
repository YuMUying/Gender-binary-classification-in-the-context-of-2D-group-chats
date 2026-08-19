# -*- coding: utf-8 -*-
"""train_foi.py — 男娘/小众性取向二分类（P(男娘)）微调

复用性别分类的 chinese-roberta-wwm-ext 微调架构，但标签换维：
  foi=1   → orientation 标签的男性（男娘+双/双/同性恋）
  foi=0   → 正常男性（male 且无 orientation）

针对性手段：
  --user-weight       用户均衡采样（阳性里 2633083674 占 43%，必须均衡）
  --pos-oversample-k  阳性用户过采样倍率（9 人 vs 56 人，默认 2.0）
  --focal-gamma       聚焦难例
  --label-smoothing   软化标签（orientation 标签本身有主观性）
  --soft-labels       按 label_confidence 转软标签（high=1.0 / medium=0.7 / low=0.55）
  --adv-user          用户身份对抗头（GRL，强制编码器不学 9 人个人风格，只学男娘共性）
  --use-nickname      昵称是强信号（男娘群名片常带"妹妹/酱"等）

用法:
  python train/train_foi.py --train data/foi-train.jsonl --val data/foi-val.jsonl \
      --user-weight --pos-oversample-k 2.0 --focal-gamma 1.5 --label-smoothing 0.05 \
      --adv-user 0.3 --soft-labels --use-nickname --epochs 4 --batch 16 \
      --out-dir models/foi-bert
"""
import argparse
import json
import os
import random
from collections import defaultdict

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler

from common import (load_jsonl, prepare_text, message_metrics, user_level_report,
                    best_threshold_by_users, write_user_csv, print_report)

LABEL_MAP = {"normal": 0, "foi": 1}
ID2LABEL = {0: "normal", 1: "foi"}

# 软标签映射：label_confidence → 阳性概率（foi=1 的目标概率）
CONF_TO_SOFT = {"high": 1.0, "medium": 0.7, "low": 0.55}


class FoiDataset(Dataset):
    def __init__(self, rows, tokenizer, max_len, use_nickname, pos_oversample_k=2.0,
                 aug_seed=42, user2idx_override=None, soft_labels=False):
        self.samples = []
        self.user_msg_count = defaultdict(int)
        self.user_ids = set()
        for r in rows:
            if r.get("label") not in LABEL_MAP:
                continue
            self.user_msg_count[r["user_id"]] += 1
            self.user_ids.add(r["user_id"])
        self.user2idx = user2idx_override if user2idx_override is not None else \
            {u: i for i, u in enumerate(sorted(self.user_ids))}
        for r in rows:
            if r.get("label") not in LABEL_MAP:
                continue
            # 软标签优先级：pseudo 行用行内 soft；foi 阳性按置信度软化；normal 恒为 0
            if r.get("pseudo"):
                soft = float(r.get("soft") or 0.6)
            elif soft_labels and r["label"] == "foi":
                conf = str(r.get("label_confidence") or "low").lower()
                soft = CONF_TO_SOFT.get(conf, CONF_TO_SOFT["low"])
            else:
                soft = 1.0 if r["label"] == "foi" else 0.0
            self.samples.append((r["user_id"], prepare_text(r, use_nickname),
                                 LABEL_MAP[r["label"]], soft, r))

        # 阳性(foi=1)过采样：复制增强，目标把阳性消息量拉到阴性消息量的 target_ratio
        if pos_oversample_k > 1.0:
            rng = random.Random(aug_seed)
            pos = [s for s in self.samples if s[2] == 1]
            neg = [s for s in self.samples if s[2] == 0]
            pos_msgs = sum(self.user_msg_count[s[0]] for s in pos)
            neg_msgs = sum(self.user_msg_count[s[0]] for s in neg)
            # target_ratio: 过采样后阳性/阴性消息量目标比例（默认 0.8，即阳性≈阴性80%）
            target_ratio = max(0.4, min(0.8, pos_oversample_k * 0.4))
            copies = max(1, int(round((neg_msgs / max(1, pos_msgs)) * target_ratio)))
            copies = min(copies, 12)
            extra = []
            for uid, text, y, soft, row in pos:
                for _ in range(copies - 1):
                    extra.append((uid, text, y, soft, row))
            self.samples.extend(extra)
            print(f"[过采样] 阳性 {len(pos)} 条 → x{copies} = {len(pos) + len(extra)} 条（阴性 {len(neg)} 条，目标比 {target_ratio:.2f}）")

        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        uid, text, y, soft, row = self.samples[i]
        enc = self.tokenizer(text, max_length=self.max_len, truncation=True, padding="max_length",
                             return_tensors="pt")
        return {
            "input_ids": enc["input_ids"][0],
            "attention_mask": enc["attention_mask"][0],
            "label": y,
            "soft": soft,
            "user_idx": self.user2idx.get(uid, -1),
            "uid": uid,
        }


class GradReverse(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lambd):
        ctx.lambd = lambd
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output.neg() * ctx.lambd, None


def dann_lambda(progress, adv_weight):
    p = 2.0 / (1.0 + np.exp(-10.0 * progress)) - 1.0
    return adv_weight * p


class FoiModel(nn.Module):
    def __init__(self, base_model, n_train_users, adv_weight):
        super().__init__()
        self.bert = base_model
        self.adv_weight = adv_weight
        self.user_head = nn.Sequential(nn.Linear(base_model.config.hidden_size, 256),
                                       nn.ReLU(), nn.Linear(256, n_train_users)) \
            if adv_weight > 0 else None

    def forward(self, input_ids, attention_mask, user_idx=None, progress=1.0):
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask,
                        output_hidden_states=True)
        logits = out.logits
        loss_adv = None
        if self.user_head is not None and user_idx is not None:
            lambd = dann_lambda(progress, self.adv_weight)
            feat = out.hidden_states[-1][:, 0, :]
            rev = GradReverse.apply(feat, lambd)
            ulogits = self.user_head(rev)
            mask = user_idx >= 0
            if mask.any():
                loss_adv = nn.functional.cross_entropy(ulogits[mask], user_idx[mask])
        return logits, loss_adv


def focal_loss(logits, targets, gamma=1.5, alpha=None):
    ce = torch.nn.functional.cross_entropy(logits, targets, reduction="none")
    pt = torch.exp(-ce)
    loss = ((1 - pt) ** gamma) * ce
    if alpha is not None:
        loss = loss * alpha[targets]
    return loss.mean()


def soft_bce(logits, soft_targets):
    """软标签二分类损失（soft target 在 [0,1]，用 BCE 对概率目标）"""
    probs = torch.sigmoid(logits[:, 1])
    eps = 1e-7
    return -(soft_targets * torch.log(probs.clamp(eps, 1 - eps)) +
             (1 - soft_targets) * torch.log((1 - probs).clamp(eps, 1 - eps))).mean()


def evaluate(model, loader, device):
    model.eval()
    ys, scs, uids = [], [], []
    with torch.no_grad():
        for batch in loader:
            logits, _ = model(batch["input_ids"].to(device), batch["attention_mask"].to(device),
                              batch["user_idx"].to(device))
            probs = torch.softmax(logits, dim=1)[:, 1]
            ys += batch["label"].tolist()
            scs += probs.cpu().tolist()
            uids += batch["uid"].tolist()
    return ys, scs, uids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/foi-train.jsonl")
    ap.add_argument("--pseudo", default="", help="伪标签样本文件（jsonl，行内 soft 字段，默认 0.6）")
    ap.add_argument("--val", default="data/foi-val.jsonl")
    ap.add_argument("--model", default="hfl/chinese-roberta-wwm-ext")
    ap.add_argument("--out-dir", default="models/foi-bert")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--max-len", type=int, default=128)
    ap.add_argument("--focal-gamma", type=float, default=1.5)
    ap.add_argument("--label-smoothing", type=float, default=0.05)
    ap.add_argument("--soft-labels", action="store_true", help="按 label_confidence 转软标签（foi 阳性）")
    ap.add_argument("--adv-user", type=float, default=0.0, help=">0 启用 GRL 用户身份对抗（防 9 人过拟合）")
    ap.add_argument("--user-weight", action="store_true")
    ap.add_argument("--pos-oversample-k", type=float, default=2.0)
    ap.add_argument("--use-nickname", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device}")

    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    train_rows = load_jsonl(args.train)
    if args.pseudo and os.path.exists(args.pseudo):
        pseudo = load_jsonl(args.pseudo)
        print(f"[数据] 追加伪标签样本 {args.pseudo}: {len(pseudo)} 条")
        train_rows = train_rows + pseudo
    val_rows = load_jsonl(args.val) if os.path.exists(args.val) else []
    if not train_rows:
        raise SystemExit("训练集为空")

    tr_users = {r["user_id"] for r in train_rows if r.get("label") in LABEL_MAP}
    va_users = {r["user_id"] for r in val_rows if r.get("label") in LABEL_MAP}
    if tr_users & va_users:
        raise SystemExit("错误：train/val 存在同一 QQ 号（数据泄漏）")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    base = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=2)

    ds_train = FoiDataset(train_rows, tokenizer, args.max_len, args.use_nickname,
                          args.pos_oversample_k, args.seed, soft_labels=args.soft_labels)
    ds_val = FoiDataset(val_rows, tokenizer, args.max_len, args.use_nickname,
                        pos_oversample_k=1.0, user2idx_override=ds_train.user2idx,
                        soft_labels=args.soft_labels) if val_rows else None

    sampler = None
    if args.user_weight:
        weights = [1.0 / max(1, ds_train.user_msg_count[u]) for u, _, _, _, _ in ds_train.samples]
        sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)

    loader = DataLoader(ds_train, batch_size=args.batch, shuffle=sampler is None, sampler=sampler)
    loader_val = DataLoader(ds_val, batch_size=args.batch) if ds_val else None

    model = FoiModel(base, len(ds_train.user_ids), args.adv_user).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    n_normal = sum(1 for _, _, y, _, _ in ds_train.samples if y == 0)
    n_foi = sum(1 for _, _, y, _, _ in ds_train.samples if y == 1)
    class_alpha = torch.tensor([(n_normal + n_foi) / (2 * max(1, n_normal)),
                                (n_normal + n_foi) / (2 * max(1, n_foi))], dtype=torch.float32).to(device)
    print(f"[数据] 训练样本 {len(ds_train)}（normal {n_normal} / foi {n_foi}），验证 {len(ds_val) if ds_val else 0}")
    print(f"[配置] adv_user={args.adv_user} soft_labels={args.soft_labels} user_weight={args.user_weight}")

    os.makedirs(args.out_dir, exist_ok=True)
    best_user_acc, best_epoch, best_state = -1, -1, None

    for epoch in range(args.epochs):
        model.train()
        total, total_adv = 0.0, 0.0
        for step, batch in enumerate(loader):
            progress = (epoch + step / len(loader)) / args.epochs
            input_ids = batch["input_ids"].to(device)
            mask = batch["attention_mask"].to(device)
            y = batch["label"].to(device)
            soft = batch["soft"].to(device)
            uid_idx = batch["user_idx"].to(device)
            logits, loss_adv = model(input_ids, mask, uid_idx, progress)
            if args.soft_labels:
                loss = soft_bce(logits, soft)
            elif args.focal_gamma > 0:
                loss = focal_loss(logits, y, gamma=args.focal_gamma, alpha=class_alpha)
            elif args.label_smoothing > 0:
                loss = nn.functional.cross_entropy(logits, y, label_smoothing=args.label_smoothing,
                                                   weight=class_alpha)
            else:
                loss = nn.functional.cross_entropy(logits, y, weight=class_alpha)
            if loss_adv is not None:
                loss = loss + loss_adv
                total_adv += loss_adv.item()
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += loss.item()
        print(f"[epoch {epoch+1}] loss={total/max(1,step+1):.4f} adv={total_adv/max(1,step+1):.4f}")

        if loader_val:
            y_true, y_score, uids = evaluate(model, loader_val, device)
            m = message_metrics(y_true, [1 if s >= 0.5 else 0 for s in y_score], y_score)
            t, acc, rep = best_threshold_by_users(uids, y_true, y_score)
            print_report(f"epoch {epoch+1} 验证", m, rep)
            if acc > best_user_acc:
                best_user_acc, best_epoch, best_state = acc, epoch + 1, model.state_dict()
                torch.save({"state": best_state, "user2idx": ds_train.user2idx,
                            "use_nickname": args.use_nickname, "model_name": args.model},
                           os.path.join(args.out_dir, "model.pt"))
                write_user_csv(os.path.join(args.out_dir, "users.csv"), rep["rows"])
                with open(os.path.join(args.out_dir, "metrics.json"), "w", encoding="utf-8") as f:
                    json.dump({"best_epoch": best_epoch, "user_accuracy": acc, "message_metrics": m,
                               "threshold": t}, f, ensure_ascii=False, indent=2)
                print(f"[保存] epoch {epoch+1} 为用户级最优 (acc={acc:.4f}, 阈值={t:.2f})")

    if best_state is None and ds_val is None:
        torch.save({"state": model.state_dict(), "user2idx": ds_train.user2idx,
                    "use_nickname": args.use_nickname, "model_name": args.model},
                   os.path.join(args.out_dir, "model.pt"))
        print("[保存] 无验证集，直接保存最终权重")
    tokenizer.save_pretrained(args.out_dir)
    base.config.save_pretrained(args.out_dir)
    print(f"\n完成。最优 epoch={best_epoch}，用户级准确率={best_user_acc:.4f}")
    print(f"模型与报告: {args.out_dir}（model.pt / users.csv / metrics.json）")


if __name__ == "__main__":
    main()

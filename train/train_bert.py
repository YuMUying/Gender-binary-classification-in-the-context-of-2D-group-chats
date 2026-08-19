# -*- coding: utf-8 -*-
"""中文预训练模型微调：群聊发言 → 性别（用户级评估 + 难例/不平衡/对抗手段）

关键选项（对应"男女风格反向"问题，详见 train/README.md）：
  --focal-gamma 2.0         Focal Loss：聚焦"风格反向"等难例
  --label-smoothing 0.1     软化硬标签，容忍个别错位样本
  --user-weight             按用户均衡采样（防止话痨主导梯度）
  --user-doc                用户级文档建模：把每人的发言按长度切成文档再分类
  --adv-user 0.5            对抗训练：GRL 反向梯度 + 用户身份判别头，
                            强制编码器不依赖"个人风格指纹"、只学性别泛化特征
  --use-nickname            文本前缀 [昵称/群名片]（强信号）
  --use-context             拼接导出样本的 before/after 上下文

用法：
  python train/train_bert.py --train data/train.jsonl --val data/val.jsonl \
      --focal-gamma 2.0 --label-smoothing 0.1 --user-weight --adv-user 0.3 \
      --out-dir models/bert --epochs 3
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

from common import (LABEL_MAP, ID2LABEL, load_jsonl, prepare_text,
                    message_metrics, user_level_report, best_threshold_by_users,
                    write_user_csv, print_report)

# ---------------- 损失与对抗组件 ----------------

def eda_augment(text, rng):
    """字符级轻扰动（EDA 简化版）：随机删除 1~2 字符 或 交换相邻字符；过短文本原样返回"""
    if len(text) <= 4:
        return text
    chars = list(text)
    if rng.random() < 0.5:
        for _ in range(rng.randint(1, 2)):
            if len(chars) > 2:
                del chars[rng.randrange(len(chars))]
    else:
        i = rng.randrange(len(chars) - 1)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def ctx_variant(row, rng):
    """上下文窗口变体：同一中心消息配不同上下文子集（重复利用上下文信息）"""
    before = row.get("before") or []
    after = row.get("after") or []
    v = rng.random()
    if v < 0.34 and before:
        return "\n".join(before + [row.get("text", "")])
    if v < 0.67 and after:
        return "\n".join([row.get("text", "")] + after)
    return row.get("text", "")


def aug_text(row, text, method, rng):
    if method == "dup":
        return text
    if method == "eda":
        return eda_augment(text, rng)
    if method == "ctx" and row is not None:
        return ctx_variant(row, rng)
    return text

def focal_loss(logits, targets, gamma=2.0, alpha=None):
    ce = torch.nn.functional.cross_entropy(logits, targets, reduction="none")
    pt = torch.exp(-ce)
    loss = ((1 - pt) ** gamma) * ce
    if alpha is not None:
        loss = loss * alpha[targets]
    return loss.mean()


class GradReverse(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lambd):
        ctx.lambd = lambd
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output.neg() * ctx.lambd, None


def dann_lambda(progress, adv_weight):
    """DANN 式渐进系数：训练早期不对抗，后期加强"""
    p = 2.0 / (1.0 + np.exp(-10.0 * progress)) - 1.0
    return adv_weight * p


class GenderModel(nn.Module):
    """性别分类头 + 可选用户身份对抗头（GRL）"""
    def __init__(self, base_model, hidden, n_train_users, adv_weight):
        super().__init__()
        self.bert = base_model
        self.adv_weight = adv_weight
        self.user_head = nn.Sequential(nn.Linear(hidden, 256), nn.ReLU(), nn.Linear(256, n_train_users)) \
            if adv_weight > 0 else None

    def forward(self, input_ids, attention_mask, user_idx=None, progress=1.0):
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask, output_hidden_states=True)
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


class ChatDataset(Dataset):
    def __init__(self, rows, tokenizer, max_len, use_nickname, use_context, user_doc, user_doc_chars,
                 oversample="none", oversample_k=2.0, aug_seed=42, user2idx_override=None,
                 hard_neg_users=None, hard_neg_weight=3.0, use_avatar=False, use_profile=False):
        self.samples = []          # (uid, text, label, raw_row|None)
        self.user_msg_count = defaultdict(int)
        self.user_ids = set()
        self.hard_neg = set(hard_neg_users or [])   # "男声女气"困难负样本用户
        self.hard_neg_weight = hard_neg_weight
        for r in rows:
            if r.get("label") not in LABEL_MAP:
                continue
            self.user_msg_count[r["user_id"]] += 1
            self.user_ids.add(r["user_id"])
        # 用户索引：默认按本数据集构建；验证集需传入训练集映射（未知用户 → -1，跳过对抗）
        self.user2idx = user2idx_override if user2idx_override is not None else \
            {u: i for i, u in enumerate(sorted(self.user_ids))}

        if user_doc:
            docs = defaultdict(list)
            user_label = {}
            for r in rows:
                if r.get("label") not in LABEL_MAP:
                    continue
                docs[r["user_id"]].append(prepare_text(r, use_nickname, use_context, use_avatar, use_profile))
                user_label[r["user_id"]] = LABEL_MAP[r["label"]]
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
                if r.get("label") not in LABEL_MAP:
                    continue
                self.samples.append((r["user_id"], prepare_text(r, use_nickname, use_context, use_avatar, use_profile),
                                     LABEL_MAP[r["label"]], r))

        # 少数类过采样（dup / eda / ctx），只作用于 label=1（female）样本
        if oversample and oversample != "none" and oversample_k > 1.0:
            rng = random.Random(aug_seed)
            minority = [s for s in self.samples if s[2] == 1]
            extra = []
            for uid, text, y, row in minority:
                # oversample_k=2.5 → 保证补 1 份，另有 50% 概率再补 1 份
                copies = int(oversample_k) - 1 + (1 if rng.random() < (oversample_k - int(oversample_k)) else 0)
                for _ in range(copies):
                    extra.append((uid, aug_text(row, text, oversample, rng), y, row))
            self.samples.extend(extra)
            print(f"[过采样] {oversample} x{oversample_k}: 少数类样本 {len(minority)} → {len(minority) + len(extra)}")

        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        uid, text, y, row = self.samples[i]
        enc = self.tokenizer(text, max_length=self.max_len, truncation=True, padding="max_length",
                             return_tensors="pt")
        # 困难负样本加权：男性"女气"用户的样本权重放大，逼模型把真女性风格与之切开
        # 夜间降权：导出端 --night-mode 给少样本用户深夜消息打 weight<1（噪声降权），两者相乘
        w = self.hard_neg_weight if (y == 0 and uid in self.hard_neg) else 1.0
        try:
            night_w = float(row.get('weight', 1.0) or 1.0)
        except (TypeError, ValueError):
            night_w = 1.0
        w = w * night_w
        return {
            "input_ids": enc["input_ids"][0],
            "attention_mask": enc["attention_mask"][0],
            "label": y,
            "user_idx": self.user2idx.get(uid, -1),   # 未知用户 → -1（对抗头跳过）
            "uid": uid,
            "weight": w,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/train.jsonl")
    ap.add_argument("--extra-train", default="", help="追加的合成/增广训练数据（逗号分隔，只进训练集）")
    ap.add_argument("--val", default="data/val.jsonl")
    ap.add_argument("--model", default="hfl/chinese-roberta-wwm-ext")
    ap.add_argument("--out-dir", default="models/bert")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--max-len", type=int, default=128)
    ap.add_argument("--focal-gamma", type=float, default=0.0, help=">0 启用 Focal Loss")
    ap.add_argument("--label-smoothing", type=float, default=0.0)
    ap.add_argument("--user-weight", action="store_true", help="按用户均衡采样")
    ap.add_argument("--user-doc", action="store_true", help="用户级文档建模")
    ap.add_argument("--user-doc-chars", type=int, default=400, help="每文档约字符数")
    ap.add_argument("--adv-user", type=float, default=0.0, help=">0 启用 GRL 用户身份对抗")
    ap.add_argument("--oversample", default="none", choices=["none", "dup", "eda", "ctx"],
                    help="少数类(female)过采样: dup=复制 / eda=字符级扰动 / ctx=上下文窗口变体")
    ap.add_argument("--oversample-k", type=float, default=2.0, help="少数类扩增倍数（如 2.5）")
    ap.add_argument("--hard-neg-users", default="", help="困难负样本用户（男声女气，逗号分隔 QQ 号）")
    ap.add_argument("--hard-neg-weight", type=float, default=3.0, help="困难负样本的损失/采样权重")
    ap.add_argument("--use-nickname", action="store_true")
    ap.add_argument("--use-context", action="store_true")
    ap.add_argument("--use-avatar", action="store_true", help="附加头像描述（行内 avatar_desc 字段）")
    ap.add_argument("--use-profile", action="store_true", help="附加主页信息（行内 profile_meta 字段）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[device] {device}")

    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    train_rows = load_jsonl(args.train)
    for extra_path in [p.strip() for p in args.extra_train.split(",") if p.strip()]:
        if os.path.exists(extra_path):
            extra = load_jsonl(extra_path)
            print(f"[数据] 追加合成样本 {extra_path}: {len(extra)} 条（仅训练集）")
            train_rows = train_rows + extra
    val_rows = load_jsonl(args.val) if os.path.exists(args.val) else []
    if not train_rows:
        raise SystemExit("训练集为空：请先采集数据并 export-dataset.js --mode train --split-by-user")
    # 训练/验证用户不相交检查
    tr_users = {r["user_id"] for r in train_rows if r.get("label") in LABEL_MAP}
    va_users = {r["user_id"] for r in val_rows if r.get("label") in LABEL_MAP}
    if tr_users & va_users:
        raise SystemExit("错误：train/val 存在同一 QQ 号（数据泄漏），请用 export-dataset.js --split-by-user 重新导出")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    base = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=2)
    hidden = base.config.hidden_size

    hard_neg_users = set(int(x) for x in args.hard_neg_users.split(",") if x.strip())
    ds_train = ChatDataset(train_rows, tokenizer, args.max_len, args.use_nickname, args.use_context,
                           args.user_doc, args.user_doc_chars, args.oversample, args.oversample_k, args.seed,
                           hard_neg_users=hard_neg_users, hard_neg_weight=args.hard_neg_weight,
                           use_avatar=args.use_avatar, use_profile=args.use_profile)
    ds_val = ChatDataset(val_rows, tokenizer, args.max_len, args.use_nickname, args.use_context,
                         args.user_doc, args.user_doc_chars,
                         user2idx_override=ds_train.user2idx,
                         use_avatar=args.use_avatar, use_profile=args.use_profile) if val_rows else None

    sampler = None
    if args.user_weight:
        # 权重按"原始每用户消息数"的倒数（困难负样本用户再乘 hard_neg_weight）
        weights = [(1.0 / max(1, ds_train.user_msg_count[u])) * (args.hard_neg_weight if (u in hard_neg_users and y == 0) else 1.0)
                   for u, _, y, _ in ds_train.samples]
        sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)

    loader = DataLoader(ds_train, batch_size=args.batch, shuffle=sampler is None, sampler=sampler)
    loader_val = DataLoader(ds_val, batch_size=args.batch) if ds_val else None

    model = GenderModel(base, hidden, len(ds_train.user_ids), args.adv_user).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    # 类别权重（默认按比例补偿男女失衡；focal 时同样生效）
    n_male = sum(1 for _, _, y, _ in ds_train.samples if y == 0)
    n_female = sum(1 for _, _, y, _ in ds_train.samples if y == 1)
    class_alpha = torch.tensor([ (n_male + n_female) / (2 * max(1, n_male)),
                                 (n_male + n_female) / (2 * max(1, n_female)) ], dtype=torch.float32).to(device)
    print(f"[数据] 训练样本 {len(ds_train)}（男 {n_male} / 女 {n_female}），验证 {len(ds_val) if ds_val else 0}")

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
            uid_idx = batch["user_idx"].to(device)
            sample_w = batch["weight"].to(device)
            logits, loss_adv = model(input_ids, mask, uid_idx, progress)
            if args.focal_gamma > 0:
                loss = focal_loss(logits, y, gamma=args.focal_gamma, alpha=class_alpha)
            elif args.label_smoothing > 0:
                ce = nn.functional.cross_entropy(logits, y, label_smoothing=args.label_smoothing,
                                                 weight=class_alpha, reduction="none")
                loss = (ce * sample_w).mean()
            else:
                ce = nn.functional.cross_entropy(logits, y, weight=class_alpha, reduction="none")
                loss = (ce * sample_w).mean()
            if loss_adv is not None:
                loss = loss + loss_adv
                total_adv += loss_adv.item()
            optimizer.zero_grad(); loss.backward(); optimizer.step()
            total += loss.item()
        print(f"[epoch {epoch+1}] loss={total/max(1,step+1):.4f} adv={total_adv/max(1,step+1):.4f}")

        if loader_val:
            y_true, y_score, uids = evaluate(model, loader_val, device, progress=1.0)
            m = message_metrics(y_true, [1 if s >= 0.5 else 0 for s in y_score], y_score)
            t, acc, rep = best_threshold_by_users(uids, y_true, y_score)
            print_report(f"epoch {epoch+1} 验证", m, rep)
            if acc > best_user_acc:
                best_user_acc, best_epoch, best_state = acc, epoch + 1, model.state_dict()
                torch.save({"state": best_state, "user2idx": ds_train.user2idx,
                            "use_nickname": args.use_nickname, "use_context": args.use_context,
                            "use_avatar": args.use_avatar, "use_profile": args.use_profile,
                            "model_name": args.model}, os.path.join(args.out_dir, "model.pt"))
                write_user_csv(os.path.join(args.out_dir, "users.csv"), rep["rows"])
                with open(os.path.join(args.out_dir, "metrics.json"), "w", encoding="utf-8") as f:
                    json.dump({"best_epoch": best_epoch, "user_accuracy": acc, "message_metrics": m,
                               "threshold": t}, f, ensure_ascii=False, indent=2)
                print(f"[保存] epoch {epoch+1} 为用户级最优 (acc={acc:.4f}, 阈值={t:.2f})")

    if best_state is None and ds_val is None:
        torch.save({"state": model.state_dict(), "user2idx": ds_train.user2idx,
                    "use_nickname": args.use_nickname, "use_context": args.use_context,
                    "use_avatar": args.use_avatar, "use_profile": args.use_profile,
                    "model_name": args.model}, os.path.join(args.out_dir, "model.pt"))
        print("[保存] 无验证集，直接保存最终权重")
    tokenizer.save_pretrained(args.out_dir)
    base.config.save_pretrained(args.out_dir)   # 保存 config，predict.py 需要
    print(f"\n完成。最优 epoch={best_epoch}，用户级准确率={best_user_acc:.4f}")
    print(f"模型与报告: {args.out_dir}（model.pt / users.csv / metrics.json）")
    print("复核错分用户: node scripts/export-context.js --user <QQ号> --format readable")


def evaluate(model, loader, device, progress=1.0):
    model.eval()
    ys, scs, uids = [], [], []
    with torch.no_grad():
        for batch in loader:
            logits, _ = model(batch["input_ids"].to(device), batch["attention_mask"].to(device),
                              batch["user_idx"].to(device), progress)
            probs = torch.softmax(logits, dim=1)[:, 1]
            ys += batch["label"].tolist()
            scs += probs.cpu().tolist()
            uids += batch["uid"].tolist()
    return ys, scs, uids


if __name__ == "__main__":
    main()

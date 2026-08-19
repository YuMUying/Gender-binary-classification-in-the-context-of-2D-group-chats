# -*- coding: utf-8 -*-
"""推理：用训练好的模型对用户做性别判定（按 QQ 号聚合输出，含置信度标记）

用法：
  对推断集（jsonl）打分：
    python train/predict.py --model-dir models/bert --input data/infer.jsonl --out outputs/predictions.csv
  对全库所有用户打分（一键，含已标注用户的标签对照）：
    python train/predict.py --model-dir models/bert --from-db --min-per-user 30 --out outputs/score-all.csv

输出列：
  user_id, n_messages, prob_female_mean, prob_female_median, prob_female_std,
  threshold, predicted, confidence(high/low-data/borderline), label(已知时), correct(已知时)

置信度规则（阈值取模型验证集校准值 metrics.json 的 threshold，缺省 0.5）：
  - n_messages < 50          → low-data（样本不足，结论仅供参考）
  - |mean - threshold| < 0.15 → borderline（临界，建议人工复核）
  - 其余                     → high
"""
import argparse
import csv
import json
import os
import statistics
from collections import defaultdict

import torch
from torch.utils.data import DataLoader

from common import ID2LABEL, load_jsonl, prepare_text


def load_metrics(model_dir):
    """读取验证集校准阈值；缺省 0.5"""
    try:
        with open(os.path.join(model_dir, 'metrics.json'), encoding='utf-8') as f:
            m = json.load(f)
        return float(m.get('threshold', 0.5)), m
    except Exception:
        return 0.5, None


def confidence_for(n_msgs, mean, threshold, margin=0.05):
    if n_msgs < 50:
        return 'low-data'
    if abs(mean - threshold) < margin:
        return 'borderline'
    return 'high'


class InferDataset(torch.utils.data.Dataset):
    def __init__(self, rows, tokenizer, max_len, use_nickname, use_context, use_avatar=False, use_profile=False):
        self.rows = rows
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.use_nickname = use_nickname
        self.use_context = use_context
        self.use_avatar = use_avatar
        self.use_profile = use_profile

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        text = prepare_text(r, self.use_nickname, self.use_context, self.use_avatar, self.use_profile)
        enc = self.tokenizer(text, max_length=self.max_len, truncation=True, padding="max_length",
                             return_tensors="pt")
        return enc["input_ids"][0], enc["attention_mask"][0], r["user_id"], r.get("group_id"), r.get("time")


def predict_rows(model, tokenizer, rows, device, batch, max_len, use_nickname, use_context,
                 use_avatar=False, use_profile=False):
    ds = InferDataset(rows, tokenizer, max_len, use_nickname, use_context)
    loader = DataLoader(ds, batch_size=batch)
    per_user = defaultdict(list)
    with torch.no_grad():
        for input_ids, mask, uid, gid, t in loader:
            out = model.bert(input_ids=input_ids.to(device), attention_mask=mask.to(device))
            probs = torch.softmax(out.logits, dim=1)[:, 1].cpu().tolist()
            for u, p in zip(uid.tolist(), probs):
                per_user[u].append(p)
    return per_user


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="models/bert")
    ap.add_argument("--input", default="data/infer.jsonl")
    ap.add_argument("--from-db", action="store_true", help="直接对全库所有用户打分（不再读 jsonl）")
    ap.add_argument("--out", default="outputs/predictions.csv")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=128)
    ap.add_argument("--min-per-user", type=int, default=0)
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    from transformers import AutoConfig, AutoTokenizer, AutoModelForSequenceClassification
    from train_bert import GenderModel

    ckpt = torch.load(os.path.join(args.model_dir, "model.pt"), map_location=device, weights_only=False)
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    cfg = AutoConfig.from_pretrained(args.model_dir)
    cfg.num_labels = 2
    base = AutoModelForSequenceClassification.from_config(cfg)
    hidden = cfg.hidden_size
    model = GenderModel(base, hidden, 1, 0.0).to(device)   # 推理不需要对抗头
    model.load_state_dict(ckpt["state"], strict=False)
    model.eval()
    use_nickname = ckpt.get("use_nickname", False)
    use_context = ckpt.get("use_context", False)
    use_avatar = ckpt.get("use_avatar", False)
    use_profile = ckpt.get("use_profile", False)

    threshold, metrics = load_metrics(args.model_dir)

    # 数据源：jsonl 或全库
    labels = {}
    if args.from_db:
        import sqlite3
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'config', 'config.json'), encoding='utf-8-sig') as f:
            db_path = json.load(f).get('database', 'data/qqchat.db')
        if not os.path.isabs(db_path):
            db_path = os.path.join(root, db_path)
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("""
            SELECT user_id, peer_id AS group_id, time, text, nickname, card
            FROM messages WHERE scene IN ('group','private') AND LENGTH(text) > 0
            ORDER BY time ASC""").fetchall()]
        for r in conn.execute("SELECT user_id, gender FROM speaker_labels WHERE gender IN ('male','female')"):
            labels[r['user_id']] = r['gender']
        # 头像描述 / 主页信息（与训练导出保持一致）
        avatar_map, profile_map = {}, {}
        try:
            with open(os.path.join(root, 'research', 'avatar_desc.jsonl'), encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    desc = d.get('desc') or {}
                    if desc.get('overall') or desc.get('content') or desc.get('vibe'):
                        avatar_map[str(d['uin'])] = '；'.join(
                            [str(x) for x in (desc.get('content'), desc.get('style'), desc.get('vibe')) if x])[:120]
        except Exception:
            pass
        if use_profile:
            for r in conn.execute("SELECT user_id, data_json FROM profile_details"):
                try:
                    d = json.loads(r['data_json'])
                    parts = []
                    if d.get('age'): parts.append(f"{d['age']}岁")
                    if d.get('constellation'): parts.append(f"星座{d['constellation']}")
                    if d.get('shengXiao'): parts.append(f"属相{d['shengXiao']}")
                    if isinstance(d.get('labels'), list) and d['labels']: parts.append("标签:" + '/'.join(d['labels']))
                    if d.get('interest'): parts.append("兴趣:" + str(d['interest'])[:30])
                    if d.get('country'): parts.append("地区:" + str(d['country']))
                    s = ' '.join(parts)
                    if s:
                        profile_map[str(r['user_id'])] = s[:100]
                except Exception:
                    pass
        if use_avatar:
            for r in rows:
                r['avatar_desc'] = avatar_map.get(str(r['user_id']))
        if use_profile:
            for r in rows:
                r['profile_meta'] = profile_map.get(str(r['user_id']))
        conn.close()
        print(f"[数据] 全库模式：{len(rows)} 条消息")
    else:
        rows = load_jsonl(args.input)
        for r in rows:
            if r.get('label'):
                labels[r['user_id']] = r['label']
        print(f"[数据] jsonl 模式：{len(rows)} 条消息")

    if not rows:
        raise SystemExit(f"无输入数据：--input {args.input} 为空，或全库无消息")

    print(f"[模型] {os.path.basename(args.model_dir)} | 校准阈值={threshold:.3f} | 设备={device}")
    per_user = predict_rows(model, tokenizer, rows, device, args.batch, args.max_len,
                            use_nickname, use_context, use_avatar, use_profile)

    os.makedirs(os.path.dirname(args.out), exist_ok=True) if os.path.dirname(args.out) else None
    rows_out = []
    for u, ps in per_user.items():
        if len(ps) < args.min_per_user:
            continue
        mean = sum(ps) / len(ps)
        med = statistics.median(ps)
        std = statistics.pstdev(ps) if len(ps) > 1 else 0.0
        pred = ID2LABEL[1 if mean >= threshold else 0]
        conf = confidence_for(len(ps), mean, threshold)
        label = labels.get(u)
        rows_out.append({
            'user_id': u, 'n_messages': len(ps),
            'prob_female_mean': round(mean, 4), 'prob_female_median': round(med, 4),
            'prob_female_std': round(std, 4), 'threshold': round(threshold, 4),
            'predicted': pred, 'confidence': conf,
            'label': label or '', 'correct': '' if not label else ('1' if pred == label else '0'),
        })

    rows_out.sort(key=lambda r: -r['n_messages'])
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['user_id', 'n_messages', 'prob_female_mean', 'prob_female_median',
                                          'prob_female_std', 'threshold', 'predicted', 'confidence',
                                          'label', 'correct'])
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    # 摘要
    n = len(rows_out)
    known = [r for r in rows_out if r['label']]
    ok = sum(1 for r in known if r['correct'] == '1')
    low = sum(1 for r in rows_out if r['confidence'] == 'low-data')
    bor = sum(1 for r in rows_out if r['confidence'] == 'borderline')
    print(f"\n完成: {args.out}（{n} 个用户）")
    if known:
        print(f"已知标签用户 {len(known)} 人，判定一致 {ok} 人（{ok / len(known):.1%}）")
    print(f"低置信（样本<50）: {low} 人 | 临界（需复核）: {bor} 人 | 高置信: {n - low - bor} 人")


if __name__ == "__main__":
    main()

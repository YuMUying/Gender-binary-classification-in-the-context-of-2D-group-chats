# -*- coding: utf-8 -*-
"""foi_predict.py — FOI 推理：滑窗 → EMA/Kalman 平滑 → 用户倾向曲线 + 置信区间

把用户的全部消息按时间排序切成窗口（每窗 N 条），逐窗用 FOI 模型打分，
得到离散的 P(男娘) 序列，再用 EMA（一阶平滑）或一阶卡尔曼滤波得到连续倾向曲线，
输出：
  - 用户级聚合：P_mean（全消息均值）、P_ema（EMA 终值）、FoiIndex（0-100 混合指数）
  - 时间轨迹：每窗口的时间/分数（写 CSV，供画倾向曲线图）
  - 置信区间：按窗口数/分数方差估算

用法：
  python train/foi_predict.py --model-dir models/foi-bert-v2 \
      --out outputs/foi_pred.csv --curve outputs/foi_curve.csv
  （--min-per-user 200 默认；--window 100 每窗消息数；--smooth ema|kalman）
"""
import argparse
import csv
import json
import math
import os
import sqlite3
import statistics
from collections import defaultdict

import torch
from torch.utils.data import DataLoader

from common import load_jsonl, prepare_text


def load_ckpt(model_dir, device):
    ckpt = torch.load(os.path.join(model_dir, "model.pt"), map_location=device, weights_only=False)
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    cfg = AutoConfig.from_pretrained(model_dir)
    cfg.num_labels = 2
    base = AutoModelForSequenceClassification.from_config(cfg)
    from train_foi import FoiModel
    model = FoiModel(base, 1, 0.0).to(device)   # 推理不需要对抗头
    model.load_state_dict(ckpt["state"], strict=False)
    model.eval()
    return model, tokenizer, ckpt


def ema_smooth(values, alpha=0.5):
    """一阶指数平滑（alpha 大 → 更依赖近期）"""
    out = []
    prev = values[0] if values else 0.0
    for v in values:
        prev = alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def kalman1d(values, R=0.05, Q=0.01):
    """一阶卡尔曼平滑：状态=真实倾向，观测=窗口分数
    R: 观测噪声方差（窗口样本噪声）  Q: 过程噪声（倾向漂移速度）"""
    x, P = values[0], 1.0
    out = []
    for z in values:
        # 预测
        x_pred, P_pred = x, P + Q
        # 更新
        K = P_pred / (P_pred + R)
        x = x_pred + K * (z - x_pred)
        P = (1 - K) * P_pred
        out.append(x)
    return out


def windowize(rows, window):
    """按时间排序的消息 → 每 window 条一个窗口，返回 [(t_start, texts), ...]"""
    rows = sorted(rows, key=lambda r: r.get('time') or 0)
    wins = []
    for i in range(0, len(rows), window):
        chunk = rows[i:i + window]
        wins.append(chunk)
    return wins


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="models/foi-bert-v2")
    ap.add_argument("--out", default="outputs/foi_pred.csv")
    ap.add_argument("--curve", default="outputs/foi_curve.csv")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=128)
    ap.add_argument("--min-per-user", type=int, default=200)
    ap.add_argument("--window", type=int, default=100, help="每窗口消息数（倾向曲线粒度）")
    ap.add_argument("--smooth", default="kalman", choices=["ema", "kalman"])
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    device = args.device if args.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
    model, tokenizer, ckpt = load_ckpt(args.model_dir, device)
    use_nickname = ckpt.get("use_nickname", False)
    print(f"[模型] {os.path.basename(args.model_dir)} | smooth={args.smooth} window={args.window} | {device}")

    # 读全库消息（含时间，用于窗口化）
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'config', 'config.json'), encoding='utf-8-sig') as f:
        db_path = json.load(f).get('database', 'data/qqchat.db')
    if not os.path.isabs(db_path):
        db_path = os.path.join(root, db_path)
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    msgs = [dict(r) for r in conn.execute("""
        SELECT user_id, peer_id AS group_id, time, text, nickname, card
        FROM messages WHERE scene IN ('group','private') AND LENGTH(text) > 0
        ORDER BY user_id, time ASC""").fetchall()]
    # orientation 标签对照
    labels = {}
    for r in conn.execute("SELECT user_id, orientation FROM speaker_labels WHERE orientation IS NOT NULL AND orientation != ''"):
        labels[r['user_id']] = r['orientation']
    gender = {}
    for r in conn.execute("SELECT user_id, gender FROM speaker_labels"):
        gender[r['user_id']] = r['gender']
    conn.close()
    print(f"[数据] 全库 {len(msgs)} 条消息")

    # 按用户分组
    by_user = defaultdict(list)
    for m in msgs:
        by_user[m['user_id']].append(m)

    user_results = []       # 用户级聚合
    curve_lines = []        # 时间轨迹
    curve_lines.append(['user_id', 'window_idx', 'time_start', 'prob_raw', 'prob_smooth', 'n_in_window'])

    for uid, umsgs in by_user.items():
        if len(umsgs) < args.min_per_user:
            continue
        wins = windowize(umsgs, args.window)
        # 逐窗口打分
        win_probs = []
        win_times = []
        win_sizes = []
        for w in wins:
            texts = [{'text': m['text'], 'nickname': m.get('nickname'), 'card': m.get('card')} for m in w]
            scores = []
            for i in range(0, len(texts), args.batch):
                batch = texts[i:i + args.batch]
                enc = tokenizer([prepare_text(r, use_nickname) for r in batch],
                                max_length=args.max_len, truncation=True, padding="max_length",
                                return_tensors="pt")
                with torch.no_grad():
                    logits, _ = model(enc["input_ids"].to(device), enc["attention_mask"].to(device))
                probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
                scores.extend(probs)
            win_probs.append(sum(scores) / len(scores))
            win_times.append(min(m['time'] for m in w))
            win_sizes.append(len(scores))
        if not win_probs:
            continue

        # 平滑
        if args.smooth == 'ema':
            smooth = ema_smooth(win_probs, alpha=0.5)
        else:
            smooth = kalman1d(win_probs)

        # 用户级聚合
        p_mean = sum(win_probs) / len(win_probs)
        p_ema_end = smooth[-1]
        # 置信区间（窗口数少 → 宽；std 大 → 宽）
        n_wins = len(win_probs)
        std = statistics.pstdev(win_probs) if n_wins > 1 else 0.0
        ci = 1.96 * std / math.sqrt(max(n_wins, 1))   # 95% CI（窗口独立近似）

        # FOI 混合指数（0-100）：以模型概率为主，EMA 终值辅助
        #   P 是"阳性概率"，映射到指数：0.5 为中性，越接近 1 越高
        foi_raw = 100 * max(0, min(1, (p_mean - 0.2) / 0.6))   # 0.2→0, 0.8→100 线性
        foi_ema = 100 * max(0, min(1, (p_ema_end - 0.2) / 0.6))
        foi_mix = 0.7 * foi_raw + 0.3 * foi_ema   # 以训练概率为主

        user_results.append({
            'user_id': uid,
            'n_messages': len(umsgs),
            'n_windows': n_wins,
            'p_mean': round(p_mean, 4),
            'p_ema_end': round(p_ema_end, 4),
            'p_std': round(std, 4),
            'ci95': round(ci, 4),
            'foi_index': round(foi_mix, 1),
            'orientation': labels.get(uid, ''),
            'gender': gender.get(uid, ''),
        })
        for i, (t, pr, ps, ns) in enumerate(zip(win_times, win_probs, smooth, win_sizes)):
            curve_lines.append([uid, i, t, round(pr, 4), round(ps, 4), ns])

    user_results.sort(key=lambda r: -r['foi_index'])
    os.makedirs(os.path.dirname(args.out), exist_ok=True) if os.path.dirname(args.out) else None
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(user_results[0].keys()) if user_results else
                           ['user_id', 'n_messages', 'n_windows', 'p_mean', 'p_ema_end', 'p_std', 'ci95', 'foi_index', 'orientation', 'gender'])
        w.writeheader()
        for r in user_results:
            w.writerow(r)
    with open(args.curve, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerows(curve_lines)

    # 摘要
    n = len(user_results)
    print(f"\n完成: {args.out}（{n} 个用户，样本≥{args.min_per_user}）")
    print(f"轨迹: {args.curve}")
    print("\n=== 已知 orientation 用户的 FOI ===")
    for r in user_results:
        if r['orientation']:
            print(f"  {r['user_id']} [{r['orientation']}] n={r['n_messages']} P_mean={r['p_mean']} FOI={r['foi_index']}")
    print("\n=== 全库 TOP 15 ===")
    for r in user_results[:15]:
        print(f"  {r['user_id']} n={r['n_messages']} P={r['p_mean']} FOI={r['foi_index']} {'★'+r['orientation'] if r['orientation'] else ''}")


if __name__ == "__main__":
    main()

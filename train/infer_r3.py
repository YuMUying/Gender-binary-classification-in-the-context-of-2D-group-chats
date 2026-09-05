# -*- coding: utf-8 -*-
"""infer_r3.py — 现役 r3 三分类推理服务（stdin/stdout 协议）+ abstain 不确定层

协议（每行一个 JSON 请求）:
  请求: {"texts": ["...", ...]}
  响应: {
    "p_female":  三seed均值消息级P_female,
    "verdict":   "female" | "male" | "abstain",
    "band":      "high" | "abstain(0.35-0.5)" | "auto",
    "n": 条数, "t_ms": 耗时
  }

裁决规则（2026-09-05 用户批准, docs/decisions.md）:
  P_female(r3 三seed均值) >= 0.50        → female（自动判女）
  P_female < 0.35                        → male（自动判男/SM侧）
  0.35 <= P_female < 0.50                → abstain（不确定：疑似男域原生女，转人工/带外验证）

模型: models/r3-s0v56/seed{7,8,9}/model.pt 三seed集成（labels: male=0, soft_male=1, female=2）
用法: 常驻 python infer_r3.py，或环境变量 QQBOT_R3_DIR 指定模型根目录
"""
import json
import os
import sys
import time

sys.stdin.reconfigure(encoding='utf-8', errors='replace')  # Windows 默认 GBK 会乱码
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
R3_DIR = os.environ.get("QQBOT_R3_DIR") or os.path.join(ROOT, "models", "r3-s0v56")
SEEDS = (7, 8, 9)
ABSTAIN_LO = 0.35
ABSTAIN_HI = 0.50
MAX_BATCH = 256


def load_models():
    import torch
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    models = []
    name = None
    for seed in SEEDS:
        ckpt = torch.load(os.path.join(R3_DIR, "seed%d" % seed, "model.pt"),
                          map_location=device, weights_only=False)
        name = name or ckpt["model_name"]
        cfg = AutoConfig.from_pretrained(name)
        cfg.num_labels = 3
        m = AutoModelForSequenceClassification.from_config(cfg)
        m.load_state_dict(ckpt["state"])
        m.to(device).eval()
        models.append(m)
    tokenizer = AutoTokenizer.from_pretrained(name)
    return models, tokenizer, device, name


def verdict_for(pf):
    if pf is None:
        return None, None
    if pf >= ABSTAIN_HI:
        return "female", "high"
    if pf < ABSTAIN_LO:
        return "male", "auto"
    return "abstain", "abstain(0.35-0.5)"


def main():
    import torch
    models, tokenizer, device, name = load_models()
    sys.stdout.write(json.dumps({
        "ready": True, "device": device, "model": "r3-s0v56-3seed",
        "labels": {"male": 0, "soft_male": 1, "female": 2},
        "abstain": [ABSTAIN_LO, ABSTAIN_HI],
    }) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if line.startswith("\ufeff"):
            line = line[1:]
        if not line:
            continue
        t0 = time.time()
        try:
            req = json.loads(line)
            texts = [str(t).strip() for t in req.get("texts", [])]
            texts = [t for t in texts if t]
            if not texts:
                sys.stdout.write(json.dumps(
                    {"p_female": None, "verdict": None, "band": None, "n": 0, "t_ms": 0}) + "\n")
                sys.stdout.flush()
                continue
            ps = []
            with torch.no_grad():
                for i in range(0, len(texts), MAX_BATCH):
                    batch = texts[i:i + MAX_BATCH]
                    enc = tokenizer(batch, padding=True, truncation=True,
                                    max_length=128, return_tensors="pt").to(device)
                    logits = sum(m(**enc).logits for m in models) / len(models)
                    prob = logits.softmax(-1)[:, 2]   # female=2
                    ps.extend(prob.cpu().tolist())
            pf = sum(ps) / len(ps)
            v, band = verdict_for(pf)
            sys.stdout.write(json.dumps({
                "p_female": round(pf, 4), "verdict": v, "band": band,
                "n": len(texts), "t_ms": int((time.time() - t0) * 1000),
            }, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({"error": str(e)[:200]}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

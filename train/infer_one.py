# -*- coding: utf-8 -*-
"""infer_one.py — 实时推理服务（stdin/stdout 协议）

从 stdin 读取 JSON: {"texts": ["...", ...], "nicknames": ["...", ...] 或省略}
加载 bert-v10-wb 模型，逐条推理，输出: {"p_female": 平均概率, "n": 条数, "t_ms": 耗时}

用法（常驻，一条消息一行）:
  echo '{"texts":["你好","在吗"]}' | python infer_one.py
"""
import json
import os
import sys
import time

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "bert-v10-wb")


def load_model():
    import torch
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    cfg = AutoConfig.from_pretrained(MODEL_DIR)
    cfg.num_labels = 2
    base = AutoModelForSequenceClassification.from_config(cfg)
    ckpt = torch.load(os.path.join(MODEL_DIR, "model.pt"), map_location=device, weights_only=False)
    # bert-v10-wb 用 GenderModel 结构（对抗头），严格加载主头
    try:
        from train_bert import GenderModel
        model = GenderModel(base, cfg.hidden_size, 1, 0.0).to(device)
    except ImportError:
        # 回退：直接序列分类头
        model = base.to(device)
    model.load_state_dict(ckpt["state"], strict=False)
    model.eval()
    return model, tokenizer, device


def main():
    model, tokenizer, device = load_model()
    sys.stdout.write(json.dumps({"ready": True, "device": device, "model": "bert-v10-wb"}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        # 容忍 BOM
        if line.startswith("\ufeff"):
            line = line[1:]
        if not line:
            continue
        try:
            req = json.loads(line)
            texts = req.get("texts", [])
            use_nickname = req.get("use_nickname", True)
            t0 = time.time()
            if not texts:
                sys.stdout.write(json.dumps({"p_female": None, "n": 0, "t_ms": 0}) + "\n")
                sys.stdout.flush()
                continue
            import torch
            from torch.utils.data import DataLoader, Dataset

            class D(Dataset):
                def __init__(self, rows):
                    self.rows = rows
                def __len__(self):
                    return len(self.rows)
                def __getitem__(self, i):
                    return self.rows[i]

            # 组装文本（昵称前缀，与训练一致）
            prep = []
            for i, t in enumerate(texts):
                nick = ""
                if use_nickname and req.get("nicknames") and i < len(req["nicknames"]) and req["nicknames"][i]:
                    nick = "[" + req["nicknames"][i] + "]"
                prep.append((nick + " " + t).strip())
            enc = tokenizer(prep, max_length=128, truncation=True, padding="max_length",
                            return_tensors="pt")
            with torch.no_grad():
                out = model(enc["input_ids"].to(device), enc["attention_mask"].to(device))
                logits = out[0] if isinstance(out, tuple) else out.logits
                probs = torch.softmax(logits, dim=1)[:, 1].cpu().tolist()
            p = sum(probs) / len(probs)
            dt = int((time.time() - t0) * 1000)
            sys.stdout.write(json.dumps({"p_female": round(p, 4), "n": len(texts), "t_ms": dt,
                                         "p_min": round(min(probs), 4), "p_max": round(max(probs), 4)}) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

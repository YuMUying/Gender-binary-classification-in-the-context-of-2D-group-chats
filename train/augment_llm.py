# -*- coding: utf-8 -*-
"""LLM 合成少数类样本：调用大模型生成"风格像女生的群聊发言"

原理（当代 GAN 替代品）：从训练集抽取女性用户的真实发言作为 few-shot 风格样例，
让 LLM 模仿其语气词/表情/句长/话题生成全新发言，弥补少数类样本不足。

配置（train/llm-config.json 或环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）：
  { "base_url": "https://api.deepseek.com/v1", "api_key": "sk-...", "model": "deepseek-chat" }
  · DeepSeek API / OpenAI / Qwen(dashscope) / Ollama(http://localhost:11434/v1) 均兼容

用法：
  python train/augment_llm.py --train data/train.jsonl --n 300 --out data/synth-female.jsonl
  python train/augment_llm.py --train data/train.jsonl --n 100 --per-call 20 --model deepseek-chat

产出 data/synth-female.jsonl：{text, label:'female', user_id: 9000000000+i(合成用户),
group_id:0, time:now, source:'llm'}。
之后训练时把该文件作为 --extra-train 追加（只进训练集，不进验证集）。
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request

from common import load_jsonl

SYSTEM_PROMPT = (
    "你是中文二次元群聊语料生成助手。任务：模仿给出的女性群友发言样例的风格，"
    "生成新的、不重复的群聊发言。要求：\n"
    "1. 口语化、自然，符合二次元群聊风格（可含语气词、颜文字、emoji，但不过度）；\n"
    "2. 每条 2~30 字，话题多样（日常、吐槽、动漫游戏、生活小事）；\n"
    "3. 不得逐字照抄样例，不得出现人名、QQ号、群号、@；\n"
    "4. 每条一行输出，不要编号、不要引号、不要任何解释。"
)


def load_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "llm-config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    return {
        "base_url": os.environ.get("LLM_BASE_URL") or cfg.get("base_url") or "https://api.deepseek.com/v1",
        "api_key": os.environ.get("LLM_API_KEY") or cfg.get("api_key") or "",
        "model": os.environ.get("LLM_MODEL") or cfg.get("model") or "deepseek-chat",
    }


def chat(cfg, messages, max_tokens=1024, temperature=1.0, tries=3):
    body = json.dumps({
        "model": cfg["model"], "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature, "stream": False,
    }).encode("utf-8")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}",
            })
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[llm] 第{i+1}次调用失败: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))
    return None


def parse_lines(text):
    """把模型输出解析为发言列表：按行、去编号/引号、过滤过长短与明显噪声"""
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[\d]+[.、)）]\s*", "", line).strip()
        line = line.strip('"“”\'')
        if not line or len(line) < 2 or len(line) > 40:
            continue
        if re.fullmatch(r"[a-zA-Z0-9\s\W]+", line):   # 纯符号/英文数字噪声
            continue
        out.append(line)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/train.jsonl", help="抽取女性样例的风格来源")
    ap.add_argument("--n", type=int, default=300, help="目标合成条数")
    ap.add_argument("--per-call", type=int, default=20, help="每次请求生成条数")
    ap.add_argument("--out", default="data/synth-female.jsonl")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = load_config()
    if not cfg["api_key"] and "11434" not in cfg["base_url"]:
        raise SystemExit("未配置 LLM：请创建 train/llm-config.json（含 api_key/base_url/model）或设置环境变量")

    # 女性样例池
    pool = []
    if os.path.exists(args.train):
        for r in load_jsonl(args.train):
            if r.get("label") == "female" and r.get("text") and len(r["text"]) >= 4:
                pool.append(r["text"])
    if not pool:
        print("[llm] 警告：train.jsonl 中没有女性样例，将使用内置通用样例（生成质量会下降）")
        pool = ["呜呜今天好累哦", "蹲蹲，有瓜吗", "贴贴~", "好耶！", "人家才没有呢", "喵喵喵？"]

    rng = random.Random(args.seed)
    existing = set(pool)
    synth = []
    uid_base = 9000000000
    calls = 0
    print(f"[llm] 模型={cfg['model']} 目标={args.n} 条，女性样例池={len(pool)} 条")

    while len(synth) < args.n and calls < args.n // args.per_call + 10:
        exemplars = rng.sample(pool, min(10, len(pool)))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "风格样例：\n" + "\n".join(exemplars) +
             f"\n\n请生成 {args.per_call} 条新的发言。"},
        ]
        text = chat(cfg, messages, max_tokens=1024, temperature=args.temperature)
        calls += 1
        if not text:
            print("[llm] 调用失败，提前结束")
            break
        for line in parse_lines(text):
            if line in existing:
                continue
            existing.add(line)
            synth.append({
                "text": line, "label": "female", "user_id": uid_base + len(synth),
                "group_id": 0, "time": int(time.time()), "source": "llm",
            })
            if len(synth) >= args.n:
                break
        print(f"[llm] 进度 {len(synth)}/{args.n}（调用 {calls} 次）")
        time.sleep(1)

    os.makedirs(os.path.dirname(args.out), exist_ok=True) if os.path.dirname(args.out) else None
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(s, ensure_ascii=False) for s in synth) + ("\n" if synth else ""))
    print(f"[llm] 完成：{len(synth)} 条 → {args.out}")
    print("训练时追加: python train/train_bert.py --train data/train.jsonl --extra-train data/synth-female.jsonl ...")


if __name__ == "__main__":
    main()

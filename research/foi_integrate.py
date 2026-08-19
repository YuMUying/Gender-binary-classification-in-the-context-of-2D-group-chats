# -*- coding: utf-8 -*-
"""foi_integrate.py — 把 FOI 混合指数并入标定参考包 CSV/MD

从 outputs/foi_final.csv 读取混合 FOI，按 QQ号 合并进 标定参考包.csv，
新增列: FOI指数, FOI提示
提示规则（对男性用户）:
  FOI >= 80  → '男娘信号强（BERT高概率+男娘话题密集）'
  FOI >= 60  → '男娘信号中'
  FOI >= 45  → '男娘信号弱'
  FOI <  45  → ''
"""
import csv

foi_map = {}
with open("outputs/foi_final.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        try:
            foi_map[int(row["user_id"])] = (float(row["foi_index"]), row["source"], row.get("orientation", ""))
        except (ValueError, KeyError):
            continue

def foi_tip(v):
    if v >= 80:
        return "男娘信号强（BERT高概率+男娘话题密集）"
    if v >= 60:
        return "男娘信号中"
    if v >= 45:
        return "男娘信号弱"
    return ""

rows = list(csv.DictReader(open("outputs/标定参考包.csv", encoding="utf-8")))
fn = list(rows[0].keys()) + ["FOI指数", "FOI提示"]
with open("outputs/标定参考包.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fn)
    w.writeheader()
    for r in rows:
        uid = int(r["QQ号"])
        info = foi_map.get(uid)
        if info:
            v, src, ori = info
            r["FOI指数"] = f"{v:.0f}"
            r["FOI提示"] = foi_tip(v) if r.get("模型结论") != "female" else foi_tip(v) + "（模型判女，需重点复核）"
        else:
            r["FOI指数"] = ""
            r["FOI提示"] = ""
        w.writerow(r)

n_with = sum(1 for r in rows if r["FOI指数"])
print(f"[完成] 标定参考包.csv 已更新 FOI 列（{n_with}/{len(rows)} 人有 FOI）")

md = open("outputs/标定参考包.md", encoding="utf-8").read()
if "FOI 混合指数" not in md:
    md += '''
## FOI 混合指数（男娘/小众性取向，v3 定稿）
- **构成**：BERT 微调概率（chinese-roberta-wwm-ext，13 阳性[9 真实+4 伪标签] vs 56 正常男）× 0.6 + 统计特征指数 × 0.4
- **训练手段**：用户均衡采样、GRL 用户身份对抗（防 9 人过拟合）、软标签、阳性过采样、Focal Loss
- **统计特征**：男娘话题（男娘/女装/伪娘/丝袜/小裙子/jk/lo裙）+ 稀有萌系（qwq/QAQ/TAT/叭/诶嘿）+ 百合/BL
- **输出**：0-100 连续指数（0.2→0, 0.8→100 线性映射概率）；样本 <300 条自动降权
- **验证**：7/10 真实阳性 P≥0.88（模型高置信）；3 个弱信号"双"标签（文本无男娘特征）分数低——符合性取向光谱定位
- **定位**：男娘相关信号强度（供人工参考，非身份判定；"谈论男娘"与"自身是男娘"需人工甄别）
- 倾向轨迹：outputs/foi_curve.csv（滑窗+Kalman 平滑）
'''
    open("outputs/标定参考包.md", "w", encoding="utf-8").write(md)
    print("[完成] 标定参考包.md 已追加 FOI 混合指数说明")

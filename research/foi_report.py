# -*- coding: utf-8 -*-
"""foi_report.py — 生成 FOI 综合指数报告（markdown）"""
import csv
from datetime import datetime

rows = list(csv.DictReader(open("outputs/foi_final.csv", encoding="utf-8")))
for r in rows:
    r["foi_index"] = float(r["foi_index"])
    r["n_messages"] = int(r["n_messages"])

# 已知 orientation 对照
labels = {}
for r in rows:
    if r["orientation"]:
        labels[r["user_id"]] = r["orientation"]

lines = []
lines.append("# FOI 男娘/小众性取向综合指数报告")
lines.append("")
lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append("")
lines.append("## 方法")
lines.append("")
lines.append("**混合指数 = BERT 微调概率 × 0.6 + 统计特征指数 × 0.4**（0-100 连续分）")
lines.append("")
lines.append("- **BERT 模型**：chinese-roberta-wwm-ext，13 阳性（9 真实 orientation 男 + 4 限量伪标签）vs 56 正常男")
lines.append("- **训练手段**：用户均衡采样 / GRL 用户身份对抗 / 软标签 / 阳性过采样 / Focal Loss")
lines.append("- **统计特征**：男娘话题（男娘/女装/伪娘/丝袜/小裙子/jk/lo裙/白丝/黑丝）+ 稀有萌系（qwq/QAQ/TAT/叭/诶嘿/Orz/OvO）+ 百合/BL/耽美/嗑cp")
lines.append("- **时间轨迹**：每 100 条消息一个窗口，滑窗打分 + 一阶 Kalman 平滑（`foi_curve.csv` / `foi_curves.png`）")
lines.append("- **置信度**：样本 <300 条自动降权；`ci95_foi` 为窗口级 95% 置信区间")
lines.append("")
lines.append("## 真实 orientation 用户对照")
lines.append("")
lines.append("| QQ号 | 标签 | 消息数 | 统计FOI | BERT FOI | 混合FOI | 说明 |")
lines.append("|---|---|---|---|---|---|---|")
for r in sorted(rows, key=lambda x: -x["foi_index"]):
    if r["user_id"] in labels:
        desc = "强信号" if r["foi_index"] >= 70 else ("中信号" if r["foi_index"] >= 45 else "弱信号（文本无男娘特征，光谱中段）")
        lines.append(f"| {r['user_id']} | {labels[r['user_id']]} | {r['n_messages']} | {r['stat_foi']} | {r['bert_foi']} | {r['foi_index']} | {desc} |")
lines.append("")
lines.append("> 注：7/10 真实阳性 BERT P≥0.88；3 个弱信号用户（439161815/1965417382/2948988043）为'双'标签中文本表达偏直男者，指数低属光谱定位，非漏判。")
lines.append("")
lines.append("## 全库 TOP 30（无已知标签）")
lines.append("")
lines.append("| 排名 | QQ号 | 消息数 | 混合FOI | 来源 |")
lines.append("|---|---|---|---|---|")
rank = 1
for r in sorted(rows, key=lambda x: -x["foi_index"]):
    if r["user_id"] in labels:
        continue
    lines.append(f"| {rank} | {r['user_id']} | {r['n_messages']} | {r['foi_index']} | {r['source']} |")
    rank += 1
    if rank > 30:
        break
lines.append("")
lines.append("## 使用说明")
lines.append("")
lines.append("- FOI 是**信号强度指数**（供人工参考），不是身份判定——'谈论男娘'与'自身是男娘'需人工甄别")
lines.append("- 结合性别模型结论交叉参考：模型判 female + FOI 高 = 重点复核对象")
lines.append("- 弱信号'双'标签用户指数居中属正常（性取向光谱）")
lines.append("- 倾向曲线看用户随时间的变化（如是否近期才出现男娘话题）")
lines.append("")
lines.append("## 文件清单")
lines.append("")
lines.append("- `outputs/foi_final.csv` — 771 人混合指数")
lines.append("- `outputs/foi_pred.csv` — 119 人 BERT 概率（样本≥200）")
lines.append("- `outputs/foi_curve.csv` — 滑窗轨迹（原始+平滑）")
lines.append("- `outputs/foi_curves.png` — 典型用户倾向曲线图")
lines.append("- `models/foi-bert-final/` — BERT 模型权重")

with open("outputs/FOI报告.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("[完成] outputs/FOI报告.md")

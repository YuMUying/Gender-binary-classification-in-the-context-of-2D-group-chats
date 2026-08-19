# -*- coding: utf-8 -*-
"""foi_curve_plot.py — 生成 FOI 倾向曲线图（滑窗概率 + Kalman 平滑）

选取：真实阳性中信号强的 3 人 + 伪标签 2 人 + 正常男 2 人作对比，
画 P(男娘) 随消息窗口的时间轨迹（原始窗口分 + Kalman 平滑线）。
"""
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

SHOW_USERS = [375569635, 963653008, 443628409,    # 真实强信号阳性
              3969964584, 2159492514,              # 伪标签
              1853545312, 2093211983]              # 正常男（对照）

curve = defaultdict(list)
with open("outputs/foi_curve.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        uid = int(row["user_id"])
        curve[uid].append((int(row["time_start"]), float(row["prob_raw"]), float(row["prob_smooth"])))

fig, ax = plt.subplots(figsize=(14, 7))
colors = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#27ae60", "#3498db", "#9b59b6"]
for i, uid in enumerate(SHOW_USERS):
    if uid not in curve:
        continue
    pts = sorted(curve[uid])
    times = [datetime.fromtimestamp(t) for t, _, _ in pts]
    raw = [p for _, p, _ in pts]
    sm = [s for _, _, s in pts]
    c = colors[i % len(colors)]
    ax.plot(times, raw, color=c, alpha=0.25, linewidth=0.8)
    ax.plot(times, sm, color=c, linewidth=2, label=f"{uid} (平滑)")
ax.axhline(0.5, color="gray", linestyle="--", linewidth=1, alpha=0.7)
ax.text(times[0] if times else 0, 0.52, "P=0.5 参考线", fontsize=9, color="gray")
ax.set_ylabel("P(男娘)")
ax.set_title("FOI 倾向曲线：滑窗 P(男娘) 原始分 + Kalman 平滑（样本≥200）")
ax.legend(loc="upper left", fontsize=8)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
ax.grid(alpha=0.3)
fig.tight_layout()
os.makedirs("outputs", exist_ok=True)
fig.savefig("outputs/foi_curves.png", dpi=130)
print("[完成] outputs/foi_curves.png")

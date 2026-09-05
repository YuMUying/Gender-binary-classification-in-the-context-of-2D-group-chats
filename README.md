# 性别二分类与"软男"细分：二次元 QQ 群语境下的性别风格推断

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个端到端的 QQ 群聊性别风格推断系统：从 OneBot 协议采集、消息入库、BERT 三分类训练，到线上推理服务与"不确定拒绝空间"（abstain）设计。本项目同时是一份完整的**负结果实验记录**——三条改进路线被数据证伪的过程与方法论同样公开。

> ⚠️ **隐私声明**：因语料来自真实社区成员的私聊/群聊，**训练数据、标注账本与模型权重均不公开**。本仓库只公开方法学、代码结构与实验协议。文中出现的 `U###`/`G###` 均为不可逆哈希别名（映射见 `docs/id-aliases.csv`，仅存 SHA-256 前 8 位），所有示例 QQ 号均为占位符。

## 任务定义

三分类：**女（F）/ 软男（SM）/ 男（M）**，线上二元裁决时 SM 折叠进 M。

- **F**：女性语体（乙女/软妹型原型 A；以及"男域原生女"原型 B——长期混迹男性主导群、说话干脆玩梗但话题选择与情绪表达仍呈女性视角的成员，即"清梦型"）
- **SM（soft_male）**：软腔男性——语体靠近女性原型但性别为男的成员
- 裁决指标：**F 类判定准确率是唯一指标**（防止把软腔真女判成男的社交灾难），M 侧含 SM 的二元召回为约束条件

## 架构

```
Pi 采集器 ×4 (Node, OneBot 11 WS, systemd)
    │ 增量同步 (锚点式 MAX(time) + jsonl + sftp)
    ▼
main.db (SQLite, 消息主库, PC)
    │ export-dataset.js (--mode train --max-per-user 2000)
    ▼
compose_r3.py (train/val 组合, val 18 人锁定协议)
    │
    ▼
train_bert3.py (chinese-roberta-wwm-ext, 3 分类, 三 seed 集成 {7,8,9})
    │ model.pt ×3
    ▼
infer_r3.py (实时推理服务, 消息级 softmax 平均) + 静态表 (全账本打分)
    │
    ▼
infer.js (线上推理响应: 私聊/群聊命令)
    ├─ r3 三 seed 均值 P_female
    ├─ abstain 裁决: ≥0.50 → F | <0.35 → M | 0.35-0.50 → 不确定(转人工)
    └─ 第三参考通道: v10 老模型排序 + LLM-as-judge 倾向 + 带外标定模型, 仅供参考
```

## 核心实验结论（详见 docs/journal/experiments.md）

| 版本 | 结论 |
|---|---|
| s0v56（现役） | 三 seed 二元 0.889（含 SM 的 M 侧 1.000）；abstain 带 0.35-0.50 将 F 判对率 86.9% → **96.7%**，被拒 18/190 人中的 6F 全部为"男域原生女"原型 |
| s0v57 | 难例塞回训练 → memorization 零泛化（阴性） |
| s0v58 | LLM 人格卡合成 6卡×300 条 → 测试对仅 +0.02（阴性：风格不可迁移） |
| s0v59 | 昵称通道消融 → val 崩盘 + 预测饱和，昵称=捷径泄漏（阴性，反向验证纯文本设计的正确性） |
| LLM-as-judge / 双模型 stacking | 分辨率 ~60-73%，不足以自动裁决 → 落地为带内**参考通道**（不改变裁决边界） |

**方法学启示**：类内分布问题（F 类含两个异质原型）无法靠样本增殖或输入特征注入解决——只有"换学习目标（多原型/对比学习）"与"引入外部知识（LLM 裁判）"两条路，且前者受制于原型 B 样本量（≥5）。

## 目录结构

```
src/          Node 采集与推理服务（OneBot 11 协议）
scripts/      数据导出/打标/回填工具（node）
train/        训练与推理核心（Python: train_bert3/common/infer_r3/absteval/compose_r3）
config/       配置样例（真实配置不入库）
docs/         实验日志（全量阴性结果）、决策记录（ADR）、数据 schema、别名映射
dev/          本地 OneBot mock
```

## 快速开始

```bash
# 训练（需 GPU）
pip install -r requirements.txt
python train/train_bert3.py --train train.jsonl --val val.jsonl \
  --out-dir models/s0v56-seed7 --epochs 4 --batch 32 --lr 2e-5 \
  --max-len 128 --user-weight --seed 7

# 实时推理服务（stdin/stdout JSON 协议, 三 seed 集成 + abstain 裁决）
python train/infer_r3.py
echo '{"texts":["你好","在吗"]}' | python train/infer_r3.py
```

输入格式：每样本一行 JSON（`{user_id, text, label}`，见 `docs/data-schema.md`）；昵称/上下文通道默认关闭（消融已证伪，见实验日志）。

## 数据 Schema

见 [`docs/data-schema.md`](docs/data-schema.md)。导出配方（复现关键）：`node scripts/export-dataset.js --mode train --format jsonl --max-per-user 2000`——`--max-per-user 2000` 截断与历史版本对齐是可复现性的硬约束。

## License

MIT

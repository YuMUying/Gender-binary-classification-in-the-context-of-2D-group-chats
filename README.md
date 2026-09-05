# 性别三分类与"软男"细分：二次元 QQ 群语境下的性别风格推断

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个端到端的 QQ 群聊性别风格推断系统：从 OneBot 协议采集、消息入库、BERT 三分类训练，到 abstain 裁决与"不确定拒绝空间"设计。本项目同时是一份完整的**负结果实验记录**——三条改进路线被数据证伪的过程与方法论同样公开。

> **隐私与使用声明**：语料与标注账本来自真实社区，**永不公开**；生产模型与决策管线模型的**权重**通过 [Releases](../../releases/tag/v1.0.0) 公开（仅供学术复现，不得用于对真实个体做身份或倾向判定）。文中 `U###`/`G###` 为不可逆哈希别名（SHA-256 前 8 位映射见 `docs/id-aliases.csv`），示例 QQ 号均为占位符。机器人本体只做**采集 + 白名单私聊 AI 助手**，不对群聊提供任何回复。

## 任务定义

三分类：**女（F）/ 软男（SM）/ 男（M）**，二元裁决时 SM 折叠进 M。

- **F**：女性语体（乙女/软妹型原型 A；以及"男域原生女"原型 B——长期混迹男性主导群、说话干脆玩梗但话题选择与情绪表达仍呈女性视角的成员）
- **SM（soft_male）**：软腔男性——语体靠近女性原型但性别为男的成员
- 裁决指标：**F 类判定准确率是唯一指标**（防止把软腔真女判成男的社交灾难），M 侧含 SM 的二元召回为约束条件

## 架构

```
采集器 (Node, OneBot 11 WS)          ← 只收消息入库, 不产生任何群聊回复
    │ 增量同步 (锚点式 MAX(time) + jsonl + sftp)
    ▼
main.db (SQLite, 消息主库)
    │ export-dataset.js (--mode train --max-per-user 2000)
    ▼
compose_r3.py (train/val 组合, val 18 人锁定协议)
    ▼
train_bert3.py (chinese-roberta-wwm-ext, 3 分类, 三 seed 集成 {7,8,9})
    ▼
infer_r3.py (推理服务, 消息级 softmax 平均)      ← 权重见 Releases
    ▼
absteval.py → abstain 裁决带 0.35-0.50 (静态表)
    ▼
人工复核 (三参考通道: v10 分歧/LLM-as-judge 倾向/带外标定模型)
```

**机器人运行时**：只收消息入库 + 白名单私聊 AI 助手（LLM, deepseek；支持角色卡系统 `/cards` `/card <名>` `/uncard`）。推理/指数等历史命令已全部下线——模型只通过离线脚本对账本评估，不向群成员暴露任何推断结果。

## 核心实验结论（详见 docs/journal/experiments.md）

| 版本 | 结论 |
|---|---|
| s0v56（现役） | 三 seed 二元 0.889（含 SM 的 M 侧 1.000）；abstain 带 0.35-0.50 将 F 判对率 86.9% → **96.7%**，被拒 18/190 人中的 6F 全部为"男域原生女"原型 |
| s0v57 | 难例塞回训练 → memorization 零泛化（阴性） |
| s0v58 | LLM 人格卡合成 6卡×300 条 → 测试对仅 +0.02（阴性：风格不可迁移） |
| s0v59 | 昵称通道消融 → val 崩盘 + 预测饱和，昵称=捷径泄漏（阴性，反向验证纯文本设计正确性） |
| LLM-as-judge / 双模型 stacking / 带外标定 | 分辨率 60-73%，不足以自动裁决 → 落地为带内**参考通道**（不改变裁决边界） |

**方法学启示**：类内分布问题（F 类含两个异质原型）无法靠样本增殖或输入特征注入解决——只剩"换学习目标（多原型/对比学习）"与"引入外部知识（LLM 裁判）"两条路，且前者受制于原型 B 样本量（≥5）。

## 目录结构

```
src/          Node 采集服务 + 私聊 AI 助手（src/llm/, OneBot 11 协议）
scripts/      数据导出/打标/回填工具（node）
train/        训练与推理核心（Python: train_bert3/common/infer_r3/absteval/compose_r3）+ 发布管线
config/       配置样例（真实配置不入库）
docs/         实验日志（全量阴性结果）、决策记录（ADR）、数据 schema、模型校验和、别名映射
dev/          本地 OneBot mock
```

## 快速开始

```bash
pip install -r requirements.txt
# 下载权重(Releases v1.0.0): seed7/8/9_model.pt → models/r3-s0v56/seed{7,8,9}/model.pt
#                            v10_model.pt      → models/bert-v10-wb-fix/model.pt
# sha256 校验见 docs/models-checksums.md; tokenizer 首次运行自动从 HF Hub 拉取

# 实时推理服务（stdin/stdout JSON, 三 seed 集成 + abstain 裁决）
python train/infer_r3.py
echo '{"texts":["你好","在吗"]}' | python train/infer_r3.py
```

训练数据格式见 `docs/data-schema.md`；导出配方：`node scripts/export-dataset.js --mode train --format jsonl --max-per-user 2000`（截断参数是可复现性硬约束）。

## 私聊 AI 助手（角色卡系统）

`src/llm/` 是一个迷你 Agent 循环（system 人设 + 历史窗口 + 工具调用 + 日预算），默认人设可在 `config/llm.json` 覆盖；`personas/*.json` 为角色卡（`{"name": ..., "身份感": ..., "语体": [...], "口头禅": [...]}` 结构，加载后拼装为系统提示词）。示例卡见 `personas/example.json`。

## License

MIT

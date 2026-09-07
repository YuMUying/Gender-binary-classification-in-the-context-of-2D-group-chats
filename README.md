# 性别三分类与"软男"细分：二次元兴趣群语境下的性别风格推断

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一项针对中文兴趣社群性别风格推断的研究工件仓库：**模型权重 + 评测代码 + 脱敏样例数据 + 完整的负结果实验记录**。方法与数据构建过程见论文（预印本）。

> **隐私与使用声明**：完整语料（302 万条消息）与标注账本**永不公开**；生产模型权重通过 [Releases](../../releases/tag/v1.0.0) 公开。**脱敏样例数据集**见 `data-sample/`（说话人以随机别名呈现、日期粗化到日、文本经规则清洗与人工审计；清洗规程与标注准则随样例发布）。

## 任务定义

三分类：**女（F）/ 软腔男（SM）/ 男（M）**，二元裁决时 SM 折叠进 M。

- **F**：女性语体（乙女/软妹型原型 A；以及"男域原生女"原型 B——长期混迹男性主导群、说话干脆玩梗但话题选择与情绪表达仍呈女性视角的成员）
- **SM（soft_male）**：软腔男性——语体靠近女性原型但性别为男的成员
- 裁决指标：**F 类判定准确率是唯一指标**（防止把软腔真女判成男的社交灾难），M 侧含 SM 的二元召回为约束条件

## 训练与评测管线

```
离线语料库 (SQLite, 私有)
    | export-dataset.js (--mode train --max-per-user 2000)
    v
compose_r3.py (train/val 组合, val 18 人锁定协议)
    v
train_bert3.py (chinese-roberta-wwm-ext, 3 分类, 三 seed 集成 {7,8,9})
    v
infer_r3.py (推理服务, 消息级 softmax 平均)      <- 权重见 Releases
    v
absteval.py -> abstain 裁决带 0.35-0.50 (静态表)
    v
人工复核 (三参考通道: v10 分歧/LLM-as-judge 倾向/带外标定模型)
```

## 核心实验结论（详见 docs/journal/experiments.md）

| 版本 | 结论 |
|---|---|
| s0v56（现役） | 三 seed 二元 0.889（含 SM 的 M 侧 1.000）；abstain 带 0.35-0.50 将 F 判对率 86.9% -> **96.4%**，被拒 18/190 人中的 6F 全部为"男域原生女"原型 |
| s0v57 | 难例塞回训练 -> memorization 零泛化（阴性） |
| s0v58 | LLM 人格卡合成 6卡×300 条 -> 测试对仅 +0.02（阴性：风格不可迁移） |
| s0v59 | 昵称通道消融 -> val 崩盘 + 预测饱和，昵称=捷径泄漏（阴性，反向验证纯文本设计正确性） |
| LLM-as-judge / 双模型 stacking / 带外标定 | 分辨率 60-73%，不足以自动裁决 -> 落地为带内**参考通道**（不改变裁决边界） |

**方法学启示**：类内分布问题（F 类含两个异质原型）无法靠样本增殖或输入特征注入解决——只剩"换学习目标（多原型/对比学习）"与"引入外部知识（LLM 裁判）"两条路，且前者受制于原型 B 样本量。

## 目录结构

```
src/          私聊 AI 助手（src/llm/）与数据存取工具
scripts/      数据导出/打标工具（node）
train/        训练与推理核心（Python: train_bert3/common/infer_r3/absteval/compose_r3）+ 发布管线
data-sample/  脱敏样例数据集（随论文公开，见其 README 与规程）
docs/         实验日志（全量阴性结果）、数据 schema、模型校验和
```

## 快速开始

```bash
pip install -r requirements.txt
# 下载权重(Releases v1.0.0): seed7/8/9_model.pt -> models/r3-s0v56/seed{7,8,9}/model.pt
#                            v10_model.pt      -> models/bert-v10-wb-fix/model.pt
# sha256 校验见 docs/models-checksums.md; tokenizer 首次运行自动从 HF Hub 拉取

# 实时推理服务（stdin/stdout JSON, 三 seed 集成 + abstain 裁决）
python train/infer_r3.py
echo '{"texts":["你好","在吗"]}' | python train/infer_r3.py
```

训练数据格式见 `docs/data-schema.md`；导出配方：`node scripts/export-dataset.js --mode train --format jsonl --max-per-user 2000`（截断参数是可复现性硬约束）。

## License

MIT

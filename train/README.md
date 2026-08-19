# 训练侧说明

## 安装

```bash
pip install -r train/requirements.txt    # torch/transformers/sklearn（CPU 版 torch 即可起步）
```

## 数据前提

先用采集侧导出（**必须按 QQ 号分层划分**，同一人不跨 train/val）：

```bash
node scripts/export-dataset.js --mode train --split-by-user --val-ratio 0.15 --seed 42
node scripts/export-dataset.js --mode infer
```

## 三步走

### 1. 基线：TF-IDF + 逻辑回归（先验证信号是否存在）

```bash
# 逐条消息分类 + 用户级聚合评估
python train/baseline_tfidf.py --train data/train.jsonl --val data/val.jsonl --mode message

# 按人聚合分类（每人全部发言拼成一个文档）
python train/baseline_tfidf.py --train data/train.jsonl --val data/val.jsonl --mode user
```

产出 `outputs/baseline-users.csv`（每用户预测/错分列表）、`outputs/baseline-terms.txt`（最像男/女的字词）。

### 2. 主力：中文 RoBERTa 微调

```bash
python train/train_bert.py \
  --train data/train.jsonl --val data/val.jsonl \
  --model hfl/chinese-roberta-wwm-ext \
  --focal-gamma 2.0 --label-smoothing 0.1 --user-weight \
  --adv-user 0.3 --use-nickname --epochs 3 --out-dir models/bert
```

产出 `models/bert/`（权重+tokenizer+`metrics.json`+`users.csv` 错分用户报告）。

### 3. 推理（对未标注用户批量标定）

```bash
python train/predict.py --model-dir models/bert --input data/infer.jsonl \
  --out outputs/predictions.csv --min-per-user 10
```

## 关键选项与"风格反向"问题的对应

> 背景：男多女少 + 男声女气/女声狂野（用户观察：男生卖萌极其夸张、尺度大，女生未必做得到）。这类用户是"风格与标签矛盾"的**难例**，单靠平均确实不够。

| 选项 | 作用 | 对应问题 |
|---|---|---|
| `--focal-gamma 2.0` | Focal Loss：损失聚焦难分样本（风格反向者正是难例），简单样本不再淹没梯度 | 难例被多数派淹没 |
| `--label-smoothing 0.1` | 软化硬标签，容忍个别错位样本 | 单条消息与标签矛盾 |
| `--user-weight` | 按"人"均衡采样，防止话痨主导 | 男女消息量差异大 |
| `--oversample eda --oversample-k 2.5` | 少数类（女）过采样：`dup`=复制 / `eda`=字符级扰动 / `ctx`=上下文窗口变体 | 少数样本重复利用 |
| `--user-doc` | 用户级文档建模：把每人的发言按 400 字切成文档整体分类，模型看到的是"一个人的完整风格"而非单条 | 平均不够 → 升级为整体建模 |
| `--adv-user 0.3` | **对抗训练**（GRL + 用户身份判别头）：编码器被迫忘记"个人风格指纹"（谁在说话），只保留"性别泛化特征" | 防止模型死记个人夸张风格 |
| `--use-nickname` | 昵称/群名片作为特征 | 强信号 |

### 关于"GAN 高级过采样"的取舍

用户提议参考 GAN 做高级过采样。结论：**未实现 GAN，实现的是它的三个工程等价物（dup/eda/ctx）+ LLM 合成**，原因：

- **GAN 的用途是"生成全新样本"**，而文本 GAN（SeqGAN 等）训练极不稳定、生成质量差，且需要大量语料训练生成器——你的少数类只有 7 个用户、几千条消息，远不足以训练任何生成模型；
- **学术/工业界对文本不平衡的标准做法**正是本脚本实现的组合：过采样（复制/扰动）+ 加权采样 + **LLM 合成**（当代 GAN 替代品）；
- 其中 `ctx`（上下文窗口变体）是**数据特有的"高级重复利用"**：同一条中心消息配不同上下文子集（只有上文/只有下文/纯中心句），生成的新样本在 BERT 看来是不同输入——比纯复制信息增益大得多。

### LLM 合成少数类样本（augment_llm.py）

已配置 DeepSeek API（`train/llm-config.json`，密钥敏感勿外传），可直接使用：

```bash
# 从训练集抽取女性真实发言作为风格样例，生成 N 条新发言
python train/augment_llm.py --train data/train.jsonl --n 300 --out data/synth-female.jsonl

# 训练时追加（只进训练集，不进验证集）
python train/train_bert.py --train data/train.jsonl --val data/val.jsonl \
  --extra-train data/synth-female.jsonl --focal-gamma 2.0 --user-weight --adv-user 0.3 ...
```

- 合成样本使用独立合成 user_id（9000000000+），不会污染真实用户的用户级评估；
- 生成质量随真实女性样例池增大而提升（样例越多越像）；
- 每次生成后建议抽查（`head data/synth-female.jsonl`），明显不自然的删掉再训练；
- 兼容 Ollama：本地装 Ollama 后把 llm-config.json 改为 `http://localhost:11434/v1` + 模型名（如 `qwen3:4b`），api_key 留空。

### 为什么是"GRL 用户身份对抗"而不是 GAN？

- GAN 的典型用途是**生成**样本（弥补少数类数据）。文本 GAN 生成质量差、训练不稳定，对中文对话不实用；
- 这里的真问题不是"生成更多女生样本"，而是**模型会过拟合个人风格极端值**（某男生的夸张卖萌被当成"女性特征"学进去）；
- 学术上成立的做法是**对抗式去偏/去风格化**：加一个"用户身份判别器"，用梯度反转层（Gradient Reversal Layer, GRL）让它与主任务对抗——编码器必须学出"预测性别有用、但推测不出是谁在说话"的表示，从而把"个人风格"从"性别特征"中剥离。这正是 DANN 领域自适应的标准组件；
- 配合 focal loss（聚焦难例）+ 用户级文档建模，比单用平均稳健得多。

### 训练后必做：错分用户复核

`models/bert/users.csv` 里列出验证集错分用户。风格反向者很可能出现在这里，**先复核标签再调模型**：

```bash
node scripts/export-context.js --user <QQ号> --format readable --limit 100
```

- 若确认标签正确（他确实男、但发言极女气）→ 该样本是真实难例，保留，观察其分数是否接近 0.5（模型"犹豫"是合理输出）；
- 若标签存疑 → `label.js --user <QQ号> --gender unknown` 移出训练集，宁缺毋滥。

## 评估口径

- **不要只看消息级 accuracy**：男多女少时全猜男就很高分；
- 看：用户级准确率、女 recall/F1、PR-AUC；
- 阈值用验证集校准（脚本自动在用户级扫最优阈值并写入 metrics.json）。

## 数据量参考

- 每人 ≥300 条有效发言（≥4字）可训练用户级模型；标注 40~60 人评估才可信；
- 数据不足时：`--user-doc` 模式比逐条模式更稳；继续深挖历史（`bulk-collect.js --until-date`）；或 LLM 伪标签扩充。

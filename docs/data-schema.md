# 数据 Schema

## 训练样本（jsonl, 每行一对象）

```json
{"user_id": 0, "group_id": 0, "time": 0, "text": "消息文本", "label": "female", "nickname": ""}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | int | 发言者 QQ 号（发布数据中以 U### 别名替代，本仓库不含真实数据） |
| group_id | int | 群号（发布数据中以 G### 别名替代） |
| time | int | unix 秒级时间戳 |
| text | str | 消息文本（`[图片]` 类占位在导出时可过滤） |
| label | str | `female` / `soft_male` / `male` 三分类；二元评估时 soft_male 并入 male |
| nickname | str | 发言者当时昵称（**消融已证伪为捷径泄漏通道，训练时应丢弃此字段**，见实验日志 s0v59） |

## 导出与复现协议

- 导出：`node scripts/export-dataset.js --mode train --format jsonl --max-per-user 2000`
- `--max-per-user 2000` 截断是可复现性硬约束（与历史全部实验对齐）
- val 集锁定 18 人协议（`train/compose_r3.py` 组合），不随机划分
- 三 seed {7,8,9} 集成，消息级 softmax 平均后取用户级均值

## 标注账本

人工标注存于主库 `speaker_labels` 表（含 label_source/label_confidence 溯源），**不随仓库发布**。论文引用时提供统计量：总账本 199 人（F 64 / M 130 / unknown 5），置信区与拒绝带的划分规则见 `docs/decisions.md`。

# data-sample — 脱敏样例数据集（De-identified Sample, v1）

论文《面向男性聚集兴趣社群的性别混淆判别：风格捷径的断裂与选择性拒绝机制》的随文公开数据。English description below.

## 内容（Contents）

| 文件 | 说明 |
|---|---|
| `data/messages_sample_deidentified.csv` | 消息样例 29,874 条：msg_id, day（粗化到日）, group（anime-1..4 / otome-1..3）, speaker（随机别名 SPK_xxxx）, text（自动清洗+人工审计） |
| `data/annotations_deidentified.csv` | 标注账本脱敏表 190 人：alias（LED_xxx）, softness（软度得分 0–1）, community（anime/otome/other）, card_gender（网络名片性别）, label（实际标注性别 F→female / M→male） |
| `audit/random_audit.csv` | 人工审计子样本 300 条（种子 43） |
| `build_sample.py` | 生成脚本（读 SQLite 源库，固定种子 42 可复现；本仓库不含源库） |
| `SCRUBBING_PROTOCOL.md` | 脱敏与抽样规程（排除规则/字段脱敏/清洗规则 R6/人工审计结果/残留风险声明） |
| `guideline.zh.md` `guideline.en.md` | 标注准则（对应论文附录 A） |
| `manifest.json` | 行数、日期范围、规则版本、校验和 |

## 隐私要点（Privacy）

- 说话人仅以随机别名出现；昵称与全部账号标识符不导出；时间粗化到日；群以类别标签呈现。
- 文本经规则清洗（URL/邮箱/手机号/QQ 号形态数字串/@提及 → 占位符）并经 300 条随机人工审计（0 条不合格）。
- **消息样例不含 190 名标注说话人的任何文本**；标注表不含任何文本字段。
- 完整 302 万条语料因隐私不予公开，需要者签署数据使用协议后按需联系。

## 引用（Citation）

 Ma, Yingsong (2026). A de-identified message sample and annotation ledger of Chinese interest-group chats for gender-confusion research (v1). Zenodo. DOI: 10.5281/zenodo.XXXXXXXX（发布后回填）

关联论文：*Mitigating Gender Confusion in Male-Dominated Interest Communities: Style Shortcut Breakdown and Selective Rejection*（arXiv, 2026）。

## 许可

数据与文档：CC BY-NC 4.0（署名-非商业性使用 4.0）。仅限研究用途；不得用于对个人的属性推断或营销。

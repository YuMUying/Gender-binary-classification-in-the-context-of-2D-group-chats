# Gender Binary Classification in 2D Group Chats

**二次元群聊场景下的性别二分类系统**：基于 QQ 群聊消息（NapCat + OneBot 11 协议采集），使用中文 RoBERTa 微调，对群成员进行性别（男/女）二分类，并提供**小众性取向/男娘指数**标注维度与**多模型分歧指数**作为人工复核辅助。

> ⚠️ 本项目仅用于个人/学术研究。聊天数据为自收集的私有数据，**不随仓库分发**（未脱敏）；训练所用的开源外部数据来源见下文。

---

## 1. 系统架构

```
QQ 客户端 (NapCat 注入) ──OneBot11 WS/HTTP──▶ 采集器 (Node.js)
                                                 │
                                    messages 表 (SQLite)
                                                 │
                                    标注 (人工) / 自动标签
                                                 │
                                    BERT 微调 (Chinese RoBERTa)
                                                 │
                                    全库推理 → 分歧指数 → 参考包
```

- **QQ 客户端**：NTQQ（推荐 9.9.26-44343，见 NapCat 官方 release 说明）
- **NapCat**：[NapCatQQ](https://github.com/NapNeko/NapCatQQ)（推荐最新 v4.18.x；`o3HookMode` 建议设为 `0` 以避免"假死"断流）
- **OneBot 11**：NapCat 内置（HTTP :3000 / WS :3001）
- **数据库**：SQLite（Node 内置 `node:sqlite`，零原生依赖）

## 2. 环境要求

| 依赖 | 版本 |
|---|---|
| Node.js | ≥ 22（使用 `node:sqlite`） |
| Python | 3.10 |
| PyTorch | ≥ 2.0（CUDA 可选，推理推荐 GPU） |
| transformers | 4.x |
| 中文 RoBERTa | `hfl/chinese-roberta-wwm-ext`（首次运行自动下载） |

```bash
pip install torch transformers scikit-learn
```

## 3. 部署 QQ / NapCat（采集端）

1. 安装 QQ NT 客户端 + [NapCat](https://github.com/NapNeko/NapCatQQ/releases)（Windows 一键包或手动注入）
2. NapCat 配置（`config/` 目录）：
   - `onebot11_<QQ号>.json`：HTTP 3000 + WS 3001（参考 `config/onebot11.example.json`）
   - `webui.json`：WebUI token（修改后需无 BOM UTF-8 保存，NapCat 的 JSON.parse 不支持 BOM）
   - `napcat_<QQ号>.json`：建议 `"o3HookMode": 0`、`"fileLog": true`（假死排查）
3. 登录：NapCat WebUI 扫码登录机器人账号
4. 验证：`curl -X POST http://127.0.0.1:3000/get_login_info` 返回账号信息

## 4. 数据采集

### 4.1 群聊实时采集

```bash
# 复制配置模板，填写目标群
cp config/config.example.json config/config-group.json
# 编辑 config-group.json 的 collect.groups 为目标群号
$env:QQBOT_CONFIG='config/config-group.json'
node src/index.js
```

采集器行为：
- WS 实时监听（live）+ 定时增量回填（schedule）
- 图片/表情自动入库 `media_files`（get_image 走 QQ 内核通道，绕开 Rkey 限制）
- 消息写入 `data/qqchat.db`（`messages` 表）

### 4.2 历史消息导出（qce 插件）

安装 `napcat-plugin-qce` 后：

```bash
# 小批量串行导出（防风控）：目标 ~4000 条/批，批间暂停
node research/qce_batcher.mjs --group <群号> --max-batches 12 --pause-ms 40000
```

导出 JSON 自动归档到 `research/qce_batches/` 并导入 DB（`research/import_qce.py`）。

### 4.3 私聊/合并转发信封

```bash
# 拉取与某用户的私聊完整历史
node scripts/fetch-private.js --user <QQ号>
# 展开私聊中的合并转发（信封），递归抓取内容
node scripts/fetch-forwards.js --user <QQ号> --max-pages 10
```

> ⚠️ **占位符问题**：腾讯合并转发中，部分参与者会显示为占位符（`user_id=1094950020`、昵称"QQ用户"），**同一占位符在不同信封中代表不同真实用户**。必须按信封发送时间窗口（`forwards.envelope_time`）与真人确认归属后再映射，详见 `docs/QQ占位符问题归档.md`。

## 5. 数据标注

### 5.1 性别标注

```bash
node scripts/label.js --user <QQ号> --gender male|female|unknown
node scripts/label.js --list        # 查看已标注
```

### 5.2 小众性取向/男娘指数标注

```sql
-- speaker_labels.orientation 列
UPDATE speaker_labels SET orientation='双' WHERE user_id=...;
-- 取值：'双' / '男娘+双' / '同性恋' 等（人工标定）
```

二次元群聊中同性恋/双性恋/男娘现象普遍，其语言风格女性化会干扰性别分类——该维度用于后续单独训练"男娘指数"，作为人工复核信号而非性别判定输入。

### 5.3 训练集导出

```bash
node scripts/export-dataset.js --mode train --split-by-user \
  --night-mode --max-per-user 2000 \
  --out data/train.jsonl --out-val data/val.jsonl
```

关键处理（均已在脚本内实现）：
- `--split-by-user`：按 QQ 号划分训练/验证（同人不跨集，防泄漏）
- `--night-mode`：深夜(0-6点)消息噪声处理——多样本用户剔除、少样本用户降权（loss 层 weight）
- `--max-per-user 2000`：控制话痨用户占比
- `config/excluded_users.json`：排除机器人/打卡号/噪音用户

## 6. 训练

```bash
cd train
python train_bert.py \
  --train ../data/train.jsonl --val ../data/val.jsonl \
  --extra-train ../data/synth-female-v2.jsonl,../data/weibo-female.jsonl \
  --focal-gamma 2.0 --label-smoothing 0.1 \
  --user-weight --oversample eda --oversample-k 2 \
  --use-nickname --epochs 3 --batch 16 --max-len 128 \
  --lr 1e-5 --weight-decay 0.01 \
  --out-dir ../models/bert-v10-wb --seed 42
```

### 6.1 训练数据来源说明

| 数据 | 来源 | 说明 |
|---|---|---|
| 群聊真实数据 | 自收集（QQ 群聊，不随仓库分发） | 敏感数据未脱敏 |
| 微博女性语料 | [十万微博数据集（AtomGit e8784）](https://gitcode.com/Premium-Resources/e8784)（48女/55男，CSV 分性别） | 提取女性推文，按真实用户分组（隔离 user_id 段） |
| WU3D 抑郁微博数据集 | [Weibo-User-Depression-Detection-Dataset](https://github.com/Xiexiaqing/Weibo-User-Depession-Detection-Dataset)（Google Drive 下载） | 仅取抑郁女性子集，**实验证明域偏移过大、混合后有害**（见 docs 实验报告） |
| LLM 合成女性样本 | gpt-5.5 生成（`research/synth_female_v2.py`） | 5 风格：正常/抽象/萌系/糙/深夜 + 病娇；隔离 user_id 段，**不进主库** |

**外部数据使用铁律**：
1. 一律用独立 user_id 段（9000xxxxxx+），绝不混入真实用户
2. 用户级平权采样下，外部用户数 ≈ 真实用户数的 50%-100%（过多会淹没真实风格）
3. 用风格偏移审查（`research/rebuild_balanced3.py` 输出）评估域偏移，偏移过大的数据宁可不用

### 6.2 模型版本

| 模型 | 说明 |
|---|---|
| `bert-v10-wb` | **生产模型**（真实+微博女性）：全库已知标签一致率 96.3% |
| `bert-v10-synth` | 真实+LLM合成（对比用） |
| `bert-v10-all` | 真实+全部外部数据（**实验证明混合抑郁数据有害，仅存档**） |
| `bert-v7` | 旧版生产模型（对比基线） |
| `erotic-bert` | 涩情等级模型（0-3 四分类，独立任务） |

## 7. 推理

```bash
# 单模型全库预测
python train/predict.py --from-db --model-dir models/bert-v10-wb \
  --out outputs/score-v10-wb-all.csv --batch 96

# 多模型分歧指数（v10/v10-synth/v10-wb/v7，各用自身阈值）
python train/predict_multi.py \
  --models bert-v10,bert-v10-synth,bert-v10-wb,bert-v7 \
  --out outputs/score-multi-v10.csv --batch 96
python research/disagree_v10.py    # per-model 阈值重算 flip/votes/disagreement
```

### 7.1 标定参考包（人工复核辅助）

```bash
python research/calib_ref.py        # 待标注用户指数（P(女)/萌系/抽象/涩情/深夜占比）
python research/merge_flip2.py      # 四模型翻案标记
python research/speech_index.py     # 话语指数（性发泄/粗口/叫爹率）
python research/integrate_indices.py # MSI男侧证据指数 + RI复核指数
```

- **MSI（男侧证据指数 0-100）**：性发泄/粗口/叫爹/求本子/要色图/涩情等级加权
- **RI（复核指数 0-100）**：判女但 MSI 高、多模型翻案、网络性别冲突等——RI 高 = 必须人工复核
- 验证结论：MSI 男女分离（男中位 40 / 女中位 ~27）；RI 与模型错误强相关（错误用户 RI≈40+ vs 正确 ≈11）

### 7.2 已知模型盲区（重要）

文本模型只能学"风格"，以下情况会误判：
1. **同性恋/双性恋/男娘男性**（风格女性化）——需外部证据（照片/空间内容/现实认识）标注
2. **抑郁暴躁风格女性**（雪々类）——风格极端，各模型均难
3. 图片/贴纸占比 >70% 的"搬图机器"（无有效文本）——无法用文本模型

## 8. 消息流保活（运维）

`research/keepalive.mjs`：每 5 分钟 `get_group_member_list(no_cache=true)` 触发 MSF 网络活性 + DB 消息新鲜度检测（15 分钟停滞告警）。**不自动重启**（重启=重新登录=风控筹码）。

NapCat"假死"（消息流断但服务活着）根因：`o3HookMode=1` 的 O3 包 hook 干扰票据重协商——**设为 0 可显著改善**；QQ 版本须匹配 NapCat 支持列表（推荐 9.9.26-44343）。

## 9. 项目结构

```
├── src/               # 采集器核心（Node，node:sqlite）
├── scripts/           # 标注/导出/信封抓取/私聊抓取
├── train/             # BERT 训练/预测/多模型分歧
├── research/          # 分析工具（指数/合成/审查/保活）
├── models/            # 模型权重（Git LFS）
├── config/            # 配置模板（真实配置不入库）
├── docs/              # 文档（占位符问题/训练报告/多模态实验）
└── data/              # 数据库与数据集（不入库，敏感）
```

## 10. 隐私与合规

- 聊天数据为自收集私有数据，未脱敏，**不随仓库分发**
- 外部数据集仅使用其公开部分，遵守各自许可证
- 本项目仅供个人学习与研究，请遵守当地法律法规与平台规则

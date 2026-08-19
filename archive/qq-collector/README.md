# qq-collector

基于 **Milky 协议**（[acidify](https://github.com/LagrangeDev/acidify) / [Yogurt](https://github.com/SaltifyDev/yogurt-releases) 协议端）的 QQ 群聊数据采集 + 自动回复机器人。

## 功能

- 实时监听好友/群消息（WebSocket 连接 Yogurt `/event` 端点）
- 消息落库：JSONL 按天分文件（`data/messages-YYYY-MM-DD.jsonl`），保留原始消息段
- 批量拉取历史消息：`get_history_messages` 自动翻页（单次上限 30 条）
- 自动回复：关键字触发 + `/指令` 路由，经 `/api/send_group_message`、`/api/send_private_message` 发送
- 断线自动重连（指数退避）

## 前置条件

1. 安卓手机安装 [Termux](https://f-droid.org/packages/com.termux/)（或任何能跑 Node 18+ 的机器）
2. Yogurt 协议端已运行并登录成功（默认 `127.0.0.1:3000`），配置见 [官方文档](https://acidify.ntqqrev.org/yogurt/start)

```bash
# Termux 里安装 Yogurt
pkg update && pkg install nodejs-lts
npm install -g @acidify/yogurt
yogurt    # 首次运行生成 config.json，填好 uin/password/signApiUrl 后重新启动并登录
```

## 安装运行

```bash
cd qq-collector
npm install        # 仅依赖 ws（纯 JS，无需编译）
# 按需修改 config.json（监听范围、关键字回复、accessToken 等）
node index.js      # 实时采集
```

## 历史消息批量拉取

```bash
node history.js --group 123456789 --limit 500            # 拉该群最新 500 条
node history.js --group 123456789 --start-seq 3000 --limit 200   # 从 seq 3000 向前拉
node history.js --friend 987654321 --limit 100
```

## 配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `milky.host/port/prefix/accessToken` | Yogurt Milky 服务地址与令牌（与 Yogurt 的 config.json 保持一致） |
| `storage.dir` | JSONL 存储目录 |
| `listen.groups/friends` | 白名单（空数组 = 全部）；只处理列表内的群/好友 |
| `filters.ignoreSelf` | 丢弃自己发出的消息 |
| `filters.keywords` | 预留：只保存含关键词的消息（留空 = 全存） |
| `reply.enabled/triggers/commands` | 自动回复：关键字（exact/contains）与 `/指令` |

## 提取"待定数据"的扩展点

- **消息文本还原**：`index.js` 的 `plainText()`（各消息段 → 文本，含图片/语音/文件摘要）
- **过滤**：`index.js` 的 `filterMessage()`（按群、人、关键词取舍）
- **回复逻辑**：`index.js` 的 `handleReply()`（可接 AI、定时任务等）
- **其他事件**：`index.js` 的 `handleEvent()` 尾部预留分支（撤回 `message_recall`、进群 `group_member_add` 等）
- **存库升级**：JSONL → SQLite，schema 见 `../QQ机器人方案.md` 第 4.3 节

## 注意事项

- Yogurt 必须配置 `signApiUrl`（外部签名服务）；Android 协议（`AndroidPhone/Pad`）用账号密码登录
- 建议使用 QQ 小号；`config.json` 与 `session-store*.json` 含敏感凭证，勿泄露
- 本工具仅用于本人合法用途（自建群管理/消息归档），注意个人信息合规

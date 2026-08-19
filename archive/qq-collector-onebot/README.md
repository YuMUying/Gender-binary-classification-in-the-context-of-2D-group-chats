# qq-collector-onebot

基于 **OneBot 11** 协议（[NapCatQQ](https://github.com/NapNeko/NapCatQQ) / [LLOneBot](https://github.com/LLOneBot/LLOneBot) / [LuckyLilliaBot](https://github.com/LLOneBot/LuckyLilliaBot)）的 QQ 群聊数据采集 + 自动回复机器人。

## 功能

- 实时监听好友/群消息（WebSocket 正向连接协议端）
- 消息落库：JSONL 按天分文件（`data/messages-YYYY-MM-DD.jsonl`），保留原始 CQ 消息段
- 批量拉取历史消息：`get_group_msg_history` / `get_friend_msg_history` 自动翻页
- 自动回复：关键字触发（exact/contains）+ `/指令` 路由
- 断线自动重连（指数退避）

## 第一步：部署 NapCatQQ（协议端）

### Windows（推荐新手）

1. 安装官方 QQ（64 位最新版），登录你准备的 **QQ 小号**（扫码或密码均可，保持在线）
2. 下载 [NapCat.Installer](https://github.com/NapNeko/NapCatQQ/releases)（或 NapCat Shell 一键包），按提示注入/启动
3. 启动后浏览器打开 `http://127.0.0.1:6099/webui`（token 见 `config/webui.json`）
4. WebUI → 网络配置 → 添加 **WebSocket 服务端**：
   - 地址 `0.0.0.0`（或 `127.0.0.1`），端口 `3001`（与下方 config.json 一致）
   - 需要时设置 Access Token（与下方 config.json 一致）
5. WebUI → 网络配置 → 确认 **HTTP 服务端** 端口为 `3000`（与下方 config.json 一致）

> Linux 服务器部署：使用 [NapCat.Shell.zip](https://github.com/NapNeko/NapCatQQ/releases) + 官方 QQNT 安装包（Framework 模式），或 Docker（`mlikiowa/napcat-docker`）。QQ 客户端登录后 NapCat 自动接管。

## 第二步：运行采集程序

```bash
cd qq-collector-onebot
npm install          # 仅依赖 ws（纯 JS）
# 按需修改 config.json（wsUrl/httpUrl/accessToken、监听范围、回复关键字）
node index.js        # 实时采集
```

## 历史消息批量拉取

```bash
node history.js --group 123456789 --limit 500                # 拉该群最新 500 条
node history.js --group 123456789 --start-seq 3000 --limit 200
node history.js --private 987654321 --limit 100
```

## 配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `onebot.wsUrl` | 协议端正向 WebSocket 地址（NapCat WebUI 里配置的端口） |
| `onebot.httpUrl` | 协议端 HTTP API 地址（发送回复、拉历史用） |
| `onebot.accessToken` | 与 NapCat WebUI 配置的 token 一致 |
| `storage.dir` | JSONL 存储目录 |
| `listen.groups/friends` | 白名单（空数组 = 全部） |
| `filters.ignoreSelf` | 丢弃自己发出的消息 |
| `reply.enabled/triggers/commands` | 关键字回复与 `/指令` |

## 扩展点（"待定数据"在这里加）

- **文本还原**：`index.js` 的 `plainText()`（CQ 段 → 文本，图片/语音/文件摘要）
- **过滤**：`index.js` 的 `filterMessage()`（按群、人、关键词取舍）
- **回复逻辑**：`index.js` 的 `handleReply()`（可接 AI、定时任务）
- **群名补充**：`saveRecord` 后调用 `get_group_info` 缓存群名（当前 group_name 为 null）
- **其他事件**：`handleEvent()` 尾部预留 notice（撤回/进群/禁言）分支
- **存库升级**：JSONL → SQLite，schema 见 `../QQ机器人方案.md` 第 4.3 节

## 注意

- 用 **QQ 小号**；NapCat 挂官方客户端属于第三方插件，存在账号风控可能
- 群聊记录含他人个人信息，仅限本人合法用途

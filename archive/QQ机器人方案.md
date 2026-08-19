# 安卓手机 QQ 群聊数据采集机器人 — 方案与部署文档

> 调研日期：2026-08（基于 GitHub 实时数据）｜目标：可登录 QQ、监听好友/群消息、提取并保存聊天数据、支持自动回复。

---

## 0. 最终选定方案（2026-08 更新）：NapCatQQ + OneBot 11，PC/服务器部署

经确认，机器人本体部署在 **PC/服务器** 上（手机仅作 QQ 扫码登录用或完全不用手机），选定当前生态最大、维护最活跃的 **NapCatQQ** 路线。

### 0.1 架构

```
┌──────────── PC / 服务器 ────────────┐
│  官方 QQNT 客户端（Windows/Linux）   │
│   · 你手动扫码/密码登录 QQ 小号      │
│   · NapCat 插件注入，接管消息收发    │
│        │ OneBot 11 (正向WS :3001 / HTTP :3000)
│  ┌─────▼─────────────────────┐      │
│  │ qq-collector-onebot        │      │
│  │  · 实时消息采集 → JSONL     │      │
│  │  · 关键字/指令自动回复      │      │
│  │  · 历史消息批量拉取         │      │
│  └───────────┬───────────────┘      │
│        data/messages-YYYY-MM-DD.jsonl│
└─────────────────────────────────────┘
```

### 0.2 部署步骤（Windows 版）

1. 安装官方 64 位 QQ，登录 **QQ 小号** 并保持在线；
2. 下载 [NapCat.Installer](https://github.com/NapNeko/NapCatQQ/releases) 一键注入/启动；
3. 打开 `http://127.0.0.1:6099/webui`（token 在 `config/webui.json`）配置网络：
   - **WebSocket 服务端**：`0.0.0.0:3001`（可设 token）
   - **HTTP 服务端**：`0.0.0.0:3000`
4. 运行采集程序（工作区 `qq-collector-onebot/`）：
   ```bash
   cd qq-collector-onebot && npm install && node index.js
   ```

> Linux 服务器：NapCat.Shell + 官方 QQNT（Framework 模式）或 Docker（`mlikaiowa/napcat-docker`）。

### 0.3 OneBot 11 群消息事件示例

```json
{
  "post_type": "message", "message_type": "group", "sub_type": "normal",
  "time": 1754208000, "self_id": 10001,
  "message_id": -2147483648, "group_id": 123456789, "user_id": 987654321,
  "raw_message": "你好",
  "message": [{"type": "text", "data": {"text": "你好"}}],
  "sender": {"user_id": 987654321, "nickname": "小明", "card": "小明明", "role": "member"}
}
```

发送回复：`POST /send_group_msg {"group_id":..., "message":[{"type":"text","data":{"text":"..."}}]}`；拉历史：`POST /get_group_msg_history {"group_id":..., "message_seq":..., "count":20}`。

> 手机本地方案（acidify/Yogurt、LLBot CLI arm64、Milky 协议）保留在第 1~8 节作为备选参考，Milky 版采集程序在工作区 `qq-collector/`。

### 0.4 迁移到树莓派 / ARM 开发板（可行性）

**结论：完全可行，采集程序零改动。** NapCat 官方生态对 ARM64 支持完整：

- **Docker 路线（推荐）**：[mlikiowa/napcat-docker](https://hub.docker.com/r/mlikiowa/napcat-docker) 官方支持 `Linux/Amd64 + Linux/Arm64`，镜像内自带 linuxqq + NapCat，一条命令拉起，扫码登录走 WebUI；
- **原生路线**：腾讯官方 [Linux QQ 3.x](https://im.qq.com/linuxqq/index.shtml) 提供 **arm64 deb** + NapCat Framework 模式（NapCat 本体是 Node.js，ARM 原生支持）；
- 硬件要求：树莓派 4B（建议 4GB+ 内存）/ 5 + **64 位系统**（linuxqq 仅 arm64，无 32 位版）；存储建议 16GB+ 高耐久卡或 SSD；
- 更轻量的替代：**LLBot CLI linux-arm64**（89MB，纯协议实现，无 Electron 开销，OneBot 11/Milky 全支持）——树莓派上比挂 linuxqq 省内存得多；
- 混合部署：树莓派只跑 `qq-collector-onebot`（Node，极轻），NapCat 留在 PC，把 `config.json` 的 `wsUrl` 改为 `ws://<PC的IP>:3001`（NapCat WebUI 将 WS 监听设为 `0.0.0.0`）即可。

Docker 启动示例：

```bash
docker run -d \
  -e NAPCAT_UID=$(id -u) -e NAPCAT_GID=$(id -g) \
  -p 3000:3000 -p 3001:3001 -p 6099:6099 \
  -v napcat-qq:/app/.config/QQ \
  -v napcat-config:/app/napcat/config \
  --name napcat --restart=always \
  mlikiowa/napcat-docker:latest
docker logs napcat    # 查看 WebUI token
```

---

## 1. 结论速览

| 方案 | 现状 | 可行性 |
|---|---|---|
| **OpenShamrock**（Xposed + OneBot 11） | ⚠️ **原 GitHub 仓库已被作者删除**（`whitechi73/OpenShamrock` 404），开发冻结于 2024-08；仅剩 gitcode 代码镜像。社区有个人续命版 [OpenShamrock-QQ-9.2.95-adapt](https://github.com/ion-aluminium/OpenShamrock-QQ-9.2.95-adapt)（v1.0.8 APK，2026-07-10，单人维护、信任度低） | 仅适合"必须官方客户端登录"场景，需锁死 QQ 9.2.95 |
| **acidify + Yogurt**（NTQQ 协议端 + Milky 协议） | ✅ **活跃维护**（2026-08 仍在更新），v1.6.3；官方支持 PC & Android 登录；构建产物正常发布在 GitHub Releases / npm | ✅ **推荐** |
| **LuckyLilliaBot / LLBot**（NTQQ 协议端/挂接，OneBot 11 + Satori + Milky） | ✅ **非常活跃**（3.5k⭐，v8.1.8 2026-08-14）；有头(HOOK QQ客户端)/无头(纯协议)双模式；提供 **CLI linux-arm64** 构建（可尝试 Termux） | ✅ **推荐候选** |
| **NapCat-Termux**（proot + linuxqq + NapCat） | 主项目 NapCatQQ ⭐10.3k 活跃，但安卓适配仓库 ⭐16、2024-08 后停更；需 1GB+ 存储、100M+ 内存 | 备选 |
| **mirai** | ⭐14.8k 但 2024-09 后基本停更 | 不推荐 |
| **icqq**（Node.js） | 原仓库迁移混乱、社区 fork 分裂；轻量但风控风险高 | 备选 |
| **QQ 官方机器人平台** | 只能收到群内 @机器人 的消息 | ❌ 不满足"监听全量群消息"需求 |

**最终选择：acidify + Yogurt（主路线），NapCat-Termux 为备选。**

理由：
1. 唯一"官方支持 Android + 持续维护 + 分发正常"的路线；
2. 不依赖手机 root（你的 root 无碍但不必要），不绑定 QQ 客户端版本；
3. 提供标准 **Milky 协议**（HTTP + WebSocket），与 OneBot 11 理念同源但强类型、更规范；
4. 账号密码登录 / 扫码登录均可，登录态持久化。

---

## 2. 总体架构

```
┌─────────────────────── 安卓手机 ───────────────────────┐
│                                                        │
│  ┌─────────────── Termux ────────────────┐             │
│  │  Yogurt 协议端 (acidify-core 实现)      │             │
│  │   · Linux arm64 二进制 / npm 包         │             │
│  │   · 密码登录(AndroidPhone/Pad 协议)     │             │
│  │     或扫码登录(PC 协议)                 │             │
│  │   · 登录态持久化 (session-store)        │             │
│  │   · Milky 服务: HTTP :3000              │             │
│  │        /api/*   API 调用(发送/撤回/历史)│             │
│  │        /event   SSE/WebSocket 事件推送  │             │
│  └──────────────────┬─────────────────────┘             │
│                     │ WebSocket (127.0.0.1)             │
│  ┌──────────────────▼─────────────────────┐             │
│  │  采集程序 qq-collector (Node.js)        │             │
│  │   · 消息事件接收 → 过滤 → 解析          │             │
│  │   · 自动回复（关键字/指令/事件钩子）     │             │
│  │   · 历史消息批量拉取(get_history_messages)│           │
│  └──────────────────┬─────────────────────┘             │
│                     │                                   │
│           ┌─────────▼─────────┐                         │
│           │ JSONL 本地存储     │  (按天分文件, 可扩展)    │
│           │ 可选: 同步到服务器 │   SQLite / 远程 HTTP    │
│           └───────────────────┘                         │
└────────────────────────────────────────────────────────┘
        ▲
        │ signApiUrl（外部签名服务，必填）
   ┌────┴────────────────────────────┐
   │ 签名服务（三选一）                │
   │  1. 自建 Lagrange Sign（PC/服务器）│
   │  2. 兼容 ICQQ 的社区签名服务      │
   │  3. 付费/公共签名服务（注意安全）  │
   └─────────────────────────────────┘
```

---

## 3. 部署步骤（手机侧）

### 3.1 安装 Termux
从 [F-Droid](https://f-droid.org/packages/com.termux/) 或官网安装（Play 商店版本已停更，不推荐）。

```bash
pkg update && pkg upgrade
pkg install nodejs-lts git
```

### 3.2 安装 Yogurt
方式一（推荐，简单）：
```bash
npm install -g @acidify/yogurt
yogurt   # 首次启动生成 config.json 后退出
```

方式二（二进制）：从 [SaltifyDev/yogurt-releases](https://github.com/SaltifyDev/yogurt-releases/releases) 下载 `yogurt-linux-arm64.zip`（Kotlin/Native 静态链接，Termux 直接可跑）。

### 3.3 配置 Yogurt（config.json 关键项）

```json
{
  "protocol": {
    "uin": 你的QQ小号,
    "password": "密码",
    "os": "AndroidPhone",
    "version": "9.2.80",
    "signApiUrl": "http://你的签名服务地址",
    "androidUseLegacySign": false
  },
  "milky": {
    "http": { "host": "127.0.0.1", "port": 3000, "accessToken": "随机长字符串" },
    "reportSelfMessage": true
  }
}
```

- `protocol.os` 可选 `Windows/Mac/Linux/AndroidPhone/AndroidPad`；Android 协议需账号密码，内置版本有 `9.1.60 / 9.1.70 / 9.2.0 / 9.2.20 / 9.2.80`。
- **`signApiUrl` 必填**：Yogurt 不自带签名，需外部签名服务（协议见官方文档 [signing](https://acidify.ntqqrev.org/yogurt/signing)）。
- 扫码登录（PC 协议）流程见官方文档 [login](https://acidify.ntqqrev.org/yogurt/login)。

### 3.4 启动顺序

```bash
yogurt                      # 会话1：协议端，登录成功后常驻
cd qq-collector && npm install && node index.js   # 会话2：采集程序
```

---

## 4. 数据提取与存储设计

### 4.1 Milky 群消息事件（`message_receive`）

```json
{
  "event_type": "message_receive",
  "time": 1754208000,
  "self_id": 10001,
  "data": {
    "message_scene": "group",
    "peer_id": 123456789,
    "message_seq": 42,
    "sender_id": 987654321,
    "time": 1754208000,
    "segments": [
      { "type": "text", "data": { "text": "你好" } },
      { "type": "image", "data": { "resource_id": "xxx", "temp_url": "https://...", "summary": "[图片]" } }
    ],
    "group": { "group_id": 123456789, "group_name": "技术交流群", "member_count": 88 },
    "group_member": { "user_id": 987654321, "nickname": "小明", "card": "小明明", "role": "member" }
  }
}
```

消息段类型：`text / mention / mention_all / face / reply / image / record / video / file / forward / market_face / light_app / xml / markdown`——提取"聊天记录"时每种段都能还原成文本或保存原始 JSON。

### 4.2 采集程序落库格式（JSONL，按天分文件）

`data/messages-2026-08-14.jsonl` 每行一条：

```json
{"event_type":"message_receive","time":1754208000,"self_id":10001,
 "scene":"group","peer_id":123456789,"seq":42,"sender_id":987654321,
 "sender_nickname":"小明","sender_card":"小明明","group_id":123456789,
 "group_name":"技术交流群","text":"你好 [图片]","segments":[{...原始段...}]}
```

"具体数据待定"时只需改采集程序的**解析/过滤层**（`index.js` 中的 `plainText()` 和 `filterMessage()`），存储层不动。

### 4.3 后续可迁移到 SQLite（建议 schema）

```sql
CREATE TABLE messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  time INTEGER, scene TEXT, peer_id INTEGER, seq INTEGER,
  sender_id INTEGER, sender_nickname TEXT, sender_card TEXT,
  group_id INTEGER, group_name TEXT,
  text TEXT, segments TEXT,      -- segments 存原始 JSON
  source TEXT DEFAULT 'live'     -- live(实时) / history(历史拉取)
);
CREATE INDEX idx_group_time ON messages(group_id, time);
```

---

## 5. 自动回复

采集程序内置三类钩子（`index.js` 的 `handleReply`）：
1. **关键字触发**：`config.reply.triggers` 中 `keyword → reply` 精确/包含匹配；
2. **指令触发**：以 `/` 开头的命令路由；
3. **事件钩子**：`message_recall`（撤回）、`group_member_add`（进群）等事件做自定义逻辑。

发送走 Milky API：`POST /api/send_group_message {"group_id":..., "message":[{"type":"text","data":{"text":"..."}}]}`。

---

## 6. 风险与合规提示

1. **封号风险**：非官方协议机器人有被冻结风险，务必用**小号**；新号先正常使用一段时间再挂机器人。
2. **签名服务安全**：`signApiUrl` 若用第三方公共服务，对方可看到你的请求流量，建议自建 Lagrange Sign（Lagrange.Core 内置 signServer 模式，跑在 PC/服务器上）。
3. **凭证保管**：`config.json`（含明文密码）、`session-store*.json`（含登录态，泄露=盗号）务必保密。
4. **隐私合规**：群聊记录含他人个人信息，仅限本人合法用途（如自建群管理/归档），遵守《个人信息保护法》。

---

## 7. 备选与扩展

- **备选路线（不想用签名服务）**：NapCat-Termux（proot 跑 linuxqq + NapCat，OneBot 11 生态）；或 [LuckyLilliaBot/LLBot](https://github.com/LLOneBot/LuckyLilliaBot)（3.5k⭐ 活跃，支持 OneBot 11/Satori/Milky，有 linux-arm64 CLI 构建可试跑 Termux，WebUI 图形化管理）；或自研 Kotlin App 内嵌 acidify-core（完全掌控、无需 Termux 常驻，可用 [Saltify](https://saltify.ntqqrev.org/) 框架）。
- **采集程序升级路径**：[Fraq](https://fraq.ntqqrev.org/)（Milky 的 TS 框架，插件体系）或 NoneBot/Koishi（均有 Milky 适配，见 [Awesome Milky](https://milky.ntqqrev.org/awesome)）。
- **多账号/多端**：Yogurt 一个实例一个账号，可多开实例。

## 8. 参考资料

- [LagrangeDev/acidify](https://github.com/LagrangeDev/acidify)（协议核心，Kotlin Multiplatform，PC & Android）
- [SaltifyDev/yogurt-releases](https://github.com/SaltifyDev/yogurt-releases)（协议端构建产物）
- [Yogurt 官方文档](https://acidify.ntqqrev.org/yogurt/start)（安装/登录/配置/签名）
- [Milky 协议文档](https://milky.ntqqrev.org/)（通信/API/事件/结构体）
- [Fraq 框架](https://fraq.ntqqrev.org/)（Milky 的 TypeScript 机器人框架）
- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) / [NapCat-Termux](https://github.com/NapNeko/NapCat-Termux)
- [LLOneBot/LuckyLilliaBot (LLBot)](https://github.com/LLOneBot/LuckyLilliaBot)（LLOneBot 换代项目，文档见 [luckylillia.com](https://luckylillia.com)）
- [LagrangeDev/Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core) / [LagrangeV2](https://github.com/LagrangeDev/LagrangeV2)
- [gitcode 上的 OpenShamrock 代码镜像](https://gitcode.com/gh_mirrors/op/OpenShamrock)（仅存档参考）

/**
 * qq-collector-onebot — 基于 OneBot 11 协议 (NapCatQQ / LLOneBot / LLBot) 的 QQ 群聊数据采集 + 自动回复机器人
 *
 * 工作方式：
 *   1. WebSocket 正向连接协议端（NapCat WebUI 里配置的 OneBot 11 正向 WS 地址）；
 *   2. message 事件 → 过滤 → 解析 CQ 码为纯文本 → 追加写入 JSONL（按天分文件）；
 *   3. 命中关键字/指令 → 通过 HTTP API（/send_group_msg 等）自动回复；
 *   4. 断线自动重连。
 *
 * 用法：node index.js
 * 依赖：npm install（仅 ws 一个纯 JS 依赖）
 */
import WebSocket from 'ws';
import { readFileSync, appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const config = JSON.parse(readFileSync(new URL('./config.json', import.meta.url), 'utf8'));
const ob = config.onebot;
const WS_HEADERS = ob.accessToken ? { Authorization: `Bearer ${ob.accessToken}` } : {};

// ---------- 工具 ----------
function dayStamp(ts = Date.now()) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** CQ 消息段 → 纯文本（扩展点：提取"待定数据"时改这里） */
function plainText(message = []) {
  return message.map((s) => {
    switch (s.type) {
      case 'text': return s.data?.text ?? '';
      case 'at': return `@${s.data?.name || s.data?.qq || ''}`;
      case 'face': return `[表情:${s.data?.id ?? ''}]`;
      case 'image': return `[图片:${s.data?.url || s.data?.file || ''}]`;
      case 'record': return '[语音]';
      case 'video': return '[视频]';
      case 'file': return `[文件:${s.data?.name ?? ''}]`;
      case 'reply': return `[回复#${s.data?.id ?? ''}]`;
      case 'forward': return '[合并转发]';
      case 'json': return `[JSON消息:${s.data?.data ?? ''}]`;
      case 'xml': return '[XML消息]';
      case 'markdown': return s.data?.content ?? '';
      case 'shake': return '[窗口抖动]';
      case 'poke': return '[戳一戳]';
      default: return `[${s.type}]`;
    }
  }).join('').trim();
}

/** 保存一条记录（按天分文件 JSONL） */
function saveRecord(record) {
  const dir = config.storage.dir || './data';
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `messages-${dayStamp(record.time * 1000)}.jsonl`);
  appendFileSync(file, JSON.stringify(record) + '\n', 'utf8');
  console.log(`[save] ${file}  ${record.message_type}#${record.group_id || record.user_id}  ${record.sender_name}: ${record.text.slice(0, 40)}`);
}

// ---------- 过滤 ----------
function filterMessage(ev) {
  const { groups, friends } = config.listen;
  if (ev.message_type === 'group' && groups.length > 0 && !groups.includes(ev.group_id)) return false;
  if (ev.message_type === 'private' && friends.length > 0 && !friends.includes(ev.user_id)) return false;
  if (config.filters.ignoreSelf && ev.user_id === ev.self_id) return false;
  return true;
}

// ---------- 自动回复 ----------
async function callApi(apiName, body) {
  const res = await fetch(`${ob.httpUrl}/${apiName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(ob.accessToken ? { Authorization: `Bearer ${ob.accessToken}` } : {}),
    },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (json.status !== 'ok') console.warn(`[api] ${apiName} 失败: retcode=${json.retcode}`);
  return json;
}

function textMsg(text) { return [{ type: 'text', data: { text } }]; }
const sendGroupMessage = (g, t) => callApi('send_group_msg', { group_id: g, message: textMsg(t) });
const sendPrivateMessage = (u, t) => callApi('send_private_msg', { user_id: u, message: textMsg(t) });

/** 回复决策（扩展点：指令路由、接 AI、白名单等在这里做） */
async function handleReply(ev, text) {
  if (!config.reply.enabled || !text) return;

  if (text.startsWith('/')) {
    const [cmdName] = text.slice(1).split(/\s+/);
    const cmd = config.reply.commands.find((c) => c.name === cmdName);
    if (cmd) {
      let replyText = '';
      if (cmd.action === 'help') {
        replyText = '可用指令：\n' + config.reply.commands.map((c) => `/${c.name} ${c.description}`).join('\n');
      } else if (cmd.action === 'about') {
        replyText = 'qq-collector-onebot v0.1.0 — 基于 OneBot 11 的数据采集机器人';
      }
      if (replyText) await replyTo(ev, replyText);
      return;
    }
  }

  for (const t of config.reply.triggers) {
    const hit = t.match === 'exact' ? text === t.keyword : text.includes(t.keyword);
    if (hit) { await replyTo(ev, t.reply); return; }
  }
}

async function replyTo(ev, text) {
  if (ev.message_type === 'group') await sendGroupMessage(ev.group_id, text);
  else await sendPrivateMessage(ev.user_id, text);
  console.log(`[reply] → ${ev.message_type}#${ev.group_id || ev.user_id}: ${text.slice(0, 40)}`);
}

// ---------- 事件处理 ----------
function handleEvent(ev) {
  if (ev.post_type === 'message' && (ev.message_type === 'group' || ev.message_type === 'private')) {
    const text = plainText(ev.message);
    const record = {
      post_type: ev.post_type,
      time: ev.time ?? Math.floor(Date.now() / 1000),
      self_id: ev.self_id,
      message_type: ev.message_type,
      sub_type: ev.sub_type ?? null,
      message_id: ev.message_id ?? null,
      group_id: ev.group_id ?? null,
      group_name: null,                 // 群名需调用 get_group_info 补充（见 README 扩展点）
      user_id: ev.user_id ?? null,
      sender_name: ev.sender?.nickname ?? '',
      sender_card: ev.sender?.card ?? '',
      sender_role: ev.sender?.role ?? null,
      text,
      message: ev.message ?? [],       // 原始 CQ 消息段
      raw: ev,
    };
    if (!filterMessage(record)) return;
    saveRecord(record);
    handleReply(record, text).catch((e) => console.error('[reply] error:', e.message));
  }
  // 其他事件（撤回 notice、进群通知等）在此追加分支：
  // else if (ev.post_type === 'notice' && ev.notice_type === 'group_recall') { ... }
  else if (ev.post_type === 'meta_event' && ev.meta_event_type === 'lifecycle') {
    console.log(`[lifecycle] 协议端 ${ev.self_id} 已就绪`);
  }
}

// ---------- 连接管理 ----------
let retry = 0;

function connect() {
  const ws = new WebSocket(ob.wsUrl, { headers: WS_HEADERS });
  console.log(`[ws] 连接 ${ob.wsUrl} ...`);

  ws.on('open', () => { retry = 0; console.log('[ws] 已连接，开始监听消息'); });

  ws.on('message', (buf) => {
    try {
      const ev = JSON.parse(buf.toString());
      if (ev?.post_type) handleEvent(ev);
      else console.warn('[ws] 未知消息结构:', buf.toString().slice(0, 200));
    } catch (e) { console.warn('[ws] 非 JSON 消息:', buf.toString().slice(0, 200)); }
  });

  ws.on('close', (code) => {
    const wait = Math.min(30000, 1000 * 2 ** retry++);
    console.warn(`[ws] 连接关闭 (code=${code})，${Math.round(wait / 1000)}s 后重连...`);
    setTimeout(connect, wait);
  });

  ws.on('error', (e) => { console.error('[ws] error:', e.message); });
}

connect();

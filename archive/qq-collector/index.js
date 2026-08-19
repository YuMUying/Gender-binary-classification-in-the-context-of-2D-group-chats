/**
 * qq-collector — 基于 Milky 协议(acidify/Yogurt)的 QQ 群聊数据采集 + 自动回复机器人
 *
 * 工作方式：
 *   1. WebSocket 连接 Yogurt 的 /event 端点，接收实时事件；
 *   2. message_receive 事件 → 过滤 → 解析为纯文本 → 追加写入 JSONL（按天分文件）；
 *   3. 命中配置的关键字/指令 → 通过 HTTP /api/send_group_message 自动回复；
 *   4. 断线自动重连。
 *
 * 用法：node index.js
 * 依赖：npm install（仅 ws 一个纯 JS 依赖，Termux 可直接安装）
 */
import WebSocket from 'ws';
import { readFileSync, appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const config = JSON.parse(readFileSync(new URL('./config.json', import.meta.url), 'utf8'));
const m = config.milky;
const HTTP_BASE = `http://${m.host}:${m.port}${m.prefix || ''}`;
const WS_URL = `ws://${m.host}:${m.port}${m.prefix || ''}/event`;
const WS_HEADERS = m.accessToken ? { Authorization: `Bearer ${m.accessToken}` } : {};

// ---------- 工具 ----------
function dayStamp(ts = Date.now()) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 把消息段列表还原为人类可读纯文本（扩展点：提取"待定数据"时改这里） */
function plainText(segments = []) {
  return segments.map((s) => {
    switch (s.type) {
      case 'text': return s.data?.text ?? '';
      case 'mention': return `@${s.data?.name || s.data?.user_id || ''}`;
      case 'mention_all': return '@全体成员';
      case 'face': return `[表情:${s.data?.face_id ?? ''}]`;
      case 'reply': return `[回复#${s.data?.message_seq ?? ''}]`;
      case 'image': return `[图片:${s.data?.summary || s.data?.temp_url || ''}]`;
      case 'record': return `[语音:${s.data?.duration ?? 0}s]`;
      case 'video': return `[视频:${s.data?.duration ?? 0}s]`;
      case 'file': return `[文件:${s.data?.file_name ?? ''}]`;
      case 'forward': return `[合并转发:${s.data?.title ?? ''}]`;
      case 'market_face': return `[表情:${s.data?.summary ?? ''}]`;
      case 'light_app': return `[小程序:${s.data?.app_name ?? ''}]`;
      case 'xml': return '[XML消息]';
      case 'markdown': return s.data?.content ?? '';
      default: return `[${s.type}]`;
    }
  }).join('').trim();
}

/** 保存一条记录到 JSONL（按天分文件） */
function saveRecord(record) {
  const dir = config.storage.dir || './data';
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `messages-${dayStamp(record.time * 1000)}.jsonl`);
  appendFileSync(file, JSON.stringify(record) + '\n', 'utf8');
  console.log(`[save] ${file}  ${record.scene}#${record.peer_id}  ${record.sender_nickname}: ${record.text.slice(0, 40)}`);
}

// ---------- 过滤 ----------
/** 返回 false 表示丢弃该消息（扩展点：按群/人/关键词过滤"待定数据"） */
function filterMessage(msg) {
  const { groups, friends } = config.listen;
  if (msg.scene === 'group' && groups.length > 0 && !groups.includes(msg.peer_id)) return false;
  if (msg.scene === 'friend' && friends.length > 0 && !friends.includes(msg.peer_id)) return false;
  if (config.filters.ignoreSelf && msg.sender_id === msg.self_id) return false;
  return true;
}

// ---------- 自动回复 ----------
async function callApi(apiName, body) {
  const res = await fetch(`${HTTP_BASE}/api/${apiName}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(m.accessToken ? { Authorization: `Bearer ${m.accessToken}` } : {}),
    },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (json.status !== 'ok') console.warn(`[api] ${apiName} 失败: retcode=${json.retcode} ${json.message ?? ''}`);
  return json;
}

async function sendGroupMessage(groupId, text) {
  return callApi('send_group_message', { group_id: groupId, message: [{ type: 'text', data: { text } }] });
}

async function sendPrivateMessage(userId, text) {
  return callApi('send_private_message', { user_id: userId, message: [{ type: 'text', data: { text } }] });
}

/** 决定是否回复及回复内容（扩展点：指令路由、接 AI 等在这里做） */
async function handleReply(msg) {
  if (!config.reply.enabled || !msg.text) return;
  const text = msg.text;

  // 1) 指令（以 / 开头）
  if (text.startsWith('/')) {
    const [cmdName, ...args] = text.slice(1).split(/\s+/);
    const cmd = config.reply.commands.find((c) => c.name === cmdName);
    if (cmd) {
      let replyText = '';
      if (cmd.action === 'help') {
        replyText = '可用指令：\n' + config.reply.commands.map((c) => `/${c.name} ${c.description}`).join('\n');
      } else if (cmd.action === 'about') {
        replyText = 'qq-collector v0.1.0 — 基于 Milky 协议的数据采集机器人';
      }
      if (replyText) await replyTo(msg, replyText);
      return;
    }
  }

  // 2) 关键字触发
  for (const t of config.reply.triggers) {
    const hit = t.match === 'exact' ? text === t.keyword : text.includes(t.keyword);
    if (hit) { await replyTo(msg, t.reply); return; }
  }
}

async function replyTo(msg, text) {
  if (msg.scene === 'group') await sendGroupMessage(msg.peer_id, text);
  else await sendPrivateMessage(msg.peer_id, text);
  console.log(`[reply] → ${msg.scene}#${msg.peer_id}: ${text.slice(0, 40)}`);
}

// ---------- 事件处理 ----------
function handleEvent(ev) {
  console.log(`[event] ${ev.event_type} @${new Date((ev.time ?? Date.now() / 1000) * 1000).toLocaleString()}`);

  if (ev.event_type === 'message_receive') {
    const d = ev.data ?? {};
    const msg = {
      event_type: ev.event_type,
      time: ev.time ?? d.time,
      self_id: ev.self_id,
      scene: d.message_scene,
      peer_id: d.peer_id,
      seq: d.message_seq,
      sender_id: d.sender_id,
      sender_nickname: d.group_member?.nickname ?? (d.friend?.nickname ?? ''),
      sender_card: d.group_member?.card ?? '',
      group_id: d.group?.group_id ?? null,
      group_name: d.group?.group_name ?? null,
      text: plainText(d.segments),
      segments: d.segments ?? [],
      // 便于后续"待定数据"扩展：保留原始结构
      raw: d,
    };
    if (!filterMessage(msg)) return;
    saveRecord(msg);
    handleReply(msg).catch((e) => console.error('[reply] error:', e.message));
  }
  // 其他事件（撤回/进群/禁言等）如需保存，在这里追加分支：
  // else if (ev.event_type === 'message_recall') { ... }
}

// ---------- 连接管理 ----------
let retry = 0;

function connect() {
  const ws = new WebSocket(WS_URL, { headers: WS_HEADERS });
  console.log(`[ws] 连接 ${WS_URL} ...`);

  ws.on('open', () => { retry = 0; console.log('[ws] 已连接，开始监听事件'); });

  ws.on('message', (buf) => {
    try {
      const ev = JSON.parse(buf.toString());
      if (ev?.event_type) handleEvent(ev);
      else console.warn('[ws] 未知消息结构:', buf.toString().slice(0, 200));
    } catch (e) { console.warn('[ws] 非 JSON 消息:', buf.toString().slice(0, 200)); }
  });

  ws.on('close', (code, reason) => {
    const wait = Math.min(30000, 1000 * 2 ** retry++);
    console.warn(`[ws] 连接关闭 (code=${code})，${Math.round(wait / 1000)}s 后重连...`);
    setTimeout(connect, wait);
  });

  ws.on('error', (e) => { console.error('[ws] error:', e.message); /* close 事件会触发重连 */ });
}

connect();

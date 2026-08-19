/**
 * history.js — 批量拉取群/好友历史消息并写入 JSONL
 *
 * 用法：
 *   node history.js --group 123456789          # 拉取该群最新 100 条
 *   node history.js --group 123456789 --limit 500 --start-seq 3000   # 从 seq 3000 向前拉
 *   node history.js --friend 987654321 --limit 200
 *
 * Milky 限制：get_history_messages 单次最多 30 条，本脚本自动翻页。
 */
import { readFileSync, appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const config = JSON.parse(readFileSync(new URL('./config.json', import.meta.url), 'utf8'));
const m = config.milky;
const HTTP_BASE = `http://${m.host}:${m.port}${m.prefix || ''}`;
const HEADERS = { 'Content-Type': 'application/json', ...(m.accessToken ? { Authorization: `Bearer ${m.accessToken}` } : {}) };

// 解析命令行参数
const args = process.argv.slice(2);
function arg(name) {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : undefined;
}
const scene = args.includes('--group') ? 'group' : args.includes('--friend') ? 'friend' : null;
const peerId = scene ? Number(arg(`--${scene}`)) : null;
const total = Number(arg('--limit') ?? 100);
const startSeq = arg('--start-seq') ? Number(arg('--start-seq')) : undefined;

if (!scene || !peerId) {
  console.error('用法: node history.js --group <群号> [--limit N] [--start-seq S]');
  console.error('      node history.js --friend <QQ号> [--limit N] [--start-seq S]');
  process.exit(1);
}

function dayStamp(ts = Date.now()) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

async function api(apiName, body) {
  const res = await fetch(`${HTTP_BASE}/api/${apiName}`, { method: 'POST', headers: HEADERS, body: JSON.stringify(body) });
  const json = await res.json();
  if (json.status !== 'ok') throw new Error(`${apiName} 失败: retcode=${json.retcode} ${json.message ?? ''}`);
  return json.data ?? {};
}

function plainText(segments = []) {
  return segments.map((s) => {
    switch (s.type) {
      case 'text': return s.data?.text ?? '';
      case 'mention': return `@${s.data?.name || s.data?.user_id || ''}`;
      case 'mention_all': return '@全体成员';
      case 'face': return `[表情:${s.data?.face_id ?? ''}]`;
      case 'image': return `[图片:${s.data?.summary || ''}]`;
      case 'record': return `[语音:${s.data?.duration ?? 0}s]`;
      case 'video': return `[视频:${s.data?.duration ?? 0}s]`;
      case 'file': return `[文件:${s.data?.file_name ?? ''}]`;
      case 'forward': return `[合并转发:${s.data?.title ?? ''}]`;
      default: return `[${s.type}]`;
    }
  }).join('').trim();
}

async function main() {
  const dir = config.storage.dir || './data';
  mkdirSync(dir, { recursive: true });

  let cur = startSeq;            // 起始 seq；不传则从最新开始
  let got = 0;
  let records = [];

  console.log(`[history] 拉取 ${scene}#${peerId}，目标 ${total} 条，起点 seq=${cur ?? '最新'}`);

  while (got < total) {
    const body = { message_scene: scene, peer_id: peerId, limit: Math.min(30, total - got) };
    if (cur !== undefined) body.start_message_seq = cur;
    const { messages = [], next_message_seq } = await api('get_history_messages', body);

    if (!messages.length) break;
    records.push(...messages);
    got += messages.length;
    console.log(`[history] 已获取 ${got} 条`);

    if (next_message_seq === undefined || next_message_seq === null) break;
    if (cur !== undefined && next_message_seq === cur) break;  // 防死循环
    cur = next_message_seq;
    await new Promise((r) => setTimeout(r, 500));  // 限速，避免风控
  }

  // 按时间排序后写入（消息按 seq 升序返回，按天分文件）
  records.sort((a, b) => (a.time ?? 0) - (b.time ?? 0));
  for (const d of records) {
    const rec = {
      event_type: 'message_receive',
      time: d.time,
      self_id: null,
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
      raw: d,
      source: 'history',
    };
    const file = path.join(dir, `messages-${dayStamp(rec.time * 1000)}.jsonl`);
    appendFileSync(file, JSON.stringify(rec) + '\n', 'utf8');
  }
  console.log(`[history] 完成，共写入 ${records.length} 条到 ${dir}/`);
}

main().catch((e) => { console.error('[history] 出错:', e.message); process.exit(1); });

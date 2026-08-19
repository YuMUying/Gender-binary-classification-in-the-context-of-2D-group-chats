/**
 * history.js — 批量拉取群/好友历史消息并写入 JSONL（OneBot 11 版）
 *
 * 用法：
 *   node history.js --group 123456789                # 拉取该群最近 100 条
 *   node history.js --group 123456789 --limit 500 --start-seq 3000   # 从 message_seq 3000 向前拉
 *   node history.js --private 987654321 --limit 200
 *
 * OneBot 11 限制：get_group_msg_history 单次数量有限（NapCat 一般 20），本脚本自动翻页。
 */
import { readFileSync, appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const config = JSON.parse(readFileSync(new URL('./config.json', import.meta.url), 'utf8'));
const ob = config.onebot;
const HEADERS = { 'Content-Type': 'application/json', ...(ob.accessToken ? { Authorization: `Bearer ${ob.accessToken}` } : {}) };

const args = process.argv.slice(2);
function arg(name) {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : undefined;
}
const mode = args.includes('--group') ? 'group' : args.includes('--private') ? 'private' : null;
const peer = mode ? Number(arg(`--${mode}`)) : null;
const total = Number(arg('--limit') ?? 100);
const startSeq = arg('--start-seq') ? Number(arg('--start-seq')) : undefined;
const PAGE = 20; // 单次翻页条数（NapCat/LLOneBot 常见上限，可调小）

if (!mode || !peer) {
  console.error('用法: node history.js --group <群号> [--limit N] [--start-seq S]');
  console.error('      node history.js --private <QQ号> [--limit N] [--start-seq S]');
  process.exit(1);
}

function dayStamp(ts = Date.now()) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

async function api(apiName, body) {
  const res = await fetch(`${ob.httpUrl}/${apiName}`, { method: 'POST', headers: HEADERS, body: JSON.stringify(body) });
  const json = await res.json();
  if (json.status !== 'ok') throw new Error(`${apiName} 失败: retcode=${json.retcode} ${json.wording ?? ''}`);
  return json.data ?? {};
}

function plainText(message = []) {
  return message.map((s) => {
    switch (s.type) {
      case 'text': return s.data?.text ?? '';
      case 'at': return `@${s.data?.name || s.data?.qq || ''}`;
      case 'face': return `[表情:${s.data?.id ?? ''}]`;
      case 'image': return `[图片:${s.data?.url || ''}]`;
      case 'record': return '[语音]';
      case 'video': return '[视频]';
      case 'file': return `[文件:${s.data?.name ?? ''}]`;
      case 'reply': return `[回复#${s.data?.id ?? ''}]`;
      default: return `[${s.type}]`;
    }
  }).join('').trim();
}

async function main() {
  const dir = config.storage.dir || './data';
  mkdirSync(dir, { recursive: true });

  let anchor = startSeq;   // 翻页锚点；不传则从最新开始
  let got = 0;
  const records = [];

  console.log(`[history] 拉取 ${mode}#${peer}，目标 ${total} 条，起点 seq=${anchor ?? '最新'}`);

  while (got < total) {
    const body = { count: Math.min(PAGE, total - got) };
    body[mode === 'group' ? 'group_id' : 'user_id'] = peer;
    if (anchor !== undefined) body.message_seq = anchor;
    const apiName = mode === 'group' ? 'get_group_msg_history' : 'get_friend_msg_history';
    const { messages = [] } = await api(apiName, body);

    if (!messages.length) break;
    records.push(...messages);
    got += messages.length;
    console.log(`[history] 已获取 ${got} 条`);

    // OneBot 11 的历史接口返回"从 message_seq 向前"的若干条；锚点用返回的最早一条的 seq
    const oldest = messages.reduce((a, b) => (a.message_seq ?? a) < (b.message_seq ?? a) ? a.message_seq : b.message_seq);
    if (oldest === anchor) break;           // 没有更多了
    anchor = oldest;
    await new Promise((r) => setTimeout(r, 500));   // 限速，避免触发风控
  }

  records.sort((a, b) => (a.time ?? 0) - (b.time ?? 0));
  for (const d of records) {
    const rec = {
      post_type: 'message',
      time: d.time,
      self_id: d.self_id ?? null,
      message_type: mode === 'group' ? 'group' : 'private',
      message_id: d.message_id ?? null,
      group_id: mode === 'group' ? peer : null,
      group_name: null,
      user_id: d.sender?.user_id ?? null,
      sender_name: d.sender?.nickname ?? '',
      sender_card: d.sender?.card ?? '',
      text: plainText(d.message ?? []),
      message: d.message ?? [],
      raw: d,
      source: 'history',
    };
    const file = path.join(dir, `messages-${dayStamp(rec.time * 1000)}.jsonl`);
    appendFileSync(file, JSON.stringify(rec) + '\n', 'utf8');
  }
  console.log(`[history] 完成，共写入 ${records.length} 条到 ${dir}/`);
}

main().catch((e) => { console.error('[history] 出错:', e.message); process.exit(1); });

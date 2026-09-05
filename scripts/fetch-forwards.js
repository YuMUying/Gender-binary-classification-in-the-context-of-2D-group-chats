/**
 * fetch-forwards.js — 拉取私聊历史中的合并转发并递归展开入库
 *
 * 用法：
 *   node scripts/fetch-forwards.js --user 0           # 拉该私聊窗口全部历史中的转发
 *   node scripts/fetch-forwards.js --user 0 --max-pages 5
 *
 * 行为：
 *   1. get_friend_msg_history 翻页拉私聊历史
 *   2. 找到 forward 段 → get_forward_msg 展开（NapCat 已内联嵌套 content，仍递归处理内嵌 forward）
 *   3. 展开出的每条消息（含原发送者/原群信息）写入 messages 表（source='forward'，按 message_id 去重）
 *   4. 转发信封写入 forwards 表（原始 JSON 留档）
 */
import { loadConfig } from '../src/config.js';
import { openDb, saveMessage, saveForward, hasForward } from '../src/db.js';
import { OneBotClient } from '../src/onebot.js';
import { cqToText, makeLogger, sleep } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);
const bot = new OneBotClient(config.onebot, log);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const userId = arg('--user') ? Number(arg('--user')) : null;
const maxPages = arg('--max-pages') ? Number(arg('--max-pages')) : 200;
const timeoutMs = arg('--timeout-ms') ? Number(arg('--timeout-ms')) : 90000;
const maxRetry = arg('--retry') ? Number(arg('--retry')) : 2;
if (!userId) {
  console.error('用法: node scripts/fetch-forwards.js --user <QQ号> [--max-pages N] [--timeout-ms N] [--retry N]');
  process.exit(1);
}

const PAGE = 20;
let expanded = 0, saved = 0;

/** 递归展开一条消息的 forward 段；inner 消息写入 messages */
async function expandForward(forwardId, envelopeUser, envelopeTime, depth = 0) {
  if (depth > 5) return;
  if (hasForward(db, forwardId)) return;
  let data;
  try {
    data = await bot.callApi('get_forward_msg', { message_id: String(forwardId) });
  } catch (e) {
    log.warn(`[forward] id=${forwardId} 展开失败: ${e.message}`);
    return;
  }
  saveForward(db, forwardId, envelopeUser, envelopeTime, JSON.stringify(data));
  expanded++;
  const msgs = data?.messages ?? [];
  for (const m of msgs) {
    const scene = m.message_type === 'group' ? 'group' : 'private';
    const peerId = scene === 'group' ? (m.group_id ?? m.user_id) : (m.user_id);
    if (peerId == null) continue;
    // 内嵌的嵌套转发段：NapCat 已在 data.content 里内联内容，继续展开
    for (const seg of m.message ?? []) {
      if (seg.type === 'forward') {
        const innerId = seg.data?.id;
        const innerContent = seg.data?.content;
        if (innerId) {
          await expandForward(innerId, m.user_id, m.time, depth + 1);
        } else if (Array.isArray(innerContent)) {
          for (const im of innerContent) await saveInner(im);
        }
      }
    }
    await saveInner(m);
  }
}

async function saveInner(m) {
  const scene = m.message_type === 'group' ? 'group' : 'private';
  const peerId = scene === 'group' ? (m.group_id ?? m.user_id) : (m.user_id);
  if (peerId == null) return;
  const text = cqToText(m.message);
  if (!text && !(m.message ?? []).length) return;
  const rec = {
    scene,
    peer_id: peerId,
    message_id: m.real_id ?? m.message_id ?? null,
    message_seq: m.real_seq != null ? Number(m.real_seq) : (m.message_seq ?? null),
    group_name: m.group_name ?? null,
    user_id: m.sender?.user_id ?? m.user_id,
    nickname: m.sender?.nickname ?? null,
    card: m.sender?.card ?? null,
    time: m.time ?? Math.floor(Date.now() / 1000),
    text,
    raw_json: JSON.stringify(m),
    source: 'forward',
  };
  if (rec.user_id == null) return;
  if (saveMessage(db, rec) === 'inserted') saved++;
}

async function main() {
  log.info(`[forward] 拉取与 QQ ${userId} 的私聊历史（最多 ${maxPages} 页）...`);
  let anchor = null;
  let pages = 0;
  let fwdFound = 0;
  while (pages < maxPages) {
    const body = { user_id: userId, count: PAGE };
    if (anchor !== null) body.message_seq = anchor;
    let msgs = [];
    let attempt = 0;
    while (attempt <= maxRetry) {
      try {
        const data = await bot.callApi('get_friend_msg_history', body, timeoutMs);
        msgs = data.messages ?? [];
        break;
      } catch (e) {
        attempt++;
        if (attempt > maxRetry) {
          log.warn(`[forward] 私聊历史失败: ${e.message}`);
          msgs = [];
          break;
        }
        log.warn(`[forward] 私聊历史第 ${attempt}/${maxRetry} 次重试失败: ${e.message}，15s 后重试...`);
        await sleep(15000);
      }
    }
    if (!msgs.length) break;
    pages++;
    for (const m of msgs) {
      for (const seg of m.message ?? []) {
        if (seg.type === 'forward' && seg.data?.id) {
          fwdFound++;
          log.info(`[forward] 展开合并转发 id=${seg.data.id} (信封时间 ${new Date((m.time ?? 0) * 1000).toLocaleString('zh-CN')})`);
          await expandForward(seg.data.id, m.user_id, m.time);
        }
      }
    }
    const seqs = msgs.map((m) => m.message_seq ?? m.real_seq).filter((s) => s != null);
    if (!seqs.length) break;
    const next = Math.min(...seqs);
    if (next === anchor) break;
    anchor = next;
    await sleep(600);
  }
  log.info(`[forward] 完成：翻页 ${pages}，发现转发 ${fwdFound} 条，展开信封 ${expanded} 个，入库消息 ${saved} 条`);
  db.close();
}

main().catch((e) => { log.error(`出错: ${e.message}`); db.close(); process.exit(1); });

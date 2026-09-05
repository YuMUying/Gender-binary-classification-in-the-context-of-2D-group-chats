/**
 * index.js — 采集服务入口（常驻进程）
 *
 * 启动顺序：
 *   1. 加载配置、打开数据库
 *   2. 初始化媒体下载器（图片/表情包）
 *   3. 连接 OneBot WebSocket（实时监听）
 *   4. WS 就绪后：按配置执行启动回填（backfillOnStart）
 *   5. 启动定时增量同步（scheduler，含媒体失败重试）
 *   6. Ctrl+C 优雅退出
 */
import { loadConfig } from './config.js';
import { openDb } from './db.js';
import { OneBotClient } from './onebot.js';
import { handleLiveEvent } from './collect.js';
import { backfillPeer } from './backfill.js';
import { startScheduler } from './scheduler.js';
import { makeReplyHandler } from './reply.js';
import { MediaDownloader } from './media.js';
import { trackContext } from './context.js';
import { makeLogger } from './utils.js';
import { handleInferRule, stopInfer } from './infer.js';
import { makeLlmHandler } from './llm/handler.js';
import { normalizeEvent } from './collect.js';

/** 为推理规则构造最小消息记录（不依赖入库；私聊/群聊均可） */
function normalizeEventForInfer(ev) {
  if (ev.post_type !== 'message') return null;
  if (ev.message_type !== 'private' && ev.message_type !== 'group') return null;
  const rec = normalizeEvent(ev);
  return rec;
}

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const bot = new OneBotClient(config.onebot, log);
const replyHandler = makeReplyHandler(config, bot, log);

// AI 助手（LLM 私聊聊天）：config/llm.json 不存在或 enabled=false 时自动关闭
let llmHandler = null;
try {
  llmHandler = makeLlmHandler(config, db, bot, log);
  if (llmHandler) log.info('[llm] AI 助手已启用（私聊白名单）');
} catch (e) {
  log.warn(`[llm] 初始化失败（忽略，采集不受影响）: ${e.message}`);
}
const media = new MediaDownloader(db, config, log);
if (config.collect?.media?.enabled) {
  media.requeuePending();   // 恢复上次进程退出时遗留的待下载项
}

// 群名缓存（同步读取 + 异步预热；未命中时先落 null，拿到后回填历史行）
const groupNameCache = new Map();
function getGroupNameSync(groupId) {
  return groupNameCache.get(groupId) ?? null;
}
function warmGroupName(groupId) {
  if (groupNameCache.has(groupId)) return;
  bot.getGroupInfo(groupId).then((info) => {
    groupNameCache.set(groupId, info.name);
    if (info.name) {
      db.prepare('UPDATE messages SET group_name=? WHERE peer_id=? AND group_name IS NULL').run(info.name, groupId);
    }
  }).catch(() => {});
}

// 实时消息计数（每 logEvery 条打印一次）
let liveInserted = 0;
let liveDup = 0;

function onInserted(record) {
  media.enqueue(record, record.segments);
  if (record.scene === 'group') trackContext(db, config.context, record, log);
}

bot.onEvent = (ev) => {
  // 推理规则优先（私聊指令/群聊@命令，无需入库即可响应）
  const recRaw = normalizeEventForInfer(ev);
  if (recRaw) {
    try { handleInferRule(recRaw, ev, ev.self_id, db, bot, log); } catch (e) { log.warn(`[infer] 触发异常: ${e.message}`); }
    // AI 助手（LLM 私聊聊天；内部自过滤白名单/指令，推理前缀让位 infer.js）
    if (llmHandler) llmHandler.handle(recRaw);
  }
  if (config.collect.live === false) return;
  const { result, record } = handleLiveEvent(db, config, ev, getGroupNameSync);
  if (result === 'inserted') {
    liveInserted++;
    if (liveInserted % config.logging.logEvery === 0) {
      log.info(`[live] 累计入库 ${liveInserted} 条（重复 ${liveDup}）`);
    }
    if (record.scene === 'group') warmGroupName(record.peer_id);
    onInserted(record);
    replyHandler(record).catch(() => {});
  } else if (result === 'dup') {
    liveDup++;
  }
};

let startupBackfillDone = false;
bot.onConnect = async () => {
  const groups = config.collect.groups ?? [];
  if (!config.collect.backfillOnStart || startupBackfillDone || !groups.length) return;
  startupBackfillDone = true;
  log.info(`[backfill] 启动回填开始，目标 ${groups.length} 个群 + ${(config.collect.friends ?? []).length} 个好友（媒体下载: ${config.collect?.media?.backfillDownload ? '开' : '关'}，上下文跟踪: ${config.context?.enabled ? '开' : '关'}）`);
  for (const g of groups) {
    try {
      const r = await backfillPeer(db, bot, config.collect.backfill, {
        scene: 'group', peerId: g, log, selfId: bot.selfId ?? null,
        onInserted: config.collect?.media?.backfillDownload ? onInserted : undefined,
      });
      log.info(`[backfill] 群 ${g}: 翻页 ${r.pages}，新增 ${r.inserted}，重复 ${r.dups}，最旧 seq=${r.oldestSeq ?? '?'}`);
    } catch (e) {
      log.error(`[backfill] 群 ${g} 失败: ${e.message}`);
    }
  }
  // 私聊好友回填（补充私聊数据源）
  for (const f of config.collect.friends ?? []) {
    try {
      const r = await backfillPeer(db, bot, config.collect.backfill, {
        scene: 'private', peerId: f, log, selfId: bot.selfId ?? null,
        onInserted: config.collect?.media?.backfillDownload ? onInserted : undefined,
      });
      log.info(`[backfill] 好友 ${f}: 翻页 ${r.pages}，新增 ${r.inserted}，重复 ${r.dups}`);
    } catch (e) {
      log.error(`[backfill] 好友 ${f} 失败: ${e.message}`);
    }
  }
  log.info('[backfill] 启动回填完成');
};

bot.connect();
const stopScheduler = startScheduler(db, bot, config, log, {
  onInserted: config.collect?.media?.backfillDownload ? onInserted : undefined,
  onTickEnd: () => { if (config.collect?.media?.enabled) media.retryFailed(); },
});

function shutdown() {
  log.info('正在退出...');
  stopScheduler();
  media.stop();
  bot.close();
  stopInfer();
  db.close();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

log.info(`[boot] QQ 数据集采集服务已启动，数据库: ${config.database}`);
log.info(`[boot] 目标群: ${config.collect.groups.length ? config.collect.groups.join(', ') : '(未配置，仅实时监听)'}`);
log.info(`[boot] 媒体采集: ${config.collect?.media?.enabled ? `开启 (${(config.collect.media.types ?? []).join('/')})` : '关闭'}`);
log.info(`[boot] 上下文跟踪: ${config.context?.enabled ? `开启 (用户 ${(config.context.users ?? []).join(', ')})` : '关闭'}`);

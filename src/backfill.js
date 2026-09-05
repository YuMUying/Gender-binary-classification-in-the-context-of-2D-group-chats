/**
 * backfill.js — 历史回填引擎
 *
 * 适配 NapCat 语义：get_group_msg_history / get_friend_msg_history(reverse_order=true)
 * 返回"含锚点、按时间升序（最旧在前）"的一页；下一锚点 = 返回页的第一条消息的 message_seq。
 *
 * scene='group' → 指定群聊；scene='private' → 指定好友的个人聊天。
 * 支持：断点续传（sync_state.oldest_seq）、去重、限速、untilSeq/untilTime/maxPerGroup。
 * 同样用于 gapfill（增量补齐）：从最新翻到与库内数据重叠为止。
 */
import { saveMessage, getState, setState } from './db.js';
import { cqToText, sleep } from './utils.js';
import { shouldExclude } from './filter.js';

/**
 * @param {object} db
 * @param {OneBotClient} bot
 * @param {object} cfg  config.collect.backfill
 * @param {object} opts { scene:'group'|'private', peerId, untilSeq, maxPages, maxPerGroup, onProgress, gapFill, selfId }
 */
export async function backfillPeer(db, bot, cfg, opts = {}) {
  const scene = opts.scene ?? 'group';
  const peerId = opts.peerId;
  const log = opts.log ?? console;
  const selfId = opts.selfId ?? null;   // 过滤机器人自己的消息
  const pageSize = cfg.pageSize ?? 20;
  const delayMs = cfg.delayMs ?? 800;
  const maxPages = opts.maxPages ?? cfg.maxPagesPerRun ?? 5000;
  const maxPerGroup = opts.maxPerGroup ?? cfg.maxPerGroup ?? null;
  const untilSeq = opts.untilSeq ?? cfg.untilSeq ?? null;

  const state = getState(db, scene, peerId);
  let anchor = state?.oldest_seq ?? null;    // 断点：从上次抓到的最旧 seq 继续向前
  let anchorFromThisRun = false;             // 锚点是否来自本次运行抓到的消息
  let inserted = 0, dups = 0, pages = 0;
  let oldestSeq = state?.oldest_seq ?? null;
  let newestSeq = state?.newest_seq ?? null;

  if (opts.gapFill) {
    // 增量模式：从最新开始，翻到与库内重叠为止
    anchor = null;
    anchorFromThisRun = false;
  }

  while (pages < maxPages) {
    let msgs = [];
    try {
      if (scene === 'private') {
        msgs = await bot.fetchPrivateHistoryPage(peerId, { messageSeq: anchor, count: pageSize });
      } else {
        msgs = await bot.fetchHistoryPage(peerId, { messageSeq: anchor, count: pageSize });
      }
    } catch (e) {
      if (/不存在/.test(e.message)) {
        if (anchor != null && !anchorFromThisRun) {
          // 断点锚点来自旧会话（客户端内存库重启后失效）→ 重置，从最新重新翻
          log.warn(`[backfill] 群 ${peerId} 旧断点锚点失效，改为从最新开始`);
          anchor = null;
          oldestSeq = null;
          setState(db, scene, peerId, { oldestSeq: null, fetchedDelta: 0 });
          continue;
        }
        // 锚点来自本次运行 → 已翻到客户端内存库底部
        log.info(`[backfill] 群 ${peerId} 已到内存库底部（${e.message}）`);
        break;
      }
      log.warn(`[backfill] 群 ${peerId} 拉取失败: ${e.message}`);
      break;
    }
    if (!msgs.length) break;
    pages++;

    let pageInserted = 0, pageDup = 0;
    let pageNewest = -Infinity;
    let pageOldestTime = Infinity;
    const nextAnchor = msgs[0]?.message_seq ?? msgs[0]?.seq ?? null;   // 返回页第一条 = 最旧消息
    for (const m of msgs) {
      const seq = m.message_seq ?? m.seq;
      if (seq != null && seq > pageNewest) pageNewest = seq;
      const t = m.time ?? Math.floor(Date.now() / 1000);
      if (t < pageOldestTime) pageOldestTime = t;
      const rec = {
        scene,
        peer_id: peerId,
        message_id: m.message_id ?? null,
        message_seq: seq ?? null,
        group_name: null,
        user_id: m.sender?.user_id ?? m.user_id ?? null,
        nickname: m.sender?.nickname ?? null,
        card: m.sender?.card ?? null,
        role: m.sender?.role ?? null,
        time: m.time ?? Math.floor(Date.now() / 1000),
        text: cqToText(m.message),
        raw_json: JSON.stringify(m),
        source: 'history',
        segments: m.message ?? [],   // 内存用：供媒体采集提取
      };
      if (rec.user_id == null) continue;
      if (!rec.text) continue;      // 空文本不占空间
      // 统一过滤：机器人自己 + 指令消息
      if (shouldExclude(rec, { selfId })) continue;
      if (saveMessage(db, rec) === 'inserted') {
        inserted++; pageInserted++;
        if (opts.onInserted) opts.onInserted(rec);
      } else { dups++; pageDup++; }
    }

    if (nextAnchor != null) {
      oldestSeq = nextAnchor;
      anchorFromThisRun = true;
      setState(db, scene, peerId, { oldestSeq: nextAnchor, newestSeq: newestSeq != null ? newestSeq : pageNewest, fetchedDelta: pageInserted });
    }
    if (pageNewest !== -Infinity && (newestSeq == null || pageNewest > newestSeq)) {
      newestSeq = pageNewest;
      setState(db, scene, peerId, { newestSeq: pageNewest, fetchedDelta: 0 });
    }

    if (opts.onProgress) opts.onProgress({ pages, inserted, dups, oldestSeq, newestSeq });

    // 停止条件
    if (nextAnchor == null) break;                                                  // 页内无 seq，无法继续
    if (anchor != null && nextAnchor === anchor) break;                             // 锚点未前移（已到最旧）
    if (untilSeq != null && oldestSeq != null && oldestSeq <= untilSeq) break;      // 已到达目标深度(seq)
    if (opts.untilTime != null && pageOldestTime !== Infinity && pageOldestTime < opts.untilTime) break;  // 已挖到目标日期
    if (maxPerGroup != null && inserted >= maxPerGroup) break;                      // 本群已采集足够
    if (opts.gapFill && pageInserted === 0 && pageDup > 0) break;                   // 增量：已与库内重叠

    anchor = nextAnchor;
    if (delayMs > 0) await sleep(delayMs);
  }

  setState(db, scene, peerId, { fetchedDelta: 0 });   // 刷新 last_sync_at
  return { peerId, pages, inserted, dups, oldestSeq, newestSeq };
}

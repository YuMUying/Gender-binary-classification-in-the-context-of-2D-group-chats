/**
 * scheduler.js — 定期增量同步（gapfill）+ 媒体失败重试
 * 服务在线时实时监听零丢失；定时器负责补齐服务离线期间的断档。
 */
import { backfillPeer } from './backfill.js';

export function startScheduler(db, bot, config, log, hooks = {}) {
  if (!config.schedule.enabled) return () => {};
  const groups = config.collect.groups ?? [];
  if (!groups.length) {
    log.info('[scheduler] 未配置目标群，跳过定时增量同步');
    return () => {};
  }

  let running = false;
  let stopped = false;

  async function tick(reason) {
    if (running) return;
    running = true;
    log.info(`[scheduler] 增量同步开始 (${reason})，目标 ${groups.length} 个群`);
    for (const g of groups) {
      if (stopped) break;
      try {
        const r = await backfillPeer(db, bot, config.collect.backfill, {
          scene: 'group', peerId: g, gapFill: true, maxPages: 200, log,
          selfId: bot.selfId ?? null,
          onInserted: hooks.onInserted,
        });
        log.info(`[scheduler] 群 ${g} 同步完成: 新增 ${r.inserted} 条 (重复 ${r.dups})`);
      } catch (e) {
        log.warn(`[scheduler] 群 ${g} 同步失败: ${e.message}`);
      }
    }
    try { hooks.onTickEnd?.(); } catch (e) { log.warn(`[scheduler] 收尾钩子失败: ${e.message}`); }
    log.info('[scheduler] 增量同步结束');
    running = false;
  }

  const timer = setInterval(() => tick('定时'), config.schedule.intervalMinutes * 60 * 1000);
  tick('启动').catch(() => { running = false; });
  return () => { stopped = true; clearInterval(timer); };
}

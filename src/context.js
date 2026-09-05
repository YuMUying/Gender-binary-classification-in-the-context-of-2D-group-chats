/**
 * context.js — 指定 QQ 号的发言及其上下文快照
 *
 * 用途：单条消息脱离上下文信息量低（尤其二次元群短句），本模块在目标用户发言时，
 * 把"前 N 条 + 该消息 + 后 N 条"写入独立 JSONL，供人工标注/上下文建模使用。
 *
 * 配置（config.json）：
 *   "context": {
 *     "enabled": true,
 *     "users": [123456789],     // 要跟踪的 QQ 号列表
 *     "window": 5,              // 前后各取 N 条
 *     "onBackfill": true,       // 历史回填命中也记录
 *     "dir": "data/context"     // 输出目录（按 <user_id>/context-YYYY-MM-DD.jsonl 分文件）
 *   }
 *
 * 幂等：context_exports 表保证每条中心消息只写一次快照。
 */
import { appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { markContextWritten, getContext } from './db.js';

function dayStamp(ts) {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** 实时/回填消息入库后调用：若发言人在跟踪列表内，写上下文快照 */
export function trackContext(db, cfg, record, log) {
  if (!cfg?.enabled || record.scene !== 'group') return;
  if (!(cfg.users ?? []).includes(record.user_id)) return;
  if (record.message_id == null) return;

  if (!markContextWritten(db, record.message_id, record.user_id)) return;   // 已写过

  const ctx = getContext(db, record.peer_id, record.message_id, cfg.window ?? 5);
  if (!ctx) return;

  const line = {
    time: ctx.center.time,
    group_id: record.peer_id,
    center: {
      message_id: ctx.center.message_id,
      user_id: ctx.center.user_id,
      nickname: ctx.center.nickname,
      card: ctx.center.card,
      text: ctx.center.text,
    },
    context: [...ctx.before, ctx.center, ...ctx.after].map((m) => ({
      user_id: m.user_id,
      nickname: m.nickname,
      card: m.card,
      text: m.text,
      time: m.time,
      is_center: m.message_id === ctx.center.message_id,
    })),
    center_raw: record.raw_json ?? null,
  };

  const dir = path.resolve(cfg.dir ?? 'data/context', String(record.user_id));
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `context-${dayStamp(ctx.center.time)}.jsonl`);
  appendFileSync(file, JSON.stringify(line) + '\n', 'utf8');
  log.info(`[context] 已记录 QQ ${record.user_id} 的发言上下文（群 ${record.peer_id}，窗口 ${ctx.before.length}+1+${ctx.after.length}）→ ${file}`);
}

/**
 * reply.js — 可选自动回复（默认关闭；数据采集场景下机器人应尽量安静）
 */
export function makeReplyHandler(config, bot, log) {
  if (!config.reply.enabled) return async () => {};   // 始终返回 Promise，避免调用方 .catch 报错
  const triggers = config.reply.triggers ?? [];

  return async (record) => {
    const text = record.text;
    if (!text) return;
    for (const t of triggers) {
      const hit = t.match === 'exact' ? text === t.keyword : text.includes(t.keyword);
      if (hit) {
        try {
          if (record.scene === 'group') await bot.sendGroupMessage(record.peer_id, t.reply);
          log.info(`[reply] → ${record.scene}#${record.peer_id}: ${t.reply.slice(0, 30)}`);
        } catch (e) {
          log.warn(`[reply] 发送失败: ${e.message}`);
        }
        return;
      }
    }
  };
}

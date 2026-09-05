/**
 * filter.js — 消息过滤（数据集纯净度）
 * 排除：
 *  1. 机器人自己的消息（self）
 *  2. 指令消息（推理 命令，非自然语言；xnn 为历史遗留同样过滤）
 *  3. 纯系统消息
 */

/** 指令消息正则（命令前缀，大小写不敏感；容忍 @机器人 前缀） */
const CMD_PATTERNS = [
  /^(?:@\S+\s*)?推理\s*[:：]?\s*(?:@?\d{5,12}|@\S+)/,  // 推理 12345 或 @某人（历史命令，仅用于过滤不入库）
  /^(?:@\S+\s*)?推理\b/,
  /^(?:@\S+\s*)?xnn\b/i,                                 // xnn（已下线的男娘指数命令，历史消息过滤用）
];

/** 判断是否指令消息 */
export function isCommandMessage(text) {
  if (!text) return false;
  const t = text.trim();
  return CMD_PATTERNS.some((re) => re.test(t));
}

/** 判断是否机器人自己的消息 */
export function isSelfMessage(rec, selfId) {
  return selfId != null && rec.user_id != null && String(rec.user_id) === String(selfId);
}

/** 统一过滤：返回 true = 应排除（不入库） */
export function shouldExclude(rec, { selfId, filterCommands = true } = {}) {
  if (!rec) return true;
  // 1) 机器人自己
  if (isSelfMessage(rec, selfId)) return true;
  // 2) 指令消息
  if (filterCommands && isCommandMessage(rec.text)) return true;
  // 3) 空文本
  if (!rec.text) return true;
  return false;
}

/** 从 CQ 段中判断是否含指令（针对 normalizeEvent 前的原始段） */
export function segmentsContainCommand(segments) {
  if (!Array.isArray(segments)) return false;
  // 文本段拼接判断
  const texts = segments.filter((s) => s.type === 'text').map((s) => s.data?.text ?? '').join(' ');
  return isCommandMessage(texts);
}

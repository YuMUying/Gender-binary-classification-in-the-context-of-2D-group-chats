/**
 * utils.js — CQ 码解析、时间工具、日志
 */

/** CQ 消息段 → 纯文本（训练特征是文本，图片/语音只留摘要） */
export function cqToText(message = []) {
  if (!Array.isArray(message)) return String(message ?? '');
  return message.map((s) => {
    switch (s.type) {
      case 'text': return s.data?.text ?? '';
      case 'at': return `@${s.data?.name || s.data?.qq || ''}`;
      case 'face': return `[表情:${s.data?.id ?? ''}]`;
      case 'image': return `[图片:${s.data?.summary || ''}]`;
      case 'record': return '[语音]';
      case 'video': return '[视频]';
      case 'file': return `[文件:${s.data?.name ?? ''}]`;
      case 'reply': return s.data?.text ? `「引用:${String(s.data.text).slice(0, 50)}」` : '';   // 保留引用原文，供上下文建模
      case 'forward': return '[合并转发]';
      case 'json': return `[JSON:${s.data?.data ?? ''}]`;
      case 'xml': return '[XML]';
      case 'markdown': return s.data?.content ?? '';
      default: return '';
    }
  }).filter(Boolean).join(' ').trim();
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

export function makeLogger(level = 'info') {
  const min = LEVELS[level] ?? 20;
  const out = (lv, args) => {
    if ((LEVELS[lv] ?? 20) < min) return;
    const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    console.log(`[${ts}] [${lv.toUpperCase()}]`, ...args);
  };
  return {
    debug: (...a) => out('debug', a),
    info: (...a) => out('info', a),
    warn: (...a) => out('warn', a),
    error: (...a) => out('error', a),
  };
}

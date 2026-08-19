/**
 * config.js — 配置加载
 * 默认读取 config/config.json；可用环境变量 QQBOT_CONFIG 指定其他路径。
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function loadConfig() {
  const file = process.env.QQBOT_CONFIG || path.join(ROOT, 'config', 'config.json');
  const raw = readFileSync(file, 'utf8').replace(/^\uFEFF/, '');   // 容忍 BOM（记事本/PS 写入常见）
  const cfg = JSON.parse(raw);

  // 默认值合并
  cfg.onebot = { accessToken: '', ...(cfg.onebot ?? {}) };
  cfg.database = cfg.database || path.join(ROOT, 'data', 'qqchat.db');
  cfg.collect = {
    groups: [], friends: [], ignoreSelf: true, live: true, backfillOnStart: true,
    backfill: { pageSize: 20, delayMs: 800, maxPagesPerRun: 5000, untilSeq: null, maxPerGroup: null },
    ...(cfg.collect ?? {}),
  };
  cfg.collect.backfill = { pageSize: 20, delayMs: 800, maxPagesPerRun: 5000, untilSeq: null, maxPerGroup: null, ...(cfg.collect.backfill ?? {}) };
  cfg.schedule = { enabled: true, intervalMinutes: 30, ...(cfg.schedule ?? {}) };
  cfg.reply = { enabled: false, triggers: [], ...(cfg.reply ?? {}) };
  cfg.logging = { level: 'info', logEvery: 200, ...(cfg.logging ?? {}) };
  return cfg;
}

export { ROOT };

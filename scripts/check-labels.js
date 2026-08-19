/**
 * check-labels.js — 标签核查：找出疑似"手打错号"的标注
 *
 * 逻辑：
 *  1. 每个标注用户的消息数（0/很少 → ⚠）
 *  2. 未标注活跃用户 top N（可能是漏标或错号的真实主人）
 *  3. 对 ⚠ 标注用户，按数字串相似度（同长度逐位差异 ≤2 / 不同长度编辑距离 ≤2）
 *     在未标注用户中找"疑似错号候选"
 *
 * 用法：node scripts/check-labels.js
 */
import { loadConfig } from '../src/config.js';
import { openDb } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

function levenshtein(a, b) {
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
  }
  return dp[m][n];
}

// 1) 标注用户消息量
const labeled = db.prepare(`
  SELECT l.user_id, l.gender, l.label_group g, COUNT(m.id) c,
         SUM(CASE WHEN LENGTH(m.text) >= 4 THEN 1 ELSE 0 END) eff
  FROM speaker_labels l LEFT JOIN messages m ON m.user_id = l.user_id AND m.scene='group'
  WHERE l.gender IN ('male','female')
  GROUP BY l.user_id ORDER BY eff ASC`).all();

// 2) 未标注活跃用户
const unlabeled = db.prepare(`
  SELECT user_id, MAX(nickname) nickname, COUNT(*) c
  FROM messages
  WHERE scene='group' AND user_id NOT IN (SELECT user_id FROM speaker_labels WHERE gender IN ('male','female'))
  GROUP BY user_id ORDER BY c DESC LIMIT 80`).all();

const weak = labeled.filter((l) => (l.eff ?? 0) < 100);

log.info('===== 标注用户消息量（升序，⚠ = 有效<100） =====');
for (const l of labeled) {
  const mark = (l.eff ?? 0) < 100 ? '⚠' : '  ';
  log.info(`${mark} QQ ${l.user_id} (${l.gender}, 群${l.g ?? '?'}): 共 ${l.c} 条, 有效 ${l.eff ?? 0} 条`);
}

log.info('\n===== 未标注活跃用户（可能漏标/错号，按发言量 top 30） =====');
for (const u of unlabeled.slice(0, 30)) {
  log.info(`QQ ${u.user_id} (${u.nickname ?? '?'}): ${u.c} 条`);
}

log.info('\n===== 疑似错号候选（弱标注用户 ↔ 未标注用户的数字相似度） =====');
const sus = new Set(weak.map((w) => String(w.user_id)));
for (const w of weak) {
  const ws = String(w.user_id);
  const candidates = [];
  for (const u of unlabeled) {
    const us = String(u.user_id);
    const d = levenshtein(ws, us);
    if (d <= 2 && !sus.has(us)) {
      candidates.push({ uid: u.user_id, nickname: u.nickname, c: u.c, d });
    }
  }
  if (candidates.length) {
    for (const c of candidates) {
      log.info(`标注 QQ ${w.user_id} (${w.gender}, ${w.c}条) ⇄ 疑似 QQ ${c.uid} (${c.nickname ?? '?'}, ${c.c}条)  编辑距离=${c.d}`);
    }
  } else {
    log.info(`标注 QQ ${w.user_id} (${w.gender}, ${w.c}条): 未找到相似未标注号`);
  }
}

db.close();

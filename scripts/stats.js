/**
 * stats.js — CLI：数据集统计概览
 * 用法：node scripts/stats.js
 */
import { loadConfig } from '../src/config.js';
import { openDb, stats, topUnlabeledUsers } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const s = stats(db);

log.info('========== 数据集统计 ==========');
log.info(`消息总数: ${s.total}`);
log.info(`未标注发言人数: ${s.unlabeledUsers}`);
log.info('\n--- 各群消息量 ---');
for (const g of s.byGroup) {
  log.info(`群 ${g.peer_id} (${g.group_name ?? '?'}): ${g.c} 条  [${new Date(g.min_t * 1000).toLocaleDateString('zh-CN')} ~ ${new Date(g.max_t * 1000).toLocaleDateString('zh-CN')}]`);
}
log.info('\n--- 标签覆盖 ---');
for (const l of s.labelCoverage) {
  log.info(`gender=${l.gender}: 用户 ${l.users} 人, 消息 ${l.msgs} 条`);
}
log.info('\n--- 发言最多的 20 人 ---');
for (const u of s.byUser.slice(0, 20)) {
  log.info(`QQ ${u.user_id} (${u.nickname ?? '?'}): ${u.c} 条`);
}

log.info('\n--- 已标注用户每人消息量（判断训练数据是否充足） ---');
const perLabeled = db.prepare(`
  SELECT l.user_id, l.gender, l.label_confidence,
         COUNT(m.id) total,
         SUM(CASE WHEN LENGTH(m.text) >= 4 AND m.text NOT LIKE '[图片%' AND m.text NOT LIKE '[动画表情%' AND m.text NOT LIKE '[表情%' AND m.text NOT LIKE '[合并转发%' AND m.text NOT LIKE '[语音%' AND m.text NOT LIKE '[文件%' AND m.text NOT LIKE '[视频%' AND m.text NOT LIKE '[JSON%' THEN 1 ELSE 0 END) effective
  FROM speaker_labels l LEFT JOIN messages m ON m.user_id = l.user_id AND m.scene='group'
  WHERE l.gender IN ('male','female')
  GROUP BY l.user_id ORDER BY effective DESC`).all();
if (!perLabeled.length) {
  log.info('(暂无标注)');
} else {
  let low = 0;
  for (const r of perLabeled) {
    const eff = r.effective ?? 0;
    if (eff < 300) low++;
    log.info(`QQ ${r.user_id} (${r.gender}, ${r.label_confidence}): 共 ${r.total} 条，有效≥4字 ${eff} 条${eff < 300 ? '  ⚠ 偏少' : ''}`);
  }
  const maleEff = perLabeled.filter((r) => r.gender === 'male').reduce((s, r) => s + (r.effective ?? 0), 0);
  const femaleEff = perLabeled.filter((r) => r.gender === 'female').reduce((s, r) => s + (r.effective ?? 0), 0);
  log.info(`\n汇总: male 有效 ${maleEff} 条 / female 有效 ${femaleEff} 条；有效<300 的标注用户 ${low} 人`);
  log.info('参考: 每人≥300条有效发言可训练用户级模型；标注人数建议扩到40~60人让评估可信');
}

log.info('\n--- 建议优先标注的未标注活跃用户 ---');
const unlabeled = topUnlabeledUsers(db, 20);
if (!unlabeled.length) log.info('(全部活跃用户已标注 🎉)');
else for (const u of unlabeled) {
  log.info(`QQ ${u.user_id} (${u.nickname ?? '?'}): ${u.c} 条  → node scripts/label.js --user ${u.user_id} --gender male|female`);
}

db.close();

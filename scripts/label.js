/**
 * label.js — CLI：手动标注发言人性别（训练标签）
 *
 * 用法：
 *   node scripts/label.js --user 123456789 --gender male        # 标注某人为男
 *   node scripts/label.js --user 987654321 --gender female
 *   node scripts/label.js --user 111222333 --gender unknown     # 明确"不确定"
 *   node scripts/label.js --list                                # 查看已标注列表
 *   node scripts/label.js --top 30                              # 按发言量列出前30名活跃用户（方便批量认人）
 *
 * 标注的是"该用户本人的性别"（你通过线下认识/个人资料确认真实性别），
 * 模型学的是"发言文本 → 性别"的映射。只标注你有把握的人，宁缺毋滥。
 */
import { loadConfig } from '../src/config.js';
import { openDb, setLabel, listLabels, labelCoverageStats } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const has = (name) => args.includes(name);

if (has('--list')) {
  const labels = listLabels(db);
  if (!labels.length) log.info('(暂无标注)');
  else for (const l of labels) log.info(`QQ ${l.user_id}  ${l.nickname ?? ''}  → ${l.gender}  (${l.label_source}, ${l.label_confidence ?? 'high'}${l.label_group ? `, 群${l.label_group}` : ''}, ${new Date((l.updated_at ?? 0) * 1000).toLocaleString('zh-CN')})`);
  db.close(); process.exit(0);
}

if (has('--top')) {
  const n = Number(arg('--top') ?? 30);
  const rows = db.prepare(`
    SELECT u.user_id, u.nickname,
           (SELECT card FROM messages WHERE user_id=u.user_id AND card IS NOT NULL AND card != '' ORDER BY time DESC LIMIT 1) card,
           u.message_count c
    FROM user_profiles u ORDER BY c DESC LIMIT ?`).all(n);
  for (const r of rows) {
    const cardStr = r.card && r.card !== r.nickname ? `（群名片: ${r.card}）` : '';
    log.info(`QQ ${r.user_id}  ${r.nickname ?? '?'}${cardStr}  发言 ${r.c} 条`);
  }
  log.info('\n标注示例: node scripts/label.js --user <QQ号> --gender male');
  db.close(); process.exit(0);
}

const userId = arg('--user') ? Number(arg('--user')) : null;
const gender = arg('--gender');
const confidence = arg('--confidence') ?? 'high';
const group = arg('--group') ? Number(arg('--group')) : null;
if (!userId || !['male', 'female', 'unknown'].includes(gender) || !['high', 'medium', 'low'].includes(confidence)) {
  console.error('用法: node scripts/label.js --user <QQ号> --gender male|female|unknown [--confidence high|medium|low] [--group <群号>]');
  console.error('      node scripts/label.js --list');
  console.error('      node scripts/label.js --top [N]');
  db.close(); process.exit(1);
}

const nickname = db.prepare('SELECT MAX(nickname) n FROM messages WHERE user_id=?').get(userId)?.n ?? null;
setLabel(db, userId, gender, nickname, 'manual', confidence, group);
log.info(`已标注 QQ ${userId} (${nickname ?? '未知昵称'}) → ${gender} (置信度 ${confidence}${group ? `, 群 ${group}` : ''})`);

// 自动化反馈：该用户消息量 + 整体标注覆盖率
const userMsgs = db.prepare(`SELECT COUNT(*) c FROM messages WHERE user_id=? AND scene='group'`).get(userId).c;
const cov = labelCoverageStats(db);
log.info(`该用户已有 ${userMsgs} 条群消息，将自动进入训练集（含之后新采集的消息）`);
log.info(`当前标注覆盖: ${cov.labeledUsers}/${cov.totalUsers} 人，${cov.labeledMsgs}/${cov.totalMsgs} 条消息 (${cov.totalMsgs ? (cov.labeledMsgs / cov.totalMsgs * 100).toFixed(1) : 0}%)`);
log.info('导出训练集: node scripts/export-dataset.js --mode train --split-by-user');
db.close();

/**
 * import-labels.js — CLI：从文本文件批量导入性别标定（支持多群分段）
 *
 * 文件格式：
 *   在群聊 0 ⑩犹格索托斯的庭院群 中采集信息，标定信息如下（QQ号+性别模式）：
 *   1. 0 男
 *   2. 0 女
 *   在群聊 0 ③庭院交流群 3 中的信息如下：
 *   1. 0 男
 *   2. 0 女
 *
 * 每行一条 "序号. QQ号 性别"；"群聊 <群号>" 之后的行归属该群（label_group 字段，
 * 用于跨群泛化验证：export-dataset.js --val-groups）。
 *
 * 用法：
 *   node scripts/import-labels.js --file 采集说明.txt [--confidence high]
 * 可反复运行，覆盖更新。
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { loadConfig, ROOT } from '../src/config.js';
import { openDb, setLabel } from '../src/db.js';
import { makeLogger } from '../src/utils.js';

const config = loadConfig();
const log = makeLogger(config.logging.level);
const db = openDb(config.database);

const args = process.argv.slice(2);
function arg(name) { const i = args.indexOf(name); return i >= 0 && args[i + 1] ? args[i + 1] : undefined; }
const file = arg('--file') ?? path.join(ROOT, '采集说明.txt');
const confidence = arg('--confidence') ?? 'high';

if (!['high', 'medium', 'low'].includes(confidence)) {
  console.error('--confidence 只能是 high|medium|low');
  db.close(); process.exit(1);
}

const GENDER_MAP = { '男': 'male', 'male': 'male', '女': 'female', 'female': 'female', '未知': 'unknown', '不确定': 'unknown', 'unknown': 'unknown' };

const raw = readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
const lines = raw.split(/\r?\n/).filter(Boolean);

let currentGroup = null;
const parsed = [];
for (const line of lines) {
  const gm = line.match(/群聊\s*(\d{5,})/);
  if (gm) { currentGroup = Number(gm[1]); continue; }
  const m = line.match(/(\d{5,})[\s\t,，:：]+(男|女|未知|不确定|male|female|unknown)/);
  if (m) parsed.push({ user_id: Number(m[1]), gender: GENDER_MAP[m[2]], group: currentGroup });
}
if (!parsed.length) {
  log.error(`未能从 ${file} 解析出任何 "QQ号 性别" 条目`);
  db.close(); process.exit(1);
}

const byGender = { male: 0, female: 0, unknown: 0 };
const byGroup = {};
for (const p of parsed) {
  setLabel(db, p.user_id, p.gender, null, 'import', confidence, p.group);
  byGender[p.gender]++;
  byGroup[p.group ?? '未分群'] = (byGroup[p.group ?? '未分群'] ?? 0) + 1;
  log.info(`已标注 QQ ${p.user_id} → ${p.gender} (${confidence}) [群 ${p.group ?? '?'}]`);
}
log.info(`\n导入完成: male ${byGender.male} 人 / female ${byGender.female} 人 / unknown ${byGender.unknown} 人`);
log.info(`分群统计: ${Object.entries(byGroup).map(([g, n]) => `群 ${g} = ${n} 人`).join('，')}`);
log.info('待采集消息后执行: node scripts/stats.js 查看覆盖率');
db.close();

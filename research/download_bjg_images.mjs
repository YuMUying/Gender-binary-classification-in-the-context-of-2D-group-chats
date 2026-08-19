/**
 * download_bjg_images.mjs — 用 get_image（QQ内核通道）批量下载白驹过隙信封图片 + 私聊图片
 *
 * 用法: node research/download_bjg_images.mjs [--only-private] [--limit N]
 * 间隔: 每张 1500ms（防风控）；失败重试 2 次
 */
import { execSync } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const BASE = 'http://127.0.0.1:3000';
const args = process.argv.slice(2);
const has = (n) => args.includes(n);
const arg = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
const ONLY_PRIVATE = has('--only-private');
const LIMIT = Number(arg('--limit') ?? 0);

async function getImage(file) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const r = await fetch(BASE + '/get_image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file }),
        signal: AbortSignal.timeout(90000),
      });
      const j = await r.json();
      if (j.status === 'ok' && j.data?.file) {
        return { ok: true, path: j.data.file, size: Number(j.data.file_size ?? 0) };
      }
      return { ok: false, err: j.message ?? 'unknown' };
    } catch (e) {
      if (attempt === 2) return { ok: false, err: e.message };
      await sleep(3000 * (attempt + 1));
    }
  }
  return { ok: false, err: 'retry exhausted' };
}

// 收集文件名：私聊 29 张（10:18 后）+ 信封 59 张（user_id=3615168664 forward）
const files = new Map(); // name -> source
try {
  const py = path.join(ROOT, 'research', 'list_bjg_image_names.py');
  const out = execSync(`python ${py}`, { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 }).trim();
  for (const [k, v] of Object.entries(JSON.parse(out))) files.set(k, v);
} catch (e) {
  console.log('信封图片收集失败:', e.message);
}

// 私聊图片（通过 OneBot 拉取 2633083674 最近 50 条）
if (true) {
  const r = await fetch(BASE + '/get_friend_msg_history', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: 2633083674, count: 50 }),
    signal: AbortSignal.timeout(20000),
  });
  const j = await r.json();
  for (const m of (j.data?.messages ?? [])) {
    if (m.time < 1787069880) continue; // 10:18 之后
    for (const seg of (m.message ?? [])) {
      if (seg.type === 'image') {
        const fn = seg.data?.file;
        if (fn) files.set(fn, 'private');
      }
    }
  }
}

const all = [...files.entries()];
console.log(`待下载: ${all.length} 张（信封 ${all.filter(([, s]) => s === 'envelope').length} + 私聊 ${all.filter(([, s]) => s === 'private').length}）`);
let ok = 0, fail = 0;
for (let i = 0; i < all.length; i++) {
  if (LIMIT && i >= LIMIT) break;
  const [fn, src] = all[i];
  const res = await getImage(fn);
  if (res.ok) {
    ok++;
    if (i % 10 === 0) console.log(`[${i + 1}/${all.length}] ✓ ${fn} (${(res.size / 1024).toFixed(0)}KB)`);
  } else {
    fail++;
    console.log(`[${i + 1}/${all.length}] ✗ ${fn}: ${res.err}`);
  }
  await sleep(1500);
}
console.log(`\n完成: 成功 ${ok} / 失败 ${fail}`);

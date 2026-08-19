// 尝试 gtimg 新版 CDN + 深挖官网配置
import { writeFile } from 'node:fs/promises';
import { existsSync, statSync, mkdirSync } from 'node:fs';

const DIR = 'C:/Users/Lenovo/Downloads/qq-bot-deploy';
mkdirSync(DIR, { recursive: true });
const OUT = DIR + '/QQ_9.9.31_260528_x64_01.exe';
if (!existsSync(OUT) || statSync(OUT).size < 100 * 1048576) {
  const url = 'https://qqdl.gtimg.cn/qqfile/QQNT/9.9.31/release/092069d7/QQ_9.9.31_260528_x64_01.exe';
  console.log('尝试 gtimg CDN:', url);
  try {
    const r = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://im.qq.com/' },
      signal: AbortSignal.timeout(1800000),
    });
    if (r.ok) {
      const buf = Buffer.from(await r.arrayBuffer());
      await writeFile(OUT, buf);
      console.log('完成:', OUT, Math.round(buf.length / 1048576), 'MB');
    } else console.log('HTTP', r.status);
  } catch (e) { console.log('失败:', e.message); }
} else console.log('已存在:', OUT);

// 官网页面里找配置/下载 json
const html = await (await fetch('https://im.qq.com/pcqq/index.shtml', { headers: { 'User-Agent': 'Mozilla/5.0' } })).text();
const configs = [...new Set([...html.matchAll(/["']([^"']*?(?:rainbow|config|pcqq|download)[^"']*?\.(?:json|js)[^"']*)["']/gi)].map((m) => m[1]))];
console.log('配置候选:', configs.slice(0, 20).join('\n'));
const seajsUses = [...html.matchAll(/seajs\.use\(([^)]+)\)/g)].map((m) => m[1]);
console.log('seajs.use:', seajsUses.slice(0, 5).join('\n'));

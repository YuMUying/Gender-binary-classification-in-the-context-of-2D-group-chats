// 下载 NapCat.Shell.Windows.Node.zip（重试版）
import { writeFile } from 'node:fs/promises';
import { existsSync, mkdirSync, statSync } from 'node:fs';

const dir = 'C:/Users/Lenovo/Downloads/qq-bot-deploy';
mkdirSync(dir, { recursive: true });
const zipPath = dir + '/NapCat.Shell.Windows.Node.zip';

if (existsSync(zipPath) && statSync(zipPath).size > 100 * 1048576) {
  console.log('已存在且完整:', zipPath);
  process.exit(0);
}

const rel = await (await fetch('https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest', {
  headers: { 'User-Agent': 'research' },
})).json();
const asset = rel.assets.find((a) => a.name.includes('Shell.Windows.Node'));
console.log('目标:', asset.name, Math.round(asset.size / 1048576), 'MB');

for (let attempt = 1; attempt <= 4; attempt++) {
  try {
    console.log(`尝试 ${attempt} ...`);
    const r = await fetch(asset.browser_download_url, {
      headers: { 'User-Agent': 'research' },
      signal: AbortSignal.timeout(600000),
    });
    if (!r.ok) { console.log('HTTP', r.status); continue; }
    const buf = Buffer.from(await r.arrayBuffer());
    await writeFile(zipPath, buf);
    console.log('完成:', zipPath, Math.round(buf.length / 1048576), 'MB');
    process.exit(0);
  } catch (e) {
    console.log(`失败: ${e.message}`);
    await new Promise((res) => setTimeout(res, 3000 * attempt));
  }
}
console.log('多次尝试后仍失败');
process.exit(1);

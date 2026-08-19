// 下载 NapCat Windows OneKey 一键安装包并解压检查
import { writeFile } from 'node:fs/promises';
import { existsSync, mkdirSync } from 'node:fs';

const UA = { headers: { 'User-Agent': 'research' } };
const rel = await (await fetch('https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest', UA)).json();
console.log('latest:', rel.tag_name);
const asset = rel.assets.find((a) => a.name.includes('OneKey'));
if (!asset) { console.log('no OneKey asset; assets:', rel.assets.map((a) => a.name).join(', ')); process.exit(1); }

const dir = 'C:/Users/Lenovo/Downloads/qq-bot-deploy';
mkdirSync(dir, { recursive: true });
const zipPath = dir + '/' + asset.name;
if (!existsSync(zipPath)) {
  console.log('下载', asset.name, Math.round(asset.size / 1024), 'KB ...');
  const buf = Buffer.from(await (await fetch(asset.browser_download_url, UA)).arrayBuffer());
  await writeFile(zipPath, buf);
  console.log('已保存:', zipPath);
} else {
  console.log('已存在:', zipPath);
}

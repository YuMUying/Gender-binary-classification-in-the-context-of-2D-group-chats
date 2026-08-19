// 获取 QQ NT 官方下载链接 + NapCat 安装器 release（不回显密钥）
async function getText(u) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) research' } });
    return { ok: r.ok, status: r.status, text: r.ok ? await r.text() : null };
  } catch (e) { return { ok: false, status: 'ERR', text: String(e.message) }; }
}

const page = await getText('https://im.qq.com/pcqq/index.shtml');
console.log(`im.qq.com/pcqq status=${page.status}`);
if (page.ok) {
  const links = [...page.text.matchAll(/https?:\/\/[^"'\s]+?\.exe[^"'\s]*/g)].map((m) => m[0]);
  const uniq = [...new Set(links)];
  console.log('exe 链接:', uniq.slice(0, 10).join('\n'));
}

const rel = await fetch('https://api.github.com/repos/NapNeko/NapCat-Installer/releases/latest', { headers: { 'User-Agent': 'research' } });
if (rel.ok) {
  const j = await rel.json();
  console.log(`\nNapCat-Installer latest: ${j.tag_name}`);
  for (const a of j.assets) console.log(`  ${a.name} (${Math.round(a.size / 1048576)}MB)  ${a.browser_download_url}`);
} else {
  console.log('NapCat-Installer release fetch failed:', rel.status);
}

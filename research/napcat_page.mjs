// 尝试直接抓 VitePress 的 .md 源
for (const p of ['/guide/start-install.md', '/guide/start-install.html', '/guide/shell.md', '/guide/start-install/index.md']) {
  const r = await fetch('https://napneko.github.io' + p, { headers: { 'User-Agent': 'Mozilla/5.0 research' } });
  const t = await r.text();
  console.log(`\n===== ${p} → ${r.status} len=${t.length} =====`);
  if (r.ok && t.includes('Shell') && t.length < 200000) {
    const txt = t.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 2500);
    console.log(txt);
  }
}

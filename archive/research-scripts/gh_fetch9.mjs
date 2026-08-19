async function getText(u) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0 research' } });
    return { ok: r.ok, status: r.status, text: r.ok ? await r.text() : null };
  } catch (e) { return { ok: false, status: 'ERR', text: String(e.message) }; }
}
function stripHtml(t) {
  return t.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
}

async function main() {
  // 1. Milky 站点导航链接
  const nav = await getText('https://milky.ntqqrev.org/');
  if (nav.ok) {
    const hrefs = [...new Set([...nav.text.matchAll(/href="([^"]+)"/g)].map(m => m[1]).filter(h => h.startsWith('/') || h.startsWith('https://milky')))];
    console.log('== milky nav hrefs ==');
    console.log(hrefs.join('\n'));
  }

  // 2. acidify 仓库 yogurt 目录 README
  for (const p of ['yogurt/README.md', 'yogurt/README_EN.md']) {
    const r = await getText(`https://raw.githubusercontent.com/LagrangeDev/acidify/main/${p}`);
    console.log(`\n== ${p} status=${r.status} ==`);
    if (r.ok) { console.log(r.text.split('\n').slice(0, 80).join('\n')); break; }
  }

  // 3. yogurt start 页面原始 HTML 里找内容(markdown 可能内嵌)
  const s = await getText('https://acidify.ntqqrev.org/yogurt/start');
  console.log(`\n== yogurt/start html len=${s.text ? s.text.length : 0} ==`);
  if (s.text) {
    // VitePress 内容在 JSON 里
    const m = s.text.match(/__VP_DATA__[^>]*>/);
    console.log('has VP_DATA:', !!m);
    const txt = stripHtml(s.text);
    console.log('text len:', txt.length, txt.slice(0, 1500));
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

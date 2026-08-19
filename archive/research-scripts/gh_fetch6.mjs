async function getText(u, headers = {}) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0 research', ...headers } });
    return { ok: r.ok, status: r.status, text: r.ok ? await r.text() : null };
  } catch (e) { return { ok: false, status: 'ERR', text: String(e.message) }; }
}

async function main() {
  // 1. GitLab API raw README
  const r1 = await getText('https://gitcode.com/api/v4/projects/1653785/repository/files/README.md/raw?ref=master');
  console.log(`== gitcode api raw README status=${r1.status} ==`);
  if (r1.ok) console.log(r1.text.split('\n').slice(0, 130).join('\n'));

  // 2. 仓库树
  const r2 = await getText('https://gitcode.com/api/v4/projects/1653785/repository/tree?ref=master&per_page=100');
  console.log(`\n== tree status=${r2.status} ==`);
  if (r2.ok) {
    try {
      const j = JSON.parse(r2.text);
      console.log(j.map(x => `${x.type} ${x.path}`).join('\n'));
    } catch (e) { console.log('not json, len=', r2.text.length, r2.text.slice(0, 300)); }
  }

  // 3. Gitee 搜索
  const r3 = await getText('https://search.gitee.com/?q=OpenShamrock&type=repository');
  console.log(`\n== gitee search status=${r3.status} ==`);
  if (r3.ok) {
    const names = [...r3.text.matchAll(/href="https:\/\/gitee\.com\/([^"]+)"[^>]*>[\s\S]{0,120}?OpenShamrock|OpenShamrock/g)].slice(0, 30);
    const seen = new Set();
    for (const m of r3.text.matchAll(/gitee\.com\/([A-Za-z0-9_\-./]+)/g)) {
      const p = m[1];
      if (!p.includes('search') && !seen.has(p)) { seen.add(p); if (seen.size > 40) break; }
    }
    console.log([...seen].join('\n'));
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

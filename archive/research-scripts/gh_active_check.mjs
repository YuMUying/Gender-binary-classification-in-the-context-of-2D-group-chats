const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return r.ok ? r.json() : null;
}

async function main() {
  const repos = [
    'LLOneBot/LLOneBot',
    'LagrangeDev/Lagrange.OneBot',
    'chrononeko/chronocat',
    'NapNeko/NapCatQQ',
    'LagrangeDev/Lagrange.Core',
    'LagrangeDev/acidify',
    'lc-cn/onebots',
    'icqqjs/icqq-onebot',
    'Misaka-Mikoto-Tech/icqq',
    'ion-aluminium/OpenShamrock-QQ-9.2.95-adapt',
  ];
  for (const r of repos) {
    const j = await api(`/repos/${r}`);
    if (!j) { console.log(`${r} | NOT FOUND`); continue; }
    console.log(`${r} | stars=${j.stargazers_count} | pushed=${String(j.pushed_at).slice(0,10)} | archived=${j.archived} | ${(j.description || '').slice(0, 60)}`);
  }
  // Shamrock 9.2.95 adapt 的 releases
  const rel = await api('/repos/ion-aluminium/OpenShamrock-QQ-9.2.95-adapt/releases?per_page=5');
  console.log('\n== OpenShamrock-QQ-9.2.95-adapt releases ==');
  if (rel && rel.length) for (const x of rel) console.log(`tag=${x.tag_name} published=${String(x.published_at).slice(0,10)} assets=${(x.assets || []).map(a => a.name).join(',')}`);
  else console.log(rel === null ? '(repo not found)' : '(no releases)');
  // NapCat 最近一个 release
  const nr = await api('/repos/NapNeko/NapCatQQ/releases/latest');
  if (nr) console.log(`\nNapCatQQ latest: ${nr.tag_name} ${String(nr.published_at).slice(0,10)}`);
  const lr = await api('/repos/LLOneBot/LLOneBot/releases/latest');
  if (lr) console.log(`LLOneBot latest: ${lr.tag_name} ${String(lr.published_at).slice(0,10)}`);
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

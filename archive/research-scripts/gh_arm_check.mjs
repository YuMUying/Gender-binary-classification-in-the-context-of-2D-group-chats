const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return r.ok ? r.json() : null;
}

async function main() {
  // 1. NapCatQQ 最新 release 的资产（找 arm64）
  const rel = await api('/repos/NapNeko/NapCatQQ/releases/latest');
  console.log(`NapCatQQ latest: ${rel?.tag_name} ${String(rel?.published_at).slice(0, 10)}`);
  for (const a of (rel?.assets ?? [])) console.log(`  asset: ${a.name} (${Math.round(a.size / 1048576)}MB)`);

  // 2. napcat-docker 仓库
  const d = await api('/repos/NapNeko/NapCat-Docker');
  console.log(`\nNapCat-Docker: ${d ? `stars=${d.stargazers_count} pushed=${String(d.pushed_at).slice(0,10)} desc=${(d.description || '').slice(0,70)}` : 'NOT FOUND'}`);
  const dr = await api('/repos/NapNeko/NapCat-Docker/contents/');
  if (dr) console.log('files:', dr.map(x => x.name).join(', '));

  // 3. LLBot linux-arm64 资产再确认（作为轻量替代）
  const lr = await api('/repos/LLOneBot/LuckyLilliaBot/releases/latest');
  console.log(`\nLLBot latest: ${lr?.tag_name}`);
  for (const a of (lr?.assets ?? []).filter(x => /arm|aarch/.test(x.name))) console.log(`  arm asset: ${a.name} (${Math.round(a.size / 1048576)}MB)`);

  // 4. Lagrange.OneBot 现在的位置（搜索）
  const s = await api('/search/repositories?q=Lagrange.OneBot&per_page=5');
  if (s) for (const it of s.items.slice(0, 5)) {
    console.log(`\nsearch Lagrange.OneBot: ${it.full_name} | stars=${it.stargazers_count} | pushed=${String(it.pushed_at).slice(0,10)}`);
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

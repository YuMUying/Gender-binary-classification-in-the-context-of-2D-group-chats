const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return r.ok ? r.json() : null;
}
async function raw(u) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'research' } });
    return r.ok ? await r.text() : null;
  } catch { return null; }
}

async function main() {
  // 找 Lagrange.OneBot 现在的位置
  const s = await api('/search/repositories?q=Lagrange+OneBot&sort=stars&order=desc&per_page=6');
  console.log('== search Lagrange OneBot ==');
  if (s) for (const it of s.items.slice(0, 6)) {
    console.log(`${it.full_name} | stars=${it.stargazers_count} | pushed=${String(it.pushed_at).slice(0,10)} | ${(it.description || '').slice(0,70)}`);
  }
  // LLOneBot README 确认 Milky 支持
  const t = await raw('https://raw.githubusercontent.com/LLOneBot/LLOneBot/main/README.md');
  console.log('\n== LLOneBot README (前 60 行) ==');
  if (t) console.log(t.split('\n').slice(0, 60).join('\n'));
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

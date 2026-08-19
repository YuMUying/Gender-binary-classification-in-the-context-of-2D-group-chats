const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function search(q) {
  const r = await fetch(`https://api.github.com/search/repositories?q=${encodeURIComponent(q)}&sort=stars&order=desc&per_page=8`, UA);
  return r.ok ? r.json() : null;
}

async function main() {
  const queries = [
    'gender classification chinese',
    '性别分类 文本',
    'gender classifier bert',
    'gender detection text',
    'chinese gender predict nlp',
  ];
  for (const q of queries) {
    const j = await search(q);
    console.log(`\n===== search: ${q} =====`);
    if (!j) { console.log('(failed)'); continue; }
    for (const it of j.items.slice(0, 8)) {
      console.log(`${it.full_name} | stars=${it.stargazers_count} | pushed=${String(it.pushed_at).slice(0,10)} | ${(it.description || '').slice(0,80)}`);
    }
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

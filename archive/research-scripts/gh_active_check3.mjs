const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };
async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  return r.ok ? r.json() : null;
}
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
  for (const r of ['LLOneBot/LuckyLilliaBot', 'LagrangeDev/LagrangeV2']) {
    const j = await api(`/repos/${r}`);
    if (j) console.log(`${r} | stars=${j.stargazers_count} | pushed=${String(j.pushed_at).slice(0,10)} | ${(j.description || '').slice(0,80)}`);
    else console.log(`${r} | NOT FOUND`);
  }
  const rel = await api('/repos/LLOneBot/LuckyLilliaBot/releases/latest');
  if (rel) {
    console.log(`\nLuckyLilliaBot latest: ${rel.tag_name} ${String(rel.published_at).slice(0,10)}`);
    for (const a of (rel.assets || []).slice(0, 20)) console.log('  asset:', a.name, `(${Math.round(a.size / 1048576)}MB)`);
  }
  // 官方文档首页，看支持平台
  const d = await getText('https://luckylillia.com');
  console.log(`\n== luckylillia.com status=${d.status} ==`);
  if (d.ok) console.log(stripHtml(d.text).slice(0, 1500));
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

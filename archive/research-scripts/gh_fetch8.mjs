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
  for (const u of [
    'https://acidify.ntqqrev.org/yogurt/start',
    'https://milky.ntqqrev.org/',
    'https://fraq.ntqqrev.org/',
    'https://acidify.ntqqrev.org/',
  ]) {
    const r = await getText(u);
    console.log(`\n########## ${u} (status=${r.status}) ##########`);
    if (r.ok) console.log(stripHtml(r.text).slice(0, 1800));
  }
  // yogurt release body
  try {
    const j = await (await fetch('https://api.github.com/repos/SaltifyDev/yogurt-releases/releases/latest', { headers: { 'User-Agent': 'research' } })).json();
    console.log('\n########## yogurt release body ##########');
    console.log((j.body || '').slice(0, 1200));
  } catch (e) { console.log('release fetch failed', e.message); }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

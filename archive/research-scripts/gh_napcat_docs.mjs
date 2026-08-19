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
  const home = await getText('https://napneko.github.io/');
  console.log(`home status=${home.status}`);
  if (home.ok) {
    const hrefs = [...new Set([...home.text.matchAll(/href="([^"]+)"/g)].map(m => m[1]).filter(h => h.startsWith('/') && !/\.(css|js|png|svg|ico|jpg|woff)/.test(h)))];
    console.log('nav:', hrefs.slice(0, 40).join('\n'));
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

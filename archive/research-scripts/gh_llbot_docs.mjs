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
  const home = await getText('https://luckylillia.com');
  if (home.ok) {
    const hrefs = [...new Set([...home.text.matchAll(/href="([^"]+)"/g)].map(m => m[1]).filter(h => h.startsWith('/') && !h.includes('static') && !h.includes('.css') && !h.includes('.js') && !h.includes('.png') && !h.includes('.svg') && !h.includes('.ico')))];
    console.log('== luckylillia.com nav ==');
    console.log(hrefs.join('\n'));
  }
  for (const p of ['/install', '/guide/install', '/docs/install', '/start', '/guide/start']) {
    const r = await getText('https://luckylillia.com' + p);
    if (r.ok && r.text && stripHtml(r.text).length > 300) {
      console.log(`\n########## ${p} ##########`);
      console.log(stripHtml(r.text).slice(0, 2600));
      break;
    }
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

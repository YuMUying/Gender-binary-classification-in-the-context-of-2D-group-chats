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
  for (const p of ['/guide/choice_install', '/guide/introduction']) {
    const r = await getText('https://luckylillia.com' + p);
    console.log(`\n########## ${p} (status=${r.status}) ##########`);
    if (r.ok) console.log(stripHtml(r.text).slice(0, 3000));
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

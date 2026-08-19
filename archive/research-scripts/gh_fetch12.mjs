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
async function api(p) {
  const r = await fetch('https://api.github.com' + p, { headers: { 'User-Agent': 'research' } });
  return r.ok ? r.json() : null;
}

async function main() {
  for (const u of [
    'https://milky.ntqqrev.org/struct/Event',
    'https://milky.ntqqrev.org/struct/IncomingSegment',
    'https://milky.ntqqrev.org/struct/GroupEntity',
    'https://milky.ntqqrev.org/struct/GroupMemberEntity',
  ]) {
    const r = await getText(u);
    console.log(`\n########## ${u} (status=${r.status}) ##########`);
    if (r.ok) console.log(stripHtml(r.text).slice(0, 2600));
  }
  const c = await api('/repos/LagrangeDev/acidify/contents/acidify-docs/content');
  console.log('\n== acidify-docs/content ==');
  if (c) console.log(c.map(x => `${x.type} ${x.path}`).join('\n'));
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

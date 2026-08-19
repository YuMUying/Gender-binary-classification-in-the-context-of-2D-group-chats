async function getText(u) {
  try {
    const r = await fetch(u, { headers: { 'User-Agent': 'Mozilla/5.0 research' } });
    return { ok: r.ok, status: r.status, text: r.ok ? await r.text() : null };
  } catch (e) { return { ok: false, status: 'ERR', text: String(e.message) }; }
}

async function main() {
  const r = await getText('https://raw.githubusercontent.com/NapNeko/NapCat-Docker/main/README.md');
  console.log(`== NapCat-Docker README status=${r.status} ==`);
  if (r.ok) console.log(r.text.split('\n').slice(0, 100).join('\n'));
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

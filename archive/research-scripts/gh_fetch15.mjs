async function raw(p, tries = 4) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch('https://raw.githubusercontent.com/LagrangeDev/acidify/main/' + p, { headers: { 'User-Agent': 'research' } });
      if (r.ok) return await r.text();
      if (r.status === 404) return null;
    } catch (e) { /* retry */ }
    await new Promise(res => setTimeout(res, 1500 * (i + 1)));
  }
  return null;
}

async function main() {
  for (const p of ['acidify-docs/content/docs/yogurt/start.mdx', 'acidify-docs/content/docs/yogurt/configuration.mdx']) {
    const t = await raw(p);
    console.log(`\n########## ${p} ##########`);
    console.log(t ? t.split('\n').slice(0, 140).join('\n') : '(fetch failed)');
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

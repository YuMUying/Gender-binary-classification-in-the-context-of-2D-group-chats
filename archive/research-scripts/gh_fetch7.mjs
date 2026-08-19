import { writeFile } from 'node:fs/promises';
const UA = { headers: { 'User-Agent': 'Mozilla/5.0 research' } };
async function getBuf(u) {
  try {
    const r = await fetch(u, UA);
    if (!r.ok) return { ok: false, status: r.status, len: 0 };
    const b = Buffer.from(await r.arrayBuffer());
    return { ok: true, status: r.status, len: b.length, b };
  } catch (e) { return { ok: false, status: 'ERR', len: 0, err: String(e.message) }; }
}
async function api(p) {
  const r = await fetch('https://api.github.com' + p, { headers: { 'User-Agent': 'research', 'Accept': 'application/vnd.github+json' } });
  return r.ok ? r.json() : null;
}

async function main() {
  const urls = [
    'https://gitcode.com/gh_mirrors/op/OpenShamrock/-/archive/master/OpenShamrock-master.zip',
    'https://gitcode.com/gh_mirrors/op/OpenShamrock/repository/archive.zip?ref=master',
    'https://gitcode.com/gh_mirrors/op/OpenShamrock/repository/archive/master.zip',
  ];
  for (const u of urls) {
    const r = await getBuf(u);
    console.log(`${u} -> ${r.ok ? 'OK len=' + r.len : 'FAIL status=' + r.status + (r.err ? ' ' + r.err : '')}`);
    if (r.ok) {
      await writeFile('G:/Deepseek/DeepSeek_WorkPlace/shamrock-src.zip', r.b);
      console.log('saved to shamrock-src.zip');
      break;
    }
  }

  // GitHub 上找 Shamrock 下载/镜像仓库
  for (const q of ['Shamrock+download', 'Shamrock+release', 'OpenShamrock+release']) {
    const j = await api(`/search/repositories?q=${q}&per_page=8`);
    console.log(`\n== search ${q} ==`);
    if (j) for (const it of j.items) {
      console.log(`${it.full_name} | stars=${it.stargazers_count} | pushed=${String(it.pushed_at).slice(0,10)} | ${(it.description || '').slice(0,70)}`);
    }
  }
}

main().catch(e => { console.error('FATAL', e.message); process.exit(1); });

// 通过 Node fetch 抓取 GitHub 关键信息（直连，不走系统代理）
const UA = { headers: { 'User-Agent': 'research-script', 'Accept': 'application/vnd.github+json' } };

async function rawText(owner, repo, branch, path) {
  for (const b of branch ? [branch] : ['main', 'master']) {
    const u = `https://raw.githubusercontent.com/${owner}/${repo}/${b}/${path}`;
    try {
      const r = await fetch(u, UA);
      if (r.status === 200) return { u, t: await r.text() };
    } catch (e) { /* try next */ }
  }
  return null;
}

async function api(p) {
  const r = await fetch('https://api.github.com' + p, UA);
  if (!r.ok) throw new Error(`${p} -> ${r.status}`);
  return r.json();
}

const HEAD = 90;

async function main() {
  // 1. OpenShamrock README
  const sham = await rawText('whitechi73', 'OpenShamrock', null, 'README.md');
  console.log(`\n########## OpenShamrock README (${sham ? sham.u : 'NOT FOUND'}) ##########`);
  if (sham) console.log(sham.t.split('\n').slice(0, HEAD).join('\n'));

  // 2. NapCat-Termux README
  const nct = await rawText('NapNeko', 'NapCat-Termux', 'main', 'README.md');
  console.log(`\n########## NapCat-Termux README (${nct ? nct.u : 'NOT FOUND'}) ##########`);
  if (nct) console.log(nct.t.split('\n').slice(0, HEAD).join('\n'));

  // 3. acidify README
  const acd = await rawText('LagrangeDev', 'acidify', null, 'README.md');
  console.log(`\n########## acidify README (${acd ? acd.u : 'NOT FOUND'}) ##########`);
  if (acd) console.log(acd.t.split('\n').slice(0, 50).join('\n'));

  // 4. 仓库活跃度
  for (const r of ['whitechi73/OpenShamrock', 'NapNeko/NapCat-Termux', 'LagrangeDev/acidify', 'LagrangeDev/Lagrange.Core', 'mamoe/mirai', 'icqqjs/icqq']) {
    try {
      const j = await api(`/repos/${r}`);
      console.log(`REPO ${r} | stars=${j.stargazers_count} archived=${j.archived} pushed=${String(j.pushed_at).slice(0,10)} default_branch=${j.default_branch}`);
    } catch (e) { console.log(`REPO ${r} FAILED ${e.message}`); }
  }

  // 5. OpenShamrock 最新 release
  try {
    const rel = await api('/repos/whitechi73/OpenShamrock/releases/latest');
    console.log(`\n########## OpenShamrock latest release ##########`);
    console.log(`tag=${rel.tag_name}  name=${rel.name}  published=${String(rel.published_at).slice(0,10)}`);
    console.log((rel.body || '(no body)').split('\n').slice(0, 40).join('\n'));
  } catch (e) { console.log(`RELEASE FAILED ${e.message}`); }

  // 6. acidify 最新 release
  try {
    const rel = await api('/repos/LagrangeDev/acidify/releases/latest');
    console.log(`\n########## acidify latest release ##########`);
    console.log(`tag=${rel.tag_name}  name=${rel.name}  published=${String(rel.published_at).slice(0,10)}`);
    console.log((rel.body || '(no body)').split('\n').slice(0, 20).join('\n'));
  } catch (e) { console.log(`ACIDIFY RELEASE FAILED ${e.message}`); }
}

main().catch(e => { console.error('FATAL', e); process.exit(1); });

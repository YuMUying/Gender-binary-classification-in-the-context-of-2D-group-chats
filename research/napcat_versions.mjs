// 查 NapCat 最新 releases（可能有比 v4.18.19 更新的版本）
const UA = { headers: { 'User-Agent': 'research' } };
const rels = await (await fetch('https://api.github.com/repos/NapNeko/NapCatQQ/releases?per_page=5', UA)).json();
for (const r of rels) {
  const body = r.body ?? '';
  const vers = [...new Set([...body.matchAll(/9\.9\.\d+[-\d.]*/g)].map((m) => m[0]))];
  console.log(`${r.tag_name} (${String(r.published_at).slice(0, 10)})  prerelease=${r.prerelease}  QQ版本: ${vers.join(', ') || '-'}`);
}

// 用 Node 下载 torch 2.5.1+cu121 Windows wheel（官方源，带进度，断点不重试但显示速率）
import { writeFile } from 'node:fs/promises';

const URL = 'https://download.pytorch.org/whl/cu121/torch-2.5.1%2Bcu121-cp310-cp310-win_amd64.whl';
const OUT = 'C:/Users/Lenovo/Downloads/qq-bot-deploy/torch-2.5.1+cu121-cp310-cp310-win_amd64.whl';
console.log('目标:', URL);

for (let attempt = 1; attempt <= 3; attempt++) {
  try {
    const r = await fetch(URL, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      signal: AbortSignal.timeout(3600000),
    });
    if (!r.ok) { console.log('HTTP', r.status); continue; }
    const total = Number(r.headers.get('content-length') ?? 0);
    const reader = r.body.getReader();
    const chunks = [];
    let got = 0;
    let lastLog = Date.now();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      got += value.length;
      if (Date.now() - lastLog > 15000) {
        lastLog = Date.now();
        console.log(`进度 ${(got / 1048576).toFixed(0)}MB${total ? ' / ' + (total / 1048576).toFixed(0) + 'MB' : ''}`);
      }
    }
    const buf = Buffer.concat(chunks);
    await writeFile(OUT, buf);
    console.log('完成:', OUT, (buf.length / 1048576).toFixed(0), 'MB');
    process.exit(0);
  } catch (e) {
    console.log(`尝试${attempt}失败: ${e.message}`);
  }
}
process.exit(1);

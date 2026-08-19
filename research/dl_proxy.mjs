// 通过本地代理 (127.0.0.1:7890) 的 CONNECT 隧道下载文件（处理 gzip/chunked/重定向）
import { writeFile } from 'node:fs/promises';
import { existsSync, statSync, mkdirSync } from 'node:fs';
import net from 'node:net';
import tls from 'node:tls';
import zlib from 'node:zlib';

const PROXY = { host: '127.0.0.1', port: 7890 };
const DIR = 'C:/Users/Lenovo/Downloads/qq-bot-deploy';
const OUT = DIR + '/NapCat.Shell.Windows.Node.zip';
mkdirSync(DIR, { recursive: true });
if (existsSync(OUT) && statSync(OUT).size > 100 * 1048576) { console.log('已存在:', OUT); process.exit(0); }

function rawGet(url) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const isHttps = u.protocol === 'https:';
    const socket = net.connect(PROXY.port, PROXY.host, () => {
      socket.write(`CONNECT ${u.hostname}:${u.port || (isHttps ? 443 : 80)} HTTP/1.1\r\nHost: ${u.hostname}\r\n\r\n`);
    });
    socket.setTimeout(120000, () => socket.destroy(new Error('timeout')));
    let buf = Buffer.alloc(0);
    const onData = (d) => {
      buf = Buffer.concat([buf, d]);
      const idx = buf.indexOf('\r\n\r\n');
      if (idx < 0) return;
      const head = buf.slice(0, idx).toString();
      const status = head.split('\r\n')[0];
      if (!/ 200 /.test(status)) { socket.destroy(new Error('CONNECT failed: ' + status)); return; }
      const rest = buf.slice(idx + 4);
      socket.removeListener('data', onData);
      const onUp = () => {
        const req = `GET ${u.pathname}${u.search} HTTP/1.1\r\nHost: ${u.hostname}\r\nUser-Agent: Mozilla/5.0 research\r\nAccept: */*\r\nAccept-Encoding: gzip\r\nConnection: close\r\n\r\n`;
        stream.write(req);
        let body = Buffer.alloc(0);
        stream.on('data', (d2) => (body = Buffer.concat([body, d2])));
        stream.on('end', () => resolve(body));
        stream.on('error', reject);
      };
      let stream;
      if (isHttps) {
        stream = tls.connect({ socket, servername: u.hostname, rejectUnauthorized: false }, onUp);
        stream.on('error', reject);
      } else {
        stream = socket;
        onUp();
      }
      if (rest.length) socket.unshift(rest);
    };
    socket.on('data', onData);
    socket.on('error', reject);
  });
}

function dechunk(buf) {
  const out = [];
  let i = 0;
  while (i < buf.length) {
    const lineEnd = buf.indexOf('\r\n', i);
    if (lineEnd < 0) break;
    const size = parseInt(buf.slice(i, lineEnd).toString(), 16);
    if (!size) break;
    out.push(buf.slice(lineEnd + 2, lineEnd + 2 + size));
    i = lineEnd + 2 + size + 2;
  }
  return Buffer.concat(out);
}

async function proxyGet(url, redirects = 6) {
  const raw = await rawGet(url);
  const idx = raw.indexOf('\r\n\r\n');
  const head = raw.slice(0, idx).toString('utf8');
  let body = raw.slice(idx + 4);
  const m = head.match(/HTTP\/1\.1 (\d+)/);
  const status = m ? Number(m[1]) : 0;
  if ([301, 302, 303, 307, 308].includes(status) && redirects > 0) {
    const loc = head.match(/location:\s*([^\r\n]+)/i);
    if (loc) { console.log('  重定向 →', loc[1].slice(0, 90)); return proxyGet(loc[1].trim(), redirects - 1); }
  }
  if (/transfer-encoding:\s*chunked/i.test(head)) body = dechunk(body);
  if (/content-encoding:\s*gzip/i.test(head)) body = zlib.gunzipSync(body);
  return body;
}

console.log('通过代理获取 release 信息...');
const relJson = await proxyGet('https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest');
const rel = JSON.parse(relJson.toString('utf8'));
const asset = rel.assets.find((a) => a.name.includes('Shell.Windows.Node'));
if (!asset) { console.log('资产未找到'); process.exit(1); }
console.log('目标:', asset.name, Math.round(asset.size / 1048576), 'MB');
console.log('下载中（112MB，可能需数分钟）...');
const data = await proxyGet(asset.browser_download_url);
await writeFile(OUT, data);
console.log('完成:', OUT, Math.round(data.length / 1048576), 'MB');

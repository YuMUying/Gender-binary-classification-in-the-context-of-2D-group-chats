// 代理抓取 GetGroupMsgHistory.ts
import net from 'node:net';
import tls from 'node:tls';
import zlib from 'node:zlib';

function rawGet(url) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const socket = net.connect(7890, '127.0.0.1', () => {
      socket.write(`CONNECT ${u.hostname}:443 HTTP/1.1\r\nHost: ${u.hostname}\r\n\r\n`);
    });
    socket.setTimeout(60000, () => socket.destroy(new Error('timeout')));
    let buf = Buffer.alloc(0);
    const onData = (d) => {
      buf = Buffer.concat([buf, d]);
      const idx = buf.indexOf('\r\n\r\n');
      if (idx < 0) return;
      const head = buf.slice(0, idx).toString();
      if (!/ 200 /.test(head.split('\r\n')[0])) { socket.destroy(); return; }
      const rest = buf.slice(idx + 4);
      socket.removeListener('data', onData);
      const stream = tls.connect({ socket, servername: u.hostname, rejectUnauthorized: false }, () => {
        stream.write(`GET ${u.pathname} HTTP/1.1\r\nHost: ${u.hostname}\r\nUser-Agent: Mozilla/5.0 research\r\nAccept-Encoding: gzip\r\nConnection: close\r\n\r\n`);
        let body = Buffer.alloc(0);
        stream.on('data', (d2) => (body = Buffer.concat([body, d2])));
        stream.on('end', () => resolve(body));
        stream.on('error', reject);
      });
      stream.on('error', reject);
      if (rest.length) socket.unshift(rest);
    };
    socket.on('data', onData);
    socket.on('error', reject);
  });
}
const raw = await rawGet('https://raw.githubusercontent.com/NapNeko/NapCatQQ/main/packages/napcat-onebot/action/go-cqhttp/GetGroupMsgHistory.ts');
let body = raw.slice(raw.indexOf('\r\n\r\n') + 4);
if (/gzip/i.test(raw.slice(0, raw.indexOf('\r\n\r\n')).toString())) body = zlib.gunzipSync(body);
console.log(body.toString('utf8'));

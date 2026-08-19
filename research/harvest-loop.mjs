/**
 * harvest-loop.mjs — 边滚动 QQ 加载历史边收割入库
 * 每轮：滚轮 200 次(带停顿) → 收割(bulk-collect) → 探测增长；增长停滞即结束
 * 用法：node research/harvest-loop.mjs --group 826904606 --rounds 30
 */
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const args = process.argv.slice(2);
const arg = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
const GROUP = arg('--group') ?? '826904606';
const MAX_ROUNDS = Number(arg('--rounds') ?? 30);
const HTTP = 'http://127.0.0.1:3000';

async function storeStats() {
  const r = await fetch(`${HTTP}/get_group_msg_history`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_id: GROUP, count: 2000 }),
  });
  const j = await r.json();
  const msgs = j.data?.messages ?? [];
  const times = msgs.map((m) => m.time ?? 0).filter((t) => t > 0);
  return { n: msgs.length, min: times.length ? Math.min(...times) : 0, max: times.length ? Math.max(...times) : 0 };
}

const SCROLL_PS = `
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W4 {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public static System.Collections.Generic.List<IntPtr> Find(int[] pids) {
    var list = new System.Collections.Generic.List<IntPtr>();
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      uint pid; GetWindowThreadProcessId(h, out pid);
      var c = new StringBuilder(256); GetClassName(h, c, 256);
      if (c.ToString() == "Chrome_WidgetWin_0") {
        foreach (var p in pids) { if (pid == (uint)p) { list.Add(h); break; } }
      }
      return true;
    }, IntPtr.Zero);
    return list;
  }
}
"@
\$pids = @(Get-Process QQ -ErrorAction SilentlyContinue | ForEach-Object { \$_.Id })
\$wins = [W4]::Find([int[]]\$pids)
\$big = [IntPtr]::Zero
\$bigArea = 0
foreach (\$h in \$wins) {
  \$r = New-Object W4+RECT
  [W4]::GetWindowRect(\$h, [ref]\$r) | Out-Null
  \$area = (\$r.Right - \$r.Left) * (\$r.Bottom - \$r.Top)
  if (\$area -gt \$bigArea) { \$bigArea = \$area; \$big = \$h; \$br = \$r }
}
if (\$big -eq [IntPtr]::Zero) { Write-Output 'NO_WIN'; exit 1 }
[W4]::ShowWindow(\$big, 9) | Out-Null
[W4]::SetForegroundWindow(\$big) | Out-Null
\$x = [int](\$br.Left + (\$br.Right - \$br.Left) * 0.75)
\$y = [int](\$br.Top + (\$br.Bottom - \$br.Top) * 0.5)
\$lp = [IntPtr]((\$y -shl 16) -bor (\$x -band 0xFFFF))
for (\$i = 0; \$i -lt 200; \$i++) {
  [W4]::PostMessage(\$big, 0x020A, [IntPtr]0x00780000, \$lp) | Out-Null
  if (\$i % 30 -eq 29) { Start-Sleep -Milliseconds 2500 }
}
Write-Output 'SCROLLED'
`;

function scroll() {
  return new Promise((resolve) => {
    const p = spawn('powershell', ['-ExecutionPolicy', 'Bypass', '-Command', SCROLL_PS]);
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.stderr.on('data', () => {});
    p.on('close', () => resolve(out.trim()));
  });
}

function harvest() {
  return new Promise((resolve) => {
    const p = spawn('node', ['scripts/bulk-collect.js', '--group', GROUP, '--no-media'], {
      cwd: 'G:/Deepseek/DeepSeek_WorkPlace/qq-gender-dataset',
    });
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.stderr.on('data', () => {});
    p.on('close', () => {
      const m = out.match(/新增 (\d+)/g) ?? [];
      resolve(m.join(' '));
    });
  });
}

const t0 = Date.now();
let lastN = 0;
for (let round = 1; round <= MAX_ROUNDS; round++) {
  const st0 = await storeStats();
  console.log(`\n[轮次 ${round}] 滚动前: 内存库 ${st0.n} 条, 最旧 ${new Date(st0.min * 1000).toLocaleString('zh-CN')}`);
  const s = await scroll();
  if (s !== 'SCROLLED') { console.log('窗口未找到，停止'); break; }
  await sleep(5000);
  const st1 = await storeStats();
  console.log(`[轮次 ${round}] 滚动后: 内存库 ${st1.n} 条, 最旧 ${new Date(st1.min * 1000).toLocaleString('zh-CN')}`);
  const hv = await harvest();
  console.log(`[轮次 ${round}] 收割: ${hv}`);
  if (st1.n <= lastN + 20 && round > 1) {
    console.log(`[轮次 ${round}] 内存库几乎不增长（${lastN} → ${st1.n}），已挖到底部，结束`);
    break;
  }
  lastN = st1.n;
}
console.log(`\n总耗时 ${Math.round((Date.now() - t0) / 60000)} 分钟`);

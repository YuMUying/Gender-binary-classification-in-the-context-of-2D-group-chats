// 精准滚动：点击消息列表区域获取焦点，再高频滚轮
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const HTTP = 'http://127.0.0.1:3000';
async function probe() {
  const r = await fetch(`${HTTP}/get_group_msg_history`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_id: 826904606, count: 1000 }),
  });
  const j = await r.json();
  const msgs = j.data?.messages ?? [];
  const times = msgs.map((m) => m.time ?? 0);
  return { n: msgs.length, min: times.length ? Math.min(...times) : 0 };
}

const ps = `
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W3 {
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
\$wins = [W3]::Find([int[]]\$pids)
\$big = [IntPtr]::Zero
\$bigArea = 0
foreach (\$h in \$wins) {
  \$r = New-Object W3+RECT
  [W3]::GetWindowRect(\$h, [ref]\$r) | Out-Null
  \$area = (\$r.Right - \$r.Left) * (\$r.Bottom - \$r.Top)
  if (\$area -gt \$bigArea) { \$bigArea = \$area; \$big = \$h; \$br = \$r }
}
if (\$big -eq [IntPtr]::Zero) { Write-Output 'NO_WIN'; exit 1 }
[W3]::ShowWindow(\$big, 9) | Out-Null
[W3]::SetForegroundWindow(\$big) | Out-Null
# 消息列表大约在窗口右侧 60%~95% 宽度、10%~90% 高度
\$x = [int](\$br.Left + (\$br.Right - \$br.Left) * 0.75)
\$y = [int](\$br.Top + (\$br.Bottom - \$br.Top) * 0.5)
\$lp = [IntPtr]((\$y -shl 16) -bor (\$x -band 0xFFFF))
# 点击聚焦（左键按下+抬起）
[W3]::PostMessage(\$big, 0x0201, [IntPtr]1, \$lp) | Out-Null  # WM_LBUTTONDOWN
Start-Sleep -Milliseconds 100
[W3]::PostMessage(\$big, 0x0202, [IntPtr]0, \$lp) | Out-Null  # WM_LBUTTONUP
Start-Sleep -Milliseconds 300
# 大量向上滚动
for (\$i = 0; \$i -lt 200; \$i++) {
  [W3]::PostMessage(\$big, 0x020A, [IntPtr]0x00780000, \$lp) | Out-Null
  if (\$i % 40 -eq 39) { Start-Sleep -Milliseconds 2000 }
}
Write-Output ("DONE rect=" + \$br.Left + "," + \$br.Top + "," + \$br.Right + "," + \$br.Bottom)
`;

const p = spawn('powershell', ['-ExecutionPolicy', 'Bypass', '-Command', ps]);
let out = '';
p.stdout.on('data', (d) => (out += d));
p.stderr.on('data', () => {});
p.on('close', async () => {
  console.log(out.trim());
  await sleep(8000);
  const cur = await probe();
  console.log('滚动+点击后:', cur.n, '条, 最旧', new Date(cur.min * 1000).toLocaleString('zh-CN'));
});

# show-qq-window.ps1 — 显示被 NapCat 隐藏启动的 QQ 主窗口
# 用法：右键"使用 PowerShell 运行"，或 powershell -ExecutionPolicy Bypass -File show-qq-window.ps1
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class QQShow {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int X, int Y, int cx, int cy, uint flags);
  public static IntPtr FindQQMain(int[] pids) {
    IntPtr found = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      uint pid; GetWindowThreadProcessId(h, out pid);
      var c = new StringBuilder(256); GetClassName(h, c, 256);
      if (c.ToString() == "Chrome_WidgetWin_0") {
        foreach (var p in pids) { if (pid == (uint)p) { found = h; return false; } }
      }
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@
$pids = @(Get-Process QQ -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
if ($pids.Count -eq 0) { Write-Host '没有运行中的 QQ 进程（请先用 NapCat 启动器启动 QQ）'; exit 1 }
$hwnd = [QQShow]::FindQQMain([int[]]$pids)
if ($hwnd -eq [IntPtr]::Zero) { Write-Host '未找到 QQ 主窗口'; exit 1 }
[QQShow]::ShowWindow($hwnd, 5) | Out-Null
[QQShow]::SetWindowPos($hwnd, [IntPtr]0, 100, 100, 1100, 760, 0x0040) | Out-Null
[QQShow]::SetForegroundWindow($hwnd) | Out-Null
Write-Host "QQ 窗口已显示 (hwnd=$hwnd)"

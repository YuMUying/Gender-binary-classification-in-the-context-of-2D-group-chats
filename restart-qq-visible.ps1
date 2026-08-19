# restart-qq-visible.ps1 — Restart QQ (with NapCat hook) and show its window ASAP to avoid black screen
$ErrorActionPreference = 'Continue'

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class QQRestart {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  public static IntPtr FindMain(int[] pids) {
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

Write-Host '1) Killing QQ / BootMain ...'
Get-Process QQ, QQEX, NapCatWinBootMain -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$env:NAPCAT_PATCH_PACKAGE = 'D:\Program Files (x86)\Tencent\NapCat\napcat\qqnt.json'
$env:NAPCAT_LOAD_PATH = 'D:\Program Files (x86)\Tencent\NapCat\napcat\loadNapCat.js'
$env:NAPCAT_INJECT_PATH = 'D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootHook.dll'
$env:NAPCAT_LAUNCHER_PATH = 'D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootMain.exe'
$env:NAPCAT_MAIN_PATH = 'D:/Program Files (x86)/Tencent/NapCat/napcat/napcat.mjs'

Write-Host '2) Starting BootMain ...'
Start-Process -FilePath 'D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootMain.exe' `
  -ArgumentList '"D:\Program Files (x86)\Tencent\QQ.exe" "D:\Program Files (x86)\Tencent\NapCat\napcat\NapCatWinBootHook.dll"' `
  -WorkingDirectory 'D:\Program Files (x86)\Tencent\NapCat\napcat'

Write-Host '3) Polling for QQ main window and showing it immediately ...'
$shown = $false
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 300
  $pids = @(Get-Process QQ -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
  if ($pids.Count -gt 0) {
    $h = [QQRestart]::FindMain([int[]]$pids)
    if ($h -ne [IntPtr]::Zero) {
      [QQRestart]::ShowWindow($h, 5) | Out-Null
      [QQRestart]::SetForegroundWindow($h) | Out-Null
      Write-Host ("Window shown (hwnd=" + $h + ", poll " + $i + ")")
      $shown = $true
      break
    }
  }
}
if (-not $shown) { Write-Host 'QQ main window not captured yet (run show-qq-window.ps1 later)' }

# qq-shot.ps1 - bring QQ window to front and screenshot it
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class W {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public static IntPtr Find(int[] pids) {
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
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$pids = @(Get-Process QQ -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$h = [W]::Find([int[]]$pids)
if ($h -eq [IntPtr]::Zero) { Write-Output 'NO_WIN'; exit 1 }
[W]::ShowWindow($h, 9) | Out-Null   # SW_RESTORE
Start-Sleep -Milliseconds 600
[W]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800
$r = New-Object W+RECT
[W]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output "hwnd=$h rect=$($r.Left),$($r.Top),$($r.Right),$($r.Bottom)"
Add-Type -AssemblyName System.Drawing
$w = $r.Right - $r.Left; $ht = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
$bmp.Save('G:\Deepseek\DeepSeek_WorkPlace\qq-gender-dataset\research\qq_window.png', [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output "SHOT_SAVED $w x $ht"

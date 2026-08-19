# tray-click.ps1 - click tray icons to find and summon the QQ main window
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Tray {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string title);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
  public struct RECT { public int Left, Top, Right, Bottom; }
  public const uint TB_BUTTONCOUNT = 0x0418;
  public const uint TB_GETITEMRECT = 0x041D;
  public const uint MOUSEEVENTF_LEFTDOWN = 0x02;
  public const uint MOUSEEVENTF_LEFTUP = 0x04;

  public static IntPtr FindToolbar() {
    IntPtr tray = FindWindowEx(IntPtr.Zero, IntPtr.Zero, "Shell_TrayWnd", null);
    if (tray == IntPtr.Zero) return IntPtr.Zero;
    IntPtr notify = FindWindowEx(tray, IntPtr.Zero, "TrayNotifyWnd", null);
    if (notify == IntPtr.Zero) return IntPtr.Zero;
    IntPtr pager = FindWindowEx(notify, IntPtr.Zero, "SysPager", null);
    IntPtr tb = IntPtr.Zero;
    if (pager != IntPtr.Zero) tb = FindWindowEx(pager, IntPtr.Zero, "ToolbarWindow32", null);
    if (tb == IntPtr.Zero) tb = FindWindowEx(notify, IntPtr.Zero, "ToolbarWindow32", null);
    return tb;
  }

  public static int ButtonCount(IntPtr tb) {
    return (int)SendMessage(tb, TB_BUTTONCOUNT, IntPtr.Zero, IntPtr.Zero);
  }

  public static bool ItemRect(IntPtr tb, int index, out RECT r) {
    r = new RECT();
    IntPtr rc = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(RECT)));
    IntPtr res = SendMessage(tb, TB_GETITEMRECT, (IntPtr)index, rc);
    if (res != IntPtr.Zero) r = (RECT)Marshal.PtrToStructure(rc, typeof(RECT));
    Marshal.FreeHGlobal(rc);
    return res != IntPtr.Zero;
  }

  public static void Click(int x, int y) {
    mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
    System.Threading.Thread.Sleep(80);
    mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
  }
}
"@

# QQ windows existing now
function Get-QQWins {
  $found = New-Object System.Collections.Generic.List[string]
  $qqPids = @(Get-Process QQ -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
  $all = New-Object System.Collections.Generic.List[string]
  # reuse scan via simple approach: use WMI? fallback: skip - we detect via Get-Process MainWindowHandle
  foreach ($p in Get-Process QQ -ErrorAction SilentlyContinue) {
    if ($p.MainWindowHandle -ne 0) { $found.Add($p.MainWindowHandle) }
  }
  return $found
}

$before = @(Get-QQWins)
Write-Output ("QQ MainWindowHandle before: " + ($before -join ','))
$tb = [Tray]::FindToolbar()
if ($tb -eq [IntPtr]::Zero) { Write-Output 'NO_TRAY_TOOLBAR'; exit 1 }
$tbRect = New-Object Tray+RECT
[Tray]::GetWindowRect($tb, [ref]$tbRect) | Out-Null
$n = [Tray]::ButtonCount($tb)
Write-Output "托盘按钮数: $n"

for ($i = 0; $i -lt $n; $i++) {
  $r = New-Object Tray+RECT
  if ([Tray]::ItemRect($tb, $i, [ref]$r)) {
    $cx = $tbRect.Left + ($r.Left + $r.Right) / 2
    $cy = $tbRect.Top + ($r.Top + $r.Bottom) / 2
    Write-Output ("点击按钮 $i @ ($cx, $cy)")
    [Tray]::Click([int]$cx, [int]$cy)
    Start-Sleep -Milliseconds 1800
    $after = @(Get-QQWins)
    if ($after.Count -gt 0) {
      Write-Output "FOUND_QQ_WINDOW: $($after -join ',')"
      # 尝试恢复显示
      $h = [IntPtr]$after[0]
      [Tray]::ShowWindow($h, 9) | Out-Null
      [Tray]::SetForegroundWindow($h) | Out-Null
      Write-Output 'SHOWN'
      exit 0
    }
    # 关闭可能弹出的无关菜单
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait('{ESC}')
    Start-Sleep -Milliseconds 400
  }
}
Write-Output 'NO_QQ_WINDOW_FOUND'

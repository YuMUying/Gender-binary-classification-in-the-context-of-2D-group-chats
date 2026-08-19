# qq-wins.ps1 - list ALL windows of QQ processes
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class WL {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  public static void List(int[] pids, System.Collections.Generic.List<string> outList) {
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      uint pid; GetWindowThreadProcessId(h, out pid);
      foreach (var p in pids) {
        if (pid == (uint)p) {
          var c = new StringBuilder(256); GetClassName(h, c, 256);
          var t = new StringBuilder(256); GetWindowText(h, t, 256);
          outList.Add(String.Format("pid={0} hwnd={1} vis={2} class={3} title={4}", pid, h, IsWindowVisible(h), c, t));
          break;
        }
      }
      return true;
    }, IntPtr.Zero);
  }
}
"@
$pids = @(Get-Process QQ -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
Write-Output ("QQ pids: " + ($pids -join ','))
$out = New-Object System.Collections.Generic.List[string]
[WL]::List([int[]]$pids, $out)
if ($out.Count -eq 0) { Write-Output 'NO_WINDOWS' } else { $out | ForEach-Object { Write-Output $_ } }

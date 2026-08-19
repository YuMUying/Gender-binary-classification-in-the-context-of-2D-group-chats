# scan-wins.ps1 - scan ALL top-level windows for Chrome_WidgetWin_0 / Electron classes
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class SW {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int max);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  public static void List(System.Collections.Generic.List<string> outList) {
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      var c = new StringBuilder(256); GetClassName(h, c, 256);
      string cls = c.ToString();
      if (cls.Contains("Chrome_WidgetWin") || cls.Contains("Electron")) {
        uint pid; GetWindowThreadProcessId(h, out pid);
        var t = new StringBuilder(256); GetWindowText(h, t, 256);
        outList.Add(String.Format("pid={0} hwnd={1} vis={2} class={3} title={4}", pid, h, IsWindowVisible(h), cls, t));
      }
      return true;
    }, IntPtr.Zero);
  }
}
"@
$out = New-Object System.Collections.Generic.List[string]
[SW]::List($out)
if ($out.Count -eq 0) { Write-Output 'NO_CHROME_WINDOWS_ANYWHERE' } else { $out | ForEach-Object { Write-Output $_ } }
Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object Id, ProcessName, MainWindowTitle | Format-Table -AutoSize

Add-Type -Namespace W2 -Name N2 -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
public struct RECT { public int L; public int T; public int R; public int B; }
'@
$out = @()
$cb = {
  param($h, $l)
  if ([W2.N2]::IsWindowVisible($h)) {
    $len = [W2.N2]::GetWindowTextLength($h)
    if ($len -gt 0) {
      $sb = New-Object System.Text.StringBuilder ($len + 2)
      [W2.N2]::GetWindowText($h, $sb, $sb.Capacity) | Out-Null
      $r = New-Object W2.N2+RECT
      [W2.N2]::GetWindowRect($h, [ref]$r) | Out-Null
      $pid2 = 0
      [W2.N2]::GetWindowThreadProcessId($h, [ref]$pid2) | Out-Null
      if ($r.R -gt 0 -and $r.B -gt 0 -and $r.L -lt 3840 -and $r.T -lt 2160) {
        Write-Output ("hwnd={0} pid={1} rect=({2},{3},{4},{5}) title={6}" -f $h, $pid2, $r.L, $r.T, $r.R, $r.B, $sb.ToString())
      }
    }
  }
  return $true
}
[W2.N2]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null

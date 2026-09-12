param([int]$ProcId = 0)
Add-Type -Namespace C -Name N -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
public struct RECT { public int L; public int T; public int R; public int B; }
'@
[C.N]::SetProcessDPIAware() | Out-Null
$p = Get-Process -Id $ProcId
$h = $p.MainWindowHandle
$r = New-Object C.N+RECT
[C.N]::GetWindowRect($h, [ref]$r) | Out-Null
Write-Output ("hwnd=" + $h + " visible=" + [C.N]::IsWindowVisible($h) + " iconic=" + [C.N]::IsIconic($h) + " rect=" + $r.L + "," + $r.T + "," + $r.R + "," + $r.B + " title=" + $p.MainWindowTitle)

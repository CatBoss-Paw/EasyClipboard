param(
  [int]$ProcId = 0,
  [int]$X = 0,
  [int]$Y = 0,
  [int]$W = 0,
  [int]$HT = 0,
  [int]$Cmd = 9
)
Add-Type -Namespace W -Name N -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int w, int ht, uint f);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
'@
[W.N]::SetProcessDPIAware() | Out-Null
$proc = Get-Process -Id $ProcId
$hwnd = $proc.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "no-main-window"; exit 1 }
if ([W.N]::IsIconic($hwnd)) {
  [W.N]::ShowWindow($hwnd, 9) | Out-Null
  Start-Sleep -Milliseconds 400
}
if ($Cmd -ne 9) {
  [W.N]::ShowWindow($hwnd, $Cmd) | Out-Null
  Start-Sleep -Milliseconds 300
}
$flags = 0x0040
if ($W -le 0 -and $HT -le 0) { $flags = $flags -bor 0x0001 }
[W.N]::SetWindowPos($hwnd, [IntPtr]::Zero, $X, $Y, $W, $HT, $flags) | Out-Null
Write-Output "placed pid=$ProcId hwnd=$hwnd at $X,$Y size=$W x $HT cmd=$Cmd"

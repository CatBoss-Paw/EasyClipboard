param(
  [string]$Folder = "",
  [int]$X = 958,
  [int]$Y = 1263,
  [int]$W = 1472,
  [int]$HT = 597
)
Add-Type -Namespace E -Name N -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int w, int ht, uint f);
'@
[E.N]::SetProcessDPIAware() | Out-Null
if ($Folder -ne "") {
  Start-Process explorer.exe -ArgumentList "`"$Folder`""
  Start-Sleep -Seconds 3
}
$sh = New-Object -ComObject Shell.Application
$wins = @($sh.Windows())
$best = $null
foreach ($w in $wins) {
  $u = ""
  try { $u = [string]$w.LocationURL } catch {}
  if ($u -match "demo_files") { $best = $w }
}
if ($null -eq $best) { Write-Output ("windows-found=" + $wins.Count); exit 1 }
$h = [IntPtr][long]$best.HWND
[E.N]::SetWindowPos($h, [IntPtr]::Zero, $X, $Y, $W, $HT, 0x0040) | Out-Null
Write-Output "explorer placed hwnd=$h"

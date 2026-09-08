param([string]$Title = "轻松剪贴板", [double]$LogicalX = 277, [double]$LogicalY = 25, [switch]$DragTo, [int]$ToX = 0, [int]$ToY = 0)
# 按 PID 定位窗口，依据逻辑坐标(560x480 基准)换算物理坐标点击/拖拽
Add-Type -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool GetWindowRect(System.IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, System.UIntPtr e);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
'@ -Name M -Namespace U
[U.M]::SetProcessDPIAware() | Out-Null
$p = Get-Process | Where-Object { $_.MainWindowTitle -eq $Title } | Select-Object -First 1
if (-not $p -or $p.MainWindowHandle -eq 0) { Write-Output "window-not-found"; exit 1 }
$r = New-Object U.M+RECT
[U.M]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$scale = ($r.Right - $r.Left) / 560.0
$px = [int]($r.Left + $LogicalX * $scale)
$py = [int]($r.Top + $LogicalY * $scale)
Write-Output "rect=($($r.Left),$($r.Top),$($r.Right),$($r.Bottom)) scale=$([math]::Round($scale,3)) target=($px,$py)"

if ($DragTo) {
  [U.M]::SetCursorPos($px, $py) | Out-Null
  Start-Sleep -Milliseconds 120
  [U.M]::mouse_event(2, 0, 0, 0, [System.UIntPtr]::Zero)
  Start-Sleep -Milliseconds 150
  $steps = 12
  for ($i = 1; $i -le $steps; $i++) {
    $cx = [int]($px + ($ToX - $px) * $i / $steps)
    $cy = [int]($py + ($ToY - $py) * $i / $steps)
    [U.M]::SetCursorPos($cx, $cy) | Out-Null
    [U.M]::mouse_event(1, 0, 0, 0, [System.UIntPtr]::Zero)
    Start-Sleep -Milliseconds 40
  }
  Start-Sleep -Milliseconds 250
  [U.M]::mouse_event(4, 0, 0, 0, [System.UIntPtr]::Zero)
} else {
  [U.M]::SetCursorPos($px, $py) | Out-Null
  Start-Sleep -Milliseconds 120
  [U.M]::mouse_event(2, 0, 0, 0, [System.UIntPtr]::Zero)
  Start-Sleep -Milliseconds 60
  [U.M]::mouse_event(4, 0, 0, 0, [System.UIntPtr]::Zero)
}

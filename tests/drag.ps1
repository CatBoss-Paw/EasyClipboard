param([int]$x1, [int]$y1, [int]$x2, [int]$y2)
# Simulate a real drag: press at (x1,y1), move in steps to (x2,y2), release.
Add-Type -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
'@ -Name M -Namespace U
[U.M]::SetProcessDPIAware() | Out-Null
$DOWN = 2; $UP = 4; $MOVE = 1

[U.M]::SetCursorPos($x1, $y1) | Out-Null
Start-Sleep -Milliseconds 120
[U.M]::mouse_event($DOWN, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150

$steps = 12
for ($i = 1; $i -le $steps; $i++) {
  $cx = [int]($x1 + ($x2 - $x1) * $i / $steps)
  $cy = [int]($y1 + ($y2 - $y1) * $i / $steps)
  [U.M]::SetCursorPos($cx, $cy) | Out-Null
  [U.M]::mouse_event($MOVE, 0, 0, 0, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 40
}
Start-Sleep -Milliseconds 250
[U.M]::mouse_event($UP, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 150

param(
  [string]$Action = "click",   # click | rightclick | dblclick | move | drag
  [int]$X = 0,
  [int]$Y = 0,
  [int]$X2 = 0,
  [int]$Y2 = 0,
  [int]$Steps = 24,            # drag interpolation steps
  [int]$PauseMs = 120          # pause between drag steps
)
Add-Type -Namespace M -Name A -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint data, UIntPtr extra);
[DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
[StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public MOUSEINPUT mi; public ulong pad; }
[StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr extraInfo; }
'@
[M.A]::SetProcessDPIAware() | Out-Null
$LEFT_DOWN = 0x0002; $LEFT_UP = 0x0004; $RIGHT_DOWN = 0x0008; $RIGHT_UP = 0x0010

function Press-Left { [M.A]::mouse_event($LEFT_DOWN, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60 }
function Release-Left { [M.A]::mouse_event($LEFT_UP, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60 }

switch ($Action) {
  "move" {
    [M.A]::SetCursorPos($X, $Y) | Out-Null
  }
  "click" {
    [M.A]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 90
    Press-Left; Release-Left
  }
  "dblclick" {
    [M.A]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 90
    Press-Left; Release-Left
    Start-Sleep -Milliseconds 90
    Press-Left; Release-Left
  }
  "rightclick" {
    [M.A]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 90
    [M.A]::mouse_event($RIGHT_DOWN, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
    [M.A]::mouse_event($RIGHT_UP, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 60
  }
  "drag" {
    [M.A]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 150
    Press-Left
    for ($i = 1; $i -le $Steps; $i++) {
      $nx = $X + [int](($X2 - $X) * $i / $Steps)
      $ny = $Y + [int](($Y2 - $Y) * $i / $Steps)
      [M.A]::SetCursorPos($nx, $ny) | Out-Null
      Start-Sleep -Milliseconds $PauseMs
    }
    Start-Sleep -Milliseconds 200
    Release-Left
  }
}
Write-Output ("done " + $Action + " " + $X + "," + $Y + " -> " + $X2 + "," + $Y2)

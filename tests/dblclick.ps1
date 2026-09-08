param([int]$x, [int]$y)
Add-Type -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, System.UIntPtr e);
'@ -Name M -Namespace U
[U.M]::SetProcessDPIAware() | Out-Null
[U.M]::SetCursorPos($x, $y) | Out-Null
Start-Sleep -Milliseconds 100
[U.M]::mouse_event(2, 0, 0, 0, [System.UIntPtr]::Zero)
Start-Sleep -Milliseconds 50
[U.M]::mouse_event(4, 0, 0, 0, [System.UIntPtr]::Zero)
Start-Sleep -Milliseconds 90
[U.M]::mouse_event(2, 0, 0, 0, [System.UIntPtr]::Zero)
Start-Sleep -Milliseconds 50
[U.M]::mouse_event(4, 0, 0, 0, [System.UIntPtr]::Zero)

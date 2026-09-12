param(
  [string[]]$Keys = @(),   # sequence like "ctrl+c", "escape", "return", "win+shift+s", "down"
  [int]$GapMs = 150
)
Add-Type -Namespace K -Name A -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
'@
[K.A]::SetProcessDPIAware() | Out-Null
$MAP = @{
  "ctrl" = 0x11; "shift" = 0x10; "alt" = 0x12; "win" = 0x5B
  "escape" = 0x1B; "return" = 0x0D; "enter" = 0x0D; "tab" = 0x09
  "up" = 0x26; "down" = 0x28; "left" = 0x25; "right" = 0x27
  "home" = 0x24; "end" = 0x23; "delete" = 0x2E; "backspace" = 0x08
  "space" = 0x20; "f9" = 0x78; "f10" = 0x79
}
foreach ($combo in $Keys) {
  $parts = $combo.ToLower().Split("+")
  $vks = New-Object System.Collections.Generic.List[byte]
  foreach ($p in $parts) {
    if ($MAP.ContainsKey($p)) { $vks.Add([byte]$MAP[$p]) }
    else { $vks.Add([byte][char]::ToUpper($p[0])) }
  }
  foreach ($v in $vks) { [K.A]::keybd_event($v, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 30 }
  for ($i = $vks.Count - 1; $i -ge 0; $i--) {
    [K.A]::keybd_event($vks[$i], 0, 2, [UIntPtr]::Zero); Start-Sleep -Milliseconds 30
  }
  Start-Sleep -Milliseconds $GapMs
}
Write-Output ("keys sent: " + ($Keys -join ","))

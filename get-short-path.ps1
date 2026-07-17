$path = (Get-Item -LiteralPath 'E:\微信web开发者工具\cli.bat').FullName
Write-Host "Full: $path"
$sb = New-Object System.Text.StringBuilder(256)
$kernel32 = Add-Type -MemberDefinition @'
[DllImport("kernel32.dll", CharSet = CharSet.Auto)]
public static extern int GetShortPathName(string path, StringBuilder shortPath, int shortPathLength);
'@ -Name 'Kernel32' -Namespace 'Win32' -PassThru
$result = $kernel32::GetShortPathName($path, $sb, 256)
if ($result -gt 0) {
    Write-Host "Short: $($sb.ToString())"
} else {
    Write-Host "Could not get short path, error: $result"
}

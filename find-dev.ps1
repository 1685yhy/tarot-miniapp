# Find DevTools path
$drive = Get-Item "E:\"
$items = Get-ChildItem "E:\" -ErrorAction SilentlyContinue
foreach ($item in $items) {
    if ($item.Name -like "*web*" -or $item.Name -like "*WeChat*" -or $item.Name -like "*微信*") {
        Write-Host "Found: $($item.FullName)"
        $cliPath = Join-Path $item.FullName "cli.bat"
        if (Test-Path $cliPath) {
            Write-Host "CLI: $cliPath"
        }
    }
}

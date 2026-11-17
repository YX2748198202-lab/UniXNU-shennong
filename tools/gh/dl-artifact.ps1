$ErrorActionPreference = 'Stop'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$zip = 'C:\Users\yoox\AppData\Local\Temp\shennong-kernel-1.zip'
$uri = 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/artifacts/14305870316/zip'
if (-not (Test-Path $zip)) {
  Invoke-WebRequest -Uri $uri -Headers $h -OutFile $zip -UseBasicParsing -MaximumRedirection 5
}
Write-Output ('zip bytes: ' + (Get-Item $zip).Length)

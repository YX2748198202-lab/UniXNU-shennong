$ErrorActionPreference = 'Continue'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$zip = Join-Path $env:TEMP 'runlogs2.zip'
Invoke-WebRequest -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs/44026143570/logs' -Headers $h -OutFile $zip -UseBasicParsing -MaximumRedirection 5
$dst = Join-Path $env:TEMP 'runlogs2'
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Expand-Archive -Path $zip -DestinationPath $dst -Force
Write-Output 'ok'

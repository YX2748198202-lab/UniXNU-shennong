$ErrorActionPreference = 'Continue'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$zip = Join-Path $env:TEMP 'runlogs.zip'
$uri = 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs/44017646483/logs'
try {
    Invoke-WebRequest -Uri $uri -Headers $h -OutFile $zip -UseBasicParsing -MaximumRedirection 5
    Write-Output ('zip bytes: ' + (Get-Item $zip).Length)
    $dst = Join-Path $env:TEMP 'runlogs'
    if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
    Expand-Archive -Path $zip -DestinationPath $dst -Force
    Get-ChildItem -Recurse $dst -File | ForEach-Object { Write-Output ($_.FullName.Substring($dst.Length+1)) }
} catch { Write-Output ('ERR: ' + $_.Exception.Message) }

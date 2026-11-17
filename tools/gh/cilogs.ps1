$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$br = 'ci-logs-44017646483'
try {
  $items = Invoke-RestMethod -Uri "https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/contents/ci-logs?ref=$br" -Headers $h
  foreach ($i in $items) { Write-Output ($i.name + "  " + $i.size) }
} catch { Write-Output ('ERR: ' + $_.Exception.Message) }

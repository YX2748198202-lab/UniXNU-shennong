$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$arts = Invoke-RestMethod -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs/44026143570/artifacts' -Headers $h
foreach ($a in $arts.artifacts) { Write-Output ($a.name + "  " + $a.size_in_bytes + "  id=" + $a.id) }

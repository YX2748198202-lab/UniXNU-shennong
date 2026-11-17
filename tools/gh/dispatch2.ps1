$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$body = @{ ref = 'bringup/premmu-locate' } | ConvertTo-Json
try { Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/workflows/kernel.yml/dispatches' -Headers $h -Body $body -ContentType 'application/json' | Out-Null; Write-Output 'dispatch OK' } catch { Write-Output ('ERR: ' + $_.Exception.Message) }
Start-Sleep -Seconds 8
$runs = Invoke-RestMethod -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs?per_page=2' -Headers $h
foreach ($r in $runs.workflow_runs) { Write-Output ("run " + $r.id + " " + $r.head_branch + " " + $r.status + " " + $r.created_at) }

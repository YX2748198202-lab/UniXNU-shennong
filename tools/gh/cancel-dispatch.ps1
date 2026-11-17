$ErrorActionPreference = 'Continue'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
try { Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs/44017577601/cancel' -Headers $h | Out-Null; Write-Output 'cancel requested' } catch { Write-Output ('cancel ERR: ' + $_.Exception.Message) }
Start-Sleep -Seconds 4
$body = @{ ref = 'bringup/premmu-locate' } | ConvertTo-Json
try { Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/workflows/kernel.yml/dispatches' -Headers $h -Body $body -ContentType 'application/json' | Out-Null; Write-Output 'dispatch OK' } catch { Write-Output ('dispatch ERR: ' + $_.Exception.Message) }
Start-Sleep -Seconds 8
$runs = Invoke-RestMethod -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs?per_page=4' -Headers $h
foreach ($r in $runs.workflow_runs) { Write-Output ("run " + $r.id + " " + $r.head_branch + " " + $r.status + " " + $r.conclusion + " " + $r.created_at) }

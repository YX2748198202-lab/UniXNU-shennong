$ErrorActionPreference = 'Continue'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
try { $r = Invoke-RestMethod -Uri 'https://api.github.com/repos/UniXNU/UniXNU' -Headers $h; Write-Output ("repo: " + $r.full_name + " default=" + $r.default_branch + " private=" + $r.private) } catch { Write-Output ("repo ERR: " + $_.Exception.Message) }
try { $r2 = Invoke-RestMethod -Uri 'https://api.github.com/repos/UniXNU/UniXNU/branches' -Headers $h; Write-Output ("branches: " + (($r2 | Select-Object -ExpandProperty name) -join ',')) } catch { Write-Output ("branches ERR: " + $_.Exception.Message) }
try { $r3 = Invoke-RestMethod -Uri 'https://api.github.com/repos/UniXNU/UniXNU/contents/patches/xnu' -Headers $h; Write-Output ("patches/xnu count: " + $r3.Count); $r3 | ForEach-Object { Write-Output ("  " + $_.name) } } catch { Write-Output ("contents ERR: " + $_.Exception.Message) }

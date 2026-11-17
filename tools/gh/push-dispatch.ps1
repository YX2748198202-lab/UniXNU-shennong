$ErrorActionPreference = 'Continue'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$repo = '\\wsl.localhost\Ubuntu-24.04\home\yoox\android\workspace\UniXNU-shennong'
$url = "https://x-access-token:$tok@github.com/YX2748198202-lab/UniXNU-shennong.git"
Write-Output '--- push ---'
git -C $repo -c safe.directory=* push $url 'HEAD:refs/heads/bringup/premmu-locate' 2>&1 | ForEach-Object { $_ -replace [regex]::Escape($tok), '***' }
Write-Output '--- dispatch ---'
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$body = @{ ref = 'bringup/premmu-locate' } | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/workflows/kernel.yml/dispatches' -Headers $h -Body $body -ContentType 'application/json'
    Write-Output 'dispatch OK'
} catch {
    Write-Output ('dispatch ERR: ' + $_.Exception.Message)
    try { $s = $_.Exception.Response.GetResponseStream(); $sr = New-Object IO.StreamReader($s); Write-Output $sr.ReadToEnd() } catch {}
}
Start-Sleep -Seconds 6
try {
    $runs = Invoke-RestMethod -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs?per_page=3' -Headers $h
    foreach ($r in $runs.workflow_runs) { Write-Output ("run " + $r.id + " " + $r.name + " branch=" + $r.head_branch + " status=" + $r.status + " " + $r.created_at) }
} catch { Write-Output ('runs ERR: ' + $_.Exception.Message) }

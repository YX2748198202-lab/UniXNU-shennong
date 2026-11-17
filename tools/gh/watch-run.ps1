$ErrorActionPreference = 'Continue'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$rid = '44026143570'
$last = ''
for ($i = 0; $i -lt 240; $i++) {
    try { $r = Invoke-RestMethod -Uri "https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs/$rid" -Headers $h } catch { Start-Sleep -Seconds 30; continue }
    $s = "$($r.status)/$($r.conclusion)"
    if ($s -ne $last) { Write-Output ("[" + (Get-Date -Format 'HH:mm:ss') + "] " + $s); $last = $s }
    if ($r.status -eq 'completed') { break }
    Start-Sleep -Seconds 45
}
Write-Output '--- jobs ---'
try {
    $js = Invoke-RestMethod -Uri "https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs/$rid/jobs" -Headers $h
    foreach ($j in $js.jobs) {
        Write-Output ("job " + $j.name + " " + $j.status + "/" + $j.conclusion)
        foreach ($st in $j.steps) { Write-Output ("   " + $st.number + " " + $st.name + " -> " + $st.conclusion) }
    }
} catch { Write-Output ('jobs ERR: ' + $_.Exception.Message) }

$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$js = Invoke-RestMethod -Uri 'https://api.github.com/repos/YX2748198202-lab/UniXNU-shennong/actions/runs/44017646483/jobs' -Headers $h
foreach ($j in $js.jobs) {
  Write-Output ("job: " + $j.name + "  " + $j.status + "/" + $j.conclusion + "  started " + $j.started_at)
  foreach ($st in $j.steps) { Write-Output ("  " + $st.number.ToString().PadLeft(2) + " " + $st.status.PadRight(11) + " " + $st.name) }
}

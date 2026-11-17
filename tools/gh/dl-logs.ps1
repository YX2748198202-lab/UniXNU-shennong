$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$br = 'ci-logs-44017646483'
$names = @('pass2.log','archive-01-build-corecrypto-14.log','archive-02-build-corecrypto-14.log','archive-09-build-sheng-source-storage.log','second-pass-evidence.txt','errors.txt','prelink.log')
$out = '\\wsl.localhost\Ubuntu-24.04\home\yoox\android\workspace\UniXNU-shennong\tools\gh\logs'
New-Item -ItemType Directory -Force -Path $out | Out-Null
foreach ($n in $names) {
  try {
    $u = "https://raw.githubusercontent.com/YX2748198202-lab/UniXNU-shennong/$br/ci-logs/$n"
    Invoke-WebRequest -Uri $u -OutFile (Join-Path $out $n) -Headers @{ 'User-Agent'='dsh' } -UseBasicParsing
  } catch { Write-Output ("fail " + $n) }
}
Write-Output 'ok'

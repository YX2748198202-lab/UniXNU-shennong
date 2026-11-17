$ErrorActionPreference = 'Continue'
$tok = (Get-Content (Join-Path $env:TEMP 'unixnu-gh-token.txt') -Raw).Trim()
$h = @{ Authorization = "token $tok"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'dsh' }
$out = '\\wsl.localhost\Ubuntu-24.04\home\yoox\android\workspace\UniXNU-shennong\tools\gh\dl'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$dirs = @('patches/xnu', 'kits/XnuPrelink/patches')
$n = 0
foreach ($d in $dirs) {
    try { $items = Invoke-RestMethod -Uri "https://api.github.com/repos/UniXNU/UniXNU/contents/$d" -Headers $h } catch { Write-Output ("list ERR $d"); continue }
    foreach ($it in $items) {
        if ($it.type -ne 'file') { continue }
        $dest = Join-Path $out (($d -replace '/','__') + '__' + $it.name)
        try { Invoke-WebRequest -Uri $it.download_url -OutFile $dest -Headers @{ 'User-Agent' = 'dsh' } -UseBasicParsing; $n++ } catch { Write-Output ("dl fail " + $it.name) }
    }
}
Write-Output ("downloaded patches: " + $n)
try {
    Invoke-WebRequest -Uri 'https://cdn.jsdelivr.net/gh/apple-oss-distributions/xnu@main/osfmk/arm64/arm_vm_init.c' -OutFile (Join-Path $out 'arm_vm_init.c') -UseBasicParsing
    Write-Output ('arm_vm_init.c bytes: ' + (Get-Item (Join-Path $out 'arm_vm_init.c')).Length)
} catch { Write-Output ('arm_vm_init failed: ' + $_.Exception.Message) }

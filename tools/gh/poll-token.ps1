$ErrorActionPreference = 'Stop'
$body = @{ client_id = '178c6fc778ccc68e1d6a'; device_code = '1d5e939cb8ba72ce95992d8a821b7e6994fc74c5'; grant_type = 'urn:ietf:params:oauth:grant-type:device_code' }
for ($i = 0; $i -lt 170; $i++) {
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-RestMethod -Method Post -Uri 'https://github.com/login/oauth/access_token' -Headers @{ Accept = 'application/json' } -Body $body
    } catch { continue }
    if ($r.access_token) {
        $p = Join-Path $env:TEMP 'unixnu-gh-token.txt'
        Set-Content -Path $p -Value $r.access_token -NoNewline
        Write-Output "AUTH_OK saved to $p"
        exit 0
    }
    if ($r.error -eq 'authorization_pending') { continue }
    if ($r.error) { Write-Output ("AUTH_FAIL " + $r.error); exit 1 }
}
Write-Output 'AUTH_TIMEOUT'

$ErrorActionPreference = 'Stop'
$body = @{ client_id = '178c6fc778ccc68e1d6a'; scope = 'repo workflow' }
$r = Invoke-RestMethod -Method Post -Uri 'https://github.com/login/device/code' -Headers @{ Accept = 'application/json' } -Body $body
$r | ConvertTo-Json

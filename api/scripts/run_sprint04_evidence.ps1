$ErrorActionPreference = 'Stop'
$apiDir = Split-Path $PSScriptRoot -Parent
$projectDir = Split-Path $apiDir -Parent
$evidencePath = Join-Path $projectDir 'docs\sprint04\evidencia-testes.txt'

function Invoke-Native {
    param([string] $Program, [string[]] $Arguments)
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $result = & $Program @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
    $lines = @($result | ForEach-Object { $_.ToString() })
    if ($exitCode -ne 0) { throw (($lines | Select-Object -Last 30) -join [Environment]::NewLine) }
    return $lines
}

$email = Read-Host 'E-mail do administrador'
$securePassword = Read-Host 'Senha do administrador' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }

Push-Location $apiDir
try {
    $env:ARIANO_TEST_ADMIN_EMAIL = $email
    $env:ARIANO_TEST_ADMIN_PASSWORD = $password
    Write-Host 'Construindo e iniciando a aplicação...'
    Invoke-Native -Program docker -Arguments @('compose', '--profile', 'full', 'up', '-d', '--build', '--wait', 'api') | Out-Null
    Write-Host 'Testando o fluxo e as validações...'
    $first = @(Invoke-Native -Program py -Arguments @('-m', 'scripts.smoke_sprint04'))
    $created = $first[-1] | ConvertFrom-Json
    if ($created.status -ne 'PASS') { throw 'A criação da demanda não foi confirmada.' }
    Write-Host 'Reiniciando a API e verificando a persistência...'
    Invoke-Native -Program docker -Arguments @('compose', '--profile', 'full', 'restart', 'api') | Out-Null
    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 2
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
            if ($health.status -eq 'ok') { $healthy = $true; break }
        }
        catch { }
    }
    if (-not $healthy) { throw 'A API não voltou a responder após o reinício.' }
    $second = @(Invoke-Native -Program py -Arguments @('-m', 'scripts.smoke_sprint04', '--verify-demand', [string] $created.demand_id))
    $verified = $second[-1] | ConvertFrom-Json
    if ($verified.status -ne 'PASS') { throw 'A persistência não foi confirmada.' }
    $services = Invoke-Native -Program docker -Arguments @('compose', '--profile', 'full', 'ps')
    $evidence = @(
        'ARIANO - Sprint 04 - evidência funcional',
        "Data: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        'Resultado: PASS',
        '', 'Fluxo criado:', ($first -join [Environment]::NewLine),
        '', 'Após reinício da API:', ($second -join [Environment]::NewLine),
        '', 'Serviços:', ($services -join [Environment]::NewLine)
    )
    Set-Content -LiteralPath $evidencePath -Value $evidence -Encoding UTF8
    Write-Host "Sprint 04 testada. Evidência: $evidencePath"
    Write-Host ($first[-1])
    Write-Host ($second[-1])
}
catch {
    $message = $_.Exception.Message
    Set-Content -LiteralPath $evidencePath -Value @(
        'ARIANO - Sprint 04 - tentativa funcional',
        "Data: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        'Resultado: FAIL', '', $message
    ) -Encoding UTF8
    Write-Error "Teste da Sprint 04 não concluído. Detalhes em $evidencePath`n$message"
    exit 1
}
finally {
    Remove-Item Env:ARIANO_TEST_ADMIN_EMAIL -ErrorAction SilentlyContinue
    Remove-Item Env:ARIANO_TEST_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    $password = $null
    Pop-Location
}


[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw '尚未安装依赖。请先运行 .\setup.ps1。'
}
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
if ($nodeCommand) {
    $nodeExecutable = $nodeCommand.Source
} else {
    $nodeExecutable = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (-not (Test-Path -LiteralPath $nodeExecutable)) {
        throw '未找到 Node.js。请安装 Node.js 20 或更高版本。'
    }
}

New-Item -ItemType Directory -Force -Path 'data\logs' | Out-Null
$backend = $null
$frontend = $null

function Test-Endpoint([string]$Url) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-LogTail([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    return ((Get-Content -LiteralPath $Path -Tail 8 -ErrorAction SilentlyContinue) -join "`n").Trim()
}

if (-not (Test-Endpoint 'http://127.0.0.1:8000/api/health')) {
    $backend = Start-Process -FilePath $venvPython `
        -ArgumentList '-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8000' `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $projectRoot 'data\logs\backend.out.log') `
        -RedirectStandardError (Join-Path $projectRoot 'data\logs\backend.err.log')
    Set-Content -LiteralPath 'data\backend.pid' -Value $backend.Id
    Write-Host "后端已启动（PID $($backend.Id)）" -ForegroundColor Green
} else {
    Write-Host '后端已经在运行，已复用现有服务。' -ForegroundColor Yellow
}

if (-not (Test-Endpoint 'http://127.0.0.1:5173')) {
    $frontend = Start-Process -FilePath $nodeExecutable -ArgumentList 'node_modules\vite\bin\vite.js', '--host', '127.0.0.1' `
        -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $projectRoot 'data\logs\frontend.out.log') `
        -RedirectStandardError (Join-Path $projectRoot 'data\logs\frontend.err.log')
    Set-Content -LiteralPath 'data\frontend.pid' -Value $frontend.Id
    Write-Host "前端已启动（PID $($frontend.Id)）" -ForegroundColor Green
} else {
    Write-Host '前端已经在运行，已复用现有服务。' -ForegroundColor Yellow
}

for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ((Test-Endpoint 'http://127.0.0.1:8000/api/health') -and (Test-Endpoint 'http://127.0.0.1:5173')) { break }
    if (($backend -and $backend.HasExited) -or ($frontend -and $frontend.HasExited)) { break }
    Start-Sleep -Milliseconds 500
}
if (-not (Test-Endpoint 'http://127.0.0.1:8000/api/health')) {
    $detail = Get-LogTail (Join-Path $projectRoot 'data\logs\backend.err.log')
    throw "后端启动失败。$detail"
}
if (-not (Test-Endpoint 'http://127.0.0.1:5173')) {
    $detail = Get-LogTail (Join-Path $projectRoot 'data\logs\frontend.err.log')
    throw "前端启动失败。$detail"
}

Write-Host '原阅已就绪：http://127.0.0.1:5173' -ForegroundColor Cyan
if (-not $NoBrowser) {
    Start-Process 'http://127.0.0.1:5173'
}

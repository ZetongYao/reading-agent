[CmdletBinding()]
param([switch]$SkipOcr)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

Write-Host '原阅：正在准备本地运行环境…' -ForegroundColor Cyan

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    throw '未找到 Python。请安装 Python 3.11 或 3.12，并勾选 Add Python to PATH。'
}

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $pythonCommand.Source -m venv .venv
}
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements-dev.txt

if (-not $SkipOcr) {
    Write-Host '正在安装 PaddleOCR（文件较大，请耐心等待）…' -ForegroundColor Cyan
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $venvPython -m pip install -r requirements-ocr.txt
    $ocrExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    if ($ocrExitCode -ne 0) {
        Write-Warning 'PaddleOCR 安装未成功。普通文字书籍仍可使用；请稍后重新运行 .\setup.ps1。'
    }
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
$codexDependencies = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$bundledNode = Join-Path $codexDependencies 'node\bin\node.exe'
$bundledPnpm = Join-Path $codexDependencies 'bin\fallback\pnpm.cmd'
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    if ($npmCommand) {
        & $npmCommand.Source install
    } elseif ((Test-Path -LiteralPath $bundledNode) -and (Test-Path -LiteralPath $bundledPnpm)) {
        $nodeDirectory = Split-Path -Parent $bundledNode
        $env:Path = "$nodeDirectory;$env:Path"
        & $bundledPnpm install
    } else {
        throw '未找到 Node.js/npm。请安装 Node.js 20 或更高版本后重新运行 setup.ps1。'
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
New-Item -ItemType Directory -Force -Path 'data\books', 'data\logs' | Out-Null

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host '已检测到 Ollama。首次使用请运行：ollama pull qwen3:4b' -ForegroundColor Green
} else {
    Write-Warning '未检测到 Ollama。应用仍可阅读书籍；如需翻译，请安装 Ollama 后运行：ollama pull qwen3:4b'
}

Write-Host '安装完成。运行 .\start.ps1 即可启动。' -ForegroundColor Green

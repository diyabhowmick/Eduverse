# Starts EduVerse. Run from anywhere: powershell -ExecutionPolicy Bypass -File run.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$envFile = Join-Path $backend '.env'
$utf8 = New-Object System.Text.UTF8Encoding($false)

if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $backend '.env.example') $envFile }

# One permanent sign-in key, created once. A new key on every start is what signs everyone out.
$text = [System.IO.File]::ReadAllText($envFile)
if ($text -notmatch '(?m)^JWT_SECRET=\S') {
    $secret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    $text = $text -replace '(?m)^JWT_SECRET=.*$', "JWT_SECRET=$secret"
    [System.IO.File]::WriteAllText($envFile, $text, $utf8)
}

$port = 8001
if ($text -match '(?m)^PORT=(\d+)') { $port = [int]$Matches[1] }

$env:PYTHONIOENCODING = 'utf-8'
Set-Location $backend
& (Join-Path $root '.venv\Scripts\python.exe') -m uvicorn app.main:app --port $port

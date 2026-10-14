$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt' }
Set-Location -LiteralPath $root
& $python -m uvicorn backend.app:app --host 127.0.0.1 --port 8123 --no-access-log

param(
    [int]$Port = 8000
)

$env:PYTHONPATH = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload

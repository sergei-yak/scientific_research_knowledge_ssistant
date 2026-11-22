param([int]$Port = 8504)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& uv sync --locked --offline
if ($LASTEXITCODE -ne 0) { throw 'Locked environment setup failed. See docs/M8_3_REPORT.md.' }
$scopePath = Join-Path $PSScriptRoot 'data/scopes/user-collections.json'
if (-not (Test-Path -LiteralPath $scopePath)) { throw 'M8 scope is missing. Complete the isolated M8 setup first.' }
& .venv/Scripts/python.exe -m research_assistant.collections start
if ($LASTEXITCODE -ne 0) { throw 'M8 target could not be verified. Preserve its declaration/volumes and inspect the setup.' }
if (-not $env:REQUEST_TIMEOUT_SECONDS) { $env:REQUEST_TIMEOUT_SECONDS = '300' }
& .venv/Scripts/python.exe -m streamlit run src/research_assistant/ui/collections_app.py --server.address 127.0.0.1 --server.port $Port --server.headless true --server.maxUploadSize 25 --server.fileWatcherType none --browser.gatherUsageStats false

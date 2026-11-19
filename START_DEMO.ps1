param([int]$Port = 8503)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& uv sync --locked --offline
if ($LASTEXITCODE -ne 0) { throw 'Locked environment setup failed. See docs/M6_DEMO_GUIDE.md.' }
& uv run --locked --offline python -m streamlit run src/research_assistant/ui/app.py --server.address 127.0.0.1 --server.port $Port --server.headless true --browser.gatherUsageStats false

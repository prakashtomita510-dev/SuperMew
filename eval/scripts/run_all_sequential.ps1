Write-Host "Starting Sequential Full Evaluation Sweep..." -ForegroundColor Cyan

$python = ".venv_311\Scripts\python.exe"

# 1. Hybrid Weight Sweep (P1-01)
Write-Host "`n[1/2] Running Hybrid Weight Sweep..." -ForegroundColor Yellow
& $python eval/scripts/run_hybrid_sweep.py

# 2. Latency Benchmark (P2-01)
Write-Host "`n[2/2] Running Latency Benchmark..." -ForegroundColor Yellow
& $python eval/scripts/run_latency_benchmark.py

Write-Host "`nAll sequential tasks completed!" -ForegroundColor Green

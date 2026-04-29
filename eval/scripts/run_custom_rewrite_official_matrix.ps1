param(
    [string]$PythonPath = ".\.venv_311\Scripts\python.exe",
    [string]$DatasetPath = "eval/datasets/custom/custom_eval.jsonl",
    [int]$TimeoutSecondsPerRun = 7200,
    [int]$HeartbeatIntervalSeconds = 60
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$heartbeat = Join-Path $scriptDir "run_with_heartbeat.ps1"
$officialEnv = Join-Path $scriptDir "with_custom_official_env.ps1"

$configs = @(
    "eval/configs/rewrite_no_rewrite_official.yaml",
    "eval/configs/rewrite_step_back_official.yaml",
    "eval/configs/rewrite_hyde_official.yaml",
    "eval/configs/rewrite_dynamic_official.yaml"
)

foreach ($config in $configs) {
    Write-Host "[rewrite-matrix] running $config"
    $command = "powershell -ExecutionPolicy Bypass -File `"$officialEnv`" `"$PythonPath`" -B eval/scripts/run_rewrite_eval.py --config `"$config`" --dataset-path `"$DatasetPath`""
    powershell -ExecutionPolicy Bypass -File $heartbeat `
        -WorkingDirectory $repoRoot `
        -IntervalSeconds $HeartbeatIntervalSeconds `
        -TimeoutSeconds $TimeoutSecondsPerRun `
        -TailLines 20 `
        -Command $command

    if ($LASTEXITCODE -ne 0) {
        throw "rewrite matrix failed on $config with exit code $LASTEXITCODE"
    }
}

Write-Host "[rewrite-matrix] aggregating official reports"
& $PythonPath -B eval/scripts/aggregate_results.py --outputs-root eval/outputs
if ($LASTEXITCODE -ne 0) {
    throw "aggregate_results.py failed with exit code $LASTEXITCODE"
}

param(
    [string]$Domain = "technology",
    [string]$Split = "dev",
    [ValidateSet("forum", "search")]
    [string]$QuerySet = "forum",
    [int]$MaxRequiredPids = 200,
    [int]$DistractorLimit = 2000,
    [int]$BatchSize = 8,
    [double]$SleepSeconds = 1.0,
    [int]$SampleLimit = 20
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $PSScriptRoot) "..")
Set-Location $repoRoot

$python = ".\.venv_311\Scripts\python.exe"
$queries = "eval/datasets/lotte/normalized/$Domain/$Split.$QuerySet.jsonl"

Write-Host "==> Official LoTTE ingestion: $Domain/$Split/$QuerySet"
& $python "eval/scripts/ingest_lotte.py" `
  --domain $Domain `
  --split $Split `
  --query-set $QuerySet `
  --queries-path $queries `
  --distractor-limit $DistractorLimit `
  --max-required-pids $MaxRequiredPids `
  --batch-size $BatchSize `
  --sleep-seconds $SleepSeconds `
  --skip-parent-store
if ($LASTEXITCODE -ne 0) {
  throw "LoTTE ingestion failed with exit code $LASTEXITCODE"
}

$configs = @(
  "eval/configs/retrieval_dense_official.yaml",
  "eval/configs/retrieval_sparse_official.yaml",
  "eval/configs/retrieval_hybrid_official.yaml",
  "eval/configs/retrieval_hybrid_rerank_official.yaml"
)

foreach ($config in $configs) {
  Write-Host "==> Running retrieval eval with $config"
  & $python "eval/scripts/run_retrieval_eval.py" `
    --config $config `
    --dataset-path $queries `
    --sample-limit $SampleLimit
  if ($LASTEXITCODE -ne 0) {
    throw "Retrieval eval failed for $config with exit code $LASTEXITCODE"
  }
}

Write-Host "==> Aggregating reports"
& $python "eval/scripts/aggregate_results.py" --outputs-root "eval/outputs"
if ($LASTEXITCODE -ne 0) {
  throw "Aggregation failed with exit code $LASTEXITCODE"
}

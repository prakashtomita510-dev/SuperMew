param(
    [string]$PythonPath = "D:\agent_demo\SuperMew\.venv_311\Scripts\python.exe",
    [string]$MockUri = "D:\agent_demo\SuperMew\eval\datasets\lotte\lotte_pilot_mock.json",
    [string]$DatabaseUrl = "sqlite:///D:/agent_demo/SuperMew/eval/datasets/lotte/lotte_pilot.db",
    [string]$Domain = "technology",
    [string]$Split = "dev",
    [ValidateSet("forum", "search")]
    [string]$QuerySet = "forum",
    [int]$DistractorLimit = 5000,
    [int]$MaxRequiredPids = 1000,
    [int]$SampleLimit = 100,
    [string]$ConfigPath = "D:\agent_demo\SuperMew\eval\configs\retrieval_baselines_pilot.yaml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$env:MILVUS_URI = $MockUri
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:MILVUS_REQUIRE_REAL = "false"
$env:DATABASE_URL = $DatabaseUrl

Write-Host "Using isolated pilot storage: $MockUri"
Write-Host "Using isolated pilot database: $DatabaseUrl"
Write-Host "Step 1/2: ingesting LoTTE corpus subset..."
& $PythonPath "D:\agent_demo\SuperMew\eval\scripts\ingest_lotte.py" `
  --domain $Domain `
  --split $Split `
  --query-set $QuerySet `
  --distractor-limit $DistractorLimit `
  --max-required-pids $MaxRequiredPids `
  --skip-parent-store

$datasetPath = "D:\agent_demo\SuperMew\eval\datasets\lotte\normalized\$Domain\$Split.$QuerySet.jsonl"

Write-Host "Step 2/2: running retrieval pilot..."
& $PythonPath "D:\agent_demo\SuperMew\eval\scripts\run_retrieval_eval.py" `
  --config $ConfigPath `
  --dataset-path $datasetPath `
  --sample-limit $SampleLimit

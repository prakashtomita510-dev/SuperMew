param(
    [string]$PythonPath = "D:\agent_demo\SuperMew\.venv_311\Scripts\python.exe",
    [string]$MockUri = "D:\agent_demo\SuperMew\eval\datasets\lotte\lotte_pilot_mock.json",
    [string]$DatabaseUrl = "sqlite:///D:/agent_demo/SuperMew/eval/datasets/lotte/lotte_pilot.db",
    [string]$DatasetPath = "D:\agent_demo\SuperMew\eval\datasets\lotte\normalized\technology\dev.forum.jsonl",
    [int]$SampleLimit = 50
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$env:MILVUS_URI = $MockUri
$env:DATABASE_URL = $DatabaseUrl
$env:MILVUS_REQUIRE_REAL = "false"
$env:PYTHONDONTWRITEBYTECODE = "1"

$configs = @(
    "D:\agent_demo\SuperMew\eval\configs\retrieval_baselines_pilot.yaml",
    "D:\agent_demo\SuperMew\eval\configs\retrieval_sparse_pilot.yaml",
    "D:\agent_demo\SuperMew\eval\configs\retrieval_hybrid_pilot.yaml",
    "D:\agent_demo\SuperMew\eval\configs\retrieval_hybrid_rerank_pilot.yaml"
)

foreach ($config in $configs) {
    Write-Host "Running retrieval pilot with config: $config"
    & $PythonPath "D:\agent_demo\SuperMew\eval\scripts\run_retrieval_eval.py" `
      --config $config `
      --dataset-path $DatasetPath `
      --sample-limit $SampleLimit
}

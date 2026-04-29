param(
    [ValidateSet("technology", "selected-domains")]
    [string]$Preset = "technology",

    [string]$PythonPath = "D:\agent_demo\SuperMew\.venv_311\Scripts\python.exe",

    [string]$IrDatasetsHome = "D:\agent_demo\SuperMew\eval\datasets\.cache\ir_datasets"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python not found: $PythonPath"
}

$env:IR_DATASETS_HOME = $IrDatasetsHome
$env:PYTHONDONTWRITEBYTECODE = "1"

$pythonScript = @'
import os
import ir_datasets

preset = os.environ["LOTTE_PRESET"]

if preset == "technology":
    names = [
        "lotte/technology/dev/forum",
        "lotte/technology/dev/search",
        "lotte/technology/test/forum",
        "lotte/technology/test/search",
    ]
elif preset == "selected-domains":
    names = [
        "lotte/technology/dev/forum",
        "lotte/technology/dev/search",
        "lotte/technology/test/forum",
        "lotte/technology/test/search",
        "lotte/science/dev/forum",
        "lotte/science/dev/search",
        "lotte/science/test/forum",
        "lotte/science/test/search",
        "lotte/writing/dev/forum",
        "lotte/writing/dev/search",
        "lotte/writing/test/forum",
        "lotte/writing/test/search",
    ]
else:
    raise ValueError(f"Unsupported preset: {preset}")

for name in names:
    ds = ir_datasets.load(name)
    print(f"warming {name}", flush=True)

    if ds.has_docs():
        count = 0
        for count, _ in enumerate(ds.docs_iter(), 1):
            if count % 50000 == 0:
                print(f"{name} docs={count}", flush=True)
        print(f"{name} docs_done={count}", flush=True)

    if ds.has_queries():
        count = 0
        for count, _ in enumerate(ds.queries_iter(), 1):
            pass
        print(f"{name} queries_done={count}", flush=True)

    if ds.has_qrels():
        count = 0
        for count, _ in enumerate(ds.qrels_iter(), 1):
            pass
        print(f"{name} qrels_done={count}", flush=True)

print(f"LoTTE preset complete: {preset}", flush=True)
'@

$env:LOTTE_PRESET = $Preset

Write-Host "Using IR_DATASETS_HOME=$IrDatasetsHome"
Write-Host "Using preset=$Preset"
Write-Host "Starting LoTTE warm-up..."

$pythonScript | & $PythonPath -

Write-Host "Done."

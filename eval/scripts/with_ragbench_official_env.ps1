param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FilePath,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgumentList,

    [string]$CollectionName = "embeddings_ragbench_techqa_official"
)

$env:MILVUS_COLLECTION = $CollectionName

$officialEnv = Join-Path $PSScriptRoot "with_official_eval_env.ps1"
& $officialEnv $FilePath @ArgumentList
exit $LASTEXITCODE

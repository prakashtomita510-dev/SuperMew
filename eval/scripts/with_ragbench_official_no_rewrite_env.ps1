param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FilePath,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgumentList,

    [string]$CollectionName = "embeddings_ragbench_techqa_official"
)

$env:RAG_REWRITE_MODE = "off"

$wrapper = Join-Path $PSScriptRoot "with_ragbench_official_env.ps1"
& $wrapper -CollectionName $CollectionName $FilePath @ArgumentList
exit $LASTEXITCODE

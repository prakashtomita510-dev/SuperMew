param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FilePath,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgumentList
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\..")
Set-Location $repoRoot

$env:DATABASE_URL = "sqlite:///./backend/supermew.db"
$env:MILVUS_REQUIRE_REAL = "true"
if (-not $env:GOOGLE_EMBED_BATCH_LIMIT) {
    $env:GOOGLE_EMBED_BATCH_LIMIT = "4"
}
if (-not $env:GOOGLE_EMBED_MIN_INTERVAL_SECONDS) {
    $env:GOOGLE_EMBED_MIN_INTERVAL_SECONDS = "6"
}
if (-not $env:EMBEDDING_MAX_RETRIES) {
    $env:EMBEDDING_MAX_RETRIES = "1"
}
if (-not $env:EMBEDDING_REQUEST_TIMEOUT_SECONDS) {
    $env:EMBEDDING_REQUEST_TIMEOUT_SECONDS = "30"
}
$env:DISABLE_INTERNET_CRAWLER_SEARCH = "true"

Write-Host "[official-eval-env] DATABASE_URL=$env:DATABASE_URL"
Write-Host "[official-eval-env] MILVUS_REQUIRE_REAL=$env:MILVUS_REQUIRE_REAL"
Write-Host "[official-eval-env] GOOGLE_EMBED_BATCH_LIMIT=$env:GOOGLE_EMBED_BATCH_LIMIT"
Write-Host "[official-eval-env] GOOGLE_EMBED_MIN_INTERVAL_SECONDS=$env:GOOGLE_EMBED_MIN_INTERVAL_SECONDS"
Write-Host "[official-eval-env] EMBEDDING_MAX_RETRIES=$env:EMBEDDING_MAX_RETRIES"
Write-Host "[official-eval-env] EMBEDDING_REQUEST_TIMEOUT_SECONDS=$env:EMBEDDING_REQUEST_TIMEOUT_SECONDS"
Write-Host "[official-eval-env] DISABLE_INTERNET_CRAWLER_SEARCH=$env:DISABLE_INTERNET_CRAWLER_SEARCH"

& $FilePath @ArgumentList
exit $LASTEXITCODE

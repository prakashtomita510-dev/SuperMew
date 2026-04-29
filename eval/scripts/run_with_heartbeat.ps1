param(
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [string]$WorkingDirectory = (Get-Location).Path,
    [int]$IntervalSeconds = 30,
    [int]$TimeoutSeconds = 1800,
    [int]$TailLines = 20,
    [string[]]$FailFastPatterns = @(),
    [int]$ConsecutivePatternLimit = 2
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$monitorDir = Join-Path $repoRoot "eval\outputs\monitor"
New-Item -ItemType Directory -Path $monitorDir -Force | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutPath = Join-Path $monitorDir "heartbeat-$stamp.out.log"
$stderrPath = Join-Path $monitorDir "heartbeat-$stamp.err.log"

Write-Host "[heartbeat] starting command"
Write-Host "[heartbeat] cwd=$WorkingDirectory"
Write-Host "[heartbeat] stdout=$stdoutPath"
Write-Host "[heartbeat] stderr=$stderrPath"
Write-Host "[heartbeat] command=$Command"
if ($FailFastPatterns.Count -gt 0) {
    Write-Host "[heartbeat] fail-fast patterns=$($FailFastPatterns -join '; ')"
    Write-Host "[heartbeat] consecutive pattern limit=$ConsecutivePatternLimit"
}

$proc = Start-Process `
    -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -ArgumentList @("-NoProfile", "-Command", $Command) `
    -WorkingDirectory $WorkingDirectory `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

$start = Get-Date
$patternHits = @{}
foreach ($pattern in $FailFastPatterns) {
    $patternHits[$pattern] = 0
}

while (-not $proc.HasExited) {
    Start-Sleep -Seconds $IntervalSeconds
    $proc.Refresh()
    if ($proc.HasExited) {
        break
    }

    $elapsed = [int]((Get-Date) - $start).TotalSeconds
    Write-Host "[heartbeat] pid=$($proc.Id) elapsed=${elapsed}s still running"

    if (Test-Path $stdoutPath) {
        $stdoutTail = Get-Content $stdoutPath -Tail $TailLines -ErrorAction SilentlyContinue
        if ($stdoutTail) {
            Write-Host "[heartbeat][stdout-tail]"
            $stdoutTail | ForEach-Object { Write-Host $_ }
        }
    }

    if (Test-Path $stderrPath) {
        $stderrTail = Get-Content $stderrPath -Tail $TailLines -ErrorAction SilentlyContinue
        if ($stderrTail) {
            Write-Host "[heartbeat][stderr-tail]"
            $stderrTail | ForEach-Object { Write-Host $_ }
        }
    }

    if ($FailFastPatterns.Count -gt 0) {
        $combinedTail = @()
        if ($stdoutTail) { $combinedTail += $stdoutTail }
        if ($stderrTail) { $combinedTail += $stderrTail }
        $combinedText = ($combinedTail -join "`n")

        foreach ($pattern in $FailFastPatterns) {
            if ($combinedText -match $pattern) {
                $patternHits[$pattern] = [int]$patternHits[$pattern] + 1
                Write-Host "[heartbeat] fail-fast match '$pattern' hit=$($patternHits[$pattern])/$ConsecutivePatternLimit"
                if ($patternHits[$pattern] -ge $ConsecutivePatternLimit) {
                    Write-Host "[heartbeat] stopping pid=$($proc.Id) because pattern '$pattern' repeated $ConsecutivePatternLimit times"
                    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                    throw "Command stopped early because '$pattern' repeated $ConsecutivePatternLimit times"
                }
            }
            else {
                $patternHits[$pattern] = 0
            }
        }
    }

    if ($elapsed -ge $TimeoutSeconds) {
        Write-Host "[heartbeat] timeout reached (${TimeoutSeconds}s), stopping pid=$($proc.Id)"
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        throw "Command timed out after ${TimeoutSeconds}s"
    }
}

$proc.Refresh()
$exitCode = $proc.ExitCode
if ($null -eq $exitCode -or $exitCode -eq "") {
    $exitCode = 0
}
Write-Host "[heartbeat] process exited with code $exitCode"

if (Test-Path $stdoutPath) {
    Write-Host "[heartbeat][stdout-final]"
    Get-Content $stdoutPath -Tail ($TailLines * 2) -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
}

if (Test-Path $stderrPath) {
    $stderrFinal = Get-Content $stderrPath -Tail ($TailLines * 2) -ErrorAction SilentlyContinue
    if ($stderrFinal) {
        Write-Host "[heartbeat][stderr-final]"
        $stderrFinal | ForEach-Object { Write-Host $_ }
    }
}

if ($FailFastPatterns.Count -gt 0) {
    $finalCombined = @()
    if (Test-Path $stdoutPath) {
        $finalCombined += Get-Content $stdoutPath -Tail ($TailLines * 4) -ErrorAction SilentlyContinue
    }
    if (Test-Path $stderrPath) {
        $finalCombined += Get-Content $stderrPath -Tail ($TailLines * 4) -ErrorAction SilentlyContinue
    }
    $finalText = ($finalCombined -join "`n")
    foreach ($pattern in $FailFastPatterns) {
        if ($finalText -match $pattern) {
            throw "Command completed but matched fail-fast pattern '$pattern' in final output"
        }
    }
}

exit $exitCode

#Requires -Version 5.1
<#
.SYNOPSIS
    Ephemeral MetaTracer CLI inside Docker (TASK-07, subtask 7.3.4).

.DESCRIPTION
    One-shot scan container: reports land in .\reports on the host and the
    container is deleted on exit (--rm). The run's SQLite database lives and
    dies inside the container; to keep run history add a data volume:

        docker run --rm -it -v "$pwd\data:/app/data" -v "$pwd\reports:/app/reports" metatracer list-runs

    The METATRACER_LLM_* variables are passed through from the host
    environment; without them the run uses the heuristic classifier only.
    METATRACER_ALLOW_LOOPBACK is a test-only flag and is NOT passed through.

.EXAMPLE
    .\scripts\docker-metatracer.ps1 scan example.com -s example.com -y
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

$ErrorActionPreference = "Stop"
$reportsDir = Join-Path (Get-Location) "reports"
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

docker run --rm -it `
    -v "${reportsDir}:/app/reports" `
    -e METATRACER_LLM_API_KEY `
    -e METATRACER_LLM_BASE_URL `
    -e METATRACER_LLM_MODEL `
    -e METATRACER_FAST_MODEL `
    metatracer @CommandArgs
exit $LASTEXITCODE

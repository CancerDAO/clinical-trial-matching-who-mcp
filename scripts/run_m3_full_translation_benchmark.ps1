param(
    [Parameter(Mandatory = $true)]
    [string]$ApiKey
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$run = Join-Path $root "production-runs\tamar-current-project-fulltest-20260818"
$input = Join-Path $run "_translation_analysis_v2\pipeline.json"
$out = Join-Path $run "_translation_m3_fulltest"
$output = Join-Path $out "translated-pipeline.json"
$cache = "$output.translations.json"
$timing = Join-Path $out "timing.json"
$python = "C:\Anaconda\envs\trialgpt\python.exe"
$translator = Join-Path $root "skills\clinical-trial-matching-who-mcp\scripts\render\report_translation.py"

New-Item -ItemType Directory -Path $out -Force | Out-Null
Remove-Item -LiteralPath $output, $cache, $timing -Force -ErrorAction SilentlyContinue

$env:TRANSLATION_MODEL_PROVIDER = "minimax"
$env:TRANSLATION_MODEL_BASE_URL = "https://api.minimaxi.com/v1"
$env:TRANSLATION_MODEL_NAME = "MiniMax-M3"
$env:MINIMAX_API_KEY = $ApiKey
$env:TRANSLATION_BATCH_MAX_UNITS = "10"
$env:TRANSLATION_BATCH_MAX_CHARACTERS = "1500"
$env:TRANSLATION_MODEL_CONCURRENCY = "8"
$env:TRANSLATION_MODEL_MAX_OUTPUT_TOKENS = "4096"
$env:TRANSLATION_MODEL_TOKEN_PARAMETER = "max_tokens"
$env:MODEL_API_TIMEOUT_SECONDS = "180"
$env:MODEL_API_RETRIES = "2"

$watch = [Diagnostics.Stopwatch]::StartNew()
try {
    & $python -X utf8 $translator --input $input --output $output
    $exitCode = $LASTEXITCODE
} finally {
    $watch.Stop()
    Remove-Item Env:MINIMAX_API_KEY -ErrorAction SilentlyContinue
}

$cacheEntries = 0
if (Test-Path $cache) {
    $cacheObject = Get-Content -LiteralPath $cache -Raw | ConvertFrom-Json
    $cacheEntries = ($cacheObject.PSObject.Properties | Measure-Object).Count
}
$result = [ordered]@{
    exit_code = $exitCode
    seconds = [math]::Round($watch.Elapsed.TotalSeconds, 2)
    minutes = [math]::Round($watch.Elapsed.TotalMinutes, 2)
    cache_entries = $cacheEntries
    output = $output
    cache = $cache
    finished_at = (Get-Date).ToString("o")
}
$result | ConvertTo-Json | Set-Content -LiteralPath $timing -Encoding utf8
$result | ConvertTo-Json

if ($exitCode -ne 0) {
    exit $exitCode
}

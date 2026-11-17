[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][guid]$GameId,
    [string]$ApiBaseUrl = 'http://127.0.0.1:8000',
    [ValidateSet('grid-only', 'screen+grid')][string]$TrainingMode = 'grid-only',
    [string]$CommandFile,
    [switch]$Wait,
    [ValidateRange(1, 24)][int]$MaxHours = 12
)

$ErrorActionPreference = 'Stop'
$apiUri = [uri]$ApiBaseUrl
if ($apiUri.Scheme -ne 'http' -or $apiUri.Host -notin @('127.0.0.1', 'localhost', '[::1]', '::1')) {
    throw 'Only a local HTTP Admin API is supported.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
$commandPath = if ($CommandFile) {
    [IO.Path]::GetFullPath($CommandFile)
} else {
    # Preserve the original durable path: an upgrade must never silently start another run.
    Join-Path $runtimeRoot "grid-detector-learning-$GameId.json"
}
$statusPath = if ($CommandFile) {
    Join-Path ([IO.Path]::GetDirectoryName($commandPath)) ([IO.Path]::GetFileNameWithoutExtension($commandPath) + '-status.json')
} else {
    Join-Path $runtimeRoot "grid-detector-learning-$GameId-status.json"
}
$endpoint = "$($ApiBaseUrl.TrimEnd('/'))/api/v1/admin/games/$GameId/grid-correction-learning"
$headers = @{Origin = 'http://127.0.0.1:3000'; 'X-Admin-Intent' = 'local-owner'}
$metadataPath = $commandPath + '.game.json'
function Write-NewJson([string]$Path, $Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 12))
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}
if ((Test-Path -LiteralPath $metadataPath) -and -not (Test-Path -LiteralPath $commandPath)) {
    throw 'Command metadata exists without its saved command. Restore the original command; no new key was created.'
}
$createdCommand = -not (Test-Path -LiteralPath $commandPath)

# Save the exact command before transmission. Every rerun replays the same key.
if (-not (Test-Path -LiteralPath $commandPath)) {
    $command = [ordered]@{
        idempotencyKey = [guid]::NewGuid().ToString()
        prepareInBackground = $true
        preparationOnly = $false
        trainingMode = $TrainingMode
        policyVersion = 'application-grid-corrections-v4'
        validationAssignments = @{}
        historicalCohorts = @()
        importJobIds = @()
        exclusions = @()
    }
    Write-NewJson $commandPath $command
}
$body = Get-Content -LiteralPath $commandPath -Raw -Encoding UTF8
$saved = $body | ConvertFrom-Json
$savedMode = if ($saved.trainingMode) { $saved.trainingMode } else { 'grid-only' }
if ($savedMode -ne $TrainingMode) {
    throw "Saved command uses '$savedMode', requested '$TrainingMode'. The saved run was not changed or submitted. Use -TrainingMode $savedMode to replay it, or an unused -CommandFile for a separate future run."
}
if ($saved.idempotencyKey -isnot [string] -or [string]::IsNullOrWhiteSpace($saved.idempotencyKey)) {
    throw 'Saved command has no idempotency key. It was not changed or submitted.'
}
[guid]$savedKey = [guid]::Empty
if (-not [guid]::TryParse($saved.idempotencyKey, [ref]$savedKey) -or $savedKey -eq [guid]::Empty) {
    throw 'Saved command has an invalid idempotency key. It was not changed or submitted.'
}
$hashAlgorithm = [Security.Cryptography.SHA256]::Create()
try {
    $commandSha = [BitConverter]::ToString($hashAlgorithm.ComputeHash([IO.File]::ReadAllBytes($commandPath))).Replace('-', '').ToLowerInvariant()
} finally { $hashAlgorithm.Dispose() }
if (Test-Path -LiteralPath $metadataPath) {
    $binding = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($binding.version -ne 1 -or $binding.gameId -ne $GameId.ToString('D') -or
        $binding.idempotencyKey -ne $saved.idempotencyKey -or $binding.commandSha256 -ne $commandSha) {
        throw 'Saved command belongs to another game or its binding changed. It was not submitted.'
    }
} else {
    $legacyName = "grid-detector-learning-$GameId.json"
    if (-not $createdCommand -and [IO.Path]::GetFileName($commandPath) -ne $legacyName) {
        throw 'Existing custom command has no game binding. It was not submitted. Restore its metadata or use an unused command file.'
    }
    Write-NewJson $metadataPath ([ordered]@{version=1; gameId=$GameId.ToString('D');
        idempotencyKey=$saved.idempotencyKey; commandSha256=$commandSha})
}
# This operator command requires the durable preparation API. Ask the backend's
# OpenAPI contract before submitting; old installations must fail before training.
$contract = Invoke-RestMethod -Uri "$($ApiBaseUrl.TrimEnd('/'))/openapi.json" -TimeoutSec 15
$route = '/api/v1/admin/games/{game_id}/grid-correction-learning'
$schemaRef = $contract.paths.PSObject.Properties[$route].Value.post.requestBody.content.'application/json'.schema.'$ref'
$schemaName = ($schemaRef -split '/')[-1]
$properties = $contract.components.schemas.PSObject.Properties[$schemaName].Value.properties.PSObject.Properties.Name
if ('prepareInBackground' -notin $properties -or 'preparationOnly' -notin $properties) {
    throw 'The API does not support durable background preparation. Update the background-learning API before submitting this saved command.'
}
$run = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers `
    -ContentType 'application/json' -Body $body -TimeoutSec 30
$learningId = $run.learningId
Write-Output "Learning: $learningId"
if (-not $Wait) {
    $run | ConvertTo-Json -Depth 12
    return
}

$watchDeadline = [DateTimeOffset]::UtcNow.AddHours($MaxHours)
$lastOutput = ''
$readFailures = 0
do {
    try {
        $run = Invoke-RestMethod -Uri "$endpoint/$learningId" -TimeoutSec 15
        $readFailures = 0
    }
    catch {
        $readFailures++
        if ($readFailures -ge 5) { throw }
        Write-Warning "Status read failed ($readFailures/5). The saved job is retained."
        Start-Sleep -Seconds 15
        continue
    }
    $run | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $statusPath -Encoding UTF8
    $line = "$($run.status) | $($run.stage)"
    if ($null -ne $run.preparation) {
        $line += " | $($run.preparation.current)/$($run.preparation.total)"
        $line += " | heartbeat $($run.preparation.heartbeatAt)"
        if ($run.preparation.stalled) {
            Write-Warning 'No preparation progress for more than five minutes. Check the worker.'
        }
    }
    if ($line -ne $lastOutput) {
        Write-Output "$(Get-Date -Format o) $line"
        $lastOutput = $line
    }
    if ($run.status -eq 'completed') {
        if ($run.verdict -ne 'PASS' -or $null -eq $run.candidateVersionId) {
            throw "Learning completed without a usable candidate: $($run.verdict). See $statusPath"
        }
        Write-Output "Candidate ready: $($run.candidateVersionId). Report: $($run.reportId). Not activated."
        return
    }
    if ($run.status -in @('failed', 'cancelled', 'waiting_for_review')) {
        throw "Learning needs attention: $($run.status), $($run.errorCode). See $statusPath"
    }
    Start-Sleep -Seconds 15
} while ([DateTimeOffset]::UtcNow -lt $watchDeadline)
throw "Monitoring time ended; job $learningId remains saved. Rerun with -Wait to continue."

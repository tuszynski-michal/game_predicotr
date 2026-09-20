[CmdletBinding()]
param(
    [switch]$VerifyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$modelRoot = Join-Path $repositoryRoot "artifacts\m5-models\sequence-number-ocr-v1"
$archiveUrl = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0//en_PP-OCRv5_mobile_rec_infer.tar"
$expectedArchiveSha256 = "E595B4CF2FFAD19FBB5A61BA345D63939577A3AB8717B6E5995642590C9101B4"
$expectedFileSha256 = [ordered]@{
    "inference.json" = "FD1B6EC722EA841A72D3BA43E527DF1D1066D5D7808E0503EE3EEC7265188753"
    "inference.pdiparams" = "3EC8A97ED6CEFE8568D3E2EE90BB193299B566A7661AA4FD52D224B96B59F66B"
    "inference.yml" = "27E91D0582F40168AA218303C76E184BC78FA7A5D105AAD0CFBAD8458B441067"
}

function Test-ExpectedModel {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return $false
    }
    foreach ($entry in $expectedFileSha256.GetEnumerator()) {
        $filePath = Join-Path $Path $entry.Key
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            return $false
        }
        $actual = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash
        if ($actual -ne $entry.Value) {
            throw "Model file has an unexpected SHA-256: $filePath"
        }
    }
    return $true
}

if (Test-ExpectedModel -Path $modelRoot) {
    Write-Output "Verified v7 OCR model: $modelRoot"
    exit 0
}

if (Test-Path -LiteralPath $modelRoot) {
    throw "Refusing to overwrite an incomplete OCR model directory: $modelRoot"
}
if ($VerifyOnly) {
    throw "The verified v7 OCR model is not installed: $modelRoot"
}

$runtimeRoot = Join-Path $repositoryRoot ".runtime\v7-model-provision"
$sessionRoot = Join-Path $runtimeRoot ([Guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $sessionRoot "en_PP-OCRv5_mobile_rec_infer.tar"
$extractionRoot = Join-Path $sessionRoot "extract"
$stagedModelRoot = Join-Path $sessionRoot "model"
New-Item -ItemType Directory -Path $extractionRoot -Force | Out-Null
try {
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath -TimeoutSec 120
    $archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($archiveHash -ne $expectedArchiveSha256) {
        throw "Downloaded Paddle archive has an unexpected SHA-256."
    }
    & tar -xf $archivePath -C $extractionRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Could not extract the official Paddle model archive."
    }
    $extractedModel = Join-Path $extractionRoot "en_PP-OCRv5_mobile_rec_infer"
    foreach ($entry in $expectedFileSha256.GetEnumerator()) {
        $source = Join-Path $extractedModel $entry.Key
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Official Paddle archive does not contain $($entry.Key)."
        }
        $actual = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
        if ($actual -ne $entry.Value) {
            throw "Official Paddle model file has an unexpected SHA-256: $($entry.Key)"
        }
    }
    New-Item -ItemType Directory -Path $stagedModelRoot -ErrorAction Stop | Out-Null
    foreach ($fileName in $expectedFileSha256.Keys) {
        Copy-Item -LiteralPath (Join-Path $extractedModel $fileName) -Destination (Join-Path $stagedModelRoot $fileName) -ErrorAction Stop
    }
    if (-not (Test-ExpectedModel -Path $stagedModelRoot)) {
        throw "Staged OCR model did not pass verification."
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $modelRoot) -Force | Out-Null
    if (Test-Path -LiteralPath $modelRoot) {
        throw "Refusing to publish over an OCR model directory created during provisioning: $modelRoot"
    }
    [IO.Directory]::Move($stagedModelRoot, $modelRoot)
    if (-not (Test-ExpectedModel -Path $modelRoot)) { throw "Installed OCR model did not pass verification." }
    Write-Output "Installed verified v7 OCR model: $modelRoot"
}
finally {
    if (Test-Path -LiteralPath $sessionRoot) {
        Remove-Item -LiteralPath $sessionRoot -Recurse -Force
    }
}

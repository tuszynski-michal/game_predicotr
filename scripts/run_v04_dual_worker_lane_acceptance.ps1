[CmdletBinding()]
param(
    [ValidateRange(30, 600)]
    [int]$TimeoutSeconds = 180,

    [string]$Output = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$composePath = Join-Path $repositoryRoot 'infra\docker\compose.yaml'
$artifactRoot = Join-Path $repositoryRoot 'artifacts\v04-dual-worker-lane-acceptance'
$pytestTempRoot = Join-Path $repositoryRoot '.pytest-tmp'
$runId = [Guid]::NewGuid().ToString('N')
$pytestBaseTemp = Join-Path $pytestTempRoot "v04-lanes-$($runId.Substring(0, 8))"
$checks = [Collections.Generic.List[object]]::new()
$failure = $null
$processEnvironmentScript = Join-Path $PSScriptRoot 'windows_process_environment.ps1'

if (-not (Test-Path -LiteralPath $processEnvironmentScript -PathType Leaf)) {
    throw "Windows process environment helper is unavailable: $processEnvironmentScript"
}
. $processEnvironmentScript
Repair-WindowsProcessPath

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $artifactRoot 'acceptance-report.json'
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Python virtual environment is unavailable: $pythonPath"
}

$dockerCommand = Get-Command -Name 'docker.exe' -ErrorAction SilentlyContinue
$dockerDesktopUserPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
$dockerDesktopPath = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
if ($null -ne $dockerCommand) {
    $dockerPath = $dockerCommand.Source
}
elseif (Test-Path -LiteralPath $dockerDesktopUserPath -PathType Leaf) {
    $dockerPath = $dockerDesktopUserPath
}
elseif (Test-Path -LiteralPath $dockerDesktopPath -PathType Leaf) {
    $dockerPath = $dockerDesktopPath
}
else {
    throw 'Docker CLI is unavailable. Start Docker Desktop and check the Windows environment.'
}

$powershellPath = (Get-Command -Name 'powershell.exe' -ErrorAction Stop).Source

function Invoke-BoundedStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [hashtable]$Environment = @{}
    )

    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $process = $null
    $processStarted = $false
    try {
        $startInfo = [Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $FilePath
        $startInfo.WorkingDirectory = $repositoryRoot
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.Arguments = (
            $Arguments | ForEach-Object {
                if ($_ -match '[\s"]') {
                    '"' + $_.Replace('"', '\"') + '"'
                }
                else {
                    $_
                }
            }
        ) -join ' '
        foreach ($entry in $Environment.GetEnumerator()) {
            $startInfo.EnvironmentVariables[$entry.Key] = [string]$entry.Value
        }

        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            throw "$Name did not start."
        }
        $processStarted = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            [void]$process.WaitForExit(5000)
            throw "$Name exceeded the per-step timeout of $TimeoutSeconds seconds."
        }

        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            $details = if ([string]::IsNullOrWhiteSpace($stderr)) {
                $stdout.Trim()
            }
            else {
                $stderr.Trim()
            }
            throw "$Name failed with exit code $($process.ExitCode). $details"
        }

        $stopwatch.Stop()
        $checks.Add(
            [ordered]@{
                name = $Name
                status = 'passed'
                durationSeconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
                exitCode = 0
            }
        )
        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            Write-Host $stdout.TrimEnd()
        }
    }
    catch {
        $stopwatch.Stop()
        $checks.Add(
            [ordered]@{
                name = $Name
                status = 'failed'
                durationSeconds = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 3)
                exitCode = if ($processStarted -and $process.HasExited) {
                    $process.ExitCode
                }
                else {
                    $null
                }
            }
        )
        throw
    }
    finally {
        if ($processStarted -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
}

try {
    New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $pytestTempRoot -Force | Out-Null

    Invoke-BoundedStep `
        -Name 'postgres-ready' `
        -FilePath $dockerPath `
        -Arguments @('compose', '-f', $composePath, 'up', '-d', '--wait', 'postgres')

    Invoke-BoundedStep `
        -Name 'isolated-postgres-lane-contract' `
        -FilePath $pythonPath `
        -Arguments @(
            '-m', 'pytest',
            'services/api/tests/integration/test_worker_job_store.py::test_worker_store_claims_general_and_image_selection_lanes_independently',
            'services/api/tests/integration/test_worker_job_store.py::test_worker_store_recovers_and_cancels_each_lane_independently',
            '--basetemp', $pytestBaseTemp,
            '-ra'
        ) `
        -Environment @{ GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1' }

    Invoke-BoundedStep `
        -Name 'worker-runtime-and-cli-regression' `
        -FilePath $pythonPath `
        -Arguments @(
            '-m', 'pytest',
            'services/worker/tests/test_job_runtime.py',
            'services/worker/tests/test_worker_cli.py',
            '--basetemp', $pytestBaseTemp,
            '-ra'
        )

    Invoke-BoundedStep `
        -Name 'powershell-syntax' `
        -FilePath $powershellPath `
        -Arguments @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', 'scripts/check_powershell_syntax.ps1'
        )

    Invoke-BoundedStep `
        -Name 'worker-supervisor-read-only-status' `
        -FilePath $powershellPath `
        -Arguments @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', 'scripts/manage_worker_lanes.ps1',
            '-Action', 'Status',
            '-Json'
        )
}
catch {
    $failure = $_.Exception.Message
}
finally {
    $resolvedTempRoot = [IO.Path]::GetFullPath($pytestTempRoot)
    $resolvedTemp = [IO.Path]::GetFullPath($pytestBaseTemp)
    if (
        (Test-Path -LiteralPath $resolvedTemp) -and
        $resolvedTemp.StartsWith(
            $resolvedTempRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }

    $report = [ordered]@{
        schemaVersion = 1
        acceptanceProfile = 'v0.4-dual-worker-lanes'
        generatedAt = [DateTimeOffset]::UtcNow.ToString('o')
        status = if ($null -eq $failure) { 'passed' } else { 'failed' }
        isolatedPostgres = $true
        includesOwnerData = $false
        startsWorkerProcesses = $false
        perStepTimeoutSeconds = $TimeoutSeconds
        checks = $checks
        failure = $failure
    }
    $resolvedOutput = [IO.Path]::GetFullPath($Output)
    New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedOutput) -Force |
        Out-Null
    [IO.File]::WriteAllText(
        $resolvedOutput,
        ($report | ConvertTo-Json -Depth 6),
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host "Acceptance report: $resolvedOutput"
}

if ($null -ne $failure) {
    throw $failure
}

Write-Host 'Dual worker lane acceptance passed.'

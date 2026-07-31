[CmdletBinding()]
param(
    [ValidateRange(30, 300)]
    [int]$TimeoutSeconds = 120,

    [string]$Output = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$composePath = Join-Path $repositoryRoot 'infra\docker\compose.yaml'
$artifactRoot = Join-Path $repositoryRoot 'artifacts\v02-admin-acceptance'
$pytestTempRoot = Join-Path $repositoryRoot '.pytest-tmp'
$runId = [Guid]::NewGuid().ToString('N')
$pytestBaseTemp = Join-Path $pytestTempRoot "v02-$($runId.Substring(0, 8))"
$checks = [Collections.Generic.List[object]]::new()
$failure = $null
$pathValue = $env:Path
Remove-Item Env:PATH -ErrorAction SilentlyContinue
$env:Path = $pathValue

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $artifactRoot 'acceptance-report.json'
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python virtual environment is missing: $pythonPath"
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$dockerDesktopPath = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$dockerDesktopUserPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
if ($null -ne $dockerCommand) {
    $dockerPath = $dockerCommand.Source
}
elseif (Test-Path -LiteralPath $dockerDesktopUserPath) {
    $dockerPath = $dockerDesktopUserPath
}
elseif (Test-Path -LiteralPath $dockerDesktopPath) {
    $dockerPath = $dockerDesktopPath
}
else {
    throw 'Docker CLI is missing. Install and start Docker Desktop before running acceptance.'
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    throw 'npm.cmd is missing from PATH. Run npm run windows:environment:setup first.'
}

function Invoke-BoundedStep {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [hashtable]$Environment = @{}
    )

    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $process = $null
    $processStarted = $false
    $stdoutTask = $null
    $stderrTask = $null
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
            throw "$Name exceeded the timeout of $TimeoutSeconds seconds."
        }

        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            $message = if ([string]::IsNullOrWhiteSpace($stderr)) {
                $stdout.Trim()
            }
            else {
                $stderr.Trim()
            }
            throw "$Name failed with exit code $($process.ExitCode). $message"
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
                exitCode = if ($null -ne $process -and $process.HasExited) {
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
        if ($processStarted -and $null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
}

try {
    New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null

    Invoke-BoundedStep `
        -Name 'postgres-ready' `
        -FilePath $dockerPath `
        -Arguments @('compose', '-f', $composePath, 'up', '-d', '--wait', 'postgres')

    Invoke-BoundedStep `
        -Name 'postgres-integration' `
        -FilePath $pythonPath `
        -Arguments @(
            '-m', 'pytest',
            'services/api/tests/integration/test_m2_admin_acceptance.py',
            'services/api/tests/integration/test_release_workflow_integration.py',
            'services/api/tests/integration/test_cleanup_repository.py',
            '--basetemp', $pytestBaseTemp,
            '-ra'
        ) `
        -Environment @{ GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1' }

    Invoke-BoundedStep `
        -Name 'admin-tests' `
        -FilePath $npmCommand.Source `
        -Arguments @('run', 'test', '--workspace', '@game-predictor/admin')

    Invoke-BoundedStep `
        -Name 'admin-typecheck' `
        -FilePath $npmCommand.Source `
        -Arguments @('run', 'typecheck', '--workspace', '@game-predictor/admin')

    Invoke-BoundedStep `
        -Name 'admin-lint' `
        -FilePath $npmCommand.Source `
        -Arguments @('run', 'lint', '--workspace', '@game-predictor/admin')

    Invoke-BoundedStep `
        -Name 'openapi-contract' `
        -FilePath $npmCommand.Source `
        -Arguments @('run', 'openapi:check')

    Invoke-BoundedStep `
        -Name 'admin-production-build' `
        -FilePath $npmCommand.Source `
        -Arguments @('run', 'admin:build')
}
catch {
    $failure = $_.Exception.Message
}
finally {
    $resolvedPytestRoot = [IO.Path]::GetFullPath($pytestTempRoot)
    $resolvedPytestTemp = [IO.Path]::GetFullPath($pytestBaseTemp)
    if (
        (Test-Path -LiteralPath $resolvedPytestTemp) -and
        $resolvedPytestTemp.StartsWith(
            $resolvedPytestRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        try {
            Remove-Item `
                -LiteralPath $resolvedPytestTemp `
                -Recurse `
                -Force `
                -ErrorAction SilentlyContinue
        }
        catch {
            Write-Warning 'Temporary acceptance files could not be removed completely.'
        }
    }

    $report = [ordered]@{
        schemaVersion = 1
        acceptanceProfile = 'admin-v0.2'
        generatedAt = [DateTimeOffset]::UtcNow.ToString('o')
        status = if ($null -eq $failure) { 'passed' } else { 'failed' }
        isolatedPostgres = $true
        includesOwnerData = $false
        checks = $checks
        failure = $failure
    }
    $outputDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($Output))
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Output -Encoding utf8
    Write-Host "Acceptance report: $Output"
}

if ($null -ne $failure) {
    throw $failure
}

Write-Host 'Admin 0.2 automated acceptance passed.'

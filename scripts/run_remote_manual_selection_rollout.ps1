[CmdletBinding()]
param(
    [switch]$Check,

    [string]$Observation = '',

    [string]$Output = '',

    [switch]$AllowLarge,

    [string]$OwnerApproval = '',

    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$script = Join-Path $repositoryRoot 'scripts\run_remote_manual_selection_rollout.py'
$process = $null

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment is missing: $python"
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $repositoryRoot 'artifacts\remote-manual-selection-rollout\stage-1.json'
}

$arguments = @("`"$script`"", '--output', "`"$Output`"")
if ($Check) {
    $arguments += '--check'
}
if (-not [string]::IsNullOrWhiteSpace($Observation)) {
    $arguments += @('--observation', "`"$Observation`"")
}
if ($AllowLarge) {
    $arguments += '--allow-large'
}
if (-not [string]::IsNullOrWhiteSpace($OwnerApproval)) {
    $arguments += @('--owner-approval', "`"$OwnerApproval`"")
}

try {
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $python
    $startInfo.Arguments = $arguments -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw 'Remote-selection rollout process did not start.'
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.WaitForExit(5000) | Out-Null
        throw "Remote-selection rollout exceeded the timeout of $TimeoutSeconds seconds."
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        Write-Output $stdout.TrimEnd()
    }
    if ($process.ExitCode -ne 0) {
        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            Write-Error $stderr.TrimEnd()
        }
        throw "Remote-selection rollout failed with exit code $($process.ExitCode)."
    }
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $process) {
        $process.Dispose()
    }
}

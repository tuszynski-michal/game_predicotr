[CmdletBinding()]
param(
    [ValidateSet('smoke', '10000', '30000')]
    [string]$Profile = 'smoke',

    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 120,

    [string]$Output = ''
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$script = Join-Path $repositoryRoot 'scripts\run_image_selection_benchmark.py'
$artifactRoot = Join-Path $repositoryRoot 'artifacts'
$runId = [Guid]::NewGuid().ToString('N')
$workRoot = Join-Path $artifactRoot "image-selection-benchmark-$runId"
$process = $null
$stdoutTask = $null
$stderrTask = $null

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment is missing: $python"
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $repositoryRoot "ai_docs\quality\image-selection-$Profile-report.json"
}

$arguments = @(
    "`"$script`"",
    '--profile', $Profile,
    '--max-seconds', $TimeoutSeconds,
    '--output', "`"$Output`"",
    '--work-root', "`"$workRoot`""
) -join ' '

try {
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $python
    $startInfo.Arguments = $arguments
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw 'Image-selection benchmark process did not start.'
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()

    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.WaitForExit(5000) | Out-Null
        throw "Image-selection benchmark exceeded the external timeout of $TimeoutSeconds seconds."
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
        throw "Image-selection benchmark failed with exit code $($process.ExitCode)."
    }
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    $resolvedArtifacts = [IO.Path]::GetFullPath($artifactRoot)
    $resolvedWorkRoot = [IO.Path]::GetFullPath($workRoot)
    if (
        (Test-Path -LiteralPath $resolvedWorkRoot) -and
        $resolvedWorkRoot.StartsWith(
            $resolvedArtifacts + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        Remove-Item -LiteralPath $resolvedWorkRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $resolvedWorkRoot) {
        throw "Image-selection benchmark cleanup failed: $resolvedWorkRoot"
    }
    if ($null -ne $process) {
        $process.Dispose()
    }
}

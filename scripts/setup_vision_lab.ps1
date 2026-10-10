param(
    [ValidateSet('Create', 'Cuda', 'Dependencies', 'Project', 'Check')]
    [string]$Step = 'Check',
    [ValidateRange(1, 120)][int]$TimeoutSeconds = 120
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$labPython = Join-Path $repoRoot '.venv-vision-lab\Scripts\python.exe'
$basePython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if ($Step -eq 'Create' -and (Test-Path -LiteralPath $labPython)) {
    Write-Output 'Isolated environment already exists; use the remaining bounded steps.'
    exit 0
}
$argsList = switch ($Step) {
    'Create' { @('-m', 'venv', '.venv-vision-lab') }
    'Cuda' { @('-m', 'pip', 'install', '--disable-pip-version-check', '--timeout', '20', '--retries', '1', '--index-url', 'https://download.pytorch.org/whl/cu130', '-c', 'constraints-vision-lab.txt', 'torch==2.12.1+cu130', 'torchvision==0.27.1+cu130') }
    'Dependencies' { @('-m', 'pip', 'install', '--disable-pip-version-check', '--timeout', '20', '--retries', '1', '-c', 'constraints-vision-lab.txt', '-r', 'requirements-vision-lab.txt') }
    'Project' { @('-m', 'pip', 'install', '--disable-pip-version-check', '--timeout', '20', '--retries', '1', '--no-deps', '--editable', '.') }
    'Check' { @('scripts/check_vision_lab_gpu.py') }
}
$executable = if ($Step -eq 'Create') { $basePython } else { $labPython }
$process = Start-Process -FilePath $executable -ArgumentList $argsList -WorkingDirectory $repoRoot -PassThru -NoNewWindow
if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    # Terminate this process tree, never an unrelated service or an unverified PID.
    & taskkill.exe /PID $process.Id /T /F | Out-Null
    $process.WaitForExit(10000) | Out-Null
    throw "Vision lab $Step timeout ${TimeoutSeconds}s (PID $($process.Id))"
}
if ($process.ExitCode -ne 0) { throw "Vision lab $Step exit $($process.ExitCode)" }

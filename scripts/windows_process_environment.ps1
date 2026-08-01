Set-StrictMode -Version Latest

function Repair-WindowsProcessPath {
    [CmdletBinding()]
    param(
        [string[]]$PreferredEntries = @()
    )

    if ($env:OS -ne 'Windows_NT') {
        return
    }

    $processVariables = [Environment]::GetEnvironmentVariables('Process')
    $pathValues = [System.Collections.Generic.List[string]]::new()
    foreach ($key in $processVariables.Keys) {
        if ([string]$key -ieq 'Path') {
            $pathValues.Add([string]$processVariables[$key])
        }
    }

    $mergedEntries = [System.Collections.Generic.List[string]]::new()
    foreach ($entry in $PreferredEntries + @($pathValues)) {
        foreach ($candidateValue in ([string]$entry -split ';')) {
            $candidate = $candidateValue.Trim()
            if (-not $candidate) {
                continue
            }
            $normalizedCandidate = $candidate.TrimEnd('\', '/')
            if (-not ($mergedEntries | Where-Object {
                        $_.TrimEnd('\', '/') -ieq $normalizedCandidate
                    })) {
                $mergedEntries.Add($candidate)
            }
        }
    }

    # Windows treats environment names case-insensitively, but a process can
    # still inherit an invalid block containing both Path and PATH. Remove the
    # uppercase variant first and recreate one canonical process variable.
    [Environment]::SetEnvironmentVariable('PATH', $null, 'Process')
    [Environment]::SetEnvironmentVariable(
        'Path',
        ($mergedEntries -join ';'),
        'Process'
    )

    $pathKeys = @(
        [Environment]::GetEnvironmentVariables('Process').Keys |
            Where-Object { [string]$_ -ieq 'Path' }
    )
    if ($pathKeys.Count -ne 1) {
        throw 'Windows process environment could not be normalized to one Path variable.'
    }
}

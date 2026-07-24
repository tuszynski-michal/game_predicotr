[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$parseFailures = @()
$scripts = Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' -File

foreach ($script in $scripts) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $script.FullName,
        [ref]$tokens,
        [ref]$errors
    )

    foreach ($parseError in $errors) {
        $parseFailures += "$($script.Name):$($parseError.Extent.StartLineNumber): $($parseError.Message)"
    }
}

if ($parseFailures.Count -gt 0) {
    throw "PowerShell syntax errors:`n$($parseFailures -join "`n")"
}

Write-Host "PowerShell syntax is valid for $($scripts.Count) script(s)."

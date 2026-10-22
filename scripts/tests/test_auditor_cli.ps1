$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $repositoryRoot 'scripts/audit_task.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw ($parseErrors | Out-String) }
$resolver = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Resolve-AuditorCli'
}, $true)
. ([scriptblock]::Create($resolver.Extent.Text))

# Load only the resolver: never execute an audit or contact a model in this test.
$script:commandSource = $null
function Get-Command {
    param($Name, $CommandType, $ErrorAction)
    if ($script:commandSource) { [pscustomobject]@{ Source = $script:commandSource } }
}
function Assert-Equal($Expected, $Actual, $Label) {
    if ($Expected -ne $Actual) { throw "$Label expected '$Expected', got '$Actual'" }
    Write-Output "PASS: $Label"
}
$argumentBuilder = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
    $node.Extent.Text.Contains('$helpArguments = @(''exec'', ''--help'')')
}, $true)
if ($null -eq $argumentBuilder) { throw 'Auditor argument builder not found' }
$Auditor = 'claude'
foreach ($Effort in @('medium', 'high', '')) {
    $cliArguments = @()
    $requiredFlags = @()
    . ([scriptblock]::Create($argumentBuilder.Extent.Text))
    $expected = '-p --permission-mode plan'
    if ($Effort -ne '') { $expected += " --effort $Effort" }
    Assert-Equal $expected ($cliArguments -join ' ') "Claude argument construction ($Effort)"
    Assert-Equal ($Effort -ne '') ($requiredFlags -contains '--effort') 'Validate advertised effort support'
}
function Add-CliFixture($RelativePath) {
    $path = Join-Path $fixture $RelativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [System.IO.File]::WriteAllText($path, '')
    return $path
}
$artifactRoot = Join-Path $repositoryRoot 'artifacts'
$fixture = Join-Path $artifactRoot ('auditor-cli-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -Force | Out-Null
try {
    Assert-Equal $null (Resolve-AuditorCli claude $fixture) 'missing installation'
    $older = Add-CliFixture 'AppData/Local/Packages/Claude_test/LocalCache/Roaming/Claude/claude-code/2.1.9/hash/claude.exe'
    Assert-Equal $older (Resolve-AuditorCli claude $fixture) 'packaged CLI without PATH'
    $newer = Add-CliFixture 'AppData/Local/Packages/Claude_test/LocalCache/Roaming/Claude/claude-code/2.1.10/hash/claude.exe'
    Add-CliFixture 'AppData/Local/Packages/Claude_test/LocalCache/Roaming/Claude/claude-code/not-a-version/hash/claude.exe' | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $fixture 'AppData/Local/Packages/Claude_test/LocalCache/Roaming/Claude/claude-code/99.0.0/incomplete') -Force | Out-Null
    Assert-Equal $newer (Resolve-AuditorCli claude $fixture) 'updated numeric version; ignore incomplete/invalid versions'
    Assert-Equal $null (Resolve-AuditorCli codex $fixture) 'do not substitute Claude for Codex'
    Assert-Equal $null (Resolve-AuditorCli git $fixture) 'do not substitute Claude for Git'
    $roaming = Add-CliFixture 'AppData/Roaming/Claude/claude-code/3.0.0/hash/claude.exe'
    Assert-Equal $roaming (Resolve-AuditorCli claude $fixture) 'unpackaged Roaming installation'
    $desktop = Add-CliFixture 'AppData/Local/Claude-Data/claude_test/claude-code/3.1.9/hash/claude.exe'
    Assert-Equal $desktop (Resolve-AuditorCli claude $fixture) 'desktop data installation without PATH'
    $desktopUpdate = Add-CliFixture 'AppData/Local/Claude-Data/claude_other/claude-code/3.1.10/new-hash/claude.exe'
    Add-CliFixture 'AppData/Local/Claude-Data/claude_other/claude-code/not-a-version/hash/claude.exe' | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $fixture 'AppData/Local/Claude-Data/claude_other/claude-code/99.0.0/incomplete') -Force | Out-Null
    Assert-Equal $desktopUpdate (Resolve-AuditorCli claude $fixture) 'desktop update; ignore invalid and incomplete versions'
    $native = Add-CliFixture '.local/bin/claude.exe'
    Assert-Equal $native (Resolve-AuditorCli claude $fixture) 'native installation precedence'
    $script:commandSource = 'C:\explicit\claude.cmd'
    Assert-Equal $script:commandSource (Resolve-AuditorCli claude $fixture) 'PATH precedence'
} finally {
    $resolvedFixture = [System.IO.Path]::GetFullPath($fixture)
    $allowedRoot = [System.IO.Path]::GetFullPath($artifactRoot) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedFixture.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Fixture cleanup escaped artifact root'
    }
    Remove-Item -LiteralPath $resolvedFixture -Recurse -Force
}

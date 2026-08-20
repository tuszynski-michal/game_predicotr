Set-StrictMode -Version Latest

function Get-ReviewerLifecycleMutexName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot
    )

    $normalizedRoot = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\').ToLowerInvariant()
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalizedRoot))
    }
    finally {
        $sha256.Dispose()
    }
    $identity = ([BitConverter]::ToString($digest)).Replace('-', '').Substring(0, 24)
    return "Local\GamePredictor.ReviewerLifecycle.$identity"
}

function Enter-ReviewerLifecycleLock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProjectRoot,
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 60000)]
        [int]$TimeoutMilliseconds
    )

    $mutexName = Get-ReviewerLifecycleMutexName -ProjectRoot $ProjectRoot
    $createdNew = $false
    $mutex = [Threading.Mutex]::new($false, $mutexName, [ref]$createdNew)
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne($TimeoutMilliseconds)
        }
        catch [Threading.AbandonedMutexException] {
            $acquired = $true
        }
        if (-not $acquired) {
            throw "Reviewer lifecycle is busy in another Windows process. Retry the operation."
        }
        return $mutex
    }
    catch {
        if (-not $acquired) {
            $mutex.Dispose()
        }
        throw
    }
}

function Exit-ReviewerLifecycleLock {
    param(
        [Parameter(Mandatory = $true)]
        [Threading.Mutex]$Mutex
    )

    try {
        $Mutex.ReleaseMutex()
    }
    finally {
        $Mutex.Dispose()
    }
}

function Write-ReviewerAtomicJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath,
        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    $directory = Split-Path -Parent $LiteralPath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = Join-Path $directory (
        ".{0}.{1}.tmp" -f ([IO.Path]::GetFileName($LiteralPath)), ([Guid]::NewGuid().ToString('N'))
    )
    try {
        [IO.File]::WriteAllText(
            $temporaryPath,
            ($Value | ConvertTo-Json -Depth 8),
            [Text.UTF8Encoding]::new($false)
        )
        if (Test-Path -LiteralPath $LiteralPath -PathType Leaf) {
            [IO.File]::Replace($temporaryPath, $LiteralPath, $null, $true)
        }
        else {
            [IO.File]::Move($temporaryPath, $LiteralPath)
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Read-ReviewerJsonState {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath
    )

    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $LiteralPath -Raw -Encoding utf8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function New-ReviewerProcessIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)]
        [Guid]$InstanceId
    )

    $executablePath = Get-ReviewerProcessExecutablePath -Process $Process
    if ([string]::IsNullOrWhiteSpace($executablePath)) {
        throw "Cannot determine the executable path for PID $($Process.Id)."
    }
    return [ordered]@{
        instanceId = $InstanceId.ToString('D')
        pid = $Process.Id
        processStartedAt = $Process.StartTime.ToUniversalTime().ToString('o')
        executablePath = [IO.Path]::GetFullPath($executablePath)
        processName = $Process.ProcessName
    }
}

function Get-ReviewerProcessExecutablePath {
    param(
        [Parameter(Mandatory = $true)]
        [Diagnostics.Process]$Process,
        [ValidateRange(1, 20)]
        [int]$MaximumAttempts = 10,
        [ValidateRange(0, 500)]
        [int]$RetryDelayMilliseconds = 50
    )

    for ($attempt = 0; $attempt -lt $MaximumAttempts; $attempt++) {
        $Process.Refresh()
        if ($Process.HasExited) {
            return $null
        }

        $candidates = [Collections.Generic.List[string]]::new()
        try {
            if (-not [string]::IsNullOrWhiteSpace($Process.Path)) {
                $candidates.Add([string]$Process.Path)
            }
        }
        catch {
            # Process.Path is transiently unavailable for some Windows executables.
        }
        try {
            if (-not [string]::IsNullOrWhiteSpace($Process.MainModule.FileName)) {
                $candidates.Add([string]$Process.MainModule.FileName)
            }
        }
        catch {
            # MainModule can have the same transient access window as Process.Path.
        }
        if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
            try {
                $record = Get-CimInstance `
                    -ClassName Win32_Process `
                    -Filter "ProcessId = $($Process.Id)" `
                    -ErrorAction Stop
                if (-not [string]::IsNullOrWhiteSpace($record.ExecutablePath)) {
                    $candidates.Add([string]$record.ExecutablePath)
                }
            }
            catch {
                # The managed probes remain authoritative when WMI is unavailable.
            }
        }

        foreach ($candidate in $candidates) {
            try {
                return [IO.Path]::GetFullPath($candidate)
            }
            catch {
                # Continue to the next independently obtained candidate.
            }
        }
        if ($attempt + 1 -lt $MaximumAttempts -and $RetryDelayMilliseconds -gt 0) {
            Start-Sleep -Milliseconds $RetryDelayMilliseconds
        }
    }
    return $null
}

function Resolve-ReviewerPublicOriginAddress {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName
    )

    try {
        $local = Resolve-DnsName `
            -Name $HostName `
            -Type A `
            -DnsOnly `
            -QuickTimeout `
            -ErrorAction Stop
        $addresses = @(
            $local |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_.IPAddress) } |
                ForEach-Object { [string]$_.IPAddress } |
                Sort-Object -Unique
        )
        if ($addresses.Count -gt 0) {
            return [pscustomobject]@{
                usesSystemDns = $true
                addresses = $addresses
            }
        }
    }
    catch {
        # A newly created Quick Tunnel can be hidden by a local negative DNS cache.
    }

    foreach ($server in @("1.1.1.1", "8.8.8.8")) {
        try {
            $public = Resolve-DnsName `
                -Name $HostName `
                -Type A `
                -Server $server `
                -DnsOnly `
                -QuickTimeout `
                -ErrorAction Stop
            $addresses = @(
                $public |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_.IPAddress) } |
                    ForEach-Object { [string]$_.IPAddress } |
                    Sort-Object -Unique
            )
            if ($addresses.Count -gt 0) {
                return [pscustomobject]@{
                    usesSystemDns = $false
                    addresses = $addresses
                }
            }
        }
        catch {
            # Try the next bounded public resolver.
        }
    }
    try {
        $dnsOverHttpsUri = (
            "https://cloudflare-dns.com/dns-query?name=" +
            [Uri]::EscapeDataString($HostName) +
            "&type=A"
        )
        $dnsOverHttps = Invoke-RestMethod `
            -Uri $dnsOverHttpsUri `
            -Headers @{ Accept = "application/dns-json" } `
            -TimeoutSec 5 `
            -ErrorAction Stop
        if ([int]$dnsOverHttps.Status -eq 0) {
            $addresses = @(Get-ReviewerDnsJsonIpv4Address -Response $dnsOverHttps)
            if ($addresses.Count -gt 0) {
                return [pscustomobject]@{
                    usesSystemDns = $false
                    addresses = $addresses
                }
            }
        }
    }
    catch {
        # The bounded controller will retry or fail closed when DoH is unavailable.
    }
    return [pscustomobject]@{
        usesSystemDns = $false
        addresses = @()
    }
}

function Get-ReviewerDnsJsonIpv4Address {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Response
    )

    $addresses = [Collections.Generic.List[string]]::new()
    foreach ($answer in @($Response.Answer)) {
        if ([int]$answer.type -ne 1) {
            continue
        }
        $parsedAddress = $null
        if (
            [Net.IPAddress]::TryParse([string]$answer.data, [ref]$parsedAddress) -and
            $parsedAddress.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork
        ) {
            $addresses.Add($parsedAddress.ToString())
        }
    }
    return @($addresses | Sort-Object -Unique)
}

function Invoke-ReviewerPublicOriginProbe {
    param(
        [Parameter(Mandatory = $true)]
        [Uri]$PublicUri,
        [Parameter(Mandatory = $true)]
        [object]$Resolution
    )

    if ([bool]$Resolution.usesSystemDns) {
        try {
            $response = Invoke-WebRequest `
                -Uri $PublicUri.AbsoluteUri `
                -UseBasicParsing `
                -TimeoutSec 5
            return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
        }
        catch {
            return $false
        }
    }

    $curl = Get-Command -Name "curl.exe" -ErrorAction SilentlyContinue
    if ($null -eq $curl) {
        return $false
    }
    foreach ($address in @($Resolution.addresses)) {
        try {
            $statusText = & $curl.Source `
                --silent `
                --show-error `
                --output NUL `
                --write-out '%{http_code}' `
                --connect-timeout 3 `
                --max-time 5 `
                --resolve "$($PublicUri.DnsSafeHost):443:$address" `
                $PublicUri.AbsoluteUri `
                2>$null
            if ($LASTEXITCODE -ne 0) {
                continue
            }
            $statusCode = 0
            if (
                [int]::TryParse(
                    ([string]$statusText).Trim(),
                    [ref]$statusCode
                ) -and
                $statusCode -ge 200 -and
                $statusCode -lt 500
            ) {
                return $true
            }
        }
        catch {
            # Try the next independently resolved address.
        }
    }
    return $false
}

function Test-ReviewerPublicOriginReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PublicOrigin,
        [scriptblock]$Resolver = $null,
        [scriptblock]$Probe = $null
    )

    try {
        $publicUri = [Uri]$PublicOrigin
        if (
            $publicUri.Scheme -ne "https" -or
            $publicUri.DnsSafeHost -notlike "*.trycloudflare.com" -or
            -not $publicUri.IsDefaultPort -or
            $publicUri.AbsolutePath -ne "/" -or
            -not [string]::IsNullOrWhiteSpace($publicUri.Query) -or
            -not [string]::IsNullOrWhiteSpace($publicUri.Fragment)
        ) {
            return $false
        }
        $resolution = if ($null -eq $Resolver) {
            Resolve-ReviewerPublicOriginAddress -HostName $publicUri.DnsSafeHost
        }
        else {
            & $Resolver $publicUri.DnsSafeHost
        }
        if ($null -eq $resolution -or @($resolution.addresses).Count -eq 0) {
            return $false
        }
        if ($null -ne $Probe) {
            return [bool](& $Probe $publicUri $resolution)
        }
        return Invoke-ReviewerPublicOriginProbe `
            -PublicUri $publicUri `
            -Resolution $resolution
    }
    catch {
        return $false
    }
}

function Test-ReviewerProcessIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [object]$State,
        [string]$ExpectedProcessName = ""
    )

    try {
        $instanceId = [Guid]::Parse([string]$State.instanceId)
        if ($instanceId -eq [Guid]::Empty) {
            throw "Empty instance id."
        }
        $expectedPid = [int]$State.pid
        $expectedStartedAt = [DateTimeOffset]::Parse([string]$State.processStartedAt)
        $expectedExecutable = [IO.Path]::GetFullPath([string]$State.executablePath)
        $process = Get-Process -Id $expectedPid -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            return [pscustomobject]@{ isMatch = $false; process = $null; reason = "missing" }
        }
        $process.Refresh()
        if (
            -not [string]::IsNullOrWhiteSpace($ExpectedProcessName) -and
            $process.ProcessName -notlike $ExpectedProcessName
        ) {
            return [pscustomobject]@{ isMatch = $false; process = $process; reason = "name" }
        }
        if ($process.StartTime.ToUniversalTime().Ticks -ne $expectedStartedAt.UtcDateTime.Ticks) {
            return [pscustomobject]@{ isMatch = $false; process = $process; reason = "start-time" }
        }
        $actualExecutable = Get-ReviewerProcessExecutablePath -Process $process
        if ([string]::IsNullOrWhiteSpace($actualExecutable)) {
            return [pscustomobject]@{
                isMatch = $false
                process = $process
                reason = "executable-unavailable"
            }
        }
        if (-not $actualExecutable.Equals($expectedExecutable, [StringComparison]::OrdinalIgnoreCase)) {
            return [pscustomobject]@{ isMatch = $false; process = $process; reason = "executable" }
        }
        return [pscustomobject]@{ isMatch = $true; process = $process; reason = "matched" }
    }
    catch {
        return [pscustomobject]@{ isMatch = $false; process = $null; reason = "invalid-state" }
    }
}

function New-ReviewerAttemptPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RuntimeDirectory,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[a-z0-9-]+$')]
        [string]$Prefix,
        [Parameter(Mandatory = $true)]
        [Guid]$InstanceId,
        [ValidateRange(0, 99)]
        [int]$Attempt = 0
    )

    $logDirectory = Join-Path $RuntimeDirectory "reviewer-lifecycle-logs"
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stem = "{0}-{1}-{2:D2}" -f $Prefix, $InstanceId.ToString('N'), $Attempt
    return [pscustomobject]@{
        out = Join-Path $logDirectory "$stem.out.log"
        error = Join-Path $logDirectory "$stem.error.log"
        process = Join-Path $logDirectory "$stem.process.log"
    }
}

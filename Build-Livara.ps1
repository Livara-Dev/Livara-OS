#Requires -Version 5.1
<# Builds on the user's Windows machine. No ISO is included in the source kit. #>
[CmdletBinding()]
param(
    [switch]$Check,
    [ValidateRange(1, 16)][int]$Jobs = 2,
    [string]$CaBundle = $env:LIVARA_BUILD_CA,
    [switch]$KeepWork,
    [switch]$NoPause
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:LivaraDocker = $null
$script:LivaraContext = $null
$runId = [Guid]::NewGuid().ToString('N').Substring(0, 16)
$createdVolumes = New-Object 'System.Collections.Generic.List[string]'
$controllerName = 'livara-controller-' + $runId
$buildCompleted = $false
$exportCompleted = $false
$transcriptStarted = $false
$mutexOwned = $false
$mutex = $null
$exitCode = 1
$savedSelectors = @{}

function Get-LivaraDockerArguments {
    param([string[]]$Arguments)
    if ($script:LivaraContext) {
        return @('--context', $script:LivaraContext) + $Arguments
    }
    return $Arguments
}

function Invoke-LivaraDocker {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $nativeArguments = Get-LivaraDockerArguments -Arguments $Arguments
    & $script:LivaraDocker @nativeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker stopped with exit code $LASTEXITCODE. Read the preceding Docker message and the build log."
    }
}

function Get-LivaraDockerOutput {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $nativeArguments = Get-LivaraDockerArguments -Arguments $Arguments
    $result = & $script:LivaraDocker @nativeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker stopped with exit code $LASTEXITCODE."
    }
    return (($result | Out-String).Trim())
}

function Test-LivaraBindPath {
    param([string]$Path)
    if ($Path -match '[,\r\n]') {
        throw 'Docker bind paths cannot contain commas or newlines. Extract the source kit to a local folder with a different name. Spaces are supported.'
    }
}

try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'This entry point is for Windows. On Linux, use make check, make kali, and make iso.'
    }
    $projectPath = (Get-Item -LiteralPath $PSScriptRoot).FullName
    Test-LivaraBindPath -Path $projectPath
    if ($projectPath -notmatch '^[A-Za-z]:\\') {
        throw 'Extract the source kit to a local Windows drive before building. Network/UNC source folders are not supported.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectPath 'build\Dockerfile') -PathType Leaf)) {
        throw 'The complete source kit is required. Extract the ZIP first; do not run the BAT from inside the ZIP viewer.'
    }
    $dockerCommand = Get-Command docker.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $dockerCommand) {
        throw 'Install Docker Desktop, enable its WSL 2 Linux backend, and start it before running Build-Livara.bat. No separate Linux distribution, Python, or Git Bash is needed.'
    }
    $script:LivaraDocker = $dockerCommand.Source
    # Select the local Desktop context explicitly; stale remote/TLS selectors do not win.
    foreach ($name in @('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')) {
        $savedSelectors[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $contexts = @(Get-LivaraDockerOutput -Arguments @('context', 'ls', '--format', '{{.Name}}')) -split '\r?\n'
    if ($contexts -contains 'desktop-linux') {
        $script:LivaraContext = 'desktop-linux'
    } else {
        $script:LivaraContext = Get-LivaraDockerOutput -Arguments @('context', 'show')
    }
    $endpoint = Get-LivaraDockerOutput -Arguments @('context', 'inspect', $script:LivaraContext, '--format', '{{.Endpoints.docker.Host}}')
    if (-not $endpoint.StartsWith('npipe://', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Select a local Docker Desktop Linux context. Remote Docker endpoints are not supported by this Windows builder.'
    }
    try {
        $engine = Get-LivaraDockerOutput -Arguments @('info', '--format', '{{.OSType}}/{{.Architecture}}')
    } catch {
        throw 'Docker Desktop is not ready. Start it, select Linux containers with the WSL 2 backend, wait for the engine to start, and retry.'
    }
    if ($engine -notin @('linux/x86_64', 'linux/amd64')) {
        throw 'Livara currently builds an amd64 ISO and needs an x86_64 Linux Docker Desktop engine. Switch from Windows containers; Windows ARM engines are not qualified.'
    }
    $memory = [Int64](Get-LivaraDockerOutput -Arguments @('info', '--format', '{{.MemTotal}}'))
    # Docker reports usable RAM, slightly below the configured WSL allocation.
    $memoryGiB = [Math]::Floor(($memory + 512MB) / 1GB)
    if (-not $Check -and $memoryGiB -lt 16) {
        throw 'Allocate at least 16 GiB RAM to Docker Desktop for VS Code and Zen source compilation; 24 GiB or more is recommended.'
    }
    if (-not $Check) {
        $engineCpus = [int](Get-LivaraDockerOutput -Arguments @('info', '--format', '{{.NCPU}}'))
        $memoryJobs = [Math]::Max(1, [Math]::Floor(($memoryGiB - 8) / 4))
        $effectiveJobs = [int][Math]::Min($Jobs, [Math]::Min($engineCpus, $memoryJobs))
        if ($effectiveJobs -lt $Jobs) {
            Write-Host ('Limiting build workers from ' + $Jobs + ' to ' + $effectiveJobs + ' for the Docker CPU/RAM allocation.')
            $Jobs = $effectiveJobs
        }
    }
    if ($CaBundle) {
        $caItem = Get-Item -LiteralPath $CaBundle
        if ($caItem.PSIsContainer -or $caItem.Length -eq 0) {
            throw '-CaBundle must name a nonempty combined PEM trust bundle.'
        }
        $CaBundle = $caItem.FullName
        Test-LivaraBindPath -Path $CaBundle
    }
    $mutex = [System.Threading.Mutex]::new($false, 'Local\LivaraOSSourceBuilder')
    try {
        $mutexOwned = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        $mutexOwned = $true
    }
    if (-not $mutexOwned) {
        throw 'Another Livara build is already running in this Windows session. Wait for it to finish.'
    }
    $outputPath = Join-Path $projectPath 'dist'
    [void](New-Item -ItemType Directory -Path $outputPath -Force)
    $logPath = Join-Path $outputPath ('build-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $runId + '.log')
    try {
        Start-Transcript -Path $logPath -Force | Out-Null
        $transcriptStarted = $true
    } catch {
        Write-Warning 'PowerShell could not start a transcript; Docker output will still appear in this window.'
    }
    Write-Host 'Livara source builder'
    Write-Host $(if ($Check) { 'Mode: local source/recipe checks and desktop package only. No VS Code/Zen compilation, Tor Browser bundle download, or ISO build.' } else { 'Mode: compile VS Code/Zen, verify official Tor Browser, then build an ISO with offline Kali core. Downloads/caches are large; compilation can take hours.' })
    Write-Host 'The builder uses Linux Docker volumes so Windows file permissions do not enter the live filesystem.'
    $builderImage = 'livara-windows-builder:0.1.0'
    $buildArguments = @('build', '--platform', 'linux/amd64', '--file', (Join-Path $projectPath 'build\windows-builder.Dockerfile'), '--tag', $builderImage)
    if ($CaBundle) {
        $buildArguments += @('--secret', ('id=proxy_ca,src=' + $CaBundle))
    }
    $buildArguments += $projectPath
    Invoke-LivaraDocker -Arguments $buildArguments
    $sourceVolume = 'livara-source-' + $runId
    $buildVolume = 'livara-build-' + $runId
    $outputVolume = 'livara-output-' + $runId
    foreach ($volume in @($sourceVolume, $buildVolume, $outputVolume)) {
        Invoke-LivaraDocker -Arguments @('volume', 'create', '--label', ('org.livara.build=' + $runId), $volume)
        $createdVolumes.Add($volume)
    }
    $runArguments = @(
        'run', '--rm', '--name', $controllerName, '--label', ('org.livara.build=' + $runId),
        '--mount', ('type=bind,source=' + $projectPath + ',target=/source,readonly'),
        '--mount', ('type=volume,source=' + $sourceVolume + ',target=/project'),
        '--mount', ('type=volume,source=' + $buildVolume + ',target=/build'),
        '--mount', ('type=volume,source=' + $outputVolume + ',target=/output'),
        '--mount', 'type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
        '--env', ('LIVARA_SOURCE_VOLUME=' + $sourceVolume),
        '--env', ('LIVARA_BUILD_VOLUME=' + $buildVolume),
        '--env', ('LIVARA_OUTPUT_VOLUME=' + $outputVolume),
        '--env', ('LIVARA_BUILD_ID=' + $runId),
        '--env', ('LIVARA_BUILD_JOBS=' + $Jobs)
    )
    if ($CaBundle) {
        $runArguments += @('--mount', ('type=bind,source=' + $CaBundle + ',target=/run/livara-build-ca.pem,readonly'), '--env', 'LIVARA_BUILD_CA=/run/livara-build-ca.pem')
    }
    $runArguments += @($builderImage, $(if ($Check) { 'check' } else { 'build' }))
    Invoke-LivaraDocker -Arguments $runArguments
    $buildCompleted = $true
    Invoke-LivaraDocker -Arguments @(
        'run', '--rm', '--label', ('org.livara.build=' + $runId),
        '--mount', ('type=volume,source=' + $outputVolume + ',target=/output,readonly'),
        '--mount', ('type=bind,source=' + $outputPath + ',target=/export'),
        $builderImage, 'export'
    )
    $exportCompleted = $true
    if ($Check) {
        Write-Host 'CHECK PASSED. Local source/recipe checks and desktop packaging completed; VS Code/Zen were not compiled, Tor Browser was not downloaded, and no ISO was created.'
    } else {
        Write-Host ('ISO READY: ' + (Join-Path $outputPath 'livara-os-0.1.0-amd64.iso'))
        Write-Host 'Its checksum was verified after copying it to Windows. Test the image in a BIOS VM before physical hardware.'
    }
    Write-Host ('Output folder: ' + $outputPath)
    $exitCode = 0
} catch {
    Write-Host ('Livara build stopped: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'See docs\windows-build.md for prerequisites and recovery steps.'
} finally {
    if ($script:LivaraDocker -and $createdVolumes.Count -gt 0) {
        # Match this run's unique label, never prune unrelated Docker data.
        try {
            $ownedContainers = Get-LivaraDockerOutput -Arguments @('ps', '-aq', '--filter', ('label=org.livara.build=' + $runId))
            if ($ownedContainers) {
                foreach ($container in ($ownedContainers -split '\r?\n')) {
                    Invoke-LivaraDocker -Arguments @('rm', '--force', $container)
                }
            }
        } catch {
            Write-Warning 'Some build containers could not be removed. Inspect Docker Desktop for this run label before deleting its volumes.'
        }
        $retain = $KeepWork -or ($buildCompleted -and -not $exportCompleted)
        foreach ($volume in $createdVolumes) {
            if ($retain) {
                Write-Host ('Retained work volume: ' + $volume)
            } else {
                try { Invoke-LivaraDocker -Arguments @('volume', 'rm', $volume) }
                catch { Write-Warning ('Could not remove owned volume ' + $volume + '; remove it later in Docker Desktop.') }
            }
        }
        if ($buildCompleted -and -not $exportCompleted) {
            Write-Warning 'The completed products remain in the retained output volume because copying to Windows failed.'
        }
    }
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
    if ($mutexOwned) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
    foreach ($name in $savedSelectors.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedSelectors[$name], 'Process')
    }
}
exit $exitCode

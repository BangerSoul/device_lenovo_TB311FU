param(
    [string]$IsoPath = (Join-Path $env:USERPROFILE 'Downloads\ubuntu-26.04.1-desktop-amd64.iso')
)

$ErrorActionPreference = 'Stop'
$expectedIsoSha256 = '601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f'
$minimumCFreeBytes = 35GB
$fatalErrors = [System.Collections.Generic.List[string]]::new()
$missingPrerequisites = [System.Collections.Generic.List[string]]::new()

try {
    $operatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem
    $processor = Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1
    $computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem
    $cVolume = Get-Volume -DriveLetter C

    $firmwareVirtualization = [bool]$processor.VirtualizationFirmwareEnabled
    $hypervisorPresent = [bool]$computerSystem.HypervisorPresent
    $virtualizationAvailable = $firmwareVirtualization -or $hypervisorPresent

    $wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
    $wslFeatureEnabled = $wslFeature.State -eq 'Enabled'
    $wslDistributions = @()
    $wslDefaultVersion = $null

    $wslCommand = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($wslFeatureEnabled -and $null -ne $wslCommand) {
        $rawWslList = & $wslCommand.Source --list --verbose 2>&1
        $wslListExitCode = $LASTEXITCODE
        $wslText = (($rawWslList | ForEach-Object { [string]$_ }) -join "`n") -replace [char]0, ''

        if ($wslListExitCode -eq 0) {
            foreach ($line in ($wslText -split "`r?`n")) {
                if ($line -match '^\s*\*?\s*(?<name>\S+)\s+(?<state>\S+)\s+(?<version>[12])\s*$' -and $Matches.name -ne 'NAME') {
                    $wslDistributions += [pscustomobject]@{
                        name = $Matches.name
                        state = $Matches.state
                        version = [int]$Matches.version
                    }
                }
            }
        }

        $rawWslStatus = & $wslCommand.Source --status 2>&1
        $wslStatusText = (($rawWslStatus | ForEach-Object { [string]$_ }) -join "`n") -replace [char]0, ''
        if ($wslStatusText -match '(?im)^\s*Default Version:\s*(?<version>[12])\s*$') {
            $wslDefaultVersion = [int]$Matches.version
        }
    }

    $isoExists = Test-Path -LiteralPath $IsoPath -PathType Leaf
    $actualIsoSha256 = $null
    $isoMatchesExpected = $false
    if ($isoExists) {
        $actualIsoSha256 = (Get-FileHash -LiteralPath $IsoPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $isoMatchesExpected = $actualIsoSha256 -eq $expectedIsoSha256
        if (-not $isoMatchesExpected) {
            $fatalErrors.Add('The Ubuntu ISO SHA-256 does not match the pinned Canonical digest.')
        }
    } else {
        $missingPrerequisites.Add('The Ubuntu 26.04.1 desktop ISO is missing.')
    }

    if (-not $virtualizationAvailable) {
        $missingPrerequisites.Add('Hardware virtualization is not available to Windows.')
    }
    if (-not $wslFeatureEnabled) {
        $missingPrerequisites.Add('The Windows Subsystem for Linux feature is disabled.')
    }
    $supportedDistro = @($wslDistributions | Where-Object {
        $_.version -eq 2 -and $_.name -match '^(Ubuntu|Ubuntu-26\.04)$'
    })
    if ($supportedDistro.Count -eq 0) {
        $missingPrerequisites.Add('An Ubuntu 26.04 WSL distribution running as WSL 2 is not installed.')
    }
    if ($cVolume.SizeRemaining -lt $minimumCFreeBytes) {
        $missingPrerequisites.Add('C: has less than 35 GB free for the Linux build workspace and ISO output.')
    }

    $exitCode = if ($fatalErrors.Count -gt 0) { 1 } elseif ($missingPrerequisites.Count -gt 0) { 2 } else { 0 }
    $report = [ordered]@{
        windowsVersion = "$($operatingSystem.Caption) $($operatingSystem.Version) (build $($operatingSystem.BuildNumber))"
        cpu = [ordered]@{
            name = $processor.Name
            virtualizationFirmwareEnabled = $firmwareVirtualization
            hypervisorPresent = $hypervisorPresent
            virtualizationAvailable = $virtualizationAvailable
        }
        wsl = [ordered]@{
            featureEnabled = $wslFeatureEnabled
            defaultVersion = $wslDefaultVersion
            distributions = @($wslDistributions)
        }
        cFreeBytes = [long]$cVolume.SizeRemaining
        minimumCFreeBytes = [long]$minimumCFreeBytes
        iso = [ordered]@{
            path = (Resolve-Path -LiteralPath $IsoPath -ErrorAction SilentlyContinue | ForEach-Object Path)
            sha256 = $actualIsoSha256
            expectedSha256 = $expectedIsoSha256
            exists = $isoExists
            matchesExpected = $isoMatchesExpected
        }
        missingPrerequisites = @($missingPrerequisites)
        errors = @($fatalErrors)
        exitCode = $exitCode
    }

    $report | ConvertTo-Json -Depth 6
    exit $exitCode
} catch {
    $fatalErrors.Add($_.Exception.Message)
    [ordered]@{
        errors = @($fatalErrors)
        exitCode = 1
    } | ConvertTo-Json -Depth 4
    exit 1
}

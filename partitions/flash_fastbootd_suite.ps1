<#
.SYNOPSIS
    Lenovo Tab with Clear Case (TB311FU / 'poplar') Fastbootd Dynamic Partition Deployment Suite.
.DESCRIPTION
    Automated fastbootd logical partition optimization, GSI deployment, and stabilized
    vendor flashing with mandatory -S 64M chunking to prevent WinUSB transfer failures (error 22).
.PARAMETER GsiPath
    Path to target system GSI image (e.g. LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img).
.PARAMETER VendorPath
    Path to stabilized EROFS vendor image (vendor_stabilized.img).
.PARAMETER ChunkSize
    Chunking flag argument (default: 64M).
.PARAMETER FactoryReset
    If specified, performs fastboot -w factory reset. Default: false (Zero Data Loss).
.PARAMETER FastbootPath
    Optional explicit path to fastboot.exe.
.PARAMETER Serial
    Optional device serial identifier.
.PARAMETER Execute
    If specified, performs live flashing on connected Fastbootd device. Default: DryRun.
.PARAMETER DryRun
    Explicit dry-run validation mode (default).
#>

[CmdletBinding()]
param(
    [string]$GsiPath = "D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img",
    [string]$VendorPath = $null,
    [string]$ChunkSize = "64M",
    [switch]$FactoryReset = $false,
    [string]$FastbootPath = $null,
    [string]$Serial = $null,
    [switch]$Execute = $false,
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }

if (-not $VendorPath) {
    $VendorPath = Join-Path $scriptDir "vendor_stabilized.img"
}

# 1. Chunk Size Boundary Validation
function Test-ChunkSize([string]$Chunk) {
    $cleaned = $Chunk.Trim().ToUpper()
    if (-not $cleaned.EndsWith("M")) {
        throw "Invalid chunk size '$Chunk'. Must specify in megabytes (e.g. '64M')."
    }
    $val = [int]($cleaned.Substring(0, $cleaned.Length - 1))
    if ($val -ge 256) {
        throw "Chunk size $Chunk will fail on WinUSB. Must be < 256M to prevent transfer failure (error 22)."
    }
    if ($val -lt 16) {
        throw "Chunk size $Chunk too small. Minimum recommended chunk size is 16M."
    }
    return $val
}

$chunkMb = Test-ChunkSize -Chunk $ChunkSize

# 2. Locate Fastboot Binary
if (-not $FastbootPath -or -not (Test-Path $FastbootPath)) {
    $candidates = @(
        "C:\platform-tools\fastboot.exe",
        (Get-Command fastboot.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Get-Command fastboot -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path $cand)) {
            $FastbootPath = $cand
            break
        }
    }
    if (-not $FastbootPath) {
        $FastbootPath = "fastboot"
    }
}

# 3. Validate Target Images
if (-not (Test-Path $GsiPath)) {
    throw "Target GSI image not found: $GsiPath"
}
$gsiItem = Get-Item $GsiPath
$gsiSize = $gsiItem.Length

if (-not (Test-Path $VendorPath)) {
    throw "Stabilized vendor image not found: $VendorPath"
}
$vendorItem = Get-Item $VendorPath
$vendorSize = $vendorItem.Length

# 4. Display Configuration Banner
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "TB311FU ('poplar') Fastbootd Dynamic Partition Deployment Suite" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Fastboot Binary:   $FastbootPath"
Write-Host "Target GSI Path:   $GsiPath ($('{0:N0}' -f $gsiSize) bytes)"
Write-Host "Stabilized Vendor: $VendorPath ($('{0:N0}' -f $vendorSize) bytes)"
Write-Host "Chunking Flag:     -S $ChunkSize (WinUSB error 22 protection)"
Write-Host "Zero Data Loss:    $(if ($FactoryReset) { 'DISABLED (Factory reset requested)' } else { 'ENABLED (Preserving encrypted /data)' })"
Write-Host ("=" * 70) -ForegroundColor Cyan

# 5. Build Deployment Plan
$plan = [System.Collections.Generic.List[string]]::new()
$serialFlag = if ($Serial) { "-s $Serial " } else { "" }

$plan.Add("$FastbootPath $serialFlag delete-logical-partition product_a")
$plan.Add("$FastbootPath $serialFlag delete-logical-partition product_b")
$plan.Add("$FastbootPath $serialFlag resize-logical-partition system_a $gsiSize")
$plan.Add("$FastbootPath $serialFlag erase system_a")
$plan.Add("$FastbootPath $serialFlag -S $ChunkSize flash system_a `"$GsiPath`"")
$plan.Add("$FastbootPath $serialFlag -S $ChunkSize flash vendor_a `"$VendorPath`"")

if ($FactoryReset) {
    $plan.Add("$FastbootPath $serialFlag -w")
}

$plan.Add("$FastbootPath $serialFlag reboot")

# 6. Safety Contract Audits
if (-not $FactoryReset) {
    foreach ($cmd in $plan) {
        if ($cmd -match " -w" -or $cmd -match "erase userdata" -or $cmd -match "format userdata") {
            throw "Violation of Zero Data Loss contract! Wipe command detected: $cmd"
        }
    }
}

foreach ($cmd in $plan) {
    if ($cmd -match "vendor_boot") {
        throw "AVB Violation: Attempt to flash salt-pinned vendor_boot: $cmd"
    }
    if ($cmd -match "--disable-verity" -or $cmd -match "--disable-verification") {
        throw "AVB Violation: Little Kernel RSA4096 signature failure trigger: $cmd"
    }
}

# 7. Execution or DryRun
$isDryRun = (-not $Execute) -or $DryRun

if ($isDryRun) {
    Write-Host "`n[DRY-RUN VALIDATION] Staging fastboot commands without device modification:`n" -ForegroundColor Yellow
    $step = 1
    foreach ($cmd in $plan) {
        Write-Host "  Step $step`: $cmd" -ForegroundColor Gray
        $step++
    }
    Write-Host "`n" + ("-" * 70)
    Write-Host "Safety Audits Passed:" -ForegroundColor Green
    Write-Host "  [PASS] Mandatory -S $ChunkSize chunking applied to system_a and vendor_a." -ForegroundColor Green
    Write-Host "  [PASS] Zero data loss contract: $(if ($FactoryReset) { '1 (-w explicit)' } else { '0 wipe commands' })." -ForegroundColor Green
    Write-Host "  [PASS] AVB Little Kernel contract: factory vendor_boot remains 100% untouched." -ForegroundColor Green
    Write-Host "  [PASS] AVB Little Kernel contract: OEM vbmeta RSA4096 signature preserved bare." -ForegroundColor Green
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "[+] DRY-RUN SUCCESS: Fastbootd deployment plan verified." -ForegroundColor Green
    exit 0
}

# 8. Live Execution Path
Write-Host "`n[Phase 1] Querying device Fastbootd state..." -ForegroundColor Cyan

$unlockedRes = & $FastbootPath $serialFlag getvar unlocked 2>&1 | Out-String
if ($unlockedRes -notmatch "unlocked:\s*yes") {
    throw "Bootloader is LOCKED. Cannot flash logical partitions."
}
Write-Host "  [+] Bootloader Unlocked: yes" -ForegroundColor Green

$userspaceRes = & $FastbootPath $serialFlag getvar is-userspace 2>&1 | Out-String
if ($userspaceRes -notmatch "is-userspace:\s*yes") {
    throw "Device is in Bootloader mode, NOT Fastbootd. Run 'fastboot reboot fastboot' first."
}
Write-Host "  [+] Fastbootd Userspace: yes" -ForegroundColor Green

Write-Host "`n[Phase 2] Executing Fastbootd commands sequentially..." -ForegroundColor Cyan
$step = 1
foreach ($cmd in $plan) {
    Write-Host "`n[*] Step $step/$($plan.Count): $cmd" -ForegroundColor Yellow
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        throw "Step $step failed with exit code $LASTEXITCODE`: $cmd"
    }
    $step++
}

Write-Host "`n" + ("=" * 70) -ForegroundColor Green
Write-Host "DEPLOYMENT SUCCESS: System and Vendor successfully flashed!" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green

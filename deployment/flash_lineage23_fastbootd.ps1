<#
.SYNOPSIS
    Lenovo Tab with Clear Case (TB311FU / 'poplar') LineageOS 23.2 Fastbootd Dynamic Partition Deployment Script.
.DESCRIPTION
    Production PowerShell deployment runner for LineageOS 23.2 (Android 16 QPR2 GSI) with stabilized
    vendor dynamic partition and custom Linux 6.6 GKI PoplarKernel boot vector.
    Enforces:
      - Default DryRun execution mode (-DryRun flag, execute only if explicit -Execute is passed).
      - WinUSB transfer chunking (-S 64M) on all logical partition flash commands.
      - Fastbootd userspace verification (fastboot getvar is-userspace == yes).
      - Logical partition management (delete product_a/product_b, resize system_a and vendor_a).
      - Flashing logical partitions: system_a (LineageOS GSI) and vendor_a (vendor_stabilized.img).
      - Flashing boot_a with 4096-aligned AVB 2.0 boot vector (pmos_boot.img / boot.img).
      - Strict prohibition: NEVER flash vendor_boot, vbmeta, vbmeta_system, vbmeta_vendor,
        or execute fastboot -w / data wiping.
.PARAMETER GsiPath
    Path to LineageOS 23.2 GSI image (default: D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img).
.PARAMETER VendorPath
    Path to stabilized EROFS vendor image (default: deployment\vendor_stabilized.img).
.PARAMETER BootPath
    Path to 4096-aligned AVB 2.0 boot vector image (default: deployment\pmos_boot.img).
.PARAMETER ChunkSize
    Chunking flag argument (default: 64M). Prevents Windows WinUSB endpoint stalls (error 22).
.PARAMETER FastbootPath
    Explicit path to fastboot binary. Defaults to searching C:\platform-tools and PATH.
.PARAMETER AdbPath
    Explicit path to adb binary. Defaults to searching C:\platform-tools and PATH.
.PARAMETER Serial
    Target device hardware serial identifier (default: HNQ09EZD).
.PARAMETER Execute
    If specified, performs live flashing against connected Fastbootd tablet. Default: DryRun.
.PARAMETER DryRun
    Explicit dry-run validation mode (default: true unless -Execute is explicitly specified).
#>

[CmdletBinding()]
param(
    [string]$GsiPath = "D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img",
    [string]$VendorPath = $null,
    [string]$BootPath = $null,
    [string]$ChunkSize = "64M",
    [string]$FastbootPath = $null,
    [string]$AdbPath = $null,
    [string]$Serial = "HNQ09EZD",
    [switch]$Execute = $false,
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

# Determine workspace root directory
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
$workspaceRoot = if (Test-Path (Join-Path $scriptDir "..\deployment")) {
    (Resolve-Path (Join-Path $scriptDir "..")).Path
} else {
    $scriptDir
}

# ==============================================================================
# 1. Chunk Size Boundary Validation (WinUSB 64M Standard)
# ==============================================================================
function Test-ChunkSize([string]$Chunk) {
    $cleaned = $Chunk.Trim().ToUpper()
    if (-not $cleaned.EndsWith("M")) {
        throw "Invalid chunk size '$Chunk'. Must specify in megabytes ending in 'M' (e.g. '64M')."
    }
    $val = [int]($cleaned.Substring(0, $cleaned.Length - 1))
    if ($val -gt 64) {
        throw "Chunk size $Chunk exceeds safe WinUSB limit! Must be <= 64M to prevent Windows WinUSB endpoint stall (error 22)."
    }
    if ($val -lt 16) {
        throw "Chunk size $Chunk is too small! Minimum recommended chunk size is 16M."
    }
    return $val
}

$chunkMb = Test-ChunkSize -Chunk $ChunkSize
$chunkBytes = [int64]$chunkMb * 1024 * 1024

# ==============================================================================
# 2. Locate Platform Tools (fastboot, adb)
# ==============================================================================
function Resolve-ToolBinary([string]$ExplicitPath, [string]$ToolName) {
    if ($ExplicitPath -and (Test-Path -Path $ExplicitPath -PathType Leaf)) {
        return (Resolve-Path $ExplicitPath).Path
    }
    $candidates = @(
        "C:\platform-tools\$ToolName.exe",
        "C:\platform-tools\$ToolName",
        (Get-Command "$ToolName.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Get-Command $ToolName -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path -Path $cand -PathType Leaf)) {
            return (Resolve-Path $cand).Path
        }
    }
    return $ToolName
}

$FastbootPath = Resolve-ToolBinary -ExplicitPath $FastbootPath -ToolName "fastboot"
$AdbPath = Resolve-ToolBinary -ExplicitPath $AdbPath -ToolName "adb"

# ==============================================================================
# 3. Resolve Target Image Paths
# ==============================================================================
function Resolve-ImagePath([string]$PathCandidate, [string[]]$Fallbacks, [string]$ImageLabel) {
    if ($PathCandidate -and (Test-Path -Path $PathCandidate -PathType Leaf)) {
        return (Resolve-Path $PathCandidate).Path
    }
    if ($PathCandidate) {
        $cands = @(
            (Join-Path $workspaceRoot $PathCandidate),
            (Join-Path $scriptDir $PathCandidate)
        )
        foreach ($c in $cands) {
            if ($c -and (Test-Path -Path $c -PathType Leaf)) {
                return (Resolve-Path $c).Path
            }
        }
    }
    foreach ($fb in $Fallbacks) {
        $fbCands = @(
            $fb,
            (Join-Path $workspaceRoot $fb),
            (Join-Path $scriptDir $fb)
        )
        foreach ($c in $fbCands) {
            if ($c -and (Test-Path -Path $c -PathType Leaf)) {
                return (Resolve-Path $c).Path
            }
        }
    }
    throw "Target $ImageLabel not found! Checked candidate '$PathCandidate' and fallbacks: $($Fallbacks -join ', ')"
}

$resolvedGsi = Resolve-ImagePath -PathCandidate $GsiPath `
    -Fallbacks @("D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img") `
    -ImageLabel "LineageOS 23.2 GSI"

$resolvedVendor = Resolve-ImagePath -PathCandidate $VendorPath `
    -Fallbacks @("deployment\vendor_stabilized.img", "partitions\vendor_stabilized.img", "C:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\partitions\vendor_stabilized.img") `
    -ImageLabel "Stabilized Vendor Image"

$resolvedBoot = Resolve-ImagePath -PathCandidate $BootPath `
    -Fallbacks @("deployment\pmos_boot.img", "deployment\boot.img", "boot_vector\pmos_boot.img", "C:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\boot_vector\pmos_boot.img") `
    -ImageLabel "AVB 2.0 Boot Vector Image"

# ==============================================================================
# 4. Image Preflight & Geometric/Cryptographic Integrity Checks
# ==============================================================================
$gsiItem = Get-Item $resolvedGsi
$gsiSize = $gsiItem.Length
$nominalGsiSize = 3446353920  # 3,446,353,920 bytes (Android 16 QPR2 GSI)

if ($gsiSize -ne $nominalGsiSize) {
    Write-Warning "Target GSI size ($gsiSize bytes) differs from nominal 3,446,353,920 bytes."
}

$vendorItem = Get-Item $resolvedVendor
$vendorSize = $vendorItem.Length
$vendorPartitionLimit = 303345664  # 303,345,664 bytes (vendor_a limit)

if ($vendorSize -gt $vendorPartitionLimit) {
    throw "Vendor image size ($vendorSize bytes) exceeds vendor_a partition ceiling ($vendorPartitionLimit bytes)!"
}

# Verify EROFS superblock magic in vendor image (0xe0f5e1e2 at offset 1024)
$vendorStream = [System.IO.File]::OpenRead($resolvedVendor)
try {
    $vendorBuf = New-Object byte[] 1028
    $null = $vendorStream.Read($vendorBuf, 0, 1028)
    $erofsMagic = [System.BitConverter]::ToInt32($vendorBuf, 1024)
    if ($erofsMagic -ne [int]0xe0f5e1e2) {
        throw ("Vendor image EROFS magic check failed! Expected 0xe0f5e1e2, got 0x{0:x8}" -f $erofsMagic)
    }
} finally {
    $vendorStream.Close()
}

$bootItem = Get-Item $resolvedBoot
$bootSize = $bootItem.Length
$nominalBootSize = 33554432  # 32 MB (33,554,432 bytes)

if ($bootSize -ne $nominalBootSize) {
    throw "Boot vector image size ($bootSize bytes) differs from nominal 32 MB ($nominalBootSize bytes)."
}

# Verify Android Boot Header v4 magic and AVB footer in boot image
$bootStream = [System.IO.File]::OpenRead($resolvedBoot)
try {
    $hdrBuf = New-Object byte[] 8
    $null = $bootStream.Read($hdrBuf, 0, 8)
    $bootMagic = [System.Text.Encoding]::ASCII.GetString($hdrBuf, 0, 8)
    if ($bootMagic -ne "ANDROID!") {
        throw "Boot image magic check failed! Expected 'ANDROID!', got '$bootMagic'."
    }

    # Read AVB Footer at offset 33,554,368 (last 64 bytes)
    $null = $bootStream.Seek(33554368, [System.IO.SeekOrigin]::Begin)
    $footerBuf = New-Object byte[] 4
    $null = $bootStream.Read($footerBuf, 0, 4)
    $footerMagic = [System.Text.Encoding]::ASCII.GetString($footerBuf, 0, 4)
    if ($footerMagic -ne "AVBf") {
        throw "AVB footer magic check failed! Expected 'AVBf', got '$footerMagic'."
    }
} finally {
    $bootStream.Close()
}

# ==============================================================================
# 5. Display Configuration Banner
# ==============================================================================
$gsiFormatted = '{0:N0}' -f $gsiSize
$vendorFormatted = '{0:N0}' -f $vendorSize
$bootFormatted = '{0:N0}' -f $bootSize
$chunkFormatted = '{0:N0}' -f $chunkBytes

Write-Host ("=" * 78) -ForegroundColor Cyan
Write-Host "LineageOS 23.2 Fastbootd Dynamic Partition Deployment Script" -ForegroundColor Cyan
Write-Host "Hardware Target: Lenovo Tab with Clear Case (TB311FU) (TB311FU / 'poplar', Serial: $Serial)" -ForegroundColor Cyan
Write-Host ("=" * 78) -ForegroundColor Cyan
Write-Host ("Fastboot Binary:   {0}" -f $FastbootPath)
Write-Host ("ADB Binary:        {0}" -f $AdbPath)
Write-Host ("Target GSI Path:   {0} ({1} bytes)" -f $resolvedGsi, $gsiFormatted)
Write-Host ("Stabilized Vendor: {0} ({1} bytes)" -f $resolvedVendor, $vendorFormatted)
Write-Host ("Boot Vector:       {0} ({1} bytes)" -f $resolvedBoot, $bootFormatted)
Write-Host ("Chunking Standard: -S {0} ({1} bytes/chunk)" -f $ChunkSize, $chunkFormatted)
Write-Host ("Data Preservation: STRICT ZERO DATA LOSS (Wipe commands strictly prohibited)") -ForegroundColor Green
Write-Host ("=" * 78) -ForegroundColor Cyan

# ==============================================================================
# 6. Build Deployment Command Plan
# ==============================================================================
$plan = [System.Collections.Generic.List[string]]::new()
$serialArg = if ($Serial) { " -s $Serial" } else { "" }

# Step 1 & 2: Delete unused product dynamic partitions to free ~1.87 GB headroom
$plan.Add("$FastbootPath$serialArg delete-logical-partition product_a")
$plan.Add("$FastbootPath$serialArg delete-logical-partition product_b")

# Step 3 & 4: Resize logical partitions to exact payload byte sizes
$plan.Add("$FastbootPath$serialArg resize-logical-partition system_a $gsiSize")
$plan.Add("$FastbootPath$serialArg resize-logical-partition vendor_a $vendorSize")

# Step 5: Erase target system_a partition before writing
$plan.Add("$FastbootPath$serialArg erase system_a")

# Step 6 & 7: Flash logical partitions with mandatory WinUSB -S 64M chunking
$plan.Add("$FastbootPath$serialArg -S $ChunkSize flash system_a `"$resolvedGsi`"")
$plan.Add("$FastbootPath$serialArg -S $ChunkSize flash vendor_a `"$resolvedVendor`"")

# Step 8: Flash 4096-aligned AVB 2.0 boot vector to boot_a
$plan.Add("$FastbootPath$serialArg flash boot_a `"$resolvedBoot`"")

# Step 9: Reboot into newly deployed LineageOS 23.2
$plan.Add("$FastbootPath$serialArg reboot")

# ==============================================================================
# 7. Strict Safety Guard Audits (MANDATORY INVARIANTS)
# ==============================================================================
# Invariant 1: Strictly PROHIBIT wiping userdata (-w / erase userdata / format userdata)
foreach ($cmd in $plan) {
    if ($cmd -match "\s+-w\b" -or $cmd -match "erase\s+userdata" -or $cmd -match "format\s+userdata") {
        throw "CRITICAL SAFETY VIOLATION: Data wiping command detected in plan: $cmd"
    }
}

# Invariant 2: Strictly PROHIBIT flashing salt-pinned vendor_boot partition
foreach ($cmd in $plan) {
    if ($cmd -match "\bflash\b.*\bvendor_boot") {
        throw "CRITICAL SAFETY VIOLATION: Flashing factory vendor_boot is fatal to AVB: $cmd"
    }
}

# Invariant 3: Strictly PROHIBIT flashing or mutating vbmeta partitions
foreach ($cmd in $plan) {
    if ($cmd -match "\bflash\b.*\bvbmeta\b" -or $cmd -match "\bflash\b.*\bvbmeta_system\b" -or $cmd -match "\bflash\b.*\bvbmeta_vendor\b") {
        throw "CRITICAL SAFETY VIOLATION: Attempt to flash bare stock vbmeta partitions: $cmd"
    }
    if ($cmd -match "--disable-verity" -or $cmd -match "--disable-verification") {
        throw "CRITICAL SAFETY VIOLATION: AVB disable flags mutate flags byte 123 (breaks Little Kernel RSA4096): $cmd"
    }
}

# Invariant 4: Validate WinUSB chunking standard on all dynamic partition writes
$systemChunked = $false
$vendorChunked = $false
foreach ($cmd in $plan) {
    if ($cmd -match "flash system_a" -and $cmd -match "-S $ChunkSize") {
        $systemChunked = $true
    }
    if ($cmd -match "flash vendor_a" -and $cmd -match "-S $ChunkSize") {
        $vendorChunked = $true
    }
}
if (-not $systemChunked) {
    throw "CRITICAL SAFETY VIOLATION: flash system_a lacks mandatory -S $ChunkSize chunking!"
}
if (-not $vendorChunked) {
    throw "CRITICAL SAFETY VIOLATION: flash vendor_a lacks mandatory -S $ChunkSize chunking!"
}

# ==============================================================================
# 8. Execution Mode: DryRun vs Live Flashing
# ==============================================================================
$isDryRun = (-not $Execute) -or $DryRun

if ($isDryRun) {
    Write-Host "`n[DRY-RUN VALIDATION] Staging deployment plan without device modification:`n" -ForegroundColor Yellow
    $step = 1
    foreach ($cmd in $plan) {
        Write-Host ("  Step {0}: {1}" -f $step, $cmd) -ForegroundColor Gray
        $step++
    }
    Write-Host ("`n" + ('-' * 78))
    Write-Host "Deployment Safety & Invariant Audits Passed:" -ForegroundColor Green
    Write-Host ("  [PASS] Mandatory -S {0} WinUSB chunking enforced on system_a and vendor_a ({1} B/chunk)." -f $ChunkSize, $chunkFormatted) -ForegroundColor Green
    Write-Host ("  [PASS] Logical partition system_a resized to {0} bytes ({1:N2} MB)." -f $gsiSize, ($gsiSize / 1MB)) -ForegroundColor Green
    Write-Host ("  [PASS] Logical partition vendor_a resized to {0} bytes ({1:N2} MB, EROFS valid)." -f $vendorSize, ($vendorSize / 1MB)) -ForegroundColor Green
    Write-Host ("  [PASS] Logical partition product_a and product_b scheduled for deletion (+1.87 GB headroom)." ) -ForegroundColor Green
    Write-Host ("  [PASS] Boot vector targets boot_a ({0} bytes, Android Header v4, AVB footer verified)." -f $bootSize) -ForegroundColor Green
    Write-Host "  [PASS] Factory stock preservation: vendor_boot remains 100% factory untouched." -ForegroundColor Green
    Write-Host "  [PASS] Factory stock preservation: stock vbmeta, vbmeta_system, vbmeta_vendor remain bare." -ForegroundColor Green
    Write-Host "  [PASS] Strict Zero Data Loss: Zero wipe commands in plan (no fastboot -w, user data preserved)." -ForegroundColor Green
    Write-Host ("=" * 78) -ForegroundColor Cyan
    Write-Host "[+] DRY-RUN SUCCESS: Fastbootd deployment plan verified and safe for execution." -ForegroundColor Green
    exit 0
}

# ==============================================================================
# 9. Live Execution Path (Requires explicit -Execute)
# ==============================================================================
Write-Host "`n[Phase 1] Preflight: Querying device Fastbootd state..." -ForegroundColor Cyan

# Step 1a: Check if already in Fastboot mode first
$fastbootDevices = try { cmd.exe /c "`"$FastbootPath`" devices 2>&1" | Out-String } catch { "" }
if ($fastbootDevices -match "$Serial" -or ($fastbootDevices.Trim().Length -gt 0 -and $fastbootDevices -match "fastboot")) {
    Write-Host "  [+] Device detected in fastboot mode." -ForegroundColor Green
} else {
    # Check if device is visible in ADB
    $adbDevices = try { cmd.exe /c "`"$AdbPath`" devices 2>&1" | Out-String } catch { "" }
    $deviceInAdb = $adbDevices -match "$Serial\s+device"
    if ($deviceInAdb) {
        Write-Host "  [+] Device $Serial detected in ADB mode. Rebooting to fastboot..." -ForegroundColor Yellow
        cmd.exe /c "`"$AdbPath`" -s $Serial reboot fastboot"
        Write-Host "  [*] Waiting 15s for device to re-enumerate in Fastbootd..." -ForegroundColor Gray
        Start-Sleep -Seconds 15
    } else {
        throw "No fastboot or ADB device detected! Ensure tablet $Serial is connected in Fastbootd mode. ADB output: $($adbDevices.Trim())"
    }
}

# Step 1b: Assert Fastbootd userspace mode (MANDATORY GATE with retry loop)
$serialFlag = if ($Serial) { "-s $Serial" } else { "" }
$userspaceOutput = ""
$waitCount = 0
Write-Host "  [*] Polling for Fastbootd userspace readiness (up to 45s)..." -ForegroundColor Gray
while ($waitCount -lt 15) {
    $userspaceOutput = cmd.exe /c "`"$FastbootPath`" $serialFlag getvar is-userspace 2>&1" | Out-String
    if ($userspaceOutput -match "is-userspace:\s*yes") {
        break
    }
    Start-Sleep -Seconds 3
    $waitCount++
}
Write-Host "  [*] Querying getvar is-userspace: $($userspaceOutput.Trim())" -ForegroundColor Gray

if ($userspaceOutput -notmatch "is-userspace:\s*yes") {
    throw "CRITICAL: Device is not in Fastbootd userspace mode! (Output: $($userspaceOutput.Trim())). Fastbootd is strictly mandatory for dynamic partition management. Execute 'fastboot reboot fastboot' and retry."
}
Write-Host "  [PASS] Fastbootd userspace mode confirmed (is-userspace == yes)." -ForegroundColor Green

# Step 1c: Verify bootloader unlock status
$unlockedOutput = cmd.exe /c "`"$FastbootPath`" $serialFlag getvar unlocked 2>&1" | Out-String
if ($unlockedOutput -notmatch "unlocked:\s*yes") {
    throw "CRITICAL: Bootloader is LOCKED. Cannot flash logical partitions or custom boot vector."
}
Write-Host "  [PASS] Bootloader unlocked state confirmed." -ForegroundColor Green

# Phase 2: Execute command plan sequentially
Write-Host "`n[Phase 2] Executing Fastbootd commands sequentially..." -ForegroundColor Cyan
$step = 1
foreach ($cmd in $plan) {
    Write-Host "`n[*] Step $step/$($plan.Count): $cmd" -ForegroundColor Yellow
    cmd.exe /c "$cmd"
    if ($LASTEXITCODE -ne 0) {
        throw "Step $step failed with exit code $LASTEXITCODE`: $cmd"
    }
    $step++
}

Write-Host "`n" + ("=" * 78) -ForegroundColor Green
Write-Host "DEPLOYMENT COMPLETE: LineageOS 23.2 successfully deployed to Lenovo Tab with Clear Case (TB311FU)!" -ForegroundColor Green
Write-Host ("=" * 78) -ForegroundColor Green
exit 0

#!/usr/bin/env bash
#
# scripts/build_fastboot_set.sh
# Fastboot Package Builder with Sparse Image Generation and Flash Scripts
# Target Device: Lenovo Tab M11 (TB311FU / 'poplar', MT8786 / Helio G88)
#
# Builds a fastboot deployment set containing:
#   - system.sparse.img (converted from EXT4 GSI with Android sparse v1.0)
#   - boot.img, init_boot.img, vendor_boot.img, dtbo.img, vbmeta.img
#   - Cross-platform flashing scripts: flash_all.sh, flash_all.bat, flash_all.ps1
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGES_DIR=""
SYSTEM_IMG=""
BOOT_IMG=""
INIT_BOOT_IMG=""
VENDOR_BOOT_IMG=""
DTBO_IMG=""
VBMETA_IMG=""
CHUNK_SIZE="64M"
OUTPUT_PKG=""
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build a Fastboot deployment set with sparse images and flashing scripts for Lenovo Tab M11 (TB311FU).

Options:
  -d, --images-dir DIR      Directory containing partition images
  -s, --system PATH         Path to system image (system_a.img or system.img)
  -b, --boot PATH           Path to boot image (boot_a.img or boot.img)
  -i, --init-boot PATH      Path to init_boot image (init_boot_a.img or init_boot.img)
  -v, --vendor-boot PATH    Path to vendor_boot image (vendor_boot_a.img or vendor_boot.img)
  -t, --dtbo PATH           Path to dtbo image (dtbo_a.img or dtbo.img)
  -m, --vbmeta PATH         Path to vbmeta image (vbmeta_a.img or vbmeta.img)
  -c, --chunk-size SIZE     Fastboot sparse chunk size (default: 64M for WinUSB compliance)
  -o, --output PATH         Output archive (.zip or .tar.gz, default: out/TB311FU-LineageOS-23.2-fastboot.zip)
  -f, --force               Overwrite existing output file
  -h, --help                Show this help message

If --images-dir is specified, images are discovered automatically by name.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--images-dir)
            IMAGES_DIR="$2"
            shift 2
            ;;
        -s|--system)
            SYSTEM_IMG="$2"
            shift 2
            ;;
        -b|--boot)
            BOOT_IMG="$2"
            shift 2
            ;;
        -i|--init-boot)
            INIT_BOOT_IMG="$2"
            shift 2
            ;;
        -v|--vendor-boot)
            VENDOR_BOOT_IMG="$2"
            shift 2
            ;;
        -t|--dtbo)
            DTBO_IMG="$2"
            shift 2
            ;;
        -m|--vbmeta)
            VBMETA_IMG="$2"
            shift 2
            ;;
        -c|--chunk-size)
            CHUNK_SIZE="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_PKG="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: Unknown argument $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

resolve_file() {
    local dir="$1"
    shift
    for name in "$@"; do
        if [[ -f "${dir}/${name}" ]]; then
            echo "${dir}/${name}"
            return 0
        fi
    done
    return 1
}

if [[ -n "$IMAGES_DIR" && -d "$IMAGES_DIR" ]]; then
    [[ -z "$SYSTEM_IMG" ]] && SYSTEM_IMG="$(resolve_file "$IMAGES_DIR" "system_transformed.img" "system_a.img" "system.img" || true)"
    [[ -z "$BOOT_IMG" ]] && BOOT_IMG="$(resolve_file "$IMAGES_DIR" "boot_a.img" "boot.img" "pmos_boot.img" || true)"
    [[ -z "$INIT_BOOT_IMG" ]] && INIT_BOOT_IMG="$(resolve_file "$IMAGES_DIR" "init_boot_a.img" "init_boot.img" || true)"
    [[ -z "$VENDOR_BOOT_IMG" ]] && VENDOR_BOOT_IMG="$(resolve_file "$IMAGES_DIR" "vendor_boot_a.img" "vendor_boot.img" || true)"
    [[ -z "$DTBO_IMG" ]] && DTBO_IMG="$(resolve_file "$IMAGES_DIR" "dtbo_a.img" "dtbo.img" || true)"
    [[ -z "$VBMETA_IMG" ]] && VBMETA_IMG="$(resolve_file "$IMAGES_DIR" "vbmeta_a.img" "vbmeta.img" || true)"
fi

check_required() {
    local label="$1"
    local path="$2"
    if [[ -z "$path" ]]; then
        echo "Error: Missing required image for $label. Specify via options." >&2
        exit 1
    fi
    if [[ ! -f "$path" ]]; then
        echo "Error: File for $label does not exist: '$path'" >&2
        exit 1
    fi
}

check_required "system" "$SYSTEM_IMG"
check_required "boot" "$BOOT_IMG"
check_required "init_boot" "$INIT_BOOT_IMG"
check_required "vendor_boot" "$VENDOR_BOOT_IMG"
check_required "dtbo" "$DTBO_IMG"
check_required "vbmeta" "$VBMETA_IMG"

if [[ -z "$OUTPUT_PKG" ]]; then
    OUTPUT_PKG="${REPO_ROOT}/out/TB311FU-LineageOS-23.2-fastboot-$(date +%Y%m%d_%H%M%S).zip"
fi

if [[ -f "$OUTPUT_PKG" ]] && ! "$FORCE"; then
    echo "Error: Output file '$OUTPUT_PKG' already exists. Use -f/--force to overwrite." >&2
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PKG")"

BUILD_TMP="$(mktemp -d)"
trap 'rm -rf "$BUILD_TMP"' EXIT

echo "===================================================================="
echo " Lenovo Tab M11 (TB311FU) Fastboot Deployment Set Builder"
echo "===================================================================="
echo "System Image:      $SYSTEM_IMG ($(du -h "$SYSTEM_IMG" | cut -f1))"
echo "Boot Image:        $BOOT_IMG"
echo "Init Boot Image:   $INIT_BOOT_IMG"
echo "Vendor Boot Image: $VENDOR_BOOT_IMG"
echo "DTBO Image:        $DTBO_IMG"
echo "VBMeta Image:      $VBMETA_IMG"
echo "Sparse Chunk Size: $CHUNK_SIZE (WinUSB standard)"
echo "Output Package:    $OUTPUT_PKG"
echo "===================================================================="

# 1. Convert system.img to Android sparse format (system.sparse.img)
echo "[*] Generating Android sparse image for system partition..."
SPARSE_TARGET="${BUILD_TMP}/system.sparse.img"

if command -v img2simg >/dev/null 2>&1; then
    echo "    Using host 'img2simg' binary..."
    img2simg "$SYSTEM_IMG" "$SPARSE_TARGET"
else
    echo "    Using built-in Python sparse converter..."
    python3 "${REPO_ROOT}/tools/img2simg.py" "$SYSTEM_IMG" "$SPARSE_TARGET"
fi

echo "[+] Sparse image generated: $(du -h "$SPARSE_TARGET" | cut -f1)"

# 2. Copy/symlink other partition images
echo "[*] Staging physical partition images..."
cp "$BOOT_IMG" "${BUILD_TMP}/boot.img"
cp "$INIT_BOOT_IMG" "${BUILD_TMP}/init_boot.img"
cp "$VENDOR_BOOT_IMG" "${BUILD_TMP}/vendor_boot.img"
cp "$DTBO_IMG" "${BUILD_TMP}/dtbo.img"
cp "$VBMETA_IMG" "${BUILD_TMP}/vbmeta.img"

# 3. Generate flash_all.sh (Linux/macOS)
echo "[*] Generating flash_all.sh..."
cat <<'EOF' > "${BUILD_TMP}/flash_all.sh"
#!/usr/bin/env bash
#
# Lenovo Tab M11 (TB311FU / 'poplar') Fastboot Flashing Script (Linux/macOS)
# Flashes LineageOS 23.2 GSI + GKI PoplarKernel + OrangeFox Boot Vector
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHUNK_SIZE="64M"
WIPE_DATA=false

usage() {
    cat <<USG
Usage: $(basename "$0") [OPTIONS]
Options:
  -w, --wipe    Perform factory reset (erase userdata and metadata). Default: NO data wipe.
  -h, --help    Show this message
USG
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -w|--wipe)
            WIPE_DATA=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument $1" >&2
            exit 2
            ;;
    esac
done

echo "===================================================================="
echo " Lenovo Tab M11 (TB311FU) LineageOS 23.2 Fastboot Flasher"
echo "===================================================================="

FASTBOOT_BIN="fastboot"
if ! command -v "$FASTBOOT_BIN" >/dev/null 2>&1; then
    echo "Error: 'fastboot' not found in PATH. Install Android SDK Platform-Tools." >&2
    exit 1
fi

echo "[*] Checking connected device in fastboot mode..."
$FASTBOOT_BIN devices

echo "[*] Setting active slot to A..."
$FASTBOOT_BIN set_active a

echo "[*] Flashing physical boot chain partitions..."
$FASTBOOT_BIN flash vbmeta_a "${SCRIPT_DIR}/vbmeta.img"
$FASTBOOT_BIN flash dtbo_a "${SCRIPT_DIR}/dtbo.img"
$FASTBOOT_BIN flash vendor_boot_a "${SCRIPT_DIR}/vendor_boot.img"
$FASTBOOT_BIN flash init_boot_a "${SCRIPT_DIR}/init_boot.img"
$FASTBOOT_BIN flash boot_a "${SCRIPT_DIR}/boot.img"

echo "[*] Transitioning to fastbootd (userspace fastboot for dynamic partitions)..."
$FASTBOOT_BIN reboot fastboot

echo "[*] Waiting for fastbootd..."
sleep 5

echo "[*] Flashing dynamic logical partition system_a with WinUSB ${CHUNK_SIZE} chunking..."
$FASTBOOT_BIN flash -S "$CHUNK_SIZE" system_a "${SCRIPT_DIR}/system.sparse.img"

if "$WIPE_DATA"; then
    echo "[!] Factory reset requested: erasing userdata and metadata..."
    $FASTBOOT_BIN erase userdata || true
    $FASTBOOT_BIN erase metadata || true
else
    echo "[*] Preserving userdata (no wipe performed)."
fi

echo "===================================================================="
echo "[+] Flashing complete! Rebooting device..."
echo "===================================================================="
$FASTBOOT_BIN reboot
EOF
chmod +x "${BUILD_TMP}/flash_all.sh"

# 4. Generate flash_all.bat (Windows Command Prompt)
echo "[*] Generating flash_all.bat..."
cat <<'EOF' > "${BUILD_TMP}/flash_all.bat"
@echo off
setlocal enabledelayedexpansion

echo ====================================================================
echo  Lenovo Tab M11 (TB311FU) LineageOS 23.2 Fastboot Flasher (Windows)
echo ====================================================================

where fastboot >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: 'fastboot' not found in PATH. Install Android SDK Platform-Tools.
    pause
    exit /b 1
)

echo [*] Checking connected device...
fastboot devices

echo [*] Setting active slot to A...
fastboot set_active a

echo [*] Flashing physical boot chain partitions...
fastboot flash vbmeta_a "%~dp0vbmeta.img"
fastboot flash dtbo_a "%~dp0dtbo.img"
fastboot flash vendor_boot_a "%~dp0vendor_boot.img"
fastboot flash init_boot_a "%~dp0init_boot.img"
fastboot flash boot_a "%~dp0boot.img"

echo [*] Transitioning to fastbootd for dynamic partition deployment...
fastboot reboot fastboot
timeout /t 5 /nobreak >nul

echo [*] Flashing dynamic partition system_a with -S 64M chunking...
fastboot flash -S 64M system_a "%~dp0system.sparse.img"

echo ====================================================================
echo [+] Flashing complete! Rebooting into system...
echo ====================================================================
fastboot reboot
pause
EOF

# 5. Generate flash_all.ps1 (Windows PowerShell)
echo "[*] Generating flash_all.ps1..."
cat <<'EOF' > "${BUILD_TMP}/flash_all.ps1"
<#
.SYNOPSIS
    Lenovo Tab M11 (TB311FU) LineageOS 23.2 Fastboot PowerShell Flasher.
#>
[CmdletBinding()]
param(
    [switch]$WipeData = $false,
    [string]$ChunkSize = "64M"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host " Lenovo Tab M11 (TB311FU) LineageOS 23.2 Fastboot Flasher" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

$fastboot = Get-Command fastboot -ErrorAction SilentlyContinue
if (-not $fastboot) {
    throw "fastboot binary not found on PATH. Install Android SDK Platform Tools."
}

Write-Host "[*] Checking device..."
& fastboot devices

Write-Host "[*] Setting active slot to A..."
& fastboot set_active a

Write-Host "[*] Flashing physical boot chain partitions..."
& fastboot flash vbmeta_a (Join-Path $scriptDir "vbmeta.img")
& fastboot flash dtbo_a (Join-Path $scriptDir "dtbo.img")
& fastboot flash vendor_boot_a (Join-Path $scriptDir "vendor_boot.img")
& fastboot flash init_boot_a (Join-Path $scriptDir "init_boot.img")
& fastboot flash boot_a (Join-Path $scriptDir "boot.img")

Write-Host "[*] Rebooting into fastbootd userspace..."
& fastboot reboot fastboot
Start-Sleep -Seconds 5

Write-Host "[*] Flashing system_a with WinUSB chunking (-S $ChunkSize)..."
& fastboot flash -S $ChunkSize system_a (Join-Path $scriptDir "system.sparse.img")

if ($WipeData) {
    Write-Host "[!] Wiping userdata and metadata..." -ForegroundColor Yellow
    & fastboot erase userdata
    & fastboot erase metadata
} else {
    Write-Host "[*] Preserving userdata (Zero Data Loss)." -ForegroundColor Green
}

Write-Host "====================================================================" -ForegroundColor Green
Write-Host "[+] Flashing completed successfully! Rebooting..." -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Green
& fastboot reboot
EOF

# 6. Archive package
echo "[*] Creating Fastboot distribution package '$OUTPUT_PKG'..."
if [[ "$OUTPUT_PKG" == *.tar.gz || "$OUTPUT_PKG" == *.tgz ]]; then
    tar -czf "$OUTPUT_PKG" -C "$BUILD_TMP" .
else
    (
        cd "$BUILD_TMP"
        zip -q -9 "$OUTPUT_PKG" flash_all.sh flash_all.bat flash_all.ps1
        # Use -0 (stored) for huge sparse and img files to speed up archiving
        zip -q -0 "$OUTPUT_PKG" system.sparse.img boot.img init_boot.img vendor_boot.img dtbo.img vbmeta.img
    )
fi

echo "===================================================================="
echo "[+] SUCCESS: Fastboot deployment set built!"
echo "    Package: $OUTPUT_PKG"
echo "    Size:    $(du -h "$OUTPUT_PKG" | cut -f1)"
echo "===================================================================="

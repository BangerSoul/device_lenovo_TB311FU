#!/usr/bin/env bash
#
# scripts/build_sideload_zip.sh
# OrangeFox / Recovery ADB Sideloadable ZIP Builder
# Target Device: Lenovo Tab M11 (TB311FU / 'poplar', MT8786 / Helio G88)
#
# Builds a flashable/sideloadable ZIP package containing:
#   - META-INF/com/google/android/update-binary
#   - META-INF/com/google/android/updater-script
#   - installer.sh
#   - Partition images: system_a, boot_a, init_boot_a, vendor_boot_a, dtbo_a, vbmeta_a
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
OUTPUT_ZIP=""
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build an OrangeFox/recovery ADB sideloadable ZIP package for Lenovo Tab M11 (TB311FU).

Options:
  -d, --images-dir DIR      Directory containing partition images
  -s, --system PATH         Path to system image (system_a.img or system.img)
  -b, --boot PATH           Path to boot image (boot_a.img or boot.img)
  -i, --init-boot PATH      Path to init_boot image (init_boot_a.img or init_boot.img)
  -v, --vendor-boot PATH    Path to vendor_boot image (vendor_boot_a.img or vendor_boot.img)
  -t, --dtbo PATH           Path to dtbo image (dtbo_a.img or dtbo.img)
  -m, --vbmeta PATH         Path to vbmeta image (vbmeta_a.img or vbmeta.img)
  -o, --output PATH         Output ZIP filepath (default: out/TB311FU-LineageOS-23.2-sideload.zip)
  -f, --force               Overwrite existing output zip
  -h, --help                Show this help message

If --images-dir is provided, images are automatically discovered by name.
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
        -o|--output)
            OUTPUT_ZIP="$2"
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

# Resolve images from directory if provided
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
    [[ -z "$SYSTEM_IMG" ]] && SYSTEM_IMG="$(resolve_file "$IMAGES_DIR" "system_a.img" "system.img" "system_transformed.img" || true)"
    [[ -z "$BOOT_IMG" ]] && BOOT_IMG="$(resolve_file "$IMAGES_DIR" "boot_a.img" "boot.img" "pmos_boot.img" || true)"
    [[ -z "$INIT_BOOT_IMG" ]] && INIT_BOOT_IMG="$(resolve_file "$IMAGES_DIR" "init_boot_a.img" "init_boot.img" || true)"
    [[ -z "$VENDOR_BOOT_IMG" ]] && VENDOR_BOOT_IMG="$(resolve_file "$IMAGES_DIR" "vendor_boot_a.img" "vendor_boot.img" || true)"
    [[ -z "$DTBO_IMG" ]] && DTBO_IMG="$(resolve_file "$IMAGES_DIR" "dtbo_a.img" "dtbo.img" || true)"
    [[ -z "$VBMETA_IMG" ]] && VBMETA_IMG="$(resolve_file "$IMAGES_DIR" "vbmeta_a.img" "vbmeta.img" || true)"
fi

# Validation of mandatory partition images
check_required() {
    local label="$1"
    local path="$2"
    if [[ -z "$path" ]]; then
        echo "Error: Missing required partition image for $label. Specify via options." >&2
        exit 1
    fi
    if [[ ! -f "$path" ]]; then
        echo "Error: File for $label does not exist: '$path'" >&2
        exit 1
    fi
}

check_required "system_a" "$SYSTEM_IMG"
check_required "boot_a" "$BOOT_IMG"
check_required "init_boot_a" "$INIT_BOOT_IMG"
check_required "vendor_boot_a" "$VENDOR_BOOT_IMG"
check_required "dtbo_a" "$DTBO_IMG"
check_required "vbmeta_a" "$VBMETA_IMG"

if [[ -z "$OUTPUT_ZIP" ]]; then
    OUTPUT_ZIP="${REPO_ROOT}/out/TB311FU-LineageOS-23.2-sideload-$(date +%Y%m%d_%H%M%S).zip"
fi

if [[ -f "$OUTPUT_ZIP" ]] && ! "$FORCE"; then
    echo "Error: Output file '$OUTPUT_ZIP' already exists. Use -f/--force to overwrite." >&2
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT_ZIP")"

command -v zip >/dev/null 2>&1 || { echo "Error: 'zip' utility is required." >&2; exit 1; }

BUILD_TMP="$(mktemp -d)"
trap 'rm -rf "$BUILD_TMP"' EXIT

echo "===================================================================="
echo " Lenovo Tab M11 (TB311FU) OrangeFox Sideload ZIP Package Builder"
echo "===================================================================="
echo "System Image:      $SYSTEM_IMG ($(du -h "$SYSTEM_IMG" | cut -f1))"
echo "Boot Image:        $BOOT_IMG ($(du -h "$BOOT_IMG" | cut -f1))"
echo "Init Boot Image:   $INIT_BOOT_IMG ($(du -h "$INIT_BOOT_IMG" | cut -f1))"
echo "Vendor Boot Image: $VENDOR_BOOT_IMG ($(du -h "$VENDOR_BOOT_IMG" | cut -f1))"
echo "DTBO Image:        $DTBO_IMG ($(du -h "$DTBO_IMG" | cut -f1))"
echo "VBMeta Image:      $VBMETA_IMG ($(du -h "$VBMETA_IMG" | cut -f1))"
echo "Output ZIP:        $OUTPUT_ZIP"
echo "===================================================================="

# 1. Stage partition images
echo "[*] Staging partition images..."
ln -sf "$(realpath "$SYSTEM_IMG")" "${BUILD_TMP}/system_a.img"
ln -sf "$(realpath "$BOOT_IMG")" "${BUILD_TMP}/boot_a.img"
ln -sf "$(realpath "$INIT_BOOT_IMG")" "${BUILD_TMP}/init_boot_a.img"
ln -sf "$(realpath "$VENDOR_BOOT_IMG")" "${BUILD_TMP}/vendor_boot_a.img"
ln -sf "$(realpath "$DTBO_IMG")" "${BUILD_TMP}/dtbo_a.img"
ln -sf "$(realpath "$VBMETA_IMG")" "${BUILD_TMP}/vbmeta_a.img"

# 2. Generate META-INF/com/google/android/updater-script
echo "[*] Writing META-INF updater-script..."
META_DIR="${BUILD_TMP}/META-INF/com/google/android"
mkdir -p "$META_DIR"

cat <<'EOF' > "${META_DIR}/updater-script"
# Lenovo Tab M11 (TB311FU / 'poplar') LineageOS 23.2 Sideload Updater Script
ui_print("==================================================");
ui_print(" Lenovo Tab M11 (TB311FU) LineageOS 23.2 Installer");
ui_print(" Android 16 QPR2 / MT8786 / GSI PoplarKernel");
ui_print("==================================================");
EOF

# 3. Generate META-INF/com/google/android/update-binary
echo "[*] Writing META-INF update-binary..."
cat <<'EOF' > "${META_DIR}/update-binary"
#!/sbin/sh
#
# Recovery update-binary entrypoint for OrangeFox / TWRP / Lineage Recovery
# Invokes installer.sh passing OUTFD and package path.
#

set -e

API_VERSION="$1"
OUTFD="$2"
ZIP_PATH="$3"

# Direct output helper
ui_print() {
    if [ -n "$OUTFD" ] && [ -e "/proc/self/fd/$OUTFD" ]; then
        echo "ui_print $1" > "/proc/self/fd/$OUTFD"
        echo "ui_print" > "/proc/self/fd/$OUTFD"
    else
        echo "$1"
    fi
}

ui_print "[*] Initializing OrangeFox/Recovery package installer..."

WORK_DIR="/tmp/tb311fu_installer"
mkdir -p "$WORK_DIR"

# Extract installer.sh from zip if not present
if [ ! -f "${WORK_DIR}/installer.sh" ]; then
    if command -v unzip >/dev/null 2>&1; then
        unzip -o "$ZIP_PATH" "installer.sh" -d "$WORK_DIR"
    fi
fi

if [ -f "${WORK_DIR}/installer.sh" ]; then
    chmod +x "${WORK_DIR}/installer.sh"
    exec sh "${WORK_DIR}/installer.sh" "$API_VERSION" "$OUTFD" "$ZIP_PATH"
else
    ui_print "[-] Error: installer.sh could not be extracted from package."
    exit 1
fi
EOF
chmod +x "${META_DIR}/update-binary"

# 4. Generate root installer.sh
echo "[*] Writing installer.sh..."
cat <<'EOF' > "${BUILD_TMP}/installer.sh"
#!/sbin/sh
#
# installer.sh - Recovery partition flasher for Lenovo Tab M11 (TB311FU)
# Flashes system_a, boot_a, init_boot_a, vendor_boot_a, dtbo_a, vbmeta_a
#

set -e

API_VERSION="$1"
OUTFD="$2"
ZIP_PATH="$3"

ui_print() {
    if [ -n "$OUTFD" ] && [ -e "/proc/self/fd/$OUTFD" ]; then
        echo "ui_print $1" > "/proc/self/fd/$OUTFD"
        echo "ui_print" > "/proc/self/fd/$OUTFD"
    else
        echo "$1"
    fi
}

ui_print "=================================================="
ui_print "  Lenovo Tab M11 (TB311FU) ROM Flasher"
ui_print "  LineageOS 23.2 (Android 16 QPR2 GSI)"
ui_print "=================================================="

# Check device codename
DEVICE="$(getprop ro.product.device || getprop ro.build.product || true)"
if [ -n "$DEVICE" ] && [ "$DEVICE" != "TB311FU" ] && [ "$DEVICE" != "poplar" ]; then
    ui_print "[!] Warning: Product device is '$DEVICE' (expected TB311FU/poplar)."
fi

# Determine target slot
SLOT="$(getprop ro.boot.slot_suffix || true)"
if [ -z "$SLOT" ]; then
    SLOT="_a"
fi
ui_print "[*] Target installation slot: $SLOT"

# Helper to find block device by partition name
find_block_dev() {
    local part="$1"
    local candidates="
        /dev/block/mapper/${part}
        /dev/block/by-name/${part}
        /dev/block/platform/bootdevice/by-name/${part}
        /dev/block/platform/*/by-name/${part}
    "
    for dev in $candidates; do
        if [ -b "$dev" ]; then
            echo "$dev"
            return 0
        fi
    done
    return 1
}

# Flash partition image from zip
flash_partition() {
    local img_name="$1"
    local part_name="$2"
    local blk_dev

    blk_dev="$(find_block_dev "$part_name" || true)"
    if [ -z "$blk_dev" ]; then
        # Try without slot suffix if suffixed lookup failed
        local base_part="${part_name%_a}"
        base_part="${base_part%_b}"
        blk_dev="$(find_block_dev "$base_part" || true)"
    fi

    if [ -z "$blk_dev" ]; then
        ui_print "[-] Warning: Block device for partition '${part_name}' not found. Skipping."
        return 0
    fi

    ui_print "[*] Flashing ${img_name} -> ${blk_dev}..."
    if command -v unzip >/dev/null 2>&1; then
        unzip -p "$ZIP_PATH" "$img_name" | dd of="$blk_dev" bs=1048576 2>/dev/null
    else
        ui_print "[-] unzip utility missing in recovery shell; cannot stream payload."
        return 1
    fi
    ui_print "[+] ${part_name} written successfully."
}

# 1. Flash physical boot chain partitions
flash_partition "vbmeta_a.img" "vbmeta_a"
flash_partition "dtbo_a.img" "dtbo_a"
flash_partition "vendor_boot_a.img" "vendor_boot_a"
flash_partition "init_boot_a.img" "init_boot_a"
flash_partition "boot_a.img" "boot_a"

# 2. Flash dynamic system partition
flash_partition "system_a.img" "system_a"

ui_print "[*] Committing writes to storage (sync)..."
sync

ui_print "=================================================="
ui_print "[+] Installation complete! Reboot into system."
ui_print "=================================================="
exit 0
EOF
chmod +x "${BUILD_TMP}/installer.sh"

# 5. Build ZIP package
echo "[*] Creating zip archive '$OUTPUT_ZIP'..."
(
    cd "$BUILD_TMP"
    # Store partition images with -0 (no compression for fast flashing and streaming)
    # Store META-INF and scripts with standard compression
    zip -q -9 -r "$OUTPUT_ZIP" META-INF installer.sh
    zip -q -0 "$OUTPUT_ZIP" system_a.img boot_a.img init_boot_a.img vendor_boot_a.img dtbo_a.img vbmeta_a.img
)

echo "===================================================================="
echo "[+] SUCCESS: OrangeFox Sideload ZIP created!"
echo "    File: $OUTPUT_ZIP"
echo "    Size: $(du -h "$OUTPUT_ZIP" | cut -f1)"
echo "===================================================================="

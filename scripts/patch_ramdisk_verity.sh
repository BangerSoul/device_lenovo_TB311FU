#!/usr/bin/env bash
#
# patch_ramdisk_verity.sh - Ramdisk fstab AVB / dm-verity patcher
#
# Removes:
#   - avb flags (avb, avb=vbmeta, avb=vbmeta_system, avb=vbmeta_vendor)
#   - avb_keys flags (avb_keys=...)
#   - verify flags (verify, verify=..., verify_at_boot)
# Converts:
#   - forceencrypt=... -> encryptable=...
#   - forceencrypt     -> encryptable
#   - forcefde=...     -> encryptable=...
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_UTIL="${SCRIPT_DIR}/patch_ramdisk_verity.py"

usage() {
    cat << 'EOF'
Usage: patch_ramdisk_verity.sh [options] <fstab_file | ramdisk_dir | boot.img> [...]

Options:
  -b, --backup        Create .bak backup copy of modified fstab files
  -o, --output <file> Output patched fstab to file (single file mode only)
  -d, --diff          Display unified diff of changes made
  -h, --help          Show this help message

Supported Targets:
  - Direct fstab files: e.g. fstab.mt6768, recovery.fstab
  - Ramdisk root directories: recursively finds all fstabs and patches them
  - boot.img / vendor_boot.img: automatically unpacks, patches ramdisk fstab,
    and repacks using magiskboot (when available)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ $# -eq 0 ]]; then
    echo "Error: No target specified." >&2
    usage
    exit 1
fi

# Check if target is a boot.img / vendor_boot.img
is_boot_image() {
    local target="$1"
    if [[ ! -f "$target" ]]; then
        return 1
    fi
    # Check Android boot image magic: "ANDROID!" (8 bytes)
    local magic
    magic="$(head -c 8 "$target" 2>/dev/null || true)"
    if [[ "$magic" == "ANDROID!" ]]; then
        return 0
    fi
    # Or filename ends in boot.img / vendor_boot.img / init_boot.img
    case "$target" in
        *.img)
            if [[ "$target" =~ (boot|vendor_boot|init_boot|recovery) ]]; then
                return 0
            fi
            ;;
    esac
    return 1
}

# If first non-flag argument is a boot image, handle via magiskboot if present
non_flag_args=()
for arg in "$@"; do
    if [[ ! "$arg" =~ ^- ]]; then
        non_flag_args+=("$arg")
    fi
done

if [[ ${#non_flag_args[@]} -eq 1 ]] && is_boot_image "${non_flag_args[0]}"; then
    boot_img="${non_flag_args[0]}"
    echo "[patch_ramdisk_verity.sh] Detected boot/kernel image: ${boot_img}"

    if ! command -v magiskboot >/dev/null 2>&1; then
        echo "[patch_ramdisk_verity.sh] Notice: magiskboot is not found in PATH."
        echo "Extracting/repacking full boot.img requires magiskboot."
        echo "If you have an extracted ramdisk or fstab, pass that path directly."
        # If python3 is available, try running python patcher in case user meant direct file
        if command -v python3 >/dev/null 2>&1 && [[ -f "${PYTHON_UTIL}" ]]; then
            exec python3 "${PYTHON_UTIL}" "$@"
        fi
        exit 1
    fi

    echo "[patch_ramdisk_verity.sh] Unpacking ${boot_img} with magiskboot..."
    WORK_DIR="$(mktemp -d -t boot_patch_XXXXXX)"
    trap 'rm -rf "${WORK_DIR}"' EXIT

    cp "${boot_img}" "${WORK_DIR}/target.img"
    (
        cd "${WORK_DIR}"
        magiskboot unpack target.img
        if [[ -f ramdisk.cpio ]]; then
            echo "[patch_ramdisk_verity.sh] Unpacking ramdisk.cpio..."
            mkdir -p ramdisk_root
            (
                cd ramdisk_root
                magiskboot cpio ../ramdisk.cpio extract || cpio -idmv < ../ramdisk.cpio 2>/dev/null || true
            )
            # Patch ramdisk root
            python3 "${PYTHON_UTIL}" ramdisk_root
            # Repack ramdisk
            (
                cd ramdisk_root
                find . | cpio -H newc -o > ../ramdisk.cpio
            )
            echo "[patch_ramdisk_verity.sh] Repacking ${boot_img}..."
            magiskboot repack target.img
            if [[ -f new-boot.img ]]; then
                mv new-boot.img "${boot_img}"
                echo "[patch_ramdisk_verity.sh] Successfully patched and repacked ${boot_img}"
            fi
        else
            echo "[patch_ramdisk_verity.sh] No ramdisk.cpio found in ${boot_img}"
        fi
    )
    exit 0
fi

# Standard path: invoke python utility
if command -v python3 >/dev/null 2>&1 && [[ -f "${PYTHON_UTIL}" ]]; then
    exec python3 "${PYTHON_UTIL}" "$@"
fi

# Fallback bash/sed implementation if python3 is unavailable
echo "[patch_ramdisk_verity.sh] Warning: python3 not available, using sed fallback" >&2

for target in "$@"; do
    if [[ "$target" =~ ^- ]]; then
        continue
    fi
    if [[ -f "$target" ]]; then
        sed -i -E \
            -e 's/avb_keys=[^,[:space:]]+,?//g' \
            -e 's/avb=[^,[:space:]]+,?//g' \
            -e 's/\bavb,?//g' \
            -e 's/verify=[^,[:space:]]+,?//g' \
            -e 's/\bverify_at_boot,?//g' \
            -e 's/\bverify,?//g' \
            -e 's/\bforceencrypt=/encryptable=/g' \
            -e 's/\bforcefde=/encryptable=/g' \
            -e 's/,[[:space:]]*$//g' \
            -e 's/,[[:space:]]*,/,/g' \
            -e 's/[[:space:]],/[[:space:]]/g' \
            "$target"
        echo "[patch_ramdisk_verity.sh] Sed patched: $target"
    fi
done

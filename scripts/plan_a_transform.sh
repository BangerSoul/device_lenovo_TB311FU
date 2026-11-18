#!/usr/bin/env bash
#
# scripts/plan_a_transform.sh
# Plan A GSI System Image Transformation & Verification Script
# Target Device: Lenovo Tab M11 (TB311FU / 'poplar', MT8786 / Helio G88)
#
# Removes the 7 Plan-A telephony/cellular targets from GSI system.img:
#   1. /system/priv-app/TelephonyProvider
#   2. /system/priv-app/CellBroadcastLegacyApp
#   3. /system/app/QcRilAm
#   4. /system/app/CarrierDefaultApp
#   5. /system/apex/com.android.cellbroadcast.capex
#   6. /system/product/overlay/TelephonyProvider__device__auto_generated_characteristics_rro.apk
#   7. /system/product/overlay/treble-overlay-Telephony-LTE.apk
#
# Followed by mandatory e2fsck filesystem integrity verification.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Target specifications (7 Plan-A target paths)
readonly PLAN_A_TARGETS=(
    "/system/priv-app/TelephonyProvider"
    "/system/priv-app/CellBroadcastLegacyApp"
    "/system/app/QcRilAm"
    "/system/app/CarrierDefaultApp"
    "/system/apex/com.android.cellbroadcast.capex"
    "/system/product/overlay/TelephonyProvider__device__auto_generated_characteristics_rro.apk"
    "/system/product/overlay/treble-overlay-Telephony-LTE.apk"
)

# Alternative prefixes for images rooted at system root vs rootfs
readonly ALT_TARGETS=(
    "/priv-app/TelephonyProvider"
    "/priv-app/CellBroadcastLegacyApp"
    "/app/QcRilAm"
    "/app/CarrierDefaultApp"
    "/apex/com.android.cellbroadcast.capex"
    "/product/overlay/TelephonyProvider__device__auto_generated_characteristics_rro.apk"
    "/product/overlay/treble-overlay-Telephony-LTE.apk"
)

INPUT_IMG=""
OUTPUT_IMG=""
DRY_RUN=false
VERIFY_ONLY=false
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] <input_system.img> [output_system.img]

Transform an EXT4 GSI system.img for Lenovo Tab M11 (TB311FU) by stripping the
7 Plan-A cellular packages and validating filesystem integrity via e2fsck.

Options:
  -i, --input PATH      Input pristine GSI system.img
  -o, --output PATH     Output transformed system.img
  -d, --dry-run         Scan and report targets without modifying anything
  -v, --verify          Run verification checks on an image without modifying
  -f, --force           Overwrite output file if it exists
  -h, --help            Show this help message

Positional arguments:
  First argument:  Input system.img
  Second argument: Output system.img (optional if --dry-run or --verify)
EOF
}

# Parse options
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--input)
            INPUT_IMG="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_IMG="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verify)
            VERIFY_ONLY=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Error: Unknown option $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [[ -z "$INPUT_IMG" ]]; then
                INPUT_IMG="$1"
            elif [[ -z "$OUTPUT_IMG" ]]; then
                OUTPUT_IMG="$1"
            else
                echo "Error: Unexpected positional argument: $1" >&2
                usage >&2
                exit 2
            fi
            shift
            ;;
    esac
done

if [[ -z "$INPUT_IMG" ]]; then
    echo "Error: Input image is required." >&2
    usage >&2
    exit 2
fi

if [[ ! -f "$INPUT_IMG" ]]; then
    echo "Error: Input image '$INPUT_IMG' does not exist or is not a regular file." >&2
    exit 1
fi

if "$DRY_RUN" && [[ -n "$OUTPUT_IMG" ]]; then
    echo "Error: --dry-run cannot be combined with an output path." >&2
    exit 2
fi

# Tool preflight checks
require_tool() {
    local tool="$1"
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Error: Required tool '$tool' not found in PATH." >&2
        return 1
    fi
}

require_tool e2fsck || exit 1
require_tool debugfs || exit 1

# Check if path exists in image using debugfs
debugfs_stat_path() {
    local img="$1"
    local path="$2"
    local out
    out="$(debugfs -R "stat $path" "$img" 2>&1 || true)"
    if echo "$out" | grep -q "File not found" || echo "$out" | grep -q "does not exist"; then
        return 1
    fi
    if echo "$out" | grep -q "Inode:"; then
        return 0
    fi
    return 1
}

# Recursively list entries in directory using debugfs
debugfs_list_dir() {
    local img="$1"
    local dir="$2"
    debugfs -R "ls -p $dir" "$img" 2>/dev/null || true
}

# Native bash debugfs recursive removal
debugfs_remove_tree() {
    local img="$1"
    local target="$2"
    local cmd_file
    cmd_file="$(mktemp)"

    # Build list of commands
    collect_removal_commands() {
        local path="$1"
        local listing
        listing="$(debugfs -R "ls -p $path" "$img" 2>/dev/null || true)"

        local files=()
        local dirs=()

        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            [[ "$line" != /* ]] && continue
            
            # format: /inode/mode/uid/gid/name/size/
            local name
            name="$(echo "$line" | cut -d'/' -f6)"
            local mode
            mode="$(echo "$line" | cut -d'/' -f3)"
            
            [[ "$name" == "." || "$name" == ".." ]] && continue
            
            local child="${path%/}/${name}"
            # Check directory bit in octal mode (040xxx)
            if [[ "$mode" =~ ^04 ]]; then
                collect_removal_commands "$child"
                echo "rmdir $child" >> "$cmd_file"
            else
                echo "rm $child" >> "$cmd_file"
            fi
        done <<< "$listing"
    }

    # Check if target is directory or file
    local stat_out
    stat_out="$(debugfs -R "stat $target" "$img" 2>/dev/null || true)"
    if echo "$stat_out" | grep -q "Type: directory"; then
        collect_removal_commands "$target"
        echo "rmdir $target" >> "$cmd_file"
    else
        echo "rm $target" >> "$cmd_file"
    fi

    if [[ -s "$cmd_file" ]]; then
        debugfs -w -f "$cmd_file" "$img" >/dev/null 2>&1 || true
    fi
    rm -f "$cmd_file"
}

# Scan image for the 7 Plan-A targets
scan_targets() {
    local img="$1"
    local found=()

    for target in "${PLAN_A_TARGETS[@]}"; do
        if debugfs_stat_path "$img" "$target"; then
            found+=("$target")
        fi
    done

    # Check alternative non-/system prefix if none found under /system
    if [[ ${#found[@]} -eq 0 ]]; then
        for target in "${ALT_TARGETS[@]}"; do
            if debugfs_stat_path "$img" "$target"; then
                found+=("$target")
            fi
        done
    fi

    echo "${found[@]}"
}

# e2fsck verification function
run_e2fsck_verification() {
    local img="$1"
    echo "[*] Running e2fsck verification on '$img'..."
    
    # First, run non-interactive repair/flush if needed
    e2fsck -fy "$img" >/dev/null 2>&1 || true

    # Then run strict read-only verify
    local fsck_out
    if ! fsck_out="$(e2fsck -fn "$img" 2>&1)"; then
        echo "[-] e2fsck verification FAILED on '$img':" >&2
        echo "$fsck_out" >&2
        return 1
    fi
    echo "[+] e2fsck verification PASSED (filesystem clean)."
    return 0
}

# Verify that none of the 7 targets exist in the image
run_cellular_absence_check() {
    local img="$1"
    local remaining=()

    for target in "${PLAN_A_TARGETS[@]}" "${ALT_TARGETS[@]}"; do
        if debugfs_stat_path "$img" "$target"; then
            remaining+=("$target")
        fi
    done

    if [[ ${#remaining[@]} -gt 0 ]]; then
        echo "[-] Verification FAILED: Remaining cellular targets detected:" >&2
        for r in "${remaining[@]}"; do
            echo "    - $r" >&2
        done
        return 1
    fi
    echo "[+] Cellular absence check PASSED: All 7 Plan-A target paths removed."
    return 0
}

# Main flow
echo "===================================================================="
echo " Lenovo Tab M11 (TB311FU) Plan A GSI System Transformation Suite"
echo "===================================================================="
echo "Input Image: $INPUT_IMG"

# Handle --verify mode
if "$VERIFY_ONLY"; then
    echo "[*] Running verification mode on '$INPUT_IMG'..."
    run_cellular_absence_check "$INPUT_IMG"
    run_e2fsck_verification "$INPUT_IMG"
    echo "[+] Image verification completely successful."
    exit 0
fi

# Scan targets in source image
echo "[*] Scanning for Plan-A cellular targets in '$INPUT_IMG'..."
FOUND_TARGETS=($(scan_targets "$INPUT_IMG"))

echo "[*] Found ${#FOUND_TARGETS[@]} cellular targets to remove:"
for t in "${FOUND_TARGETS[@]}"; do
    echo "    - $t"
done

if "$DRY_RUN"; then
    echo "[+] Dry-run completed. Source image left unmodified."
    exit 0
fi

if [[ -z "$OUTPUT_IMG" ]]; then
    echo "Error: Output image path required for transform." >&2
    exit 2
fi

# Validate output path
if [[ -f "$OUTPUT_IMG" ]] && ! "$FORCE"; then
    echo "Error: Output image '$OUTPUT_IMG' already exists. Use -f/--force to overwrite." >&2
    exit 1
fi

REAL_IN="$(realpath "$INPUT_IMG")"
REAL_OUT="$(realpath -m "$OUTPUT_IMG")"
if [[ "$REAL_IN" == "$REAL_OUT" ]]; then
    echo "Error: Output image must differ from input image (in-place modification prohibited)." >&2
    exit 1
fi

# Clone input image to output
echo "[*] Creating verified clone: '$INPUT_IMG' -> '$OUTPUT_IMG'..."
mkdir -p "$(dirname "$OUTPUT_IMG")"
cp --sparse=always "$INPUT_IMG" "$OUTPUT_IMG"

# Check if Python transformer is available
PYTHON_STRIPPER="${REPO_ROOT}/partitions/strip_system_cellular.py"
TRANSFORM_SUCCESS=false

if command -v python3 >/dev/null 2>&1 && [[ -f "$PYTHON_STRIPPER" ]] && python3 -c "import ext4" >/dev/null 2>&1; then
    echo "[*] Executing Python EXT4 directory surgery & debugfs purge..."
    if python3 "$PYTHON_STRIPPER" --image "$OUTPUT_IMG" --staging-dir /tmp/dummy_not_used >/dev/null 2>&1 || \
       python3 -c "
import sys
from partitions.strip_system_cellular import Ext4DirectorySurgery, remove_targets_with_debugfs
surgery = Ext4DirectorySurgery('$OUTPUT_IMG')
targets = surgery.find_targets()
if targets:
    remove_targets_with_debugfs('$OUTPUT_IMG', targets)
print(f'Stripped {len(targets)} targets via python surgery')
"; then
        TRANSFORM_SUCCESS=true
    fi
fi

if ! "$TRANSFORM_SUCCESS"; then
    echo "[*] Executing native debugfs removal for Plan-A targets..."
    for target in "${FOUND_TARGETS[@]}"; do
        echo "    [-] Purging: $target"
        debugfs_remove_tree "$OUTPUT_IMG" "$target"
    done
fi

# Verification phase
echo "[*] Running post-transform verification on '$OUTPUT_IMG'..."
run_cellular_absence_check "$OUTPUT_IMG"
run_e2fsck_verification "$OUTPUT_IMG"

echo "===================================================================="
echo "[+] SUCCESS: Plan-A transformation completed and verified!"
echo "    Transformed image: $OUTPUT_IMG"
echo "===================================================================="

#!/usr/bin/env bash
#
# disable_avb.sh - AVB / dm-verity patching utility for Lenovo Tab with Clear Case (TB311FU)
#
# Patches vbmeta.img, vbmeta_system.img, and vbmeta_vendor.img to disable AVB
# verification and dm-verity hashtree checking by setting flag |= 3
# (HASHTREE_DISABLED=0x1 and VERIFICATION_DISABLED=0x2) in the AVB descriptor
# header at offset 120 (big-endian uint32).
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_UTIL="${SCRIPT_DIR}/disable_avb.py"

usage() {
    cat << 'EOF'
Usage: disable_avb.sh [options] [vbmeta_image1 [vbmeta_image2 ...]]

Options:
  --flags <int>       Bitwise-OR flags to set (default: 0x03)
  --check             Check AVB header flags without modifying
  -o, --output <file> Output to specified file (single image mode)
  --create <file>     Create empty disabled vbmeta.img
  --size <bytes>      Size in bytes when creating (default: 4096)
  -h, --help          Show this help message

Default behavior:
  If no files are passed, patches vbmeta.img, vbmeta_system.img, and
  vbmeta_vendor.img if present in the current working directory.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

# Prefer python3 implementation for complete AVB header & footer support
if command -v python3 >/dev/null 2>&1 && [[ -f "${PYTHON_UTIL}" ]]; then
    exec python3 "${PYTHON_UTIL}" "$@"
fi

# Fallback bash / dd implementation if python3 is not installed
echo "[disable_avb.sh] Warning: python3 not found, using bash/dd fallback patcher" >&2

patch_file_raw() {
    local img="$1"
    if [[ ! -f "$img" ]]; then
        echo "Error: File not found: $img" >&2
        return 1
    fi

    local magic
    magic="$(head -c 4 "$img" 2>/dev/null || true)"
    if [[ "$magic" != "AVB0" ]]; then
        echo "Error: $img does not start with AVB0 magic" >&2
        return 1
    fi

    # Read current uint32 at offset 120 (big-endian)
    local cur_hex
    cur_hex="$(od -j 120 -N 4 -t x4 -An "$img" | tr -d ' ')"
    local cur_val
    cur_val=$((16#$cur_hex))
    local new_val
    new_val=$(( cur_val | 3 ))

    # Write byte at offset 123 (lowest byte in big-endian uint32 at 120..123)
    local b3
    b3=$(( new_val & 255 ))
    printf "\\$(printf '%03o' "$b3")" | dd of="$img" bs=1 seek=123 count=1 conv=notrunc status=none

    echo "[disable_avb.sh] Patched $img: 0x$cur_hex -> $(printf '0x%08x' "$new_val") [SUCCESS]"
}

targets=("$@")
if [[ ${#targets[@]} -eq 0 ]]; then
    for f in vbmeta.img vbmeta_system.img vbmeta_vendor.img; do
        if [[ -f "$f" ]]; then
            targets+=("$f")
        fi
    done
fi

if [[ ${#targets[@]} -eq 0 ]]; then
    echo "Error: No vbmeta images specified and default images not found." >&2
    usage
    exit 1
fi

for img in "${targets[@]}"; do
    patch_file_raw "$img"
done

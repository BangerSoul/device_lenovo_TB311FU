#!/usr/bin/env bash
#
# scripts/build_ota_payload.sh
# Android A/B OTA Payload (payload.bin) & Properties Builder
# Target Device: Lenovo Tab M11 (TB311FU / 'poplar', MT8786 / Helio G88)
#
# Generates signed payload.bin and payload_properties.txt using a test signing key.
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
KEY_PATH=""
OUTPUT_DIR=""
ZIP_OUTPUT=""
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build an Android A/B OTA payload (payload.bin + payload_properties.txt) for Lenovo Tab M11 (TB311FU).

Options:
  -d, --images-dir DIR      Directory containing partition images
  -s, --system PATH         Path to system image (system_a.img or system.img)
  -b, --boot PATH           Path to boot image (boot_a.img or boot.img)
  -i, --init-boot PATH      Path to init_boot image (init_boot_a.img or init_boot.img)
  -v, --vendor-boot PATH    Path to vendor_boot image (vendor_boot_a.img or vendor_boot.img)
  -t, --dtbo PATH           Path to dtbo image (dtbo_a.img or dtbo.img)
  -m, --vbmeta PATH         Path to vbmeta image (vbmeta_a.img or vbmeta.img)
  -k, --key PATH            Path to RSA private signing key (default: keys/testkey.pem, auto-generated if missing)
  -o, --output-dir DIR      Output directory for payload.bin and payload_properties.txt (default: out/ota)
  -z, --zip-pkg PATH        Path to bundle into OTA zip package (default: out/TB311FU-LineageOS-23.2-ota.zip)
  -f, --force               Overwrite existing output files
  -h, --help                Show this help message
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
        -k|--key)
            KEY_PATH="$2"
            shift 2
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -z|--zip-pkg)
            ZIP_OUTPUT="$2"
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

if [[ -z "$KEY_PATH" ]]; then
    KEY_PATH="${REPO_ROOT}/keys/testkey.pem"
fi

if [[ ! -f "$KEY_PATH" ]]; then
    mkdir -p "$(dirname "$KEY_PATH")"
    echo "[*] Generating test signing key: $KEY_PATH..."
    openssl genrsa -out "$KEY_PATH" 2048
fi

if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="${REPO_ROOT}/out/ota"
fi

mkdir -p "$OUTPUT_DIR"

PAYLOAD_BIN="${OUTPUT_DIR}/payload.bin"
PAYLOAD_PROPS="${OUTPUT_DIR}/payload_properties.txt"

if [[ -f "$PAYLOAD_BIN" ]] && ! "$FORCE"; then
    echo "Error: Output payload '$PAYLOAD_BIN' already exists. Use -f/--force to overwrite." >&2
    exit 1
fi

echo "===================================================================="
echo " Lenovo Tab M11 (TB311FU) Android A/B OTA Payload Builder"
echo "===================================================================="
echo "System Image:      $SYSTEM_IMG ($(du -h "$SYSTEM_IMG" | cut -f1))"
echo "Boot Image:        $BOOT_IMG"
echo "Init Boot Image:   $INIT_BOOT_IMG"
echo "Vendor Boot Image: $VENDOR_BOOT_IMG"
echo "DTBO Image:        $DTBO_IMG"
echo "VBMeta Image:      $VBMETA_IMG"
echo "Signing Key:       $KEY_PATH"
echo "Output Directory:  $OUTPUT_DIR"
echo "===================================================================="

# Check if native delta_generator binary is available
DELTA_GEN="$(command -v delta_generator || true)"
if [[ -z "$DELTA_GEN" && -f "${REPO_ROOT}/tools/bin/delta_generator" ]]; then
    DELTA_GEN="${REPO_ROOT}/tools/bin/delta_generator"
fi

BUILD_SUCCESS=false

if [[ -n "$DELTA_GEN" && -x "$DELTA_GEN" ]]; then
    echo "[*] Using host delta_generator binary: $DELTA_GEN..."
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT

    PART_NAMES="system:boot:init_boot:vendor_boot:dtbo:vbmeta"
    PART_FILES="$SYSTEM_IMG:$BOOT_IMG:$INIT_BOOT_IMG:$VENDOR_BOOT_IMG:$DTBO_IMG:$VBMETA_IMG"

    # Step 1: Generate unsigned payload
    "$DELTA_GEN" -out_file="${TMP_DIR}/unsigned-payload.bin" \
        -partition_names="$PART_NAMES" \
        -new_partitions="$PART_FILES"

    # Step 2: Compute hash digests
    "$DELTA_GEN" --in_file="${TMP_DIR}/unsigned-payload.bin" \
        -signature_size=256 \
        -out_metadata_hash_file="${TMP_DIR}/sig_metadata.bin" \
        -out_hash_file="${TMP_DIR}/sig_hash.bin"

    # Step 3: Sign digests with RSA test key
    openssl pkeyutl -sign -inkey "$KEY_PATH" -pkeyopt digest:sha256 -in "${TMP_DIR}/sig_hash.bin" -out "${TMP_DIR}/signed_hash.bin"
    openssl pkeyutl -sign -inkey "$KEY_PATH" -pkeyopt digest:sha256 -in "${TMP_DIR}/sig_metadata.bin" -out "${TMP_DIR}/signed_metadata.bin"

    # Step 4: Inject signatures into final signed payload
    "$DELTA_GEN" --in_file="${TMP_DIR}/unsigned-payload.bin" \
        --out_file="$PAYLOAD_BIN" \
        --signature_size=256 \
        --metadata_signature_file="${TMP_DIR}/signed_metadata.bin" \
        --payload_signature_file="${TMP_DIR}/signed_hash.bin"

    # Step 5: Dump properties
    "$DELTA_GEN" --in_file="$PAYLOAD_BIN" --properties_file="$PAYLOAD_PROPS"
    BUILD_SUCCESS=true
fi

if ! "$BUILD_SUCCESS"; then
    echo "[*] Using Python A/B payload generator..."
    PYTHONPATH="${REPO_ROOT}" python3 "${REPO_ROOT}/tools/build_payload.py" \
        --partitions \
            "system=$SYSTEM_IMG" \
            "boot=$BOOT_IMG" \
            "init_boot=$INIT_BOOT_IMG" \
            "vendor_boot=$VENDOR_BOOT_IMG" \
            "dtbo=$DTBO_IMG" \
            "vbmeta=$VBMETA_IMG" \
        --key "$KEY_PATH" \
        --out-payload "$PAYLOAD_BIN" \
        --out-properties "$PAYLOAD_PROPS"
fi

# Bundle into OTA package zip if requested or by default
if [[ -z "$ZIP_OUTPUT" ]]; then
    ZIP_OUTPUT="${REPO_ROOT}/out/TB311FU-LineageOS-23.2-ota-$(date +%Y%m%d_%H%M%S).zip"
fi

echo "[*] Packaging OTA release ZIP: '$ZIP_OUTPUT'..."
mkdir -p "$(dirname "$ZIP_OUTPUT")"
(
    cd "$OUTPUT_DIR"
    zip -q -0 "$ZIP_OUTPUT" payload.bin payload_properties.txt
)

echo "===================================================================="
echo "[+] SUCCESS: Android A/B OTA Payload created!"
echo "    Payload:    $PAYLOAD_BIN ($(du -h "$PAYLOAD_BIN" | cut -f1))"
echo "    Properties: $PAYLOAD_PROPS"
echo "    OTA ZIP:    $ZIP_OUTPUT ($(du -h "$ZIP_OUTPUT" | cut -f1))"
echo "===================================================================="
cat "$PAYLOAD_PROPS"

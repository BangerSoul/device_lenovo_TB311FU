#!/usr/bin/env bash
# ==============================================================================
# ArrowOS Automated Build Script for Lenovo Tab with Clear Case (TB311FU / poplar)
# Target: ArrowOS 14.0 (Android 14)
# ==============================================================================

set -eo pipefail

TARGET_DEVICE="TB311FU"
ROM_NAME="arrow"
LUNCH_VARIANT="${1:-userdebug}"
LUNCH_TARGET="${ROM_NAME}_${TARGET_DEVICE}-${LUNCH_VARIANT}"
# Limit default build jobs to 4 to prevent Out-Of-Memory thrashing on 8GB RAM
BUILD_JOBS="${BUILD_JOBS:-4}"

# Memory management guards for 8GB host
export GOMEMLIMIT="4GiB"
export GOGC="50"
export _JAVA_OPTIONS="-Xmx4g"
export NINJA_ARGS="-j${BUILD_JOBS}"
export BUILD_BROKEN_DISABLE_BAZEL="true"

echo "======================================================================"
echo " Starting ArrowOS Build for Lenovo Tab with Clear Case (${TARGET_DEVICE})"
echo " Target: ${LUNCH_TARGET}"
echo " Jobs:   ${BUILD_JOBS}"
echo "======================================================================"

# Ensure we are at the top of the Android build tree
if [ ! -f "build/envsetup.sh" ]; then
    echo "ERROR: Please run this script from the root of your ArrowOS source tree!"
    echo "Example:"
    echo "  cd /path/to/arrowos-source"
    echo "  bash device/lenovo/TB311FU/scripts/build_arrow.sh [userdebug|user|eng]"
    exit 1
fi

# Set up ccache (capped to 30G to preserve NVMe disk space)
export USE_CCACHE=1
export CCACHE_EXEC="$(which ccache 2>/dev/null || echo '/usr/bin/ccache')"
export CCACHE_DIR="${HOME}/.ccache"
if [ -x "${CCACHE_EXEC}" ]; then
    "${CCACHE_EXEC}" -M 30G 2>/dev/null || true
    echo "CCache enabled at: ${CCACHE_DIR} (30GB cap)"
fi

# Initialize build environment
echo "--> Sourcing build/envsetup.sh..."
source build/envsetup.sh

# Select lunch target
echo "--> Executing lunch ${LUNCH_TARGET}..."
lunch "${LUNCH_TARGET}"

# Build bacon (ArrowOS target zip)
echo "--> Compiling ArrowOS image target (m bacon)..."
m bacon -j"${BUILD_JOBS}"

echo "======================================================================"
echo " ArrowOS build finished successfully!"
echo " Output images located in: out/target/product/${TARGET_DEVICE}/"
echo "======================================================================"

# If USB Ventoy drive is mounted, copy the flashable zip
USB_MOUNT="/run/media/bangersoul/Ventoy"
if [ -d "${USB_MOUNT}" ]; then
    echo "--> Detected USB drive at ${USB_MOUNT}. Copying output zip..."
    cp -v out/target/product/"${TARGET_DEVICE}"/Arrow-*.zip "${USB_MOUNT}/" 2>/dev/null || true
    sync
    echo "--> Successfully copied flashable ZIP to USB drive!"
fi

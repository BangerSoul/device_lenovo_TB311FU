#!/bin/sh
#
# Copyright (C) 2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#
# Widevine L1 Security Level Verification Script for Lenovo Tab M11 (TB311FU)
#

echo "================================================================================"
echo " Widevine DRM L1 Verification on Lenovo Tab M11 (TB311FU)"
echo "================================================================================"

# 1. Check MediaDrm Security Level via dumpsys
echo "[*] Querying dumpsys media.drm for Widevine crypto engine..."
SEC_LEVEL=$(dumpsys media.drm 2>/dev/null | grep -i "securityLevel" | head -n 1 | tr -d ' \r\n')

if [ -n "$SEC_LEVEL" ]; then
    echo "[+] Found DRM Security Level: $SEC_LEVEL"
else
    echo "[!] Could not query securityLevel directly from media.drm dumpsys."
fi

# 2. Check vendor DRM service status
echo "[*] Verifying vendor Widevine HIDL daemon status..."
WIDEVINE_PID=$(getprop init.svc.vendor.drm-widevine-hal-1-4)
if [ "$WIDEVINE_PID" = "running" ]; then
    echo "[+] vendor.drm-widevine-hal-1-4 is RUNNING."
else
    echo "[!] vendor.drm-widevine-hal-1-4 status: $WIDEVINE_PID"
fi

# 3. Verify read-only mount status of protect1 and protect2
echo "[*] Checking mount options of DRM partitions..."
mount | grep -E "protect1|protect2|persist" | while read -r line; do
    echo "    $line"
    if echo "$line" | grep -q "ro,"; then
        echo "    [+] Partition is correctly mounted READ-ONLY."
    else
        echo "    [!] WARNING: Partition is NOT mounted read-only!"
    fi
done

echo "================================================================================"
echo " Verification Complete."
echo "================================================================================"

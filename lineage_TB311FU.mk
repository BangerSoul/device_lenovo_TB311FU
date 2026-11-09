#
# Copyright (C) 2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from Lineage common product configuration
$(call inherit-product-if-exists, vendor/lineage/config/common_full_tablet_wifionly.mk)

# Inherit from device configuration
$(call inherit-product, $(LOCAL_DIR)/device.mk)

# Device Identifiers
PRODUCT_NAME := lineage_TB311FU
PRODUCT_DEVICE := TB311FU
PRODUCT_BRAND := Lenovo
PRODUCT_MODEL := Tab M11
PRODUCT_MANUFACTURER := lenovo

# GMS Client ID Base
PRODUCT_GMS_CLIENTID_BASE := android-lenovo

# Build Fingerprint and Description (matching Lenovo official ROW release)
PRODUCT_BUILD_PROP_OVERRIDES += \
    PRODUCT_NAME=TB311FU \
    BUILD_FINGERPRINT="Lenovo/TB311FU_ROW/TB311FU:14/UP1A.231005.007/TB311FU_ROW_OPEN_USER_M1457.5_W_ZUI_17.5.36.508_ST_261024:user/release-keys" \
    PRIVATE_BUILD_DESC="TB311FU_ROW-user 14 UP1A.231005.007 release-keys"

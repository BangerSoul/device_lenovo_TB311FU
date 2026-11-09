#
# Copyright (C) 2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

$(call inherit-product-if-exists, $(SRC_TARGET_DIR)/product/generic_ramdisk.mk)
$(call inherit-product-if-exists, $(SRC_TARGET_DIR)/product/virtual_ab_ota.mk)

DEVICE_PATH := device/lenovo/TB311FU

# Include Vendor Tree Makefiles
$(call inherit-product-if-exists, vendor/lenovo/TB311FU/TB311FU-vendor.mk)

# Overlays (Display 90Hz, Audio Routing, Stylus)
DEVICE_PACKAGE_OVERLAYS += $(DEVICE_PATH)/overlay
PRODUCT_ENFORCE_RRO_TARGETS := *

# Rootdir & Init scripts
PRODUCT_COPY_FILES += \
    $(DEVICE_PATH)/rootdir/etc/fstab.mt6768:$(TARGET_COPY_OUT_VENDOR)/etc/fstab.mt6768 \
    $(DEVICE_PATH)/rootdir/etc/init.mt6768.rc:$(TARGET_COPY_OUT_VENDOR)/etc/init/hw/init.mt6768.rc \
    $(DEVICE_PATH)/rootdir/etc/ueventd.mt6768.rc:$(TARGET_COPY_OUT_VENDOR)/etc/ueventd.rc

# VINTF Compatibility Manifest
DEVICE_MANIFEST_FILE += $(DEVICE_PATH)/vintf/manifest.xml
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE += $(DEVICE_PATH)/vintf/device_framework_matrix.xml

# HAL Packages & Shims
PRODUCT_PACKAGES += \
    libshim_camera \
    libshim_sensors \
    libshim_composer \
    libshim_hwc \
    libshim_gralloc \
    libshim_power \
    android.hardware.sensors-service.multihal

# Stylus IDC (Lenovo Tab Pen / AP500U)
PRODUCT_COPY_FILES += \
    $(DEVICE_PATH)/configs/idc/Lenovo_Pen.idc:$(TARGET_COPY_OUT_VENDOR)/usr/idc/Lenovo_Pen.idc \
    $(DEVICE_PATH)/configs/idc/NVT-ts.idc:$(TARGET_COPY_OUT_VENDOR)/usr/idc/NVT-ts.idc

/*
 * Copyright (C) 2026 The LineageOS Project
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * MediaTek MT6769 Camera HAL Compatibility Shim for Android 15
 * Bridges GraphicBuffer constructors, buffer accessors, and vendor metadata tags.
 */

#define LOG_TAG "ShimCamera"
#define LOG_NDEBUG 0

#include <stdint.h>
#include <string>
#include <ui/GraphicBuffer.h>
#include <system/camera_metadata.h>
#include <system/graphics.h>
#include <log/log.h>

extern "C" {

/**
 * 1. Legacy GraphicBuffer Constructor (5 arguments)
 * Symbol: _ZN7android13GraphicBufferC1EjjijNSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE
 * Signature: GraphicBuffer(uint32_t inWidth, uint32_t inHeight, PixelFormat inFormat,
 *                          uint32_t inUsage, std::string requestorName)
 */
void _ZN7android13GraphicBufferC1EjjijNSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE(
        void* thisptr, uint32_t inWidth, uint32_t inHeight, int32_t inFormat,
        uint32_t inUsage, std::string requestorName) {
    if (!thisptr) {
        ALOGE("Shim: GraphicBuffer(5-arg) constructor called with null thisptr");
        return;
    }

    // Validate / sanitize pixel format (Edge Case: fallback to YV12 if invalid/unspecified)
    if (inFormat <= 0) {
        ALOGW("Shim: Unspecified pixel format %d received, falling back to HAL_PIXEL_FORMAT_YV12", inFormat);
        inFormat = HAL_PIXEL_FORMAT_YV12;
    }

    ALOGD("Shim: GraphicBuffer(5-arg) constructor: %ux%u format=%d usage=0x%x req=%s",
          inWidth, inHeight, inFormat, inUsage, requestorName.c_str());

    /*
     * RefBase Lifecycle Management:
     * Caller (camera.mt6768.so) allocates heap storage via operator new and passes thisptr.
     * Placement-new initializes android::GraphicBuffer and its RefBase subobject with
     * mStrong = INITIAL_STRONG_VALUE, ensuring safe transition when wrapped in android::sp<GraphicBuffer>.
     */
    new (thisptr) android::GraphicBuffer(
            inWidth,
            inHeight,
            inFormat,
            1, // Layer count
            static_cast<uint64_t>(inUsage),
            requestorName);
}

/**
 * 2. Legacy GraphicBuffer Constructor (6 arguments with 64-bit usage)
 * Symbol: _ZN7android13GraphicBufferC1EjjijNSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEEyj
 */
void _ZN7android13GraphicBufferC1EjjijNSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEEyj(
        void* thisptr, uint32_t inWidth, uint32_t inHeight, int32_t inFormat,
        uint32_t inUsage, std::string requestorName, uint64_t inUsage64, uint32_t inStride) {
    if (!thisptr) {
        ALOGE("Shim: GraphicBuffer(6-arg) constructor called with null thisptr");
        return;
    }

    if (inFormat <= 0) {
        inFormat = HAL_PIXEL_FORMAT_YV12;
    }

    uint64_t combinedUsage = static_cast<uint64_t>(inUsage) | inUsage64;
    ALOGD("Shim: GraphicBuffer(6-arg) constructor: %ux%u format=%d usage=0x%llx req=%s",
          inWidth, inHeight, inFormat, (unsigned long long)combinedUsage, requestorName.c_str());

    /*
     * RefBase Lifecycle Management:
     * Caller (camera.mt6768.so) allocates heap storage via operator new and passes thisptr.
     * Placement-new initializes android::GraphicBuffer and its RefBase subobject with
     * mStrong = INITIAL_STRONG_VALUE, ensuring safe transition when wrapped in android::sp<GraphicBuffer>.
     */
    new (thisptr) android::GraphicBuffer(
            inWidth,
            inHeight,
            inFormat,
            1,
            combinedUsage,
            requestorName);
}

/**
 * 3. GraphicBuffer getNativeBuffer accessor shim
 * Symbol: _ZNK7android13GraphicBuffer15getNativeBufferEv
 */
void* _ZNK7android13GraphicBuffer15getNativeBufferEv(android::GraphicBuffer* thisptr) {
    if (!thisptr) {
        ALOGE("Shim: getNativeBuffer called on null GraphicBuffer");
        return nullptr;
    }
    return const_cast<ANativeWindowBuffer*>(thisptr->toANativeWindowBuffer());
}

/**
 * 4. MediaTek Vendor Camera Metadata Tag Resolver
 * Intercepts vendor section [0x80000000, 0x8000FFFF]
 */
int get_mtk_camera_metadata_tag_name(uint32_t tag, const char** name) {
    if (!name) {
        return -1;
    }

    // MediaTek proprietary vendor tag ranges
    if (tag >= 0x80000000 && tag <= 0x8000FFFF) {
        uint32_t section_tag = tag & 0xFFFF;
        switch (section_tag) {
            case 0x0001:
                *name = "com.mediatek.control.capture.zsd";
                return 0;
            case 0x0002:
                *name = "com.mediatek.control.capture.hdr";
                return 0;
            case 0x0003:
                *name = "com.mediatek.control.capture.supernight";
                return 0;
            case 0x0004:
                *name = "com.mediatek.control.capture.eis";
                return 0;
            default:
                *name = "com.mediatek.control.capture.generic";
                return 0;
        }
    }

    // Unknown vendor tag - return NAME_NOT_FOUND (-2) cleanly
    return -2;
}

int get_mtk_camera_metadata_tag_type(uint32_t tag) {
    if (tag >= 0x80000000 && tag <= 0x8000FFFF) {
        return TYPE_BYTE;
    }
    return -1;
}

} // extern "C"

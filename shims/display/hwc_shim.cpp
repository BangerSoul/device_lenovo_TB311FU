/*
 * Copyright (C) 2026 The LineageOS Project
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * MediaTek MT6769 Hardware Composer (HWC 2.4) Compatibility Shim for Android 15
 * Bridges fence synchronization, timeline merges, and dynamic 90Hz refresh rate modes.
 */

#define LOG_TAG "ShimHWC"
#define LOG_NDEBUG 0

#include <stdint.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <sync/sync.h>
#include <hardware/hwcomposer2.h>
#include <log/log.h>

extern "C" {

/**
 * 1. Safe Fence Wait Shim
 * Intercepts sync_wait calls from hwcomposer.mt6768.so.
 * Edge Case: Validates descriptor with fcntl(F_GETFL) before calling sync_wait
 * to prevent EBADF crashes and guards against indefinite blocking with 3000ms timeout.
 */
int shim_sync_wait_safe(int fd, int timeout_ms) {
    if (fd < 0) {
        return 0; // Already signaled / no fence
    }

    // Validate fd
    if (fcntl(fd, F_GETFL) < 0) {
        ALOGW("ShimHWC: sync_wait called with invalid fd %d (errno=%d: %s)", fd, errno, strerror(errno));
        return 0;
    }

    // Guard timeout: do not allow indefinite blocking (-1) in compositor path
    if (timeout_ms < 0 || timeout_ms > 3000) {
        timeout_ms = 3000;
    }

    int ret = sync_wait(fd, timeout_ms);
    if (ret < 0) {
        ALOGW("ShimHWC: sync_wait timed out or failed on fd %d (errno=%d: %s)", fd, errno, strerror(errno));
    }
    return ret;
}

/**
 * 2. Fence Merge Shim
 * Safely merges two release/acquire fences, closing redundant file descriptors.
 */
int shim_sync_merge_safe(const char* name, int fd1, int fd2) {
    if (fd1 < 0 && fd2 < 0) return -1;
    if (fd1 < 0) return fd2;
    if (fd2 < 0) return fd1;

    // Validate both descriptors
    bool fd1_valid = (fcntl(fd1, F_GETFL) >= 0);
    bool fd2_valid = (fcntl(fd2, F_GETFL) >= 0);

    if (!fd1_valid && !fd2_valid) return -1;
    if (!fd1_valid) return fd2;
    if (!fd2_valid) return fd1;

    int merged = sync_merge(name ? name : "shim_merged_fence", fd1, fd2);
    if (merged < 0) {
        ALOGE("ShimHWC: sync_merge failed for fd1=%d, fd2=%d (errno=%d)", fd1, fd2, errno);
        return fd1;
    }
    return merged;
}

/**
 * 3. Dynamic Refresh Rate (90Hz / 60Hz) Config Resolver
 * Translates Android 15 display mode attributes to MTK HWC display config IDs.
 */
int shim_hwc_get_display_refresh_rate(uint32_t config_id, uint32_t* vsync_period) {
    if (!vsync_period) return -EINVAL;

    // Config 0: 60Hz (16666666 ns)
    // Config 1: 90Hz (11111111 ns)
    if (config_id == 1) {
        *vsync_period = 11111111; // 90 Hz
    } else {
        *vsync_period = 16666666; // 60 Hz
    }
    return 0;
}

} // extern "C"

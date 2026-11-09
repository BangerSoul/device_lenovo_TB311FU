/*
 * Copyright (C) 2026 The LineageOS Project
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * MediaTek MT6769 Power HAL & libperfservice AIDL Compatibility Shim for Android 15
 * Bridges AIDL IPower setBoost / setMode calls to MediaTek libperfservice and /proc/perfmgr.
 */

#define LOG_TAG "ShimPower"
#define LOG_NDEBUG 0

#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <dlfcn.h>
#include <errno.h>
#include <string.h>
#include <mutex>
#include <log/log.h>

// Android AIDL Power Types (compatible values)
enum class AidlBoost : int32_t {
    INTERACTION = 0,
    DISPLAY_UPDATE_IMMINENT = 1,
    ML_ACCELERATOR = 2,
    AUDIO_LAUNCH = 3,
    CAMERA_LAUNCH = 4,
    CAMERA_SHOT = 5,
};

enum class AidlMode : int32_t {
    DOUBLE_TAP_TO_WAKE = 0,
    LOW_POWER = 1,
    SUSTAINED_PERFORMANCE = 2,
    FIXED_PERFORMANCE = 3,
    VR = 4,
    DEVICE_IDLE = 5,
    INTERACTIVE = 6,
    EXPENSIVE_RENDERING = 7,
};

namespace {

// MTK Perfservice Function Pointers
typedef int (*PerfLockAcqFunc)(int handle, int duration, int list[], int size);
typedef int (*PerfLockRelFunc)(int handle);
typedef void (*PerfUserScnCheckAllFunc)(void);

static void* g_perf_lib_handle = nullptr;
static PerfLockAcqFunc g_perf_lock_acq = nullptr;
static PerfLockRelFunc g_perf_lock_rel = nullptr;
static std::mutex g_power_mutex;
static int g_interaction_handle = 0;

static void ensure_perf_service_loaded() {
    std::lock_guard<std::mutex> lock(g_power_mutex);
    if (g_perf_lib_handle != nullptr) return;

    const char* perf_libs[] = {
        "/vendor/lib64/libperfservice.so",
        "/vendor/lib64/libperfmgr.so",
        "/vendor/lib/libperfservice.so",
        "libperfservice.so",
    };

    for (const char* path : perf_libs) {
        g_perf_lib_handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        if (g_perf_lib_handle) {
            ALOGI("ShimPower: Loaded perfservice library from %s", path);
            g_perf_lock_acq = reinterpret_cast<PerfLockAcqFunc>(dlsym(g_perf_lib_handle, "perf_lock_acq"));
            g_perf_lock_rel = reinterpret_cast<PerfLockRelFunc>(dlsym(g_perf_lib_handle, "perf_lock_rel"));
            break;
        }
    }

    if (!g_perf_lib_handle) {
        ALOGW("ShimPower: libperfservice not available; using direct sysfs fallback.");
    }
}

static void sysfs_write(const char* path, const char* value) {
    int fd = open(path, O_WRONLY);
    if (fd >= 0) {
        write(fd, value, strlen(value));
        close(fd);
    } else {
        ALOGV("ShimPower: Failed to write '%s' to %s: %s", value, path, strerror(errno));
    }
}

} // namespace

extern "C" {

/**
 * AIDL Power setBoost bridge
 * Translates Android 15 boost hints to MediaTek frequency locks.
 */
int shim_power_set_boost(int32_t boost_type, int32_t duration_ms) {
    ensure_perf_service_loaded();

    // Edge Case: Framework sends duration <= 0; default to 100ms window
    if (duration_ms <= 0) {
        duration_ms = 100;
    }

    // Clamp maximum duration to 5000ms
    if (duration_ms > 5000) {
        duration_ms = 5000;
    }

    ALOGD("ShimPower: setBoost type=%d, duration=%dms", boost_type, duration_ms);

    if (g_perf_lock_acq) {
        // MT6769 CPU Boost parameters: CMD_SET_CPU_FREQ, max freq 2.0GHz
        int boost_params[] = { 0x00400000, 2000000, 0x00404000, 1800000 };
        g_interaction_handle = g_perf_lock_acq(g_interaction_handle, duration_ms, boost_params, 4);
        return 0;
    }

    // Direct sysfs boost fallback
    sysfs_write("/proc/perfmgr/boost_ctrl/eas_ctrl/perfserv_ta_boost", "1");
    sysfs_write("/sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq", "1500000");
    return 0;
}

/**
 * AIDL Power setMode bridge
 * Translates Android 15 modes: LOW_POWER, DOUBLE_TAP_TO_WAKE, SUSTAINED_PERFORMANCE.
 */
int shim_power_set_mode(int32_t mode_type, int enabled) {
    ALOGD("ShimPower: setMode type=%d, enabled=%d", mode_type, enabled);

    auto mode = static_cast<AidlMode>(mode_type);
    switch (mode) {
        case AidlMode::DOUBLE_TAP_TO_WAKE: {
            const char* val = enabled ? "1" : "0";
            sysfs_write("/sys/touchpanel/double_tap_enable", val);
            sysfs_write("/proc/driver/touchpanel/double_tap", val);
            sysfs_write("/sys/devices/platform/goodix_ts.0/gesture/enable", val);
            return 0;
        }

        case AidlMode::LOW_POWER: {
            if (enabled) {
                sysfs_write("/proc/perfmgr/boost_ctrl/eas_ctrl/perfserv_ta_boost", "0");
                sysfs_write("/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq", "1200000");
            } else {
                sysfs_write("/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq", "2000000");
            }
            return 0;
        }

        case AidlMode::SUSTAINED_PERFORMANCE: {
            // Sustained performance mode: limit peak thermal throttle oscillation
            sysfs_write("/proc/perfmgr/boost_ctrl/cpu_ctrl/perfserv_freq", enabled ? "1800000" : "0");
            return 0;
        }

        default:
            return 0;
    }
}

/**
 * Check if mode is supported
 */
int shim_power_is_mode_supported(int32_t mode_type) {
    auto mode = static_cast<AidlMode>(mode_type);
    switch (mode) {
        case AidlMode::DOUBLE_TAP_TO_WAKE:
        case AidlMode::LOW_POWER:
        case AidlMode::SUSTAINED_PERFORMANCE:
        case AidlMode::INTERACTIVE:
            return 1;
        default:
            return 0;
    }
}

/**
 * Check if boost is supported
 */
int shim_power_is_boost_supported(int32_t boost_type) {
    auto boost = static_cast<AidlBoost>(boost_type);
    switch (boost) {
        case AidlBoost::INTERACTION:
        case AidlBoost::DISPLAY_UPDATE_IMMINENT:
        case AidlBoost::CAMERA_LAUNCH:
        case AidlBoost::AUDIO_LAUNCH:
            return 1;
        default:
            return 0;
    }
}

} // extern "C"

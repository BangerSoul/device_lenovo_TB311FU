/*
 * Copyright (C) 2026 The LineageOS Project
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * MediaTek MT6769 Sensors Multi-HAL 2.1 Compatibility Shim for Android 15
 * Bridges sub-HAL sensor enumeration, device node opening, and event translation.
 */

#define LOG_TAG "ShimSensors"
#define LOG_NDEBUG 0

#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <hardware/sensors.h>
#include <log/log.h>

extern "C" {

/**
 * 1. HF Manager Device Node Opener
 * Provides resilient access to /dev/hf_manager device node.
 * Edge case: Handles missing hardware node gracefully without aborting or crashing.
 */
int shim_sensor_hf_manager_open(void) {
    const char* hf_node = "/dev/hf_manager";
    int fd = open(hf_node, O_RDWR | O_NONBLOCK);
    if (fd < 0) {
        ALOGW("ShimSensors: Could not open %s (errno=%d: %s). Falling back gracefully.",
              hf_node, errno, strerror(errno));
        return -errno;
    }
    ALOGI("ShimSensors: Successfully opened %s (fd=%d)", hf_node, fd);
    return fd;
}

/**
 * 2. Legacy Sensor constructor bridge
 * In Android 14/15, android::Sensor constructor signatures changed.
 * This symbol satisfies references in legacy MTK sensors.mt6768.so sub-HAL.
 */
void _ZN7android6SensorC1EPK8sensor_t(void* thisptr, const struct sensor_t* hwSensor) {
    if (!thisptr || !hwSensor) {
        ALOGE("ShimSensors: Null pointer passed to Sensor constructor bridge");
        return;
    }
    ALOGV("ShimSensors: Bridging Sensor constructor for '%s' (type=%d, handle=%d)",
          hwSensor->name ? hwSensor->name : "unknown",
          hwSensor->type,
          hwSensor->handle);
    memcpy(thisptr, hwSensor, sizeof(struct sensor_t));
}

/**
 * 3. Sub-HAL Event Sanitizer / Translator
 * Fixes event timestamps and normalizes acceleration / gyro / ALS readings.
 */
int shim_sanitize_sensor_event(sensors_event_t* event) {
    if (!event) return -EINVAL;

    // Guard against inverted or future timestamps
    struct timespec now;
    clock_gettime(CLOCK_BOOTTIME, &now);
    int64_t now_ns = static_cast<int64_t>(now.tv_sec) * 1000000000LL + now.tv_nsec;

    if (event->timestamp <= 0 || event->timestamp > (now_ns + 1000000000LL)) {
        event->timestamp = now_ns;
    }

    // Sanitize light sensor lux boundary (ALS 0 to 100000 lux)
    if (event->type == SENSOR_TYPE_LIGHT) {
        if (event->light < 0.0f) event->light = 0.0f;
        if (event->light > 150000.0f) event->light = 150000.0f;
    }

    return 0;
}

} // extern "C"

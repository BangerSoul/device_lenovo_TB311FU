#!/usr/bin/env python3
"""
Build Magisk / KernelSU / APatch Flashable Module for Lenovo Tab with Clear Case (TB311FU)
Packages Track A GSI stabilization fixes:
  - 90Hz Display Refresh Rate & Display Color Profiles (sRGB/DCI-P3/Natural/Boosted/Saturated) via FrameworkResOverlay
  - Quad-Speaker Discrete Audio Policy & Lenovo OEM Dolby Atmos DAP (AIDL DAX3)
  - Bluetooth A2DP audio routing
  - Dual Stylus Calibration (Himax HX83102E & Novatek NVT-ts, 4096 Pressure Levels & Palm Rejection)
  - Post-Boot Daemon (Cellular/RIL Termination, AudioFX disablement, & SELinux Optimization)
"""

import os
import shutil
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODULE_DIR = BASE_DIR / "magisk_module"
OUTPUT_ZIP = BASE_DIR / "tb311fu-gsi-stabilizer.zip"

MODULE_PROP = """id=tb311fu-gsi-stabilization
name=Lenovo Tab with Clear Case (TB311FU) GSI Hardware Stabilization Suite
version=v2.7.0
versionCode=270
author=Antigravity Creative Suite & Custom ROM Team
description=Hardware stabilization suite for Lenovo Tab with Clear Case (TB311FU / MT6769) on GSIs. v2.7.0: Fixes speaker volume - eliminates -12dB gain_speaker offset, deploys full-range quad-speaker volume curves (0dB at 100%), tunes Dolby DAP volume leveler (-256 to -144) and disables redundant AW883xx distortion regulator. Features Lenovo OEM Dolby Atmos DAP (AIDL DAX3), Display Color Profiles via FrameworkResOverlay, AP500U active stylus (4096 pressure), Wi-Fi tablet conversion, SELinux, AudioFX elimination.
"""

CUSTOMIZE_SH = """SKIPUNZIP=0

ui_print "*************************************************"
ui_print "   Lenovo Tab with Clear Case (TB311FU) GSI Stabilizer     "
ui_print "   SoC: MediaTek Helio G88 / MT6769             "
ui_print "   Suite Version: v2.7.0 (Speaker Volume Fix)   "
ui_print "*************************************************"

ui_print "- Installing Display Color Profiles & 90Hz Framework Overlay..."
ui_print "- Calibrating Lenovo Tab Pen (AP500U) Active Stylus..."
ui_print "- Configuring Quad-Speaker Spatial Audio Policy (0dB Max)..."
ui_print "- Calibrating Full-Scale Speaker Volume Tables..."
ui_print "- Tuning Lenovo OEM Dolby Atmos DAP (-144 Target & Headroom)..."
ui_print "- Installing Post-Boot Cellular & SELinux Daemon..."
ui_print "- Fabricated overlays will blank No Service text at boot..."

# Ensure proper permissions
set_perm $MODPATH/post-fs-data.sh 0 0 0755
set_perm $MODPATH/service.sh 0 0 0755
set_perm_recursive $MODPATH/system/bin 0 0 0755 0755
set_perm $MODPATH/system/bin/gsi-post-boot.sh 0 0 0755
set_perm_recursive $MODPATH/system/product/overlay 0 0 0755 0644
set_perm_recursive $MODPATH/system/vendor/overlay 0 0 0755 0644
set_perm_recursive $MODPATH/system/usr/idc 0 0 0755 0644
set_perm_recursive $MODPATH/system/etc 0 0 0755 0644
set_perm_recursive $MODPATH/system/etc/permissions 0 0 0755 0644
set_perm_recursive $MODPATH/system/vendor/etc 0 0 0755 0644

ui_print " "
ui_print "✓ All v2.6.0 hardware stabilization features successfully deployed!"
ui_print "✓ Reboot to activate 90Hz, Dolby Atmos DAP, and color profiles."
"""

SERVICE_SH = """#!/system/bin/sh
# Late-start service for Lenovo TB311FU GSI stabilization
MODDIR=${0%/*}
[ -z "$MODPATH" ] && MODPATH="$MODDIR"
PATH=$PATH:/data/adb/ksu/bin:/data/adb/ap/bin:/data/adb/magisk

mount_global() {
    nsenter -t 1 -m -- mount "$@" 2>/dev/null || mount "$@" 2>/dev/null || true
}

# Refresh audio policy and effect bind-mounts into global namespace
if [ -f "$MODPATH/system/etc/audio_policy_configuration.xml" ] && [ -f "/vendor/etc/audio_policy_configuration.xml" ]; then
    mount -o bind "$MODPATH/system/etc/audio_policy_configuration.xml" /vendor/etc/audio_policy_configuration.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/etc/audio_policy_configuration.xml" /vendor/etc/audio_policy_configuration.xml
fi

if [ -f "$MODPATH/system/vendor/etc/audio_effects_config.xml" ] && [ -f "/vendor/etc/audio_effects_config.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/audio_effects_config.xml" /vendor/etc/audio_effects_config.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/audio_effects_config.xml" /vendor/etc/audio_effects_config.xml
fi

if [ -f "$MODPATH/system/vendor/etc/audio_effects.xml" ] && [ -f "/vendor/etc/audio_effects.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/audio_effects.xml" /vendor/etc/audio_effects.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/audio_effects.xml" /vendor/etc/audio_effects.xml
fi

if [ -f "$MODPATH/system/vendor/etc/audio_policy_volumes.xml" ] && [ -f "/vendor/etc/audio_policy_volumes.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/audio_policy_volumes.xml" /vendor/etc/audio_policy_volumes.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/audio_policy_volumes.xml" /vendor/etc/audio_policy_volumes.xml
fi

if [ -f "$MODPATH/system/vendor/etc/default_volume_tables.xml" ] && [ -f "/vendor/etc/default_volume_tables.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/default_volume_tables.xml" /vendor/etc/default_volume_tables.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/default_volume_tables.xml" /vendor/etc/default_volume_tables.xml
fi

if [ -f "$MODPATH/system/vendor/etc/dolby/dax-default.xml" ] && [ -f "/vendor/etc/dolby/dax-default.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/dolby/dax-default.xml" /vendor/etc/dolby/dax-default.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/dolby/dax-default.xml" /vendor/etc/dolby/dax-default.xml
fi

# Refresh FrameworkResOverlay bind-mount
OVERLAY_SRC="$MODPATH/system/vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk"
if [ -f "$OVERLAY_SRC" ] && [ -f "/vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk" ]; then
    mount -o bind "$OVERLAY_SRC" /vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk 2>/dev/null || true
    mount_global -o bind "$OVERLAY_SRC" /vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk
fi

# Refresh IDC bind-mount if not currently mounted
mkdir -p /data/system/devices/idc 2>/dev/null || true
if [ -d "$MODPATH/system/usr/idc" ]; then
    cp -f "$MODPATH/system/usr/idc/"* /data/system/devices/idc/ 2>/dev/null || true
    chmod 644 /data/system/devices/idc/* 2>/dev/null || true
    mount -o bind "$MODPATH/system/usr/idc" /system/usr/idc 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/usr/idc" /system/usr/idc
fi

# Dual-Layer Backlight Floor Guard: Prevent screen blackout if slider is set to 0% while awake
(
    while true; do
        b=$(cat /sys/class/leds/lcd-backlight/brightness 2>/dev/null || echo 0)
        if [ "$b" -gt 0 ] && [ "$b" -lt 48 ]; then
            echo 48 > /sys/class/leds/lcd-backlight/brightness 2>/dev/null || true
        fi
        sleep 1
    done
) &

# Wait for boot completion before firing optimization sequence
while [ "$(getprop sys.boot_completed)" != "1" ]; do
    sleep 2
done

# Disable HW overlays immediately on SurfaceFlinger to eliminate MediaTek HWC flicker
service call SurfaceFlinger 1008 i32 1 2>/dev/null || true
settings put system peak_refresh_rate 90.0 2>/dev/null || true
settings put system min_refresh_rate 60.0 2>/dev/null || true
cmd display clear-user-preferred-display-mode 2>/dev/null || true
setprop persist.vendor.sys.pq.disp.aal.bypass 1
setprop persist.vendor.sys.pq.debug.adaptive.en 0
settings put secure icon_blacklist mobile,cell,phone 2>/dev/null || true
settings put system carrier_label 0 2>/dev/null || true
settings put secure lock_screen_show_carrier_text 0 2>/dev/null || true
settings put system show_carrier_text 0 2>/dev/null || true
settings put system status_bar_show_carrier 0 2>/dev/null || true
settings put secure status_bar_show_carrier 0 2>/dev/null || true
settings put system carrier_text_mode 0 2>/dev/null || true
settings put system lockscreen_show_carrier 0 2>/dev/null || true
settings put secure lockscreen_show_carrier 0 2>/dev/null || true
settings put global lockscreen_show_carrier 0 2>/dev/null || true

# ── Fabricated overlay: blank all "No service" / carrier strings ──────────────
OVERLAY_WAIT=0
until cmd overlay list android >/dev/null 2>&1 || [ "$OVERLAY_WAIT" -ge 30 ]; do
    sleep 2
    OVERLAY_WAIT=$((OVERLAY_WAIT + 2))
done

# Fabricate overlays targeting android framework-res (blank carrier & emergency strings)
cmd overlay fabricate --target android --name NoServiceHide android:string/lockscreen_carrier_default string '' 2>/dev/null || true
cmd overlay fabricate --target android --name NoServiceHide2 android:string/emergency_calls_only string '' 2>/dev/null || true
cmd overlay fabricate --target android --name NoServiceHide3 android:string/lockscreen_missing_sim_message string '' 2>/dev/null || true
cmd overlay fabricate --target android --name NoServiceHide5 android:string/lockscreen_network_locked_message string '' 2>/dev/null || true
cmd overlay fabricate --target android --name NoServiceHide6 android:string/lockscreen_missing_sim_instructions string '' 2>/dev/null || true
cmd overlay fabricate --target android --name NoServiceHide7 android:string/lockscreen_missing_sim_instructions_long string '' 2>/dev/null || true

# Fabricate overlays targeting com.android.systemui (blank missing SIM text and zero shade carrier width)
cmd overlay fabricate --target com.android.systemui --name HideSysUiCarrier com.android.systemui:string/keyguard_missing_sim_message_short string '' 2>/dev/null || true
cmd overlay fabricate --target com.android.systemui --name HideSysUiCarrier2 com.android.systemui:string/keyguard_missing_sim_message string '' 2>/dev/null || true
cmd overlay fabricate --target com.android.systemui --name HideSysUiCarrier3 com.android.systemui:integer/shade_carrier_max_em 0x10 0 2>/dev/null || true

# Enable all fabricated overlays for user 0
cmd overlay enable --user 0 'com.android.shell:NoServiceHide' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:NoServiceHide2' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:NoServiceHide3' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:NoServiceHide5' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:NoServiceHide6' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:NoServiceHide7' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:HideSysUiCarrier' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:HideSysUiCarrier2' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:HideSysUiCarrier3' 2>/dev/null || true

# Fabricate overlays to disable voice and SMS telephony capability on Wi-Fi-only tablet
cmd overlay fabricate --target android --name TabletVoiceConfig android:bool/config_voice_capable 0x12 0x0 2>/dev/null || true
cmd overlay fabricate --target android --name TabletSmsConfig android:bool/config_sms_capable 0x12 0x0 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:TabletVoiceConfig' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:TabletSmsConfig' 2>/dev/null || true

# Fabricate display features and color profiles
cmd overlay fabricate --target android --name NightDisplay android:bool/config_nightDisplayAvailable 0x12 0x1 2>/dev/null || true
cmd overlay fabricate --target android --name ColorTransformAccelerated android:bool/config_setColorTransformAccelerated 0x12 0x1 2>/dev/null || true
cmd overlay fabricate --target android --name ExtraDim android:bool/config_reduceBrightColorsAvailable 0x12 0x1 2>/dev/null || true
cmd overlay fabricate --target android --name LidControlsSleep android:bool/config_lidControlsSleep 0x12 0x1 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:NightDisplay' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:ColorTransformAccelerated' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:ExtraDim' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:LidControlsSleep' 2>/dev/null || true

# Disable conflicting AOSP AudioFX to prevent DSP collisions with Dolby DAP
pm disable-user org.lineageos.audiofx 2>/dev/null || pm disable org.lineageos.audiofx 2>/dev/null || true
am force-stop org.lineageos.audiofx 2>/dev/null || true
pkill -9 -f org.lineageos.audiofx 2>/dev/null || true

# Ensure Lenovo OEM Dolby Atmos DAP service (dms-hal-2-0) is active
setprop ro.vendor.dolby.dax.version "DAX3_3.13.0.9_r1"
setprop vendor.audio.dolby.ds2.enabled true
setprop vendor.audio.dolby.ds2.hardbypass false
setprop dax.support.offload true
start dms-hal-2-0 2>/dev/null || true

# Execute post-boot stabilization daemon
if [ -f "$MODDIR/system/bin/gsi-post-boot.sh" ]; then
    sh "$MODDIR/system/bin/gsi-post-boot.sh" > /dev/null 2>&1
elif [ -f "/system/bin/gsi-post-boot.sh" ]; then
    sh "/system/bin/gsi-post-boot.sh" > /dev/null 2>&1
fi
"""

POST_FS_DATA_SH = """#!/system/bin/sh
# Early boot initialization for Lenovo TB311FU GSI
MODDIR=${0%/*}
[ -z "$MODPATH" ] && MODPATH="$MODDIR"
PATH=$PATH:/data/adb/ksu/bin:/data/adb/ap/bin:/data/adb/magisk

mount_global() {
    nsenter -t 1 -m -- mount "$@" 2>/dev/null || mount "$@" 2>/dev/null || true
}

# Signal Wi-Fi only tablet early to prevent cellular framework deadlocks
set_early_prop() {
    resetprop -n "$1" "$2" 2>/dev/null || setprop "$1" "$2" 2>/dev/null || true
}

set_early_prop ro.radio.noril yes
set_early_prop ro.carrier "wifi-only"
set_early_prop ro.telephony.default_network 0
# Allocate single logical slot to prevent SystemUI CarrierTextManager ArrayIndexOutOfBoundsException crash loop
set_early_prop telephony.active_modems.max_count 1
set_early_prop ro.telephony.sim.count 1
set_early_prop ro.vendor.mtk_telephony_add_on_0 0
set_early_prop persist.radio.multisim.config "ss"
set_early_prop persist.radio.noril 1
set_early_prop persist.sys.phh.no_telephony true
set_early_prop config.disable_telephony true
set_early_prop ro.com.android.dataroaming false
set_early_prop ro.com.android.mobiledata false

# Anti-flicker display properties (disable unaligned latching & HW overlays & AAL pulsing)
set_early_prop debug.sf.disable_hwc_overlays 1
set_early_prop persist.sys.phh.disable_hwc 1
set_early_prop persist.vendor.sys.pq.disp.aal.bypass 1
set_early_prop persist.vendor.sys.pq.debug.adaptive.en 0
set_early_prop persist.vendor.dfps.force_fps 90
set_early_prop debug.sf.latch_unsignaled 1

# Bluetooth Audio fallback properties: Keep HAL active to avoid MTK AIDL crash loop
set_early_prop persist.bluetooth.bluetooth_audio_hal.disabled false
set_early_prop persist.bluetooth.system_audio_hal.enabled true
set_early_prop persist.bluetooth.a2dp_offload.disabled true
set_early_prop ro.bluetooth.a2dp_offload.supported false

# Sensor Framework: Virtual Gyroscope & Sensor Fusion
set_early_prop ro.vendor.sensors.v_gyro true
set_early_prop persist.vendor.sensors.virtual_gyro 1
set_early_prop debug.sensor.fusion 1

# Mask telephony feature XMLs on Wi-Fi-only tablet via bind-mounting empty XML
touch /data/local/tmp/empty_perm.xml
chmod 644 /data/local/tmp/empty_perm.xml
for perm in /system/etc/permissions/android.hardware.telephony*.xml /vendor/etc/permissions/android.hardware.telephony*.xml; do
    if [ -f "$perm" ]; then
        mount -o bind /data/local/tmp/empty_perm.xml "$perm" 2>/dev/null || true
        mount_global -o bind /data/local/tmp/empty_perm.xml "$perm"
    fi
done

# Bind-mount tablet core hardware over handheld core hardware
TAB_PERM="$MODPATH/system/etc/permissions/tablet_core_hardware.xml"
if [ -f "$TAB_PERM" ]; then
    for handheld in /vendor/etc/permissions/handheld_core_hardware*.xml /system/etc/permissions/handheld_core_hardware*.xml; do
        if [ -f "$handheld" ]; then
            mount -o bind "$TAB_PERM" "$handheld" 2>/dev/null || true
            mount_global -o bind "$TAB_PERM" "$handheld"
        fi
    done
fi

# Bind-mount quad-speaker audio policy over vendor audio policy
AUDIO_POLICY_SRC="$MODPATH/system/etc/audio_policy_configuration.xml"
if [ ! -f "$AUDIO_POLICY_SRC" ] && [ -f "$MODPATH/system/vendor/etc/audio_policy_configuration.xml" ]; then
    AUDIO_POLICY_SRC="$MODPATH/system/vendor/etc/audio_policy_configuration.xml"
fi

if [ -f "$AUDIO_POLICY_SRC" ] && [ -f "/vendor/etc/audio_policy_configuration.xml" ]; then
    mount -o bind "$AUDIO_POLICY_SRC" /vendor/etc/audio_policy_configuration.xml 2>/dev/null || true
    mount_global -o bind "$AUDIO_POLICY_SRC" /vendor/etc/audio_policy_configuration.xml
fi

# Clamp hardware backlight floor at 48 PWM to eliminate 0-nit blackout
if [ -f /sys/class/leds/lcd-backlight/min_brightness ]; then
    echo 48 > /data/local/tmp/min_brightness
    chmod 644 /data/local/tmp/min_brightness
    mount -o bind /data/local/tmp/min_brightness /sys/class/leds/lcd-backlight/min_brightness 2>/dev/null || true
    mount_global -o bind /data/local/tmp/min_brightness /sys/class/leds/lcd-backlight/min_brightness
fi

# Ensure IDC files are permanently present in both /system/usr/idc and /data/system/devices/idc
mkdir -p /data/system/devices/idc 2>/dev/null || true
if [ -d "$MODPATH/system/usr/idc" ]; then
    cp -f "$MODPATH/system/usr/idc/"* /data/system/devices/idc/ 2>/dev/null || true
    chmod 644 /data/system/devices/idc/* 2>/dev/null || true
    mount -o bind "$MODPATH/system/usr/idc" /system/usr/idc 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/usr/idc" /system/usr/idc
fi

# Mask non-functional cellular APK on Wi-Fi tablet
if [ -d "/system/app/QcRilAm" ]; then
    mount_global -t tmpfs tmpfs /system/app/QcRilAm
fi

# Mask conflicting persistent AudioFX to prevent DSP collisions with Dolby DAP
if [ -d "/system/system_ext/priv-app/AudioFX" ]; then
    mount_global -t tmpfs tmpfs /system/system_ext/priv-app/AudioFX
fi

# Unmask vendor audio directory if PHH mounted empty tmpfs over it
while umount -l /vendor/etc/audio 2>/dev/null; do true; done

# Bind-mount FrameworkResOverlay.apk (color profiles, 90Hz, 12-bit brightness, tablet mode)
OVERLAY_SRC="$MODPATH/system/vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk"
if [ -f "$OVERLAY_SRC" ] && [ -f "/vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk" ]; then
    mount -o bind "$OVERLAY_SRC" /vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk 2>/dev/null || true
    mount_global -o bind "$OVERLAY_SRC" /vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk
fi

# Bind-mount audio effects configuration with Dolby DAP
EFFECTS_SRC="$MODPATH/system/vendor/etc/audio_effects_config.xml"
if [ -f "$EFFECTS_SRC" ] && [ -f "/vendor/etc/audio_effects_config.xml" ]; then
    mount -o bind "$EFFECTS_SRC" /vendor/etc/audio_effects_config.xml 2>/dev/null || true
    mount_global -o bind "$EFFECTS_SRC" /vendor/etc/audio_effects_config.xml
fi

AUDIO_EFFECTS_XML="$MODPATH/system/vendor/etc/audio_effects.xml"
if [ -f "$AUDIO_EFFECTS_XML" ] && [ -f "/vendor/etc/audio_effects.xml" ]; then
    mount -o bind "$AUDIO_EFFECTS_XML" /vendor/etc/audio_effects.xml 2>/dev/null || true
    mount_global -o bind "$AUDIO_EFFECTS_XML" /vendor/etc/audio_effects.xml
fi

# Bind-mount volume tables (0dB max speaker curve)
if [ -f "$MODPATH/system/vendor/etc/audio_policy_volumes.xml" ] && [ -f "/vendor/etc/audio_policy_volumes.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/audio_policy_volumes.xml" /vendor/etc/audio_policy_volumes.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/audio_policy_volumes.xml" /vendor/etc/audio_policy_volumes.xml
fi

if [ -f "$MODPATH/system/vendor/etc/default_volume_tables.xml" ] && [ -f "/vendor/etc/default_volume_tables.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/default_volume_tables.xml" /vendor/etc/default_volume_tables.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/default_volume_tables.xml" /vendor/etc/default_volume_tables.xml
fi

# Bind-mount Dolby DAX configuration (tuned leveler targets & headroom)
if [ -f "$MODPATH/system/vendor/etc/dolby/dax-default.xml" ] && [ -f "/vendor/etc/dolby/dax-default.xml" ]; then
    mount -o bind "$MODPATH/system/vendor/etc/dolby/dax-default.xml" /vendor/etc/dolby/dax-default.xml 2>/dev/null || true
    mount_global -o bind "$MODPATH/system/vendor/etc/dolby/dax-default.xml" /vendor/etc/dolby/dax-default.xml
fi
"""

SEPOLICY_RULE = """allow surfaceflinger ged_device chr_file { ioctl read write open getattr map }
allow untrusted_app ged_device chr_file { ioctl read write open getattr }
allow platform_app ged_device chr_file { ioctl read write open getattr }
allow system_server ged_device chr_file { ioctl read write open getattr }
allow mtk_hal_sensors hf_manager_device chr_file { ioctl read write open getattr }
allow mtk_hal_sensors nvdata_file dir { search read open write add_name getattr }
allow mtk_hal_sensors nvdata_file file { read write open create getattr }
allow system_server mtk_hal_sensors { binder call transfer }
allow system_server sysfs_leds file { read write open getattr }
allow system_server sysfs_boot_mode file { read open getattr }
allow mtk_hal_audio sysfs_batteryinfo dir { search }
allow mtk_hal_audio sysfs_batteryinfo file { open read getattr }
allow mtk_hal_audio default_prop file { open read getattr map }
allow system_server audioserver_tmpfs file { read write }
allow system_server proc_mtk_batoc_throttling dir { search }
allow system_server vcu_device chr_file { read write open ioctl }
allow system_server vndbinder_device chr_file { read write open ioctl }
permissive mtk_hal_sensors
permissive mtk_hal_audio
permissive mtk_hal_gnss
permissive mtk_hal_power
"""

def main():
    print(f"[*] Preparing Magisk module directory structure at: {MODULE_DIR}")
    if MODULE_DIR.exists():
        shutil.rmtree(MODULE_DIR)

    # Create target directories
    (MODULE_DIR / "system" / "product" / "overlay").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "vendor" / "overlay" / "FrameworkResOverlay").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "usr" / "idc").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "etc").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "etc" / "permissions").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "vendor" / "etc").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "vendor" / "etc" / "dolby").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "bin").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "app" / "QcRilAm").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "app" / "QcRilAm" / ".replace").touch()
    (MODULE_DIR / "system" / "system_ext" / "priv-app" / "AudioFX").mkdir(parents=True, exist_ok=True)
    (MODULE_DIR / "system" / "system_ext" / "priv-app" / "AudioFX" / ".replace").touch()

    # 1. Write control files with strict UNIX LF line endings
    print("[*] Writing module metadata and scripts...")
    with open(MODULE_DIR / "module.prop", "w", encoding="utf-8", newline="\n") as f:
        f.write(MODULE_PROP)

    with open(MODULE_DIR / "customize.sh", "w", encoding="utf-8", newline="\n") as f:
        f.write(CUSTOMIZE_SH)

    with open(MODULE_DIR / "service.sh", "w", encoding="utf-8", newline="\n") as f:
        f.write(SERVICE_SH)

    with open(MODULE_DIR / "post-fs-data.sh", "w", encoding="utf-8", newline="\n") as f:
        f.write(POST_FS_DATA_SH)

    with open(MODULE_DIR / "sepolicy.rule", "w", encoding="utf-8", newline="\n") as f:
        f.write(SEPOLICY_RULE)

    # 2. Copy payload files from gsi_suite
    print("[*] Copying payload assets...")
    
    # Overlay APKs
    src_apk = BASE_DIR / "overlay" / "treble-overlay-lenovo-tb311fu.apk"
    dst_apk = MODULE_DIR / "system" / "product" / "overlay" / "treble-overlay-lenovo-tb311fu.apk"
    shutil.copy2(src_apk, dst_apk)
    print(f"  -> Added Treble Overlay: {dst_apk.name} ({dst_apk.stat().st_size} bytes)")

    src_fw_overlay = BASE_DIR / "overlay" / "FrameworkResOverlay.apk"
    dst_fw_overlay = MODULE_DIR / "system" / "vendor" / "overlay" / "FrameworkResOverlay" / "FrameworkResOverlay.apk"
    shutil.copy2(src_fw_overlay, dst_fw_overlay)
    print(f"  -> Added FrameworkResOverlay (Color Modes + Display): {dst_fw_overlay.name} ({dst_fw_overlay.stat().st_size} bytes)")

    # Stylus IDCs (Himax HX83102E and Novatek NVT-ts) and tuning
    src_idc = BASE_DIR / "stylus" / "NVT-ts.idc"
    dst_idc = MODULE_DIR / "system" / "usr" / "idc" / "NVT-ts.idc"
    shutil.copy2(src_idc, dst_idc)
    print(f"  -> Added Stylus IDC: {dst_idc.name}")

    src_himax = BASE_DIR / "stylus" / "himax-touchscreen.idc"
    dst_himax = MODULE_DIR / "system" / "usr" / "idc" / "himax-touchscreen.idc"
    shutil.copy2(src_himax, dst_himax)
    print(f"  -> Added Stylus IDC: {dst_himax.name}")

    src_tune = BASE_DIR / "stylus" / "touch_tuning.conf"
    dst_tune = MODULE_DIR / "system" / "usr" / "idc" / "touch_tuning.conf"
    shutil.copy2(src_tune, dst_tune)
    print(f"  -> Added Touch Tuning: {dst_tune.name}")

    # Audio policy (system/etc and system/vendor/etc)
    src_audio = BASE_DIR / "audio" / "audio_policy_configuration.xml"
    dst_audio = MODULE_DIR / "system" / "etc" / "audio_policy_configuration.xml"
    shutil.copy2(src_audio, dst_audio)
    print(f"  -> Added Audio Policy (system): {dst_audio.name}")

    dst_vendor_audio = MODULE_DIR / "system" / "vendor" / "etc" / "audio_policy_configuration.xml"
    shutil.copy2(src_audio, dst_vendor_audio)
    print(f"  -> Added Audio Policy (vendor): {dst_vendor_audio.name}")

    # Tablet Core Hardware permission XML
    src_tablet_perm = BASE_DIR / "permissions" / "tablet_core_hardware.xml"
    dst_tablet_perm = MODULE_DIR / "system" / "etc" / "permissions" / "tablet_core_hardware.xml"
    shutil.copy2(src_tablet_perm, dst_tablet_perm)
    print(f"  -> Added Tablet Permissions: {dst_tablet_perm.name}")

    # Audio effects configuration (audio_effects_config.xml for AIDL HAL)
    src_effects_cfg = BASE_DIR / "audio" / "audio_effects_config.xml"
    dst_effects_cfg = MODULE_DIR / "system" / "vendor" / "etc" / "audio_effects_config.xml"
    shutil.copy2(src_effects_cfg, dst_effects_cfg)
    print(f"  -> Added Audio Effects Config (AIDL DAP): {dst_effects_cfg.name}")

    dst_effects_cfg_sys = MODULE_DIR / "system" / "etc" / "audio_effects_config.xml"
    shutil.copy2(src_effects_cfg, dst_effects_cfg_sys)
    print(f"  -> Added Audio Effects Config (system): {dst_effects_cfg_sys.name}")

    # Audio effects XML (audio_effects.xml for AudioFlinger legacy fallback)
    src_effects = BASE_DIR / "audio" / "audio_effects.xml"
    dst_effects = MODULE_DIR / "system" / "etc" / "audio_effects.xml"
    shutil.copy2(src_effects, dst_effects)
    print(f"  -> Added Audio Effects (system): {dst_effects.name}")

    dst_vendor_effects = MODULE_DIR / "system" / "vendor" / "etc" / "audio_effects.xml"
    shutil.copy2(src_effects, dst_vendor_effects)
    print(f"  -> Added Audio Effects (vendor): {dst_vendor_effects.name}")

    # Audio Policy Volumes
    src_volumes = BASE_DIR / "audio" / "audio_policy_volumes.xml"
    if src_volumes.exists():
        dst_volumes_sys = MODULE_DIR / "system" / "etc" / "audio_policy_volumes.xml"
        shutil.copy2(src_volumes, dst_volumes_sys)
        dst_volumes_ven = MODULE_DIR / "system" / "vendor" / "etc" / "audio_policy_volumes.xml"
        shutil.copy2(src_volumes, dst_volumes_ven)
        print(f"  -> Added Audio Policy Volumes: {dst_volumes_ven.name}")

    # Default Volume Tables
    src_tables = BASE_DIR / "audio" / "default_volume_tables.xml"
    if src_tables.exists():
        dst_tables_sys = MODULE_DIR / "system" / "etc" / "default_volume_tables.xml"
        shutil.copy2(src_tables, dst_tables_sys)
        dst_tables_ven = MODULE_DIR / "system" / "vendor" / "etc" / "default_volume_tables.xml"
        shutil.copy2(src_tables, dst_tables_ven)
        print(f"  -> Added Default Volume Tables: {dst_tables_ven.name}")

    # Dolby DAX Configuration (Tuned Volume Leveler & Headroom)
    src_dax = BASE_DIR / "audio" / "dax-default.xml"
    if src_dax.exists():
        dst_dax = MODULE_DIR / "system" / "vendor" / "etc" / "dolby" / "dax-default.xml"
        shutil.copy2(src_dax, dst_dax)
        print(f"  -> Added Tuned Dolby DAX Config: {dst_dax.name} ({dst_dax.stat().st_size} bytes)")

    # Post-boot daemon
    src_daemon = BASE_DIR / "selinux" / "gsi-post-boot.sh"
    dst_daemon = MODULE_DIR / "system" / "bin" / "gsi-post-boot.sh"
    shutil.copy2(src_daemon, dst_daemon)
    print(f"  -> Added Post-Boot Daemon: {dst_daemon.name}")

    # 3. Create zip archive
    print(f"[*] Packaging flashable archive to: {OUTPUT_ZIP}")
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(MODULE_DIR):
            for file in files:
                abs_file = Path(root) / file
                rel_path = abs_file.relative_to(MODULE_DIR)
                zinfo = zipfile.ZipInfo(rel_path.as_posix())
                if file.endswith(".sh") or "bin" in abs_file.parts:
                    zinfo.external_attr = 0o100755 << 16
                else:
                    zinfo.external_attr = 0o100644 << 16
                zipf.writestr(zinfo, abs_file.read_bytes())

    zip_size = OUTPUT_ZIP.stat().st_size
    print(f"[✓] Flashable module successfully built!")
    print(f"    File: {OUTPUT_ZIP.name}")
    print(f"    Size: {zip_size:,} bytes")
    print(f"    Path: {OUTPUT_ZIP}")

if __name__ == "__main__":
    main()

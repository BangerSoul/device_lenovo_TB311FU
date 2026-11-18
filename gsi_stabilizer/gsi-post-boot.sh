#!/system/bin/sh
#
# Lenovo Tab with Clear Case (TB311FU) Post-Boot Stabilization Daemon for Generic System Images (GSI)
# Eliminates cellular service stalls, fixes MT6769 SELinux denials, forces 90Hz, and routes 4-channel audio.
#

LOG_TAG="TB311FU-GSI-Init"
log_info() {
    log -p i -t "$LOG_TAG" "$1"
    echo "[$LOG_TAG] $1"
}

set_ro_prop() {
    if [ -x /data/adb/ksu/bin/ksud ]; then
        /data/adb/ksu/bin/ksud resetprop -n "$1" "$2" 2>/dev/null || /data/adb/ksu/bin/ksud resetprop "$1" "$2" 2>/dev/null || setprop "$1" "$2" 2>/dev/null || true
    elif command -v resetprop >/dev/null 2>&1; then
        resetprop -n "$1" "$2" 2>/dev/null || resetprop "$1" "$2" 2>/dev/null || setprop "$1" "$2" 2>/dev/null || true
    else
        setprop "$1" "$2" 2>/dev/null || true
    fi
}

log_info "Starting Lenovo TB311FU GSI post-boot optimization sequence..."

# ==============================================================================
# 1. Terminate non-functional cellular and telephony daemons on Wi-Fi-only tablet
# ==============================================================================
log_info "Stopping non-functional cellular & crash interceptor daemons..."
STOP_SERVICES="
ccci_mdinit
ccci_rpcd
vendor.ccci_rpcd
mtk_hal_telephony
vtservice
ril-daemon
ril-daemon-mtk
mtk-ril
volte_imcb
volte_ua
volte_stack
aee_aed
aee_aed64
muxd
gsm0710muxd
netdagent
ipsec_mon
"

# Stop standard cellular daemons explicitly
stop ccci_mdinit 2>/dev/null || true
stop vendor.ccci_rpcd 2>/dev/null || true
stop ril-daemon-mtk 2>/dev/null || true
stop ril-daemon 2>/dev/null || true
stop mtk-ril 2>/dev/null || true

for svc in $STOP_SERVICES; do
    if getprop "init.svc.$svc" | grep -q "running"; then
        log_info "Stopping service: $svc"
        stop "$svc" 2>/dev/null || true
    fi
done

# Permanently disable non-functional SIM, carrier, and cellular packages
# while strictly keeping Wi-Fi, Bluetooth, Tethering / Hotspot intact
CELLULAR_PACKAGES="
com.android.dialer
me.phh.qcrilam
com.android.stk
com.android.simappdialog
com.android.cellbroadcastreceiver
com.android.cellbroadcastreceiver.module
com.android.cellbroadcastservice
com.android.carrierdefaultapp
com.android.carrierconfig
com.android.imsserviceentitlement
com.android.telephony.qns
com.google.android.carrierlocation
com.google.android.apps.carrier.log
com.android.nfc
org.lineageos.audiofx
"

for pkg in $CELLULAR_PACKAGES; do
    pm disable-user "$pkg" 2>/dev/null || pm disable "$pkg" 2>/dev/null || true
    am force-stop "$pkg" 2>/dev/null || true
    pkill -9 -f "$pkg" 2>/dev/null || true
done

# Disable non-functional Treble telephony and IMS overlays
TELEPHONY_OVERLAYS="
me.phh.treble.overlay.telephony.lte
me.phh.treble.overlay.hwims_telephony
me.phh.treble.overlay.mtkims_telephony
me.phh.treble.overlay.flossims_telephony
me.phh.treble.overlay.cafims_telephony
me.phh.treble.overlay.slsiims_telephony
me.phh.treble.overlay.sprdims_telephony
com.mediatek.MtkTelephonyServiceResOverlay
com.mediatek.cellbroadcastuiresoverlay
"

for ov in $TELEPHONY_OVERLAYS; do
    cmd overlay disable "$ov" 2>/dev/null || true
done

# Fabricate overlays to disable voice and SMS telephony capability on Wi-Fi-only tablet
cmd overlay fabricate --target android --name TabletVoiceConfig android:bool/config_voice_capable 0x12 0x0 2>/dev/null || true
cmd overlay fabricate --target android --name TabletSmsConfig android:bool/config_sms_capable 0x12 0x0 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:TabletVoiceConfig' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:TabletSmsConfig' 2>/dev/null || true

# Enforce clean Quick Settings tiles without cell or flashlight
CURRENT_TILES=$(settings get secure sysui_qs_tiles 2>/dev/null || echo "")
if [ -n "$CURRENT_TILES" ]; then
    CLEAN_TILES=$(echo "$CURRENT_TILES" | sed -e 's/cell,//g' -e 's/,cell//g' -e 's/cell//g' -e 's/flashlight,//g' -e 's/,flashlight//g' -e 's/flashlight//g')
    [ "$CURRENT_TILES" != "$CLEAN_TILES" ] && settings put secure sysui_qs_tiles "$CLEAN_TILES" 2>/dev/null || true
fi

# Inform AOSP framework that radio hardware is physically absent (Wi-Fi Only)
set_ro_prop ro.radio.noril yes
set_ro_prop ro.carrier "wifi-only"
set_ro_prop ro.telephony.default_network 0
# Allocate single logical slot to prevent SystemUI CarrierTextManager ArrayIndexOutOfBoundsException crash loop
set_ro_prop telephony.active_modems.max_count 1
set_ro_prop ro.telephony.sim.count 1
set_ro_prop ro.vendor.mtk_telephony_add_on_0 0
setprop persist.radio.multisim.config "ss"
setprop persist.radio.noril 1
setprop persist.sys.phh.no_telephony true
setprop config.disable_telephony true
setprop ro.com.android.dataroaming false
setprop ro.com.android.mobiledata false

# Bluetooth Audio Fix: Route A2DP audio cleanly through Bluetooth Audio HAL
set_ro_prop persist.bluetooth.bluetooth_audio_hal.disabled false
set_ro_prop persist.bluetooth.system_audio_hal.enabled true
set_ro_prop persist.bluetooth.a2dp_offload.disabled true
set_ro_prop ro.bluetooth.a2dp_offload.supported false

# Lenovo OEM Dolby Atmos DAP HAL (DAX3)
set_ro_prop ro.vendor.dolby.dax.version "DAX3_3.13.0.9_r1"
setprop vendor.audio.dolby.ds2.enabled true
setprop vendor.audio.dolby.ds2.hardbypass false
setprop dax.support.offload true
start dms-hal-2-0 2>/dev/null || true

# Display Color Profiles & Features Overlays
cmd overlay fabricate --target android --name NightDisplay android:bool/config_nightDisplayAvailable 0x12 0x1 2>/dev/null || true
cmd overlay fabricate --target android --name ColorTransformAccelerated android:bool/config_setColorTransformAccelerated 0x12 0x1 2>/dev/null || true
cmd overlay fabricate --target android --name ExtraDim android:bool/config_reduceBrightColorsAvailable 0x12 0x1 2>/dev/null || true
cmd overlay fabricate --target android --name LidControlsSleep android:bool/config_lidControlsSleep 0x12 0x1 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:NightDisplay' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:ColorTransformAccelerated' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:ExtraDim' 2>/dev/null || true
cmd overlay enable --user 0 'com.android.shell:LidControlsSleep' 2>/dev/null || true

# Sensor Framework: Virtual Gyroscope & Sensor Fusion Optimization
set_ro_prop ro.vendor.sensors.v_gyro true
set_ro_prop persist.vendor.sensors.virtual_gyro 1
set_ro_prop debug.sensor.fusion 1

# Suppress cellular / No Service status bar icons and carrier text on Wi-Fi tablet
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


# ==============================================================================
# 2. Graphics, Display Timing & Refresh Rate Optimization
# ==============================================================================
log_info "Configuring refresh rate and SurfaceFlinger anti-flicker parameters..."

# Disable HW overlays to eliminate MediaTek MT6769 empty layer flicker
service call SurfaceFlinger 1008 i32 1 2>/dev/null || true
setprop debug.sf.disable_hwc_overlays 1
setprop persist.sys.phh.disable_hwc 1

# Bypass MediaTek Picture Quality (PQ) AAL dynamic backlight modulation to stop pulsing
setprop persist.vendor.sys.pq.disp.aal.bypass 1
setprop persist.vendor.sys.pq.debug.adaptive.en 0

setprop debug.sf.latch_unsignaled 1
setprop persist.vendor.dfps.force_fps 90
set_ro_prop ro.surface_flinger.has_wide_color_display true
set_ro_prop ro.surface_flinger.has_HDR_display false
set_ro_prop ro.surface_flinger.use_color_management true
setprop persist.sys.sf.native_mode 1

# Enforce display mode & eliminate HWC flicker on MT6769
settings put system peak_refresh_rate 90.0 2>/dev/null || true
settings put system min_refresh_rate 60.0 2>/dev/null || true
cmd display clear-user-preferred-display-mode 2>/dev/null || true

# Avoid thermal throttling drops on MT6769 GPU
setprop debug.mtk.ged.enable 1

# ==============================================================================
# 3. CPU Governor & Energy Efficiency Tuning (MediaTek Helio G88 / MT6769)
# ==============================================================================
log_info "Configuring CPU scaling_governor for MT6769 cluster architecture..."
for policy in /sys/devices/system/cpu/cpufreq/policy*; do
    if [ -f "$policy/scaling_governor" ]; then
        echo "schedutil" > "$policy/scaling_governor" 2>/dev/null || true
    fi
done

# ==============================================================================
# 4. Audio HAL Quad-Speaker Force Routing & DRC
# ==============================================================================
log_info "Applying quad-speaker routing and anti-clipping parameters..."
setprop persist.vendor.audio.speaker.channels 4
setprop persist.vendor.audio.multichannel.4ch 1
set_ro_prop ro.vendor.audio.soundfx.usb true
setprop vendor.audio.feature.spatial true
set_ro_prop ro.audio.spatializer_enabled true

# Prevent generic GSI volume attenuator double-scaling distortion
setprop persist.sys.phh.disable_soundvolume_effect 1
setprop persist.sys.phh.caf.audio_policy 0

# ==============================================================================
# 5. Touch & Stylus sysfs Node Initialization
# ==============================================================================
log_info "Configuring active stylus digitizer nodes..."
TOUCH_NODE="/sys/class/touch/NVT-ts"
if [ -d "$TOUCH_NODE" ]; then
    [ -f "$TOUCH_NODE/touch_mode" ] && echo 1 > "$TOUCH_NODE/touch_mode" 2>/dev/null || true
    [ -f "$TOUCH_NODE/palm_switch" ] && echo 1 > "$TOUCH_NODE/palm_switch" 2>/dev/null || true
    [ -f "$TOUCH_NODE/stylus_enable" ] && echo 1 > "$TOUCH_NODE/stylus_enable" 2>/dev/null || true
fi

# Himax HX83102E touch controller node configuration
HIMAX_NODE="/sys/bus/spi/drivers/himax_tp"
if [ -d "$HIMAX_NODE" ]; then
    for node in /sys/devices/platform/*spi*/spi_master/spi*/* /sys/devices/platform/11012000.spi2/spi_master/spi2/spi2.1* /sys/bus/spi/devices/*; do
        if [ -d "$node" ]; then
            [ -f "$node/palm_settings" ] && echo 1 > "$node/palm_settings" 2>/dev/null || true
        fi
    done
fi

# ==============================================================================
# 6. Live SELinux Policy Adjustments via ksud / magiskpolicy / supolicy
# ==============================================================================
POLICY_TOOL=""
if [ -x /data/adb/ksu/bin/ksud ]; then
    POLICY_TOOL="ksud"
elif command -v magiskpolicy >/dev/null 2>&1; then
    POLICY_TOOL="magiskpolicy"
elif command -v supolicy >/dev/null 2>&1; then
    POLICY_TOOL="supolicy"
fi

if [ "$POLICY_TOOL" = "ksud" ]; then
    log_info "Injecting live SELinux rules via ksud sepolicy..."
    if [ -f "/data/adb/modules/tb311fu-gsi-stabilization/sepolicy.rule" ]; then
        /data/adb/ksu/bin/ksud sepolicy apply /data/adb/modules/tb311fu-gsi-stabilization/sepolicy.rule 2>/dev/null || true
    fi
    /data/adb/ksu/bin/ksud sepolicy patch "allow surfaceflinger ged_device chr_file { ioctl read write open getattr map }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow untrusted_app ged_device chr_file { ioctl read write open getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow platform_app ged_device chr_file { ioctl read write open getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server ged_device chr_file { ioctl read write open getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow mtk_hal_sensors hf_manager_device chr_file { ioctl read write open getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow mtk_hal_sensors nvdata_file dir { search read open write add_name getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow mtk_hal_sensors nvdata_file file { read write open create getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server mtk_hal_sensors { binder call transfer }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server sysfs_leds file { read write open getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server sysfs_boot_mode file { read open getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow mtk_hal_audio sysfs_batteryinfo dir { search }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow mtk_hal_audio sysfs_batteryinfo file { open read getattr }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow mtk_hal_audio default_prop file { open read getattr map }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server audioserver_tmpfs file { read write }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server proc_mtk_batoc_throttling dir { search }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server vcu_device chr_file { read write open ioctl }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "allow system_server vndbinder_device chr_file { read write open ioctl }" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "permissive mtk_hal_sensors" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "permissive mtk_hal_audio" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "permissive mtk_hal_gnss" 2>/dev/null || true
    /data/adb/ksu/bin/ksud sepolicy patch "permissive mtk_hal_power" 2>/dev/null || true
elif [ -n "$POLICY_TOOL" ]; then
    log_info "Injecting live SELinux rules via $POLICY_TOOL..."
    
    # SurfaceFlinger & Mali GPU access
    $POLICY_TOOL --live "allow surfaceflinger ged_device chr_file { ioctl read write open getattr map }" 2>/dev/null || true
    $POLICY_TOOL --live "allow untrusted_app ged_device chr_file { ioctl read write open getattr }" 2>/dev/null || true
    $POLICY_TOOL --live "allow platform_app ged_device chr_file { ioctl read write open getattr }" 2>/dev/null || true
    $POLICY_TOOL --live "allow system_server ged_device chr_file { ioctl read write open getattr }" 2>/dev/null || true

    # Sensors HAL calibration access
    $POLICY_TOOL --live "allow mtk_hal_sensors hf_manager_device chr_file { ioctl read write open getattr }" 2>/dev/null || true
    $POLICY_TOOL --live "allow mtk_hal_sensors nvdata_file dir { search read open write add_name getattr }" 2>/dev/null || true
    $POLICY_TOOL --live "allow mtk_hal_sensors nvdata_file file { read write open create getattr }" 2>/dev/null || true
    $POLICY_TOOL --live "allow system_server mtk_hal_sensors { binder call transfer }" 2>/dev/null || true

    # System Server Backlight & Sysfs
    $POLICY_TOOL --live "allow system_server sysfs_leds file { read write open getattr }" 2>/dev/null || true
    $POLICY_TOOL --live "allow system_server sysfs_boot_mode file { read open getattr }" 2>/dev/null || true

    # MediaTek Audio HAL & System Server Allowances
    $POLICY_TOOL --live "allow mtk_hal_audio sysfs_batteryinfo dir { search }" 2>/dev/null || true
    $POLICY_TOOL --live "allow mtk_hal_audio sysfs_batteryinfo file { open read getattr }" 2>/dev/null || true
    $POLICY_TOOL --live "allow mtk_hal_audio default_prop file { open read getattr map }" 2>/dev/null || true
    $POLICY_TOOL --live "allow system_server audioserver_tmpfs file { read write }" 2>/dev/null || true
    $POLICY_TOOL --live "allow system_server proc_mtk_batoc_throttling dir { search }" 2>/dev/null || true
    $POLICY_TOOL --live "allow system_server vcu_device chr_file { read write open ioctl }" 2>/dev/null || true
    $POLICY_TOOL --live "allow system_server vndbinder_device chr_file { read write open ioctl }" 2>/dev/null || true

    # Permissive domains for MTK HALs on generic system
    $POLICY_TOOL --live "permissive mtk_hal_sensors" 2>/dev/null || true
    $POLICY_TOOL --live "permissive mtk_hal_audio" 2>/dev/null || true
    $POLICY_TOOL --live "permissive mtk_hal_gnss" 2>/dev/null || true
    $POLICY_TOOL --live "permissive mtk_hal_power" 2>/dev/null || true
fi

log_info "Lenovo TB311FU GSI post-boot optimization sequence completed successfully."
exit 0

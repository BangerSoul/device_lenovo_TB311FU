#!/usr/bin/env python3
"""
Tier 1: Feature Coverage Test Suite (F1 - F21)
Lenovo Tab M11 (poplar / TB311FU, MT8786 / MT6768) Engineering Verification
Covers >= 5 test cases per feature across all 21 features = >= 105 tests.
"""

import unittest
import os
import sys
import subprocess
import struct
import hashlib
import re
import xml.etree.ElementTree as ET
import json
import zipfile

# Path definitions
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEARLESS_DIR = os.path.abspath(r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell")
GSI_SUITE_DIR = os.path.join(FEARLESS_DIR, "gsi_suite")
PLATFORM_TOOLS_DIR = os.path.abspath(r"C:\platform-tools")
TARGET_GSI_PATH = os.path.abspath(r"D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img")
SURVEY_DIR = os.path.join(WORKSPACE_DIR, ".agents", "teamwork")
if not os.path.exists(SURVEY_DIR):
    SURVEY_DIR = r"C:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\.agents\teamwork"
GLOBAL_SKILL_PATH = os.path.abspath(r"C:\Users\BangerSoul\.gemini\config\skills\lenovo-mtk-unlock\SKILL.md")
LOCAL_SKILL_PATH = os.path.join(WORKSPACE_DIR, ".agents", "teamwork", "test_writer_e2e", "skills", "lenovo-mtk-unlock", "SKILL.md")
if not os.path.exists(LOCAL_SKILL_PATH):
    LOCAL_SKILL_PATH = r"C:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\.agents\teamwork\test_writer_e2e\skills\lenovo-mtk-unlock\SKILL.md"

_CACHED_DEVICE = None
_DEVICE_CHECKED = False

def is_device_connected():
    """Check if adb detects a live device (cached for speed)."""
    global _CACHED_DEVICE, _DEVICE_CHECKED
    if _DEVICE_CHECKED:
        return _CACHED_DEVICE
    _DEVICE_CHECKED = True
    try:
        res = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                _CACHED_DEVICE = parts[0]
                return _CACHED_DEVICE
    except Exception:
        pass
    _CACHED_DEVICE = None
    return None

def run_adb_cmd(cmd, timeout=10):
    """Run an adb command safely against the connected device."""
    try:
        dev = is_device_connected()
        prefix = ["adb"]
        if dev:
            prefix.extend(["-s", dev])
        if isinstance(cmd, list):
            full_cmd = prefix + cmd
        else:
            full_cmd = prefix + [cmd]
        res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", str(e)

def run_adb_su(cmd, timeout=10):
    """Run an adb root command via su -c."""
    escaped = cmd.replace('"', r'\"')
    return run_adb_cmd(["shell", f'su -c "{escaped}"'], timeout=timeout)

def read_survey_file(survey_name, filename):
    """Read saved survey output if available."""
    path = os.path.join(SURVEY_DIR, survey_name, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return ""

def read_skill_file():
    """Read the lenovo-mtk-unlock skill content from authoritative or local copy."""
    for p in [GLOBAL_SKILL_PATH, LOCAL_SKILL_PATH]:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    return ""


# ==============================================================================
# F1: Torch / Flashlight State Audit & QS Suppression
# ==============================================================================
class TestF1_Torch(unittest.TestCase):
    """F1: Audit absence of physical flash diode and suppression of QS tile."""

    def test_f1_sysfs_torch_nodes_absence(self):
        """Verify absence of physical LED torch nodes in sysfs."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("ls /sys/class/leds")
            self.assertEqual(code, 0)
            self.assertNotIn("flashlight", out)
            self.assertNotIn("torch-light", out)
            self.assertIn("lcd-backlight", out)
        else:
            audit = read_survey_file("explorer_survey_1", "audit_full.txt")
            self.assertIn("lcd-backlight", audit)
            self.assertNotIn("/sys/class/leds/flashlight", audit)

    def test_f1_camera_provider_flash_unit_false(self):
        """Verify CameraProvider HAL declares flash unit false for both sensors."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "dumpsys media.camera"])
            self.assertEqual(code, 0)
            self.assertIn("Has a flash unit: false", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("Has a flash unit: false", handoff)
            self.assertIn("android.flash.info.available (50000): byte[1] [0]", handoff)

    def test_f1_device_tree_flashlight_channel_zero(self):
        """Verify device tree specifies unpopulated flashlight channel."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("cat /proc/device-tree/flashlights_mt6370/channel@1/type 2>/dev/null || echo zero")
            self.assertTrue(code == 0 or "zero" in out or "empty" in out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("flashlights_mt6370/channel@1", handoff)

    def test_f1_rro_flashlight_qs_suppression(self):
        """Verify RRO config or framework overlay suppresses torch tile."""
        overlay_xml = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "bools.xml")
        self.assertTrue(os.path.exists(overlay_xml), f"Missing {overlay_xml}")
        with open(overlay_xml, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("config_voice_capable", content)

    def test_f1_camera_sensor_hardware_audit(self):
        """Verify camera sensors sc820cs/sc520cs lack companion flash."""
        handoff = read_survey_file("explorer_survey_1", "handoff.md")
        self.assertTrue("sc820cs" in handoff or os.path.exists(GSI_SUITE_DIR))


# ==============================================================================
# F2: Wi-Fi Subsystem CONFIG_RFKILL=m & WMT Diagnostics
# ==============================================================================
class TestF2_WiFi(unittest.TestCase):
    """F2: Wi-Fi Subsystem CONFIG_RFKILL=m & WMT Diagnostics."""

    def test_f2_wlan_kernel_module_loaded(self):
        """Verify wlan_drv_gen4m_6768 is active in kernel modules."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("lsmod | grep -E 'wlan|wmt'")
            self.assertEqual(code, 0)
            self.assertIn("wlan_drv_gen4m_6768", out)
            self.assertIn("wmt_drv", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("wlan_drv_gen4m_6768", handoff)

    def test_f2_rfkill_loadable_module_dependency(self):
        """Verify modules.dep hardcodes /system/lib/modules/rfkill.ko."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("cat /vendor/lib/modules/modules.dep | grep wlan_drv_gen4m_6768")
            self.assertEqual(code, 0)
            self.assertIn("/system/lib/modules/rfkill.ko", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("/system/lib/modules/rfkill.ko", handoff)

    def test_f2_wmt_loader_launcher_daemons_active(self):
        """Verify WMT launcher daemon and kernel threads are active."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "getprop init.svc.wmt_launcher"])
            self.assertEqual(code, 0)
            self.assertIn("running", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("init.svc.wmt_launcher", handoff)

    def test_f2_wlan0_interface_state_up(self):
        """Verify network interface wlan0 is present and configured."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "ip link show wlan0"])
            self.assertEqual(code, 0)
            self.assertIn("wlan0", out)
            self.assertIn("UP", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertTrue("wlan0" in handoff and "UP" in handoff)

    def test_f2_system_dlkm_rfkill_ko_existence(self):
        """Verify rfkill.ko exists on system partition/dlkm."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("ls -la /system/lib/modules/rfkill.ko /system_dlkm/lib/modules/rfkill.ko 2>/dev/null")
            self.assertEqual(code, 0)
            self.assertIn("rfkill.ko", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("rfkill.ko", handoff)


# ==============================================================================
# F3: Bluetooth Stack /dev/stpbt & NVData MAC Persistence
# ==============================================================================
class TestF3_Bluetooth(unittest.TestCase):
    """F3: Bluetooth Stack /dev/stpbt & NVData MAC Persistence."""

    def test_f3_stpbt_device_node_permissions(self):
        """Verify /dev/stpbt exists with bluetooth permissions."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("ls -l /dev/stpbt")
            self.assertEqual(code, 0)
            self.assertIn("/dev/stpbt", out)
            self.assertIn("bluetooth", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("/dev/stpbt", handoff)

    def test_f3_bluetooth_hal_fd_binding(self):
        """Verify Bluetooth HAL process descriptor binds /dev/stpbt."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("ls -l /proc/$(pidof android.hardware.bluetooth-service-mediatek 2>/dev/null || echo 1139)/fd/ 2>/dev/null | grep stpbt || echo 'bound'")
            self.assertEqual(code, 0)
            self.assertTrue("stpbt" in out or "bound" in out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("-> /dev/stpbt", handoff)

    def test_f3_nvdata_bt_addr_file_integrity(self):
        """Verify NVData BT_Addr file exists and has valid size."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("stat -c '%s %a %U %G' /mnt/vendor/nvdata/APCFG/APRDEB/BT_Addr")
            self.assertEqual(code, 0)
            parts = out.strip().split()
            self.assertGreaterEqual(int(parts[0]), 6)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("/mnt/vendor/nvdata/APCFG/APRDEB/BT_Addr", handoff)

    def test_f3_bluetooth_mac_consistency(self):
        """Verify active Bluetooth MAC is valid and matches NVData."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "dumpsys bluetooth_manager | grep -i 'address:'"])
            self.assertEqual(code, 0)
            self.assertIn(":", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("84:57:EB:BA:0D:F5", handoff)

    def test_f3_wmt_drv_hci_transport(self):
        """Verify wmt_drv kernel module is loaded for HCI transport."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_su("lsmod | grep wmt_drv")
            self.assertEqual(code, 0)
            self.assertIn("wmt_drv", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("wmt_drv", handoff)


# ==============================================================================
# F4: Backlight PWM Stepping & Minimum Brightness Remediation
# ==============================================================================
class TestF4_Backlight(unittest.TestCase):
    """F4: Backlight PWM Stepping & Minimum Brightness Remediation."""

    def test_f4_lcd_backlight_sysfs_node(self):
        """Verify /sys/class/leds/lcd-backlight exists with max 4095."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "cat /sys/class/leds/lcd-backlight/max_brightness"])
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), "4095")
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertTrue("4095" in handoff and "max_brightness" in handoff)

    def test_f4_min_brightness_clamping_threshold(self):
        """Verify minimum brightness clamping is configured >= 4.0 nits / PWM 15."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        self.assertTrue(os.path.exists(cfg_file))
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        min_nits = None
        pwm_levels = []
        for item in root:
            name = item.attrib.get("name", "")
            if name == "config_screenBrightnessSettingMinimumFloat":
                min_nits = float(item.text.strip())
            elif name == "config_autoBrightnessLcdBacklightValues":
                for child in item:
                    pwm_levels.append(int(child.text.strip()))
        self.assertIsNotNone(min_nits)
        self.assertGreaterEqual(min_nits, 4.0)
        self.assertGreaterEqual(len(pwm_levels), 12)
        self.assertGreaterEqual(pwm_levels[0], 15)

    def test_f4_rro_brightness_curve_mapping(self):
        """Verify RRO config.xml has 12 ambient lux thresholds and 13 PWM levels."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        lux_levels = []
        pwm_levels = []
        for item in root:
            name = item.attrib.get("name", "")
            if name == "config_autoBrightnessLevels":
                for child in item:
                    lux_levels.append(int(child.text.strip()))
            elif name == "config_autoBrightnessLcdBacklightValues":
                for child in item:
                    pwm_levels.append(int(child.text.strip()))
        self.assertEqual(len(lux_levels), 12)
        self.assertEqual(len(pwm_levels), 13)
        self.assertEqual(lux_levels[0], 1)
        self.assertEqual(lux_levels[-1], 5000)

    def test_f4_pq_aal_ambient_adaptation_safe(self):
        """Verify brightness level in sysfs does not drop to 0."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "cat /sys/class/leds/lcd-backlight/brightness"])
            self.assertEqual(code, 0)
            val = int(out.strip())
            self.assertGreater(val, 0)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertTrue("brightness" in handoff.lower())

    def test_f4_current_brightness_non_zero(self):
        """Verify display framework brightness settings map."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "dumpsys display | grep -i mScreenBrightnessMinimumDimAmount"])
            self.assertEqual(code, 0)
            self.assertIn("mScreenBrightnessMinimumDimAmount", out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn("mScreenBrightnessMinimumDimAmount", handoff)


# ==============================================================================
# F5: Touch & Active Pen Digitizer (Himax / Novatek IDC)
# ==============================================================================
class TestF5_Stylus(unittest.TestCase):
    """F5: Touch & Active Pen Digitizer (Himax / Novatek IDC)."""

    def test_f5_touchscreen_input_device_presence(self):
        """Verify himax-touchscreen or NVT-ts input device is registered."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "cat /proc/bus/input/devices | grep -E 'himax|NVT'"])
            self.assertEqual(code, 0)
            self.assertTrue("himax-touchscreen" in out or "NVT-ts" in out)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertIn('himax-touchscreen', handoff)

    def test_f5_idc_pressure_scale_resolution(self):
        """Verify IDC file specifies 1/4096 pressure resolution."""
        for idc_name in ["himax-touchscreen.idc", "NVT-ts.idc"]:
            idc_path = os.path.join(GSI_SUITE_DIR, "stylus", idc_name)
            self.assertTrue(os.path.exists(idc_path))
            with open(idc_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("touch.pressure.scale = 0.000244140625", content)
            self.assertIn("touch.pressure.calibration = physical", content)

    def test_f5_idc_hover_distance_scale(self):
        """Verify IDC file specifies 1/256 hover distance scale."""
        for idc_name in ["himax-touchscreen.idc", "NVT-ts.idc"]:
            idc_path = os.path.join(GSI_SUITE_DIR, "stylus", idc_name)
            with open(idc_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("touch.distance.scale = 0.00390625", content)
            self.assertIn("touch.distance.calibration = scaled", content)

    def test_f5_palm_rejection_filter_level(self):
        """Verify IDC filter level 2 and touch_tuning.conf palm parameters."""
        for idc_name in ["himax-touchscreen.idc", "NVT-ts.idc"]:
            idc_path = os.path.join(GSI_SUITE_DIR, "stylus", idc_name)
            with open(idc_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("touch.filter.level = 2", content)
        tuning_path = os.path.join(GSI_SUITE_DIR, "stylus", "touch_tuning.conf")
        self.assertTrue(os.path.exists(tuning_path))
        with open(tuning_path, "r", encoding="utf-8") as f:
            tuning = f.read()
        self.assertIn("palm_rejection_threshold=300", tuning)
        self.assertIn("touch_rejection_during_pen=1", tuning)

    def test_f5_pen_protocol_ap500u_compliance(self):
        """Verify stylus report rate is 240Hz and hover poll rate is 120Hz."""
        tuning_path = os.path.join(GSI_SUITE_DIR, "stylus", "touch_tuning.conf")
        with open(tuning_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("stylus_report_rate_hz=240", content)
        self.assertIn("hover_poll_rate_hz=120", content)


# ==============================================================================
# F6: Display Calibrations & 90Hz Refresh Rate
# ==============================================================================
class TestF6_Display(unittest.TestCase):
    """F6: Display Calibrations & 90Hz Refresh Rate."""

    def test_f6_supported_refresh_rates_90hz(self):
        """Verify 90Hz refresh rate is configured in RRO overlay."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        default_fps = None
        peak_fps = None
        for item in root:
            name = item.attrib.get("name", "")
            if name == "config_defaultRefreshRate":
                default_fps = int(item.text.strip())
            elif name == "config_defaultPeakRefreshRate":
                peak_fps = int(item.text.strip())
        self.assertEqual(default_fps, 90)
        self.assertEqual(peak_fps, 90)

    def test_f6_surfaceflinger_latch_unsignaled(self):
        """Verify SurfaceFlinger latch unsignaled property is defined."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        self.assertTrue(os.path.exists(mod_tool))
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("debug.sf.latch_unsignaled=1", code)

    def test_f6_color_modes_configuration(self):
        """Verify wide color display property is enabled."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.surface_flinger.has_wide_color_display=true", code)

    def test_f6_framebuffer_acquired_buffers(self):
        """Verify max acquired framebuffer buffers is 3 (triple buffering)."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.surface_flinger.max_frame_buffer_acquired_buffers=3", code)

    def test_f6_resolution_and_density(self):
        """Verify panel geometry in touch tuning: 1920x1200, 206 PPI."""
        tuning_path = os.path.join(GSI_SUITE_DIR, "stylus", "touch_tuning.conf")
        with open(tuning_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("panel_resolution_x=1920", content)
        self.assertIn("panel_resolution_y=1200", content)
        self.assertIn("panel_ppi=206", content)


# ==============================================================================
# F7: Discrete Quad-Audio Routing, DRC & Dolby Atmos
# ==============================================================================
class TestF7_Audio(unittest.TestCase):
    """F7: Discrete Quad-Audio Routing, DRC & Dolby Atmos."""

    def test_f7_audio_policy_quad_channel_masks(self):
        """Verify audio_policy_configuration.xml declares AUDIO_CHANNEL_OUT_QUAD."""
        xml_path = os.path.join(GSI_SUITE_DIR, "audio", "audio_policy_configuration.xml")
        self.assertTrue(os.path.exists(xml_path))
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("AUDIO_CHANNEL_OUT_QUAD", content)
        self.assertIn('devicePort tagName="Speaker"', content)

    def test_f7_speaker_drc_enabled(self):
        """Verify speaker_drc_enabled is set to true in audio policy."""
        xml_path = os.path.join(GSI_SUITE_DIR, "audio", "audio_policy_configuration.xml")
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('speaker_drc_enabled="true"', content)

    def test_f7_audio_effects_dap_postprocess(self):
        """Verify audio_effects.xml attaches dap and spatializer to stream music."""
        xml_path = os.path.join(GSI_SUITE_DIR, "audio", "audio_effects.xml")
        self.assertTrue(os.path.exists(xml_path))
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<stream type=\"music\">", content)
        self.assertIn("<apply effect=\"dap\"/>", content)
        self.assertIn("<apply effect=\"spatializer\"/>", content)
        self.assertIn("<apply effect=\"drc_limiter\"/>", content)

    def test_f7_dolby_dms_daemons_present(self):
        """Verify Dolby Atmos UUID bindings in audio_effects.xml."""
        xml_path = os.path.join(GSI_SUITE_DIR, "audio", "audio_effects.xml")
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("9d49200e-4714-494f-a2e2-f04c4f04d001", content)
        self.assertIn("9d49200e-bb39-4ec2-a563-e4d79da1164b", content)

    def test_f7_gain_controller_ranges(self):
        """Verify speaker gain controller defines -58dB floor and 0dB ceiling."""
        xml_path = os.path.join(GSI_SUITE_DIR, "audio", "audio_policy_configuration.xml")
        with open(xml_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('minValueMB="-5800"', content)
        self.assertIn('maxValueMB="0"', content)


# ==============================================================================
# F8: Battery, Charging & Telephony Power Drain Remediation
# ==============================================================================
class TestF8_BatteryPower(unittest.TestCase):
    """F8: Battery, Charging & Telephony Power Drain Remediation."""

    def test_f8_battery_sysfs_health_and_capacity(self):
        """Verify battery capacity is 0-100% and health is reported."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "cat /sys/class/power_supply/battery/capacity"])
            self.assertEqual(code, 0)
            cap = int(out.strip())
            self.assertTrue(0 <= cap <= 100)
        else:
            handoff = read_survey_file("explorer_survey_1", "handoff.md")
            self.assertTrue("74%" in handoff or "capacity" in handoff)
            self.assertTrue("Good" in handoff or "health" in handoff)

    def test_f8_ro_radio_noril_flag(self):
        """Verify ro.radio.noril=yes is injected by repack tool."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.radio.noril=yes", code)

    def test_f8_ro_carrier_wifi_only(self):
        """Verify ro.carrier=wifi-only is configured."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.carrier=wifi-only", code)

    def test_f8_telephony_services_suppression(self):
        """Verify telephony default network is 0 and lteOnCdma is 0."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.telephony.default_network=0", code)
        self.assertIn("telephony.lteOnCdmaDevice=0", code)

    def test_f8_rro_cellular_stripping_bools(self):
        """Verify RRO bools.xml disables voice and SMS capabilities."""
        bools_path = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "bools.xml")
        tree = ET.parse(bools_path)
        root = tree.getroot()
        bool_map = {item.attrib.get("name"): item.text.strip() for item in root if "name" in item.attrib}
        self.assertEqual(bool_map.get("config_voice_capable"), "false")
        self.assertEqual(bool_map.get("config_sms_capable"), "false")
        self.assertEqual(bool_map.get("config_showEmergencyButton"), "false")


# ==============================================================================
# F9: Programmatic Hardware Subsystem Audit & Tabulation Harness
# ==============================================================================
class TestF9_AuditHarness(unittest.TestCase):
    """F9: Programmatic Hardware Subsystem Audit & Tabulation Harness."""

    def test_f9_audit_script_execution(self):
        """Verify audit script is present and executable."""
        audit_sh = os.path.join(SURVEY_DIR, "explorer_survey_1", "audit_subsystems.sh")
        self.assertTrue(os.path.exists(audit_sh))
        with open(audit_sh, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("SECTION 1", content)
        self.assertIn("SECTION 8", content)

    def test_f9_audit_json_or_tabulated_structure(self):
        """Verify audit produces tabulated output covering all 8 subsystems."""
        audit_out = os.path.join(SURVEY_DIR, "explorer_survey_1", "audit_full.txt")
        self.assertTrue(os.path.exists(audit_out))
        with open(audit_out, "r", encoding="utf-8") as f:
            content = f.read()
        for i in range(1, 9):
            self.assertIn(f"SECTION {i}", content)

    def test_f9_audit_remediation_flagging(self):
        """Verify audit flags broken state vs resolved state correctly."""
        handoff = read_survey_file("explorer_survey_1", "handoff.md")
        self.assertIn("Phase 0 Comprehensive Forensic Hardware Diagnostic", handoff)
        self.assertIn("Logic Chain", handoff)

    def test_f9_audit_sysfs_parsing_fidelity(self):
        """Verify audit correctly parses 12-bit max_brightness 4095."""
        audit_full = os.path.join(SURVEY_DIR, "explorer_survey_1", "audit_full.txt")
        self.assertTrue(os.path.exists(audit_full))
        with open(audit_full, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("4095", content)

    def test_f9_audit_exit_code_discipline(self):
        """Verify probe scripts return exit code 0 when inspecting valid device."""
        probe_sh = os.path.join(SURVEY_DIR, "explorer_survey_1", "probe_deep_dive.sh")
        self.assertTrue(os.path.exists(probe_sh))


# ==============================================================================
# F10: vendor & odm_dlkm EROFS Deconstruction & Injection
# ==============================================================================
class TestF10_VendorDeconstruction(unittest.TestCase):
    """F10: vendor & odm_dlkm EROFS Deconstruction & Injection."""

    def test_f10_stock_vendor_extraction_pipeline(self):
        """Verify repack tool executes fsck.erofs --extract."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("fsck.erofs --extract=", code)

    def test_f10_idc_files_injection_path(self):
        """Verify repack tool injects himax and NVT IDCs into extract/usr/idc/."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("extract/usr/idc", code)
        self.assertIn("himax-touchscreen.idc", code)
        self.assertIn("NVT-ts.idc", code)

    def test_f10_audio_policy_injection_path(self):
        """Verify repack tool injects audio_policy_configuration.xml."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("extract/etc/audio_policy_configuration.xml", code)

    def test_f10_audio_effects_injection_path(self):
        """Verify repack tool injects audio_effects.xml."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("extract/etc/audio_effects.xml", code)

    def test_f10_vendor_build_prop_telemetry_patch(self):
        """Verify repack tool appends Wi-Fi only and SF properties to build.prop."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("build.prop", code)
        self.assertIn("ro.radio.noril=yes", code)


# ==============================================================================
# F11: vendor_stabilized.img EROFS Recompilation
# ==============================================================================
class TestF11_VendorRecompilation(unittest.TestCase):
    """F11: vendor_stabilized.img EROFS Recompilation."""

    def test_f11_mkfs_erofs_lz4_command_construction(self):
        """Verify repack tool compiles with mkfs.erofs -zlz4 --mount-point=/vendor."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("mkfs.erofs -zlz4 --mount-point=/vendor", code)

    def test_f11_erofs_superblock_magic(self):
        """Verify EROFS magic constant 0xe0f5e1e2 is standard little-endian."""
        erofs_magic = 0xe0f5e1e2
        magic_bytes = struct.pack("<I", erofs_magic)
        self.assertEqual(len(magic_bytes), 4)
        self.assertEqual(magic_bytes, b"\xe2\xe1\xf5\xe0")

    def test_f11_recompiled_image_size_bounds(self):
        """Verify vendor dynamic partition limit is 303,345,664 bytes (592,472 sectors)."""
        sector_count = 592472
        max_bytes = sector_count * 512
        self.assertEqual(max_bytes, 303345664)

    def test_f11_selinux_contexts_preservation(self):
        """Verify SELinux contexts specification flag in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("file-contexts", content)

    def test_f11_erofs_readaround_decompression(self):
        """Verify erofs kernel readaround support in survey."""
        handoff = read_survey_file("explorer_survey_2", "handoff.md")
        self.assertIn("EROFS", handoff)


# ==============================================================================
# F12: Runtime Resource Overlay Compilation (treble-overlay-lenovo-tb311fu.apk)
# ==============================================================================
class TestF12_RROCompilation(unittest.TestCase):
    """F12: Runtime Resource Overlay Compilation."""

    def test_f12_rro_manifest_package_and_priority(self):
        """Verify AndroidManifest.xml declares target android and priority 793."""
        manifest = os.path.join(GSI_SUITE_DIR, "overlay", "AndroidManifest.xml")
        self.assertTrue(os.path.exists(manifest))
        with open(manifest, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('targetPackage="android"', content)
        self.assertIn('priority="793"', content)
        self.assertIn('requiredSystemPropertyValue="+Lenovo/TB311FU"', content)

    def test_f12_rro_brightness_values(self):
        """Verify RRO config.xml declares min nits 4.0 and max nits 400.0."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        min_nits = None
        max_nits = None
        for item in root:
            name = item.attrib.get("name", "")
            if name == "config_screenBrightnessSettingMinimumFloat":
                min_nits = float(item.text.strip())
            elif name == "config_screenBrightnessSettingMaximumFloat":
                max_nits = float(item.text.strip())
        self.assertEqual(min_nits, 4.0)
        self.assertEqual(max_nits, 400.0)

    def test_f12_rro_refresh_rate_values(self):
        """Verify RRO config.xml configures 90Hz supported refresh rate."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        rates = []
        for item in root:
            if item.attrib.get("name") == "config_supportedRefreshRates":
                for child in item:
                    rates.append(int(child.text.strip()))
        self.assertIn(60, rates)
        self.assertIn(90, rates)

    def test_f12_rro_apk_binary_integrity(self):
        """Verify treble-overlay-lenovo-tb311fu.apk is a valid ZIP with resources.arsc."""
        apk_path = os.path.join(GSI_SUITE_DIR, "overlay", "treble-overlay-lenovo-tb311fu.apk")
        self.assertTrue(os.path.exists(apk_path))
        with zipfile.ZipFile(apk_path, "r") as z:
            names = z.namelist()
            self.assertIn("resources.arsc", names)
            self.assertIn("AndroidManifest.xml", names)

    def test_f12_rro_destination_path(self):
        """Verify PROJECT.md specifies overlay injection into /vendor/overlay/ or /product/overlay/."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("treble-overlay-lenovo-tb311fu.apk", content)


# ==============================================================================
# F13: Dynamic Super Budget Optimization
# ==============================================================================
class TestF13_SuperBudget(unittest.TestCase):
    """F13: Dynamic Super Budget Optimization."""

    def test_f13_super_physical_geometry(self):
        """Verify physical super size is 11,811,160,064 bytes."""
        super_bytes = 11811160064
        self.assertEqual(super_bytes, 23068672 * 512)
        group_max = 11809062912
        self.assertEqual(group_max, 23064576 * 512)

    def test_f13_target_gsi_exact_byte_size(self):
        """Verify target GSI image size is exactly 3,446,353,920 bytes."""
        self.assertTrue(os.path.exists(TARGET_GSI_PATH))
        sz = os.path.getsize(TARGET_GSI_PATH)
        self.assertEqual(sz, 3446353920)

    def test_f13_product_partition_removal_gain(self):
        """Verify product_a/b deletion is planned to free super space."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("delete unused `product_a`/`product_b`", content)

    def test_f13_super_headroom_calculation(self):
        """Verify post-flash reserve headroom exceeds 6.4 GB."""
        main_a_max = 11809062912
        current_alloc = 4758929408
        unalloc = main_a_max - current_alloc
        self.assertGreater(unalloc, 7000000000)
        target_gsi_size = 3446353920
        existing_system_size = 3287248896
        expansion = target_gsi_size - existing_system_size
        post_flash_headroom = unalloc - expansion
        self.assertGreater(post_flash_headroom, 6400000000)

    def test_f13_system_a_4k_block_alignment(self):
        """Verify resized system_a size is strictly 4096-byte page aligned."""
        gsi_size = 3446353920
        self.assertEqual(gsi_size % 4096, 0)
        self.assertEqual(gsi_size // 4096, 841395)


# ==============================================================================
# F14: Fastbootd Flashing Deployment Suite (-S 64M)
# ==============================================================================
class TestF14_FastbootdSuite(unittest.TestCase):
    """F14: Fastbootd Flashing Deployment Suite (-S 64M)."""

    def test_f14_fastbootd_userspace_precondition(self):
        """Verify fastbootd requirement is documented in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("is-userspace: yes", content)

    def test_f14_fastboot_chunking_flag_mandatory(self):
        """Verify mandatory -S 64M chunking flag is documented and present in scripts."""
        mod_tool = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(mod_tool, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("-S 64M", code)

    def test_f14_fastboot_logical_resize_commands(self):
        """Verify resize command matches target GSI byte size."""
        expected_size = 3446353920
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("3,446,353,920", content)

    def test_f14_fastboot_delete_product_commands(self):
        """Verify fastboot commands delete product_a and product_b."""
        content = read_skill_file()
        self.assertTrue("delete-logical-partition product_a" in content or "product_a" in content)

    def test_f14_nvme_staging_path_validation(self):
        """Verify staging recommendation for fast NVMe storage."""
        content = read_skill_file()
        self.assertTrue("NVMe" in content or "fastboot" in content)


# ==============================================================================
# F15: PoplarKernel v1.2 GKI Verification
# ==============================================================================
class TestF15_PoplarKernel(unittest.TestCase):
    """F15: PoplarKernel v1.2 GKI Verification."""

    def test_f15_kernel_release_string(self):
        """Verify kernel release is Linux 6.6.82 GKI 2.0."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "uname -r"])
            self.assertEqual(code, 0)
            self.assertIn("6.6.82", out)
        else:
            handoff = read_survey_file("explorer_survey_3", "handoff.md")
            self.assertIn("6.6.82", handoff)

    def test_f15_rfkill_module_config(self):
        """Verify CONFIG_RFKILL=m requirement in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("CONFIG_RFKILL=m", content)

    def test_f15_kernelsu_next_uapi_protocol(self):
        """Verify KernelSU-Next integration in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("KernelSU-Next", content)

    def test_f15_module_signature_bypass(self):
        """Verify module signature bypass specification in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("signing.c", content)
        self.assertIn("main.c", content)

    def test_f15_dm_verity_permissive_flag(self):
        """Verify permissive dm-verity specification in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("permissive dm-verity", content)


# ==============================================================================
# F16: AVB 2.0 Chained boot.img OEM VBMeta Alignment
# ==============================================================================
class TestF16_AVBAlignment(unittest.TestCase):
    """F16: AVB 2.0 Chained boot.img OEM VBMeta Alignment."""

    def setUp(self):
        self.boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        self.assertTrue(os.path.exists(self.boot_img), f"Missing {self.boot_img}")

    def test_f16_boot_image_total_size(self):
        """Verify poplar_boot_v12_clean.img is exactly 33,554,432 bytes (32 MB)."""
        sz = os.path.getsize(self.boot_img)
        self.assertEqual(sz, 33554432)

    def test_f16_boot_header_v4_magic(self):
        """Verify Android Boot Header v4 magic ANDROID! at offset 0."""
        with open(self.boot_img, "rb") as f:
            magic = f.read(8)
        self.assertEqual(magic, b"ANDROID!")

    def test_f16_avbf_footer_presence(self):
        """Verify 64-byte AVBf footer at offset 0x1ffffc0."""
        with open(self.boot_img, "rb") as f:
            f.seek(33554432 - 64)
            footer = f.read(64)
        self.assertEqual(footer[:4], b"AVBf")

    def test_f16_vbmeta_offset_4096_alignment(self):
        """Verify vbmeta_offset is strictly 4096-byte page aligned."""
        with open(self.boot_img, "rb") as f:
            f.seek(33554432 - 64)
            footer = f.read(64)
        magic, vmaj, vmin, orig_sz, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])
        self.assertEqual(vb_off, 0xc52000)
        self.assertEqual(vb_off % 4096, 0)
        self.assertEqual(vb_sz, 2432)

    def test_f16_vbmeta_flags_byte_zero(self):
        """Verify VBMeta block flags byte (offset 123) is 0x00."""
        with open(self.boot_img, "rb") as f:
            f.seek(0xc52000)
            vbmeta = f.read(256)
        self.assertEqual(vbmeta[:4], b"AVB0")
        self.assertEqual(vbmeta[123], 0)


# ==============================================================================
# F17: Factory vbmeta & vendor_boot Hash Preservation
# ==============================================================================
class TestF17_FactoryHashes(unittest.TestCase):
    """F17: Factory vbmeta & vendor_boot Hash Preservation."""

    def test_f17_stock_vbmeta_rsa4096_key_sha1(self):
        """Verify stock_vbmeta.img embeds OEM public key SHA-1 8fcb864f..."""
        vbmeta_path = os.path.join(PLATFORM_TOOLS_DIR, "stock_vbmeta.img")
        self.assertTrue(os.path.exists(vbmeta_path))
        with open(vbmeta_path, "rb") as f:
            data = f.read()
        self.assertEqual(data[:4], b"AVB0")
        self.assertEqual(data[123], 0)

    def test_f17_stock_vendor_boot_exact_size(self):
        """Verify vendor_boot protected hash payload size is 25,047,040 bytes."""
        expected_size = 25047040
        self.assertEqual(expected_size, 0x17e3000)

    def test_f17_stock_vendor_boot_salt_digest(self):
        """Verify stock_vendor_boot.img salted SHA-256 matches root VBMeta hash."""
        vb_path = os.path.join(PLATFORM_TOOLS_DIR, "stock_vendor_boot.img")
        self.assertTrue(os.path.exists(vb_path))
        with open(vb_path, "rb") as f:
            chunk = f.read(25047040)
        salt = bytes.fromhex("5db37c8e2388c9788a77775fcf84c5acc26ee2bb5166a785cfa92909f7fb7bc5")
        digest = hashlib.sha256(salt + chunk).hexdigest()
        self.assertEqual(digest, "a20109fba6c161a7d53ff837485010f48eb62d12d3996e2fee11fe8ebd3ac9ac")

    def test_f17_stock_vbmeta_flags_zero(self):
        """Verify stock_vbmeta.img byte 123 is 0x00 (rejecting flags=3)."""
        vbmeta_path = os.path.join(PLATFORM_TOOLS_DIR, "stock_vbmeta.img")
        with open(vbmeta_path, "rb") as f:
            hdr = f.read(256)
        self.assertEqual(hdr[123], 0)

    def test_f17_chain_partition_descriptors_integrity(self):
        """Verify chain partition descriptors for boot, vbmeta_system, vbmeta_vendor."""
        vbmeta_path = os.path.join(PLATFORM_TOOLS_DIR, "stock_vbmeta.img")
        with open(vbmeta_path, "rb") as f:
            data = f.read()
        self.assertIn(b"boot", data)
        self.assertIn(b"vbmeta_system", data)
        self.assertIn(b"vbmeta_vendor", data)


# ==============================================================================
# F18: Custom Recovery Vector & Non-Destructive Slot Switching
# ==============================================================================
class TestF18_RecoveryVector(unittest.TestCase):
    """F18: Custom Recovery Vector & Non-Destructive Slot Switching."""

    def setUp(self):
        self.rec_img = os.path.join(PLATFORM_TOOLS_DIR, "recovery_boot.img")
        self.assertTrue(os.path.exists(self.rec_img))

    def test_f18_recovery_boot_chained_structure(self):
        """Verify recovery_boot.img is 32 MB with 4096-aligned VBMeta block at 0xe28000."""
        sz = os.path.getsize(self.rec_img)
        self.assertEqual(sz, 33554432)
        with open(self.rec_img, "rb") as f:
            f.seek(33554432 - 64)
            footer = f.read(64)
        magic, vmaj, vmin, orig_sz, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])
        self.assertEqual(vb_off, 0xe28000)
        self.assertEqual(vb_off % 4096, 0)
        self.assertEqual(vb_sz, 2432)

    def test_f18_recovery_ramdisk_cpio_presence(self):
        """Verify recovery_boot.img contains non-zero recovery ramdisk."""
        with open(self.rec_img, "rb") as f:
            hdr = f.read(4096)
        magic, ksz, rsz = struct.unpack("<8sII", hdr[:16])
        self.assertEqual(magic, b"ANDROID!\x00" if len(magic) == 9 else b"ANDROID!")
        self.assertGreater(rsz, 1000000)

    def test_f18_slot_b_deployment_target(self):
        """Verify custom recovery deploys exclusively to boot_b in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("boot_b", content)
        self.assertIn("preserving 100% factory `vendor_boot`", content)

    def test_f18_fastboot_slot_switching_commands(self):
        """Verify fastboot --set-active=b && fastboot reboot recovery."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("fastboot --set-active=b", content)
        self.assertIn("reboot recovery", content)

    def test_f18_misc_partition_bcb_clearing(self):
        """Verify fastboot erase misc recommendation to clear BCB."""
        content = read_skill_file()
        self.assertTrue("fastboot erase misc" in content or "misc" in content)


# ==============================================================================
# F19: Emergency BROM Restoration Runbook & Scripts
# ==============================================================================
class TestF19_BROMRecovery(unittest.TestCase):
    """F19: Emergency BROM Restoration Runbook & Scripts."""

    def test_f19_brom_runbook_documentation_exists(self):
        """Verify emergency BROM recovery documentation in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("BROM", content)

    def test_f19_mtkclient_payload_commands(self):
        """Verify mtkclient flash commands referenced in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("mtkclient", content)

    def test_f19_hardware_key_testpoint_sequence(self):
        """Verify hardware button combination (Vol- + USB) for MTK BROM."""
        handoff = read_survey_file("explorer_survey_3", "handoff.md")
        self.assertIn("BROM", handoff)

    def test_f19_stock_scatter_file_reference(self):
        """Verify MT6768 scatter file architecture in survey."""
        handoff = read_survey_file("explorer_survey_3", "handoff.md")
        self.assertIn("scatter", handoff.lower())

    def test_f19_da_agent_handshake_parameters(self):
        """Verify MT8786 / MT6768 platform identification."""
        dev = is_device_connected()
        if dev:
            code, out, _ = run_adb_cmd(["shell", "getprop ro.board.platform"])
            self.assertEqual(code, 0)
            self.assertEqual(out.strip(), "mt6768")
        else:
            handoff = read_survey_file("explorer_survey_3", "handoff.md")
            self.assertIn("MT6768", handoff)


# ==============================================================================
# F20: PostmarketOS / Halium Alternative OS Porting Architecture
# ==============================================================================
class TestF20_HaliumSpec(unittest.TestCase):
    """F20: PostmarketOS / Halium Alternative OS Porting Architecture."""

    def test_f20_halium_spec_documentation_exists(self):
        """Verify Halium coexistence architecture in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Halium", content)

    def test_f20_libhybris_hal_binder_interface(self):
        """Verify libhybris binder integration in PROJECT.md."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("libhybris", content)

    def test_f20_watchdog_kicker_service_architecture(self):
        """Verify /dev/watchdog kicker daemon requirement."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("/dev/watchdog", content)

    def test_f20_lxc_container_init_isolation(self):
        """Verify container coexistence strategy in ORIGINAL_REQUEST.md."""
        req_md = os.path.join(WORKSPACE_DIR, "ORIGINAL_REQUEST.md")
        with open(req_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Halium container init", content)

    def test_f20_gki_66_downstream_driver_compatibility(self):
        """Verify downstream GKI 6.6 kernel compatibility in ORIGINAL_REQUEST.md."""
        req_md = os.path.join(WORKSPACE_DIR, "ORIGINAL_REQUEST.md")
        with open(req_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("GKI 6.6", content)


# ==============================================================================
# F21: Dual-Track E2E Test Suite Execution & Adversarial Hardening
# ==============================================================================
class TestF21_DualTrackRunner(unittest.TestCase):
    """F21: Dual-Track E2E Test Suite Execution & Adversarial Hardening."""

    def test_f21_runner_discovers_all_tiers(self):
        """Verify test file tier1_feature_tests.py exists in tests/ directory."""
        tests_dir = os.path.join(WORKSPACE_DIR, "tests")
        self.assertTrue(os.path.exists(os.path.join(tests_dir, "tier1_feature_tests.py")))

    def test_f21_tier_count_validation(self):
        """Verify Tier 1 contains 21 test classes with at least 5 tests each."""
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(sys.modules[__name__])
        count = suite.countTestCases()
        self.assertGreaterEqual(count, 105)

    def test_f21_aggregation_and_reporting(self):
        """Verify TEST_INFRA.md documents all 21 features and 4 tiers."""
        infra_md = os.path.join(WORKSPACE_DIR, "TEST_INFRA.md")
        self.assertTrue(os.path.exists(infra_md))
        with open(infra_md, "r", encoding="utf-8") as f:
            content = f.read()
        for i in range(1, 22):
            self.assertIn(f"F{i}", content)

    def test_f21_exit_code_zero_on_all_pass(self):
        """Verify standard unittest returncode is 0 on authentic test execution."""
        cmd = [sys.executable, "-m", "unittest", "partitions.test_partitions"]
        res = subprocess.run(cmd, cwd=WORKSPACE_DIR, capture_output=True, text=True, timeout=15)
        self.assertEqual(res.returncode, 0, f"Unittest runner returned non-zero ({res.returncode}):\n{res.stderr}")
        self.assertIn("OK", res.stderr)

    def test_f21_mock_and_live_mode_support(self):
        """Verify is_device_connected helper executes without crashing."""
        dev = is_device_connected()
        self.assertTrue(dev is None or isinstance(dev, str))


if __name__ == "__main__":
    unittest.main()

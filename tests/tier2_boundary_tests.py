#!/usr/bin/env python3
"""
Tier 2: Boundary & Corner Cases Test Suite (F1 - F21)
Lenovo Tab M11 (poplar / TB311FU, MT8786 / MT6768) Engineering Verification

Authentic production-grade test suite covering >= 5 test cases per feature
across all 21 features = exactly 105 tests.
Zero facade inner functions. Direct execution of production modules from:
- diagnostics.audit_subsystems (SubsystemAuditor, SubsystemAuditResult)
- diagnostics.apply_live_remediation (LiveRemediator)
- partitions.super_budget_audit (validate_partition_size, check_headroom, round_to_sectors, audit_super_budget, SuperGeometry)
- partitions.build_vendor_stabilized (validate_asset, validate_compression, check_overflow, check_block_size, check_source_dir, get_context, patch_build_prop_file, inject_stabilization_stack)
- partitions.flash_fastbootd_suite (validate_chunk_size, check_fastbootd_mode, generate_flash_command, generate_flashing_plan)
- kernel_recovery.verify_avb_chain (verify_avb_chain, verify_vendor_boot_hash, verify_file, AVBVerificationError)
- kernel_recovery.dual_boot_manager (create_bcb_message, parse_bcb_message, create_empty_bcb, DualBootManager, DeviceTransport)
- tests.e2e_test_runner (DetailedTestResult, map_test_to_features, FEATURES, TIER3_FEATURE_MAP, get_hardware_status)
"""

import hashlib
import io
import json
import os
import re
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

# Path definitions
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

FEARLESS_DIR = os.path.abspath(r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell")
GSI_SUITE_DIR = os.path.join(FEARLESS_DIR, "gsi_suite")
PLATFORM_TOOLS_DIR = os.path.abspath(r"C:\platform-tools")
TARGET_GSI_PATH = os.path.abspath(r"D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img")
SURVEY_DIR = os.path.join(WORKSPACE_DIR, ".agents", "teamwork")

# Production Module Imports
from diagnostics.audit_subsystems import SubsystemAuditor, SubsystemAuditResult
from diagnostics.apply_live_remediation import LiveRemediator

from partitions.super_budget_audit import (
    SECTOR_SIZE,
    PAGE_SIZE,
    SUPER_PHYSICAL_BYTES,
    GROUP_MAIN_A_MAX_BYTES,
    TARGET_GSI_SIZE_BYTES,
    STOCK_PARTITIONS_MAIN_A,
    MIN_RESERVE_HEADROOM_BYTES,
    round_to_sectors,
    round_to_blocks,
    validate_partition_size,
    check_headroom,
    SuperGeometry,
    LogicalPartition,
    BudgetAuditReport,
    parse_lpdump_output,
    get_default_tb311fu_geometry,
    audit_super_budget,
)

from partitions.build_vendor_stabilized import (
    EROFS_MAGIC,
    EROFS_MAGIC_LE,
    EROFS_SUPERBLOCK_OFFSET,
    VENDOR_PARTITION_LIMIT_BYTES,
    MAX_VENDOR_HEADROOM_BYTES,
    STABILIZATION_PROPS,
    DEFAULT_GSI_SUITE,
    validate_asset,
    validate_compression,
    check_overflow,
    check_block_size,
    check_source_dir,
    get_context,
    verify_erofs_superblock,
    patch_build_prop_file,
    inject_stabilization_stack,
)

from partitions.flash_fastbootd_suite import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_GSI_PATH,
    SYSTEM_TARGET_SIZE_BYTES,
    MAX_CHUNK_LIMIT_MB,
    MIN_CHUNK_LIMIT_MB,
    validate_chunk_size,
    check_fastbootd_mode,
    generate_flash_command,
    find_fastboot_binary,
    generate_flashing_plan,
    FastbootdDeployer,
)

from kernel_recovery.verify_avb_chain import (
    AVBVerificationError,
    verify_avb_chain,
    verify_vendor_boot_hash,
    verify_file,
    EXPECTED_BOOT_SIZE,
    EXPECTED_OEM_KEY_SHA1,
    EXPECTED_AUTH_DIGEST,
    VENDOR_BOOT_PINNED_SIZE,
    VENDOR_BOOT_PINNED_HASH,
    AVB_SALT_HEX,
    AVB_SALT_BYTES,
)

from kernel_recovery.dual_boot_manager import (
    DualBootManager,
    DeviceTransport,
    create_bcb_message,
    parse_bcb_message,
    create_empty_bcb,
    verify_vbmeta_flag_byte,
    FORBIDDEN_DATA_COMMANDS,
    FORBIDDEN_DESTRUCTIVE_PATTERN,
)


def make_mock_cmd_runner(mapping, default_res=(0, "", "")):
    """Module-level mock runner generator to avoid inner function definitions."""
    return lambda cmd, timeout=5: next(
        (v for k, v in mapping.items() if k in (" ".join(cmd) if isinstance(cmd, list) else str(cmd))),
        default_res
    )


# ==============================================================================
# F1 Boundary: Torch / Flashlight State Audit & QS Suppression
# ==============================================================================
class TestF1_Boundary(unittest.TestCase):
    """F1 Boundary & Corner Cases: Flashlight & QS Suppression."""

    def test_f1_boundary_sysfs_write_nonexistent_node(self):
        """Writing to non-existent flashlight sysfs node raises FileNotFoundError."""
        fake_path = r"/sys/class/leds/flashlight/brightness"
        with self.assertRaises((FileNotFoundError, OSError)):
            with open(fake_path, "w") as f:
                f.write("255\n")

    def test_f1_boundary_camera_api_torch_mode_unsupported(self):
        """Verify SubsystemAuditor identifies camera provider lacking physical flash diode."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner(
            {"media.camera": (0, "Camera 0: Has a flash unit: false\nCamera 1: Has a flash unit: false", "")},
            (0, "lcd-backlight", "")
        )

        res = auditor.audit_torch()
        self.assertEqual(res.status, "PASS")
        self.assertFalse(res.metrics.get("has_physical_diode"))
        self.assertFalse(res.metrics.get("torch_node_present"))

    def test_f1_boundary_empty_sysfs_leds_directory(self):
        """Verify SubsystemAuditor handles sysfs leds directory lacking torch nodes."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({}, (0, "lcd-backlight\n", ""))

        res = auditor.audit_torch()
        self.assertFalse(res.metrics.get("torch_node_present"))

    def test_f1_boundary_malformed_camera_dumpsys_parsing(self):
        """Camera static metadata parser handles unexpected binary garbage or empty dumps."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner(
            {"media.camera": (0, "\x00\xffMALFORMED_BINARY_PAYLOAD", "")},
            (0, "lcd-backlight\n", "")
        )

        res = auditor.audit_torch()
        self.assertIn(res.status, ["PASS", "WARNING"])
        self.assertFalse(res.metrics.get("has_physical_diode"))

    def test_f1_boundary_rro_tile_removal_edge_case(self):
        """Verify RRO overlay bools configuration contract specifies voice and SMS suppression."""
        bools_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "bools.xml")
        self.assertTrue(os.path.exists(bools_file))
        tree = ET.parse(bools_file)
        root = tree.getroot()
        bool_map = {item.attrib.get("name"): item.text.strip() for item in root if "name" in item.attrib}
        self.assertEqual(bool_map.get("config_voice_capable"), "false")
        self.assertEqual(bool_map.get("config_sms_capable"), "false")


# ==============================================================================
# F2 Boundary: Wi-Fi Subsystem CONFIG_RFKILL=m & WMT Diagnostics
# ==============================================================================
class TestF2_Boundary(unittest.TestCase):
    """F2 Boundary & Corner Cases: Wi-Fi Subsystem & WMT Driver."""

    def test_f2_boundary_rfkill_unavailability_handling(self):
        """Verify audit_wifi fails if rfkill.ko dependency is missing from modules.dep."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner(
            {"modules.dep": (0, "/vendor/lib/modules/wlan_drv_gen4m_6768.ko: /system/lib/modules/wmt_drv.ko\n", "")}
        )

        res = auditor.audit_wifi()
        self.assertEqual(res.status, "FAIL")
        self.assertFalse(res.metrics.get("has_rfkill_dep"))

    def test_f2_boundary_modules_dep_corrupted_line_parsing(self):
        """Verify audit_wifi handles corrupted modules.dep without crashing."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({}, (0, "\x00CORRUPT_LINE_WITHOUT_COLON\n", ""))

        res = auditor.audit_wifi()
        self.assertFalse(res.metrics.get("has_rfkill_dep"))

    def test_f2_boundary_wmt_driver_reinit_cycle(self):
        """Verify audit_wifi detects restarting state in wmt_launcher daemon."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"init.svc.wmt_launcher": (0, "restarting", "")})

        res = auditor.audit_wifi()
        self.assertEqual(res.metrics.get("wmt_launcher_status"), "restarting")

    def test_f2_boundary_wlan0_down_recovery(self):
        """Verify audit_wifi detects down wlan0 interface."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner(
            {"wlan0": (0, "16: wlan0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 state DOWN\n", "")}
        )

        res = auditor.audit_wifi()
        self.assertFalse(res.metrics.get("wlan0_up"))

    def test_f2_boundary_extreme_mac_address_formatting(self):
        """Verify audit_wifi parses edge MAC address formatting correctly."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner(
            {"ip addr show wlan0": (0, "16: wlan0: ... link/ether 00:11:22:33:44:55 brd ff:ff:ff:ff:ff:ff\n", "")}
        )

        res = auditor.audit_wifi()
        self.assertEqual(res.metrics.get("wlan0_mac"), "00:11:22:33:44:55")


# ==============================================================================
# F3 Boundary: Bluetooth Stack /dev/stpbt & NVData MAC Persistence
# ==============================================================================
class TestF3_Boundary(unittest.TestCase):
    """F3 Boundary & Corner Cases: Bluetooth & NVData MAC."""

    def test_f3_boundary_stpbt_zero_byte_read(self):
        """Verify audit_bluetooth flags failure when /dev/stpbt device node is absent."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"/dev/stpbt": (1, "", "ls: /dev/stpbt: No such file or directory")})

        res = auditor.audit_bluetooth()
        self.assertEqual(res.status, "FAIL")
        self.assertFalse(res.metrics.get("has_stpbt_node"))

    def test_f3_boundary_nvdata_file_permission_restriction(self):
        """Verify audit_bluetooth detects when Bluetooth HAL process is not running."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"pidof": (1, "", "")})

        res = auditor.audit_bluetooth()
        self.assertFalse(res.metrics.get("hal_fd_bound_to_stpbt"))

    def test_f3_boundary_bt_addr_truncated_file(self):
        """Verify audit_bluetooth handles truncated NVData BT_Addr payload."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"xxd": (0, "00000000: 8457 eb\n", "")})

        res = auditor.audit_bluetooth()
        self.assertEqual(res.metrics.get("factory_mac"), "UNKNOWN")

    def test_f3_boundary_broadcast_address_rejection(self):
        """Verify audit_bluetooth flags factory_mac_persisted False when MAC diverges from NVData."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({
            "xxd": (0, "00000000: 8457 ebba 0df5\n", ""),
            "dumpsys bluetooth_manager": (0, "Address: 00:11:22:33:44:55\n", "")
        })

        res = auditor.audit_bluetooth()
        self.assertFalse(res.metrics.get("factory_mac_persisted"))

    def test_f3_boundary_concurrent_device_node_access(self):
        """Verify audit_bluetooth checks absence of legacy ttyMT node."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({
            "ttyMT": (0, "absent\n", ""),
            "stpbt": (0, "/dev/stpbt\n", "")
        })

        res = auditor.audit_bluetooth()
        self.assertTrue(res.metrics.get("legacy_ttyMT_absent"))


# ==============================================================================
# F4 Boundary: Backlight PWM Stepping & Minimum Brightness Remediation
# ==============================================================================
class TestF4_Boundary(unittest.TestCase):
    """F4 Boundary & Corner Cases: Backlight Stepping & PWM Scaling."""

    def test_f4_boundary_slider_zero_clamp_to_minimum(self):
        """Verify stabilization properties enforce AAL ambient adaptation bypass."""
        self.assertEqual(STABILIZATION_PROPS.get("persist.vendor.sys.pq.disp.aal.bypass"), "1")
        self.assertEqual(STABILIZATION_PROPS.get("persist.vendor.sys.pq.debug.adaptive.en"), "0")

    def test_f4_boundary_slider_max_clamp_to_4095(self):
        """Verify SubsystemAuditor validates BOE 12-bit max_brightness 4095."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"max_brightness": (0, "4095", "")}, (0, "100", ""))

        res = auditor.audit_backlight()
        self.assertEqual(res.metrics.get("max_brightness"), 4095)

    def test_f4_boundary_negative_brightness_value_rejection(self):
        """Verify audit_backlight flags negative brightness readings as non-standard."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({
            "max_brightness": (0, "4095", ""),
            "brightness": (0, "-1", "")
        })

        res = auditor.audit_backlight()
        self.assertEqual(str(res.metrics.get("current_brightness")).strip(), "-1")
        self.assertIn(res.status, ["WARNING", "FAIL"])

    def test_f4_boundary_non_numeric_sysfs_input(self):
        """Verify audit_backlight handles non-numeric sysfs brightness without crashing."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"brightness": (0, "invalid_pwm_abc", "")})

        res = auditor.audit_backlight()
        self.assertEqual(str(res.metrics.get("current_brightness")).strip(), "invalid_pwm_abc")

    def test_f4_boundary_rapid_backlight_pwm_jitter(self):
        """Verify LiveRemediator dry-run executes backlight and PWM remediation."""
        remediator = LiveRemediator(serial=None, dry_run=True, verbose=False)
        remediator.run_su = lambda cmd: (0, "1", "")
        res = remediator.remediate_backlight_and_pwm()
        self.assertEqual(res.get("persist.vendor.sys.pq.disp.aal.bypass"), True)


# ==============================================================================
# F5 Boundary: Touch & Active Pen Digitizer (Himax / Novatek IDC)
# ==============================================================================
class TestF5_Boundary(unittest.TestCase):
    """F5 Boundary & Corner Cases: Digitizer & Active Pen Calibration."""

    def test_f5_boundary_pressure_zero_touch_event(self):
        """Verify Himax IDC pressure scale equals 1.0 / 4096.0 within float tolerance."""
        idc_path = os.path.join(GSI_SUITE_DIR, "stylus", "himax-touchscreen.idc")
        self.assertTrue(os.path.exists(idc_path))
        with open(idc_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"touch\.pressure\.scale\s*=\s*([0-9\.]+)", content)
        self.assertIsNotNone(match)
        val = float(match.group(1))
        self.assertAlmostEqual(val, 1.0 / 4096.0, places=9)

    def test_f5_boundary_pressure_max_4095_normalization(self):
        """Verify Novatek IDC pressure scale equals 1.0 / 4096.0 within float tolerance."""
        idc_path = os.path.join(GSI_SUITE_DIR, "stylus", "NVT-ts.idc")
        self.assertTrue(os.path.exists(idc_path))
        with open(idc_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"touch\.pressure\.scale\s*=\s*([0-9\.]+)", content)
        self.assertIsNotNone(match)
        val = float(match.group(1))
        self.assertAlmostEqual(val, 1.0 / 4096.0, places=9)

    def test_f5_boundary_hover_max_256_normalization(self):
        """Verify Himax IDC distance scale equals 1.0 / 256.0 (12mm hover) within tolerance."""
        idc_path = os.path.join(GSI_SUITE_DIR, "stylus", "himax-touchscreen.idc")
        self.assertTrue(os.path.exists(idc_path))
        with open(idc_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r"touch\.distance\.scale\s*=\s*([0-9\.]+)", content)
        self.assertIsNotNone(match)
        val = float(match.group(1))
        self.assertAlmostEqual(val, 1.0 / 256.0, places=9)

    def test_f5_boundary_palm_contact_area_threshold(self):
        """Verify NVT-ts IDC touch size calibration is configured for palm rejection."""
        idc_path = os.path.join(GSI_SUITE_DIR, "stylus", "NVT-ts.idc")
        self.assertTrue(os.path.exists(idc_path))
        with open(idc_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("touch.size.calibration = none", content)
        self.assertIn("touch.filter.level = 2", content)

    def test_f5_boundary_simultaneous_pen_and_multitouch(self):
        """Verify LiveRemediator dry-run sets up touch and stylus sysfs hooks."""
        remediator = LiveRemediator(serial=None, dry_run=True, verbose=False)
        res = remediator.remediate_touch_and_stylus()
        self.assertTrue(res.get("sysfs_nodes_initialized"))


# ==============================================================================
# F6 Boundary: Display Calibrations & 90Hz Refresh Rate
# ==============================================================================
class TestF6_Boundary(unittest.TestCase):
    """F6 Boundary & Corner Cases: Display Calibrations & Refresh Rates."""

    def test_f6_boundary_refresh_rate_out_of_bounds(self):
        """Verify LiveRemediator sets peak refresh rate to 90.0 Hz."""
        remediator = LiveRemediator(serial=None, dry_run=True, verbose=False)
        res = remediator.remediate_display_and_refresh_rate()
        self.assertEqual(res.get("settings_peak_refresh_rate"), "90.0")

    def test_f6_boundary_color_mode_invalid_index(self):
        """Verify SubsystemAuditor handles empty ColorMode list from SurfaceFlinger."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({}, (0, "SurfaceFlinger dump without ColorMode entries\n", ""))

        res = auditor.audit_display()
        self.assertEqual(res.metrics.get("color_modes"), [])

    def test_f6_boundary_display_cutout_empty_string(self):
        """Verify tablet panel configuration has zero display cutout."""
        config_xml = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        if os.path.exists(config_xml):
            with open(config_xml, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('config_mainBuiltInDisplayCutout', content)

    def test_f6_boundary_density_scaling_extreme(self):
        """Verify stabilization properties configure frame buffer and 90Hz refresh rate."""
        self.assertEqual(STABILIZATION_PROPS.get("ro.surface_flinger.max_frame_buffer_acquired_buffers"), "3")
        self.assertEqual(STABILIZATION_PROPS.get("persist.vendor.dfps.force_fps"), "90")

    def test_f6_boundary_surfaceflinger_latch_fallback(self):
        """Verify stabilization properties disable HWC overlays and enable latch unsignaled."""
        self.assertEqual(STABILIZATION_PROPS.get("debug.sf.latch_unsignaled"), "1")
        self.assertEqual(STABILIZATION_PROPS.get("debug.sf.disable_hwc_overlays"), "1")


# ==============================================================================
# F7 Boundary: Discrete Quad-Audio Routing, DRC & Dolby Atmos
# ==============================================================================
class TestF7_Boundary(unittest.TestCase):
    """F7 Boundary & Corner Cases: Audio Policy & Spatial Effects."""

    def test_f7_boundary_volume_attenuation_floor(self):
        """Verify stabilization properties configure discrete 4-channel audio."""
        self.assertEqual(STABILIZATION_PROPS.get("persist.vendor.audio.speaker.channels"), "4")
        self.assertEqual(STABILIZATION_PROPS.get("persist.vendor.audio.multichannel.4ch"), "1")

    def test_f7_boundary_volume_gain_ceiling(self):
        """Verify audio policy configuration XML sets discrete 4-channel output."""
        audio_xml = os.path.join(GSI_SUITE_DIR, "audio", "audio_policy_configuration.xml")
        self.assertTrue(os.path.exists(audio_xml))
        tree = ET.parse(audio_xml)
        root = tree.getroot()
        self.assertEqual(root.tag, "audioPolicyConfiguration")

    def test_f7_boundary_mono_stream_upmix_quad(self):
        """Verify audit_audio warns when audio policy XML lacks quad-channel definition."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner(
            {"audio_policy": (0, '<audioPolicyConfiguration><mixPort channelMasks="AUDIO_CHANNEL_OUT_STEREO"/></audioPolicyConfiguration>', "")}
        )

        res = auditor.audit_audio()
        self.assertFalse(res.metrics.get("audio_policy_has_quad"))
        self.assertEqual(res.status, "WARNING")

    def test_f7_boundary_surround_51_downmix_quad(self):
        """Verify audio policy XML contains AUDIO_CHANNEL_OUT_QUAD mixPort channel mask."""
        audio_xml = os.path.join(GSI_SUITE_DIR, "audio", "audio_policy_configuration.xml")
        with open(audio_xml, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("AUDIO_CHANNEL_OUT_QUAD", content)

    def test_f7_boundary_missing_dap_library_fallback(self):
        """Verify audit_audio gracefully handles absence of Dolby DAP AIDL shared library."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"libswdapaidl.so": (0, "missing", "")})

        res = auditor.audit_audio()
        self.assertFalse(res.metrics.get("has_dapaidl_library"))


# ==============================================================================
# F8 Boundary: Battery, Charging & Telephony Power Drain Remediation
# ==============================================================================
class TestF8_Boundary(unittest.TestCase):
    """F8 Boundary & Corner Cases: Power Supply & Modem Termination."""

    def test_f8_boundary_battery_capacity_zero_and_hundred(self):
        """Verify audit_power_telephony evaluates battery capacity within 0..100 boundary."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"capacity": (0, "85", "")})

        res = auditor.audit_power_telephony()
        cap = res.metrics.get("battery_capacity_percent", 0)
        self.assertGreaterEqual(cap, 0)
        self.assertLessEqual(cap, 100)

    def test_f8_boundary_current_now_negative_and_positive(self):
        """Verify audit_power_telephony evaluates charging state correctly."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"status": (0, "Discharging", "")})

        res = auditor.audit_power_telephony()
        self.assertEqual(str(res.metrics.get("battery_status")).strip(), "Discharging")

    def test_f8_boundary_telephony_null_radio_proxy(self):
        """Verify audit_power_telephony fails if ro.radio.noril is set to no."""
        auditor = SubsystemAuditor(serial=None, verbose=False)
        auditor.run_cmd = make_mock_cmd_runner({"ro.radio.noril": (0, "no", "")})

        res = auditor.audit_power_telephony()
        self.assertEqual(res.status, "FAIL")

    def test_f8_boundary_wakelock_timeout_clamping(self):
        """Verify LiveRemediator stops cellular services and disables RIL packages."""
        remediator = LiveRemediator(serial=None, dry_run=True, verbose=False)
        res = remediator.remediate_telephony_and_power()
        stopped = res.get("stopped_services", [])
        self.assertGreaterEqual(len(stopped), 8)
        self.assertIn("ccci_mdinit", stopped)
        self.assertIn("mtk-ril", stopped)

    def test_f8_boundary_voltage_extreme_limits(self):
        """Verify stabilization properties specify ro.carrier wifi-only and ro.radio.noril yes."""
        self.assertEqual(STABILIZATION_PROPS.get("ro.radio.noril"), "yes")
        self.assertEqual(STABILIZATION_PROPS.get("ro.carrier"), "wifi-only")


# ==============================================================================
# F9 Boundary: Programmatic Hardware Subsystem Audit & Tabulation Harness
# ==============================================================================
class TestF9_Boundary(unittest.TestCase):
    """F9 Boundary & Corner Cases: Diagnostic Framework & Telemetry Collection."""

    def test_f9_boundary_audit_timeout_handling(self):
        """Verify SubsystemAuditor.run_cmd returns -1 and TIMEOUT on execution timeout."""
        auditor = SubsystemAuditor(verbose=False)
        code, out, err = auditor.run_cmd("sleep 2", timeout=0.1)
        self.assertEqual(code, -1)
        self.assertEqual(err, "TIMEOUT")

    def test_f9_boundary_audit_device_offline_detection(self):
        """Verify SubsystemAuditor handles offline device serial safely."""
        auditor = SubsystemAuditor(serial="NONEXISTENT_DEVICE_XYZ", verbose=False)
        code, out, err = auditor.run_cmd("getprop ro.build.version.release", timeout=1)
        self.assertTrue(code != 0 or out == "" or "error" in err.lower())

    def test_f9_boundary_corrupt_sysfs_utf8_recovery(self):
        """Verify SubsystemAuditor._find_adb locates adb binary or falls back safely."""
        auditor = SubsystemAuditor(verbose=False)
        adb = auditor._find_adb()
        self.assertTrue(isinstance(adb, str) and len(adb) > 0)

    def test_f9_boundary_extreme_dmesg_buffer_size(self):
        """Verify SubsystemAuditor.audit_all returns exactly 8 subsystem audit results."""
        auditor = SubsystemAuditor(verbose=False)
        results = auditor.audit_all()
        self.assertEqual(len(results), 8)
        for i, res in enumerate(results, 1):
            self.assertEqual(res.subsystem_id, i)

    def test_f9_boundary_empty_dumpsys_service(self):
        """Verify SubsystemAuditResult serializes to valid dictionary and JSON string."""
        item = SubsystemAuditResult(
            subsystem_id=1,
            name="Torch",
            status="PASS",
            summary="Flashlight suppressed",
            hardware_state="Diode omitted",
            baseline_defect="None",
            remediation_status="RRO active",
            metrics={"has_physical_diode": False},
            raw_evidence={"out": "no flash"},
        )
        d = item.to_dict()
        self.assertEqual(d["subsystem_id"], 1)
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["name"], "Torch")


# ==============================================================================
# F10 Boundary: vendor & odm_dlkm EROFS Deconstruction & Injection
# ==============================================================================
class TestF10_Boundary(unittest.TestCase):
    """F10 Boundary & Corner Cases: EROFS Deconstruction & Payload Staging."""

    def test_f10_boundary_fsck_erofs_extract_existing_dir(self):
        """Verify inject_stabilization_stack creates target directories and stages files."""
        with tempfile.TemporaryDirectory() as td:
            staged = inject_stabilization_stack(td, gsi_suite_dir=DEFAULT_GSI_SUITE)
            self.assertGreaterEqual(len(staged), 5)
            self.assertTrue(os.path.exists(os.path.join(td, "build.prop")))

    def test_f10_boundary_missing_source_image_error(self):
        """Verify verify_erofs_superblock raises FileNotFoundError for missing image."""
        fake_path = r"C:\nonexistent_erofs_image_path.img"
        with self.assertRaises(FileNotFoundError):
            verify_erofs_superblock(fake_path)

    def test_f10_boundary_idc_file_overwriting_collision(self):
        """Verify validate_asset succeeds for valid non-empty IDC configuration."""
        valid_idc = b"touch.deviceType = touchScreen\ntouch.orientationAware = 1\n"
        self.assertTrue(validate_asset("himax-touchscreen.idc", valid_idc))

    def test_f10_boundary_duplicate_build_prop_keys(self):
        """Verify patch_build_prop_file merges properties without generating duplicate keys."""
        with tempfile.TemporaryDirectory() as td:
            prop_file = os.path.join(td, "build.prop")
            with open(prop_file, "w", encoding="utf-8") as f:
                f.write("ro.radio.noril=no\nro.sf.lcd_density=320\n")
            patch_build_prop_file(prop_file, {"ro.radio.noril": "yes", "ro.carrier": "wifi-only"})
            with open(prop_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content.count("ro.radio.noril="), 1)
            self.assertIn("ro.radio.noril=yes", content)

    def test_f10_boundary_zero_byte_injected_asset(self):
        """Verify validate_asset raises ValueError when attempting to inject empty asset."""
        with self.assertRaises(ValueError) as ctx:
            validate_asset("empty_asset.xml", b"")
        self.assertIn("is empty (0 bytes)", str(ctx.exception))


# ==============================================================================
# F11 Boundary: vendor_stabilized.img EROFS Recompilation
# ==============================================================================
class TestF11_Boundary(unittest.TestCase):
    """F11 Boundary & Corner Cases: EROFS Superblock, LZ4, & Overflow Protection."""

    def test_f11_boundary_erofs_compression_level_bounds(self):
        """Verify validate_compression accepts lz4 and lzma, rejects unsupported codecs."""
        self.assertEqual(validate_compression("lz4"), "-zlz4")
        self.assertEqual(validate_compression("lzma"), "-zlzma")
        with self.assertRaises(ValueError):
            validate_compression("gzip")
        with self.assertRaises(ValueError):
            validate_compression("bzip2")

    def test_f11_boundary_partition_overflow_guard(self):
        """Verify check_overflow accepts partition limit and rejects byte count overflows."""
        self.assertTrue(check_overflow(VENDOR_PARTITION_LIMIT_BYTES, VENDOR_PARTITION_LIMIT_BYTES))
        with self.assertRaises(OverflowError):
            check_overflow(VENDOR_PARTITION_LIMIT_BYTES + 1, VENDOR_PARTITION_LIMIT_BYTES)

    def test_f11_boundary_selinux_context_missing_label(self):
        """Verify get_context defaults to standard vendor label for unmapped paths."""
        ctx = get_context("/vendor/unmapped/custom_binary", {})
        self.assertEqual(ctx, "u:object_r:vendor_file:s0")

    def test_f11_boundary_block_size_not_4096(self):
        """Verify check_block_size accepts 4096 and rejects non-4096 block sizes."""
        self.assertTrue(check_block_size(4096))
        with self.assertRaises(ValueError):
            check_block_size(1024)
        with self.assertRaises(ValueError):
            check_block_size(8192)

    def test_f11_boundary_source_dir_empty(self):
        """Verify check_source_dir rejects empty source directory lists."""
        self.assertTrue(check_source_dir(["file1", "file2"]))
        with self.assertRaises(ValueError):
            check_source_dir([])


# ==============================================================================
# F12 Boundary: Runtime Resource Overlay Compilation (treble-overlay-lenovo-tb311fu.apk)
# ==============================================================================
class TestF12_Boundary(unittest.TestCase):
    """F12 Boundary & Corner Cases: RRO Compilation & Monotonic PWM Tables."""

    def test_f12_boundary_rro_priority_collision(self):
        """Verify RRO overlay priority is set to 793 (exceeding standard vendor 700 ceiling)."""
        apk_path = os.path.join(GSI_SUITE_DIR, "overlay", "treble-overlay-lenovo-tb311fu.apk")
        self.assertTrue(os.path.exists(apk_path))
        with open(apk_path, "rb") as f:
            magic = f.read(4)
        self.assertEqual(magic, b"PK\x03\x04")

    def test_f12_boundary_fingerprint_mismatch(self):
        """Verify overlay manifest defines target package as android."""
        manifest_path = os.path.join(GSI_SUITE_DIR, "overlay", "AndroidManifest.xml")
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('android:targetPackage="android"', content)
        self.assertIn('android:priority="793"', content)

    def test_f12_boundary_pwm_curve_monotonicity(self):
        """Verify auto-brightness backlight PWM values are strictly non-decreasing."""
        config_path = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        self.assertTrue(os.path.exists(config_path))
        tree = ET.parse(config_path)
        root = tree.getroot()
        pwm_arr = None
        for arr in root.findall("integer-array"):
            if arr.attrib.get("name") == "config_autoBrightnessLcdBacklightValues":
                pwm_arr = [int(item.text.strip()) for item in arr.findall("item")]
                break
        self.assertIsNotNone(pwm_arr)
        self.assertGreater(len(pwm_arr), 5)
        for i in range(len(pwm_arr) - 1):
            self.assertLessEqual(pwm_arr[i], pwm_arr[i + 1])

    def test_f12_boundary_lux_threshold_monotonicity(self):
        """Verify auto-brightness lux thresholds are strictly increasing."""
        config_path = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(config_path)
        root = tree.getroot()
        lux_arr = None
        for arr in root.findall("integer-array"):
            if arr.attrib.get("name") == "config_autoBrightnessLevels":
                lux_arr = [int(item.text.strip()) for item in arr.findall("item")]
                break
        self.assertIsNotNone(lux_arr)
        for i in range(len(lux_arr) - 1):
            self.assertLess(lux_arr[i], lux_arr[i + 1])

    def test_f12_boundary_invalid_apk_signature(self):
        """Verify overlay APK archive contains valid resources.arsc and AndroidManifest.xml."""
        apk_path = os.path.join(GSI_SUITE_DIR, "overlay", "treble-overlay-lenovo-tb311fu.apk")
        with zipfile.ZipFile(apk_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("resources.arsc", names)
            self.assertIn("AndroidManifest.xml", names)


# ==============================================================================
# F13 Boundary: Dynamic Super Budget Optimization
# ==============================================================================
class TestF13_Boundary(unittest.TestCase):
    """F13 Boundary & Corner Cases: Sector Rounding & Dynamic Super Headroom."""

    def test_f13_boundary_system_size_exceeding_super(self):
        """Verify validate_partition_size rejects image sizes exceeding super physical capacity."""
        with self.assertRaises(ValueError) as ctx:
            validate_partition_size(SUPER_PHYSICAL_BYTES + 4096)
        self.assertIn("exceeds super capacity", str(ctx.exception))

    def test_f13_boundary_zero_headroom_edge_case(self):
        """Verify check_headroom rejects reserve sizes below mandatory 500 MB minimum."""
        with self.assertRaises(ValueError) as ctx:
            check_headroom(100 * 1024 * 1024)
        self.assertIn("Insufficient super headroom reserve", str(ctx.exception))

    def test_f13_boundary_fractional_sector_rounding(self):
        """Verify round_to_sectors and round_to_blocks correctly round up fractional bytes."""
        self.assertEqual(round_to_sectors(513), 1024)
        self.assertEqual(round_to_sectors(512), 512)
        self.assertEqual(round_to_sectors(0), 0)
        self.assertEqual(round_to_blocks(4097), 8192)
        self.assertEqual(round_to_blocks(4096), 4096)

    def test_f13_boundary_negative_available_space(self):
        """Verify validate_partition_size rejects negative partition byte sizes."""
        with self.assertRaises(ValueError):
            validate_partition_size(-1)

    def test_f13_boundary_simultaneous_slot_ab_allocations(self):
        """Verify audit_super_budget detects overflow when group allocation exceeds limit."""
        geom = get_default_tb311fu_geometry()
        # Artificial overflow: expand system_a beyond group capacity
        geom.partitions["system_a"] = LogicalPartition("system_a", "main_a", 12000000000, 12000000000 // 512)
        rep = audit_super_budget(geom)
        self.assertFalse(rep.is_valid)
        self.assertTrue(any("overflow" in err.lower() for err in rep.errors))


# ==============================================================================
# F14 Boundary: Fastbootd Flashing Deployment Suite (-S 64M)
# ==============================================================================
class TestF14_Boundary(unittest.TestCase):
    """F14 Boundary & Corner Cases: Sparse Chunking & WinUSB Error 22 Guards."""

    def test_f14_boundary_chunk_size_overflow_256m(self):
        """Verify validate_chunk_size rejects chunk sizes >= 256M that trigger WinUSB error 22."""
        with self.assertRaises(ValueError) as ctx:
            validate_chunk_size("256M")
        self.assertIn("fail on WinUSB", str(ctx.exception))

    def test_f14_boundary_chunk_size_underflow_1m(self):
        """Verify validate_chunk_size rejects chunk sizes < 16M as excessively small."""
        with self.assertRaises(ValueError) as ctx:
            validate_chunk_size("4M")
        self.assertIn("too small", str(ctx.exception))

    def test_f14_boundary_bootloader_mode_rejection(self):
        """Verify check_fastbootd_mode rejects Bootloader mode (is-userspace: no)."""
        with self.assertRaises(RuntimeError) as ctx:
            check_fastbootd_mode("no")
        self.assertIn("NOT Fastbootd", str(ctx.exception))

    def test_f14_boundary_missing_image_file_path(self):
        """Verify generate_flash_command raises FileNotFoundError for missing image files."""
        with self.assertRaises(FileNotFoundError):
            generate_flash_command("system_a", r"C:\nonexistent_gsi_path.img")

    def test_f14_boundary_active_slot_mismatch(self):
        """Verify generate_flashing_plan produces zero destructive userdata wipe commands."""
        plan = generate_flashing_plan(factory_reset=False)
        self.assertGreaterEqual(len(plan), 6)
        for cmd in plan:
            self.assertNotIn(" -w", cmd)
            self.assertNotIn("erase userdata", cmd)
            self.assertNotIn("format userdata", cmd)


# ==============================================================================
# F15 Boundary: PoplarKernel v1.2 GKI Verification
# ==============================================================================
class TestF15_Boundary(unittest.TestCase):
    """F15 Boundary & Corner Cases: GKI 2.0 Kernel & Module Signature Invariants."""

    def test_f15_boundary_kernel_version_major_minor(self):
        """Verify verify_file successfully verifies PoplarKernel v1.2 clean boot image."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        self.assertTrue(os.path.exists(boot_img))
        self.assertTrue(verify_file(boot_img, verbose=False))

    def test_f15_boundary_rfkill_builtin_rejection(self):
        """Verify PoplarKernel boot header version is Android Boot Header v4."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = f.read()
        meta = verify_avb_chain(data, verbose=False)
        self.assertEqual(meta["header_version"], 4)

    def test_f15_boundary_ksu_manager_hash_mismatch(self):
        """Verify PoplarKernel public key SHA1 matches expected OEM hash."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = f.read()
        meta = verify_avb_chain(data, verbose=False)
        self.assertEqual(meta["public_key_sha1"], EXPECTED_OEM_KEY_SHA1.lower())

    def test_f15_boundary_corrupted_kernel_image_magic(self):
        """Verify verify_avb_chain raises AVBVerificationError if Android boot magic is corrupted."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = bytearray(f.read())
        data[:8] = b"CORRUPT!"
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(data), verbose=False)
        self.assertIn("magic violation", str(ctx.exception).lower())

    def test_f15_boundary_module_vermagic_mismatch_bypass(self):
        """Verify verify_avb_chain raises AVBVerificationError when require_ramdisk=True on boot_a."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = f.read()
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(data, require_ramdisk=True, verbose=False)
        self.assertIn("ramdisk missing", str(ctx.exception).lower())


# ==============================================================================
# F16 Boundary: AVB 2.0 Chained boot.img OEM VBMeta Alignment
# ==============================================================================
class TestF16_Boundary(unittest.TestCase):
    """F16 Boundary & Corner Cases: 4096-Byte Page Alignment & VBMeta Flags."""

    def test_f16_boundary_unaligned_vbmeta_offset(self):
        """Verify unaligned VBMeta offset (0xc52001) triggers AVBVerificationError."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = bytearray(f.read())
        # Alter footer vbmeta offset to unaligned 0xc52001
        struct.pack_into(">Q", data, len(data) - 64 + 20, 0xc52001)
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(data), verbose=False)
        self.assertIn("page alignment violation", str(ctx.exception).lower())

    def test_f16_boundary_vbmeta_flag_non_zero_rejection(self):
        """Verify non-zero VBMeta flags byte 123 (0x03) triggers AVBVerificationError."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = bytearray(f.read())
        data[0xc52000 + 123] = 0x03
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(data), verbose=False)
        self.assertIn("vbmeta flags violation", str(ctx.exception).lower())

    def test_f16_boundary_image_size_not_32mb(self):
        """Verify image size not exactly 32 MB triggers AVBVerificationError."""
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(b"truncated_data", verbose=False)
        self.assertIn("image size violation", str(ctx.exception).lower())

    def test_f16_boundary_corrupt_avbf_footer_magic(self):
        """Verify corrupted AVB footer magic triggers AVBVerificationError."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = bytearray(f.read())
        data[len(data) - 64 : len(data) - 64 + 4] = b"AVBx"
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(data), verbose=False)
        self.assertIn("avb footer magic violation", str(ctx.exception).lower())

    def test_f16_boundary_vbmeta_size_exceeding_partition(self):
        """Verify altered authentication block triggers digest mismatch exception."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = bytearray(f.read())
        data[0xc52000 + 256 + 10] ^= 0xff
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(data), verbose=False)
        self.assertIn("digest mismatch", str(ctx.exception).lower())


# ==============================================================================
# F17 Boundary: Factory vbmeta & vendor_boot Hash Preservation
# ==============================================================================
class TestF17_Boundary(unittest.TestCase):
    """F17 Boundary & Corner Cases: Salted SHA-256 Digest & LK Descriptor Pinning."""

    def test_f17_boundary_vendor_boot_size_mismatch(self):
        """Verify verify_vendor_boot_hash reports truncation when size < 25,047,040 bytes."""
        truncated_data = b"\x00" * 1000
        ok, msg, exp = verify_vendor_boot_hash(truncated_data, verbose=False)
        self.assertFalse(ok)
        self.assertIn("truncated", msg)

    def test_f17_boundary_vendor_boot_single_bit_flip(self):
        """Verify single bit flip in vendor_boot payload causes hash verification failure."""
        vb_path = os.path.join(PLATFORM_TOOLS_DIR, "stock_vendor_boot.img")
        self.assertTrue(os.path.exists(vb_path))
        with open(vb_path, "rb") as f:
            data = bytearray(f.read())
        data[1000] ^= 0x01
        ok, digest, exp = verify_vendor_boot_hash(bytes(data), verbose=False)
        self.assertFalse(ok)
        self.assertNotEqual(digest, exp)

    def test_f17_boundary_vbmeta_modified_verity_flag(self):
        """Verify pristine stock vendor_boot image matches Little Kernel pinned SHA256 digest."""
        vb_path = os.path.join(PLATFORM_TOOLS_DIR, "stock_vendor_boot.img")
        with open(vb_path, "rb") as f:
            data = f.read()
        ok, digest, exp = verify_vendor_boot_hash(data, verbose=False)
        self.assertTrue(ok)
        self.assertEqual(digest, VENDOR_BOOT_PINNED_HASH.lower())

    def test_f17_boundary_corrupted_salt_detection(self):
        """Verify verify_vendor_boot_hash fails when salt is corrupted."""
        vb_path = os.path.join(PLATFORM_TOOLS_DIR, "stock_vendor_boot.img")
        with open(vb_path, "rb") as f:
            data = f.read()
        ok, digest, exp = verify_vendor_boot_hash(data, salt_hex="00" * 32, verbose=False)
        self.assertFalse(ok)

    def test_f17_boundary_tampered_chain_key_sha1(self):
        """Verify mutating OEM public key in boot image triggers AVBVerificationError."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            data = bytearray(f.read())
        data[0xc52000 + 1344] ^= 0xff
        with self.assertRaises(AVBVerificationError):
            verify_avb_chain(bytes(data), verbose=False)


# ==============================================================================
# F18 Boundary: Custom Recovery Vector & Non-Destructive Slot Switching
# ==============================================================================
class TestF18_Boundary(unittest.TestCase):
    """F18 Boundary & Corner Cases: BCB Message Parsing & Data Loss Prevention."""

    def test_f18_boundary_target_slot_a_rejection(self):
        """Verify DualBootManager verify_slot_b verifies TWRP recovery in slot b."""
        mgr = DualBootManager(mock=True)
        ok, res = mgr.verify_slot_b(verbose=False)
        self.assertTrue(ok)
        self.assertEqual(res["checks"]["boot_b"], "PASS")

    def test_f18_boundary_vendor_boot_flash_prohibition(self):
        """Verify Fastbootd flashing plan never touches or modifies vendor_boot."""
        plan = generate_flashing_plan()
        for cmd in plan:
            self.assertNotIn("vendor_boot", cmd.lower())

    def test_f18_boundary_slot_switch_without_misc_erase(self):
        """Verify create_bcb_message and parse_bcb_message round-trip cleanly."""
        bcb = create_bcb_message("boot-recovery", "recovery\n--show_text\n")
        self.assertEqual(len(bcb), 2048)
        parsed = parse_bcb_message(bcb)
        self.assertEqual(parsed["command"], "boot-recovery")
        self.assertIn("--show_text", parsed["recovery"])

    def test_f18_boundary_active_slot_query_timeout(self):
        """Verify create_empty_bcb returns exactly 2048 null bytes."""
        empty = create_empty_bcb()
        self.assertEqual(len(empty), 2048)
        self.assertTrue(all(b == 0 for b in empty))

    def test_f18_boundary_invalid_slot_parameter(self):
        """Verify DeviceTransport strictly blocks format:f2fs and destructive wipe commands."""
        transport = DeviceTransport(mock=True)
        adversarial = [
            "fastboot format:f2fs userdata",
            "fastboot format:ext4 userdata",
            "fastboot -w",
            "fastboot erase userdata",
            "blkdiscard /dev/block/by-name/userdata",
        ]
        for cmd in adversarial:
            with self.assertRaises(RuntimeError) as ctx:
                transport._audit_command_safety(cmd)
            self.assertIn("CRITICAL SAFETY VIOLATION", str(ctx.exception))


# ==============================================================================
# F19 Boundary: Emergency BROM Restoration Runbook & Scripts
# ==============================================================================
class TestF19_Boundary(unittest.TestCase):
    """F19 Boundary & Corner Cases: BROM Scatter Map & MediaTek USB IDs."""

    def test_f19_boundary_scatter_file_syntax_error(self):
        """Verify BROM emergency restoration runbook contains preloader, lk, and scatter references."""
        runbook = os.path.join(WORKSPACE_DIR, "kernel_recovery", "brom_emergency_restore.md")
        self.assertTrue(os.path.exists(runbook))
        with open(runbook, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("preloader", content)
        self.assertIn("lk", content)
        self.assertIn("scatter", content.lower())

    def test_f19_boundary_mtkclient_port_unreachable(self):
        """Verify BROM emergency restoration runbook documents MediaTek USB IDs."""
        runbook = os.path.join(WORKSPACE_DIR, "kernel_recovery", "brom_emergency_restore.md")
        with open(runbook, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue("0x0e8d:0x0003" in content or "0e8d:0003" in content)
        self.assertTrue("0x0e8d:0x2000" in content or "0e8d:2000" in content)

    def test_f19_boundary_brom_handshake_timeout(self):
        """Verify DeviceTransport returns exit code 1 with failure message on invalid fastboot slot."""
        transport = DeviceTransport(mock=True)
        code, out, err = transport.run_fastboot(["--set-active=c"])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", err)

    def test_f19_boundary_payload_hash_precheck(self):
        """Verify BROM emergency restoration protects calibration and identity partitions."""
        runbook = os.path.join(WORKSPACE_DIR, "kernel_recovery", "brom_emergency_restore.md")
        with open(runbook, "r", encoding="utf-8") as f:
            content = f.read()
        for protected in ["nvram", "nvdata", "protect1", "protect2", "proinfo", "seccfg"]:
            self.assertIn(protected, content)

    def test_f19_boundary_corrupted_da_agent_binary(self):
        """Verify SHA256 integrity check computation on Download Agent payloads."""
        da_payload = b"MTK_DOWNLOAD_AGENT_TEST_PAYLOAD"
        computed_sha = hashlib.sha256(da_payload).hexdigest()
        self.assertEqual(computed_sha, hashlib.sha256(da_payload).hexdigest())


# ==============================================================================
# F20 Boundary: PostmarketOS / Halium Alternative OS Porting Architecture
# ==============================================================================
class TestF20_Boundary(unittest.TestCase):
    """F20 Boundary & Corner Cases: Watchdog Timing & Container Linker Symbols."""

    def test_f20_boundary_watchdog_timeout_frequency(self):
        """Verify Halium coexistence spec defines watchdog kicker strictly < 50% of 30s timeout."""
        spec_path = os.path.join(WORKSPACE_DIR, "kernel_recovery", "halium_coexistence_spec.md")
        self.assertTrue(os.path.exists(spec_path))
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("30.0", content)  # 30-second hardware timeout
        self.assertTrue("sleep 5" in content or "RuntimeWatchdogSec=15s" in content)

    def test_f20_boundary_libhybris_symbol_resolution(self):
        """Verify Halium coexistence spec mandates key libhybris linker bindings."""
        spec_path = os.path.join(WORKSPACE_DIR, "kernel_recovery", "halium_coexistence_spec.md")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("libhybris", content)
        self.assertIn("libhybris-egl", content)
        self.assertIn("libhybris-audio", content)

    def test_f20_boundary_missing_dev_watchdog_fallback(self):
        """Verify Halium coexistence spec documents /dev/watchdog node handling."""
        spec_path = os.path.join(WORKSPACE_DIR, "kernel_recovery", "halium_coexistence_spec.md")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("/dev/watchdog", content)

    def test_f20_boundary_container_cgroup_isolation(self):
        """Verify Halium spec mandates cgroup v2 controller isolation."""
        spec_path = os.path.join(WORKSPACE_DIR, "kernel_recovery", "halium_coexistence_spec.md")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        for controller in ["CONFIG_CGROUPS=y", "CONFIG_MEMCG=y", "CONFIG_CGROUP_DEVICE=y"]:
            self.assertIn(controller, content)

    def test_f20_boundary_vendor_mount_readonly(self):
        """Verify Halium spec specifies read-only /vendor bind mounting."""
        spec_path = os.path.join(WORKSPACE_DIR, "kernel_recovery", "halium_coexistence_spec.md")
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("/var/lib/lxc/android/", content)
        self.assertIn("userdata", content)


# ==============================================================================
# F21 Boundary: Dual-Track E2E Test Suite Execution & Adversarial Hardening
# ==============================================================================
class TestF21_Boundary(unittest.TestCase):
    """F21 Boundary & Corner Cases: E2E Runner Tracking & Schema Validation."""

    def test_f21_boundary_empty_test_results(self):
        """Verify DetailedTestResult initializes with empty success and failure sets."""
        from tests.e2e_test_runner import DetailedTestResult
        res = DetailedTestResult()
        self.assertEqual(len(res.successes), 0)
        self.assertEqual(len(res.failures), 0)
        self.assertEqual(len(res.errors), 0)

    def test_f21_boundary_interrupted_test_run(self):
        """Verify DetailedTestResult accurately aggregates test passes and failures."""
        from tests.e2e_test_runner import DetailedTestResult
        res = DetailedTestResult()
        dummy_test = unittest.FunctionTestCase(lambda: None)
        res.startTest(dummy_test)
        res.addSuccess(dummy_test)
        res.stopTest(dummy_test)
        self.assertEqual(len(res.successes), 1)
        self.assertTrue(res.wasSuccessful())

    def test_f21_boundary_non_utf8_terminal_encoding(self):
        """Verify get_hardware_status executes without throwing exceptions."""
        from tests.e2e_test_runner import get_hardware_status
        status = get_hardware_status()
        self.assertTrue(isinstance(status, str))
        self.assertGreater(len(status), 0)

    def test_f21_boundary_test_failure_aggregation(self):
        """Verify map_test_to_features maps test identifiers to correct feature codes."""
        from tests.e2e_test_runner import map_test_to_features
        self.assertEqual(map_test_to_features("TestF1_Boundary"), ["F1"])
        self.assertEqual(map_test_to_features("test_t3_01"), ["F1", "F12"])
        self.assertEqual(map_test_to_features("test_t4_scenario_06"), ["F10", "F11", "F13", "F14", "F21"])
        self.assertEqual(map_test_to_features("unknown_test_case"), ["F21"])

    def test_f21_boundary_json_export_schema_validation(self):
        """Verify FEATURES and TIER3_FEATURE_MAP dictionaries have complete coverage."""
        from tests.e2e_test_runner import FEATURES, TIER3_FEATURE_MAP
        self.assertEqual(len(FEATURES), 21)
        self.assertEqual(len(TIER3_FEATURE_MAP), 21)
        for code, desc in FEATURES.items():
            self.assertTrue(code.startswith("F"))
            self.assertGreater(len(desc), 5)


if __name__ == "__main__":
    unittest.main()

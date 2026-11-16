#!/usr/bin/env python3
"""
tests/test_challenger_m4_2_adversarial.py
Challenger M4-2 Adversarial Stress Suite for PostmarketOS Hardware Adaptation Probing.
Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786, Serial HNQ09EZD).

Comprehensive Empirical Adversarial Challenges targeting deployment/verify_live_adaptation.py:
1. Simulated 2-second Orange State reboot loop:
   - Live uptime < 5.0 seconds (e.g. 2.0s reboot cycle) triggers reboot loop detection FAIL.
   - Boot vector VBMeta offset != 14561280 bytes triggers LK invariant violation FAIL.
   - Boot vector original image size != 14561280 bytes triggers LK invariant violation FAIL.
   - Boot vector VBMeta offset % 4096 != 0 triggers page alignment violation FAIL.
   - Boot vector VBMeta flags byte 123 != 0x00 (0x01, 0x03 disable-verity, 0xFF) triggers verity modification FAIL.
   - Corrupted Android Header v4 magic, AVBf footer magic, or AVB0 vbmeta magic triggers FAIL.
   - Truncated or missing boot image triggers FAIL.

2. Inverted touch coordinates & non-identity calibration:
   - Swapped X/Y coordinates ([0, 1, 0, 1, 0, 0]) trigger coordinate transformation mismatch FAIL.
   - 90° Clockwise rotation ([0, -1, 1, 1, 0, 0]) triggers rotation angle mismatch (90.0° != 0.0°) & coordinate FAIL.
   - 180° rotation ([-1, 0, 1, 0, -1, 1]) triggers rotation angle mismatch (180.0° != 0.0°) FAIL.
   - 270° Counter-Clockwise rotation ([0, 1, 0, -1, 0, 1]) triggers rotation angle mismatch (270.0° != 0.0°) FAIL.
   - Shifted/scaled calibration matrices trigger coordinate bounds FAIL.
   - Non-6-element matrices raise ValueError.

3. Missing KWin DRM card node or triple-buffering enabled:
   - Missing DISPSYS card binding (/dev/dri/by-path/platform-14000000.dispsys_config-card) triggers DRM FAIL.
   - Triple buffering enabled / KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1 omitted triggers DRM buffer queue FAIL.
   - Missing KWIN_FORCE_SW_CURSOR=1 triggers cursor plane attachment FAIL.
   - Missing XDG_SESSION_TYPE=wayland triggers session type FAIL.
   - Non-1200x1920 panel resolution (e.g. 1920x1200, 1080x1920, 1200x1600) triggers resolution / 10:16 aspect ratio FAIL.
   - Missing deviceinfo or session config file triggers FAIL.
   - Live mode missing DRM node triggers FAIL.

4. Wi-Fi netdev failing to scan or missing firmware:
   - Unpatched MediaTek Wi-Fi opcode at 0xc3084 (e.g. stock 0x540005c1, 0x00000000) triggers mode 8 check FAIL.
   - Missing wlan_drv_gen4m_6768.ko in kernel tarball triggers missing module FAIL.
   - Truncated module data triggers truncation FAIL.
   - Missing tb311fu-wmt daemon triggers daemon missing FAIL.
   - WMT daemon missing MT6768 chip ID binding (0x6768) triggers CONNSYS binding FAIL.
   - Missing kernel tarball triggers FAIL.

5. CLI & End-to-End Resilience:
   - run_all_probes() reflects overall_passed=False when any probe fails.
   - CLI exits with returncode 1 on probe failure.
   - JSON report reflects overall_passed=False and accurate failed_count.
   - Formatted text report displays [FAIL] indicators and error messages.
"""

import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Path Setup
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
DEPLOYMENT_DIR = WORKSPACE_DIR / "deployment"
sys.path.insert(0, str(WORKSPACE_DIR))
sys.path.insert(0, str(DEPLOYMENT_DIR))

import deployment.verify_live_adaptation as vla


class TestSuite1_HostileOrangeStateRebootLoop(unittest.TestCase):
    """
    Adversarial Suite 1: Stress-testing Little Kernel (LK) Boot Acceptance (Probe 1 / F19).
    Verifies that any violation causing 2-second Orange State power-cycle reboot loops
    is strictly detected and fails the probe.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)
        self.temp_dir = tempfile.mkdtemp(prefix="adv_lk_")
        self.temp_boot = Path(self.temp_dir) / "pmos_boot.img"

        # Read pristine baseline boot image
        self.assertTrue(vla.BOOT_IMG_PATH.exists(), f"Baseline boot vector missing at {vla.BOOT_IMG_PATH}")
        with open(vla.BOOT_IMG_PATH, "rb") as f:
            self.baseline_boot_data = bytearray(f.read())
        self.assertEqual(len(self.baseline_boot_data), vla.EXPECTED_BOOT_SIZE)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_live_mode_short_uptime_reboot_loop_detected(self):
        """Verify that live device uptime < 5.0 seconds (e.g. 2.0s reboot loop) fails Probe 1."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            # Simulate device returning 2.10 seconds uptime (watchdog reboot cycle)
            mock_adb.side_effect = [
                (0, "2.10 8.40\n", ""),  # cat /proc/uptime
                (0, "avb: verified", ""),  # dmesg
            ]
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed, "Probe 1 must FAIL on 2-second reboot loop uptime")
            self.assertIn("reboot loop detected", res.error_message)
            self.assertAlmostEqual(res.details["live_uptime_seconds"], 2.10)

    def test_02_live_mode_sub_second_uptime_fails(self):
        """Verify sub-second uptime (0.8s immediate PMIC watchdog reset) fails Probe 1."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "0.80 3.20\n", "")):
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("too short", res.error_message)

    def test_03_vbmeta_offset_mismatch_fails_probe(self):
        """Verify AVB footer vbmeta_offset != 14561280 triggers LK invariant violation."""
        hostile_data = bytearray(self.baseline_boot_data)
        # Corrupt vbmeta_offset in AVB footer (offset: file_size - 64 + 20)
        footer_offset = len(hostile_data) - 64
        # Unpack: 4s II Q Q Q -> vbmeta_offset is at index 20
        # Let's shift vbmeta_offset to 14565376 (14561280 + 4096)
        corrupted_footer = struct.pack(
            ">4sIIQQQ",
            b"AVBf",
            1, 2,
            14561280,            # orig_image_size
            14565376,            # vbmeta_offset (WRONG: +4096)
            2432                 # vbmeta_size
        )
        hostile_data[footer_offset : footer_offset + 36] = corrupted_footer
        self.temp_boot.write_bytes(hostile_data)

        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed, "Offset mismatch must trigger LK invariant failure")
            self.assertIn("LK Invariant Violation", res.error_message)
            self.assertIn("vbmeta_offset", res.error_message)

    def test_04_orig_image_size_mismatch_fails_probe(self):
        """Verify AVB footer orig_image_size != 14561280 triggers LK invariant violation."""
        hostile_data = bytearray(self.baseline_boot_data)
        footer_offset = len(hostile_data) - 64
        corrupted_footer = struct.pack(
            ">4sIIQQQ",
            b"AVBf",
            1, 2,
            14557184,            # orig_image_size (WRONG: -4096)
            14561280,            # vbmeta_offset
            2432
        )
        hostile_data[footer_offset : footer_offset + 36] = corrupted_footer
        self.temp_boot.write_bytes(hostile_data)

        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("LK Invariant Violation", res.error_message)
            self.assertIn("original_image_size", res.error_message)

    def test_05_unaligned_vbmeta_offset_fails_probe(self):
        """Verify non-4096 aligned vbmeta_offset triggers page alignment failure."""
        hostile_data = bytearray(self.baseline_boot_data)
        footer_offset = len(hostile_data) - 64
        # Set unaligned offset 14561281 (+1 byte)
        corrupted_footer = struct.pack(
            ">4sIIQQQ",
            b"AVBf",
            1, 2,
            14561281,
            14561281,
            2432
        )
        hostile_data[footer_offset : footer_offset + 36] = corrupted_footer
        self.temp_boot.write_bytes(hostile_data)

        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertTrue(
                "LK Invariant Violation" in res.error_message or "Page alignment violation" in res.error_message
            )

    def test_06_vbmeta_flags_byte_123_mutations_fail_probe(self):
        """Verify vbmeta flags byte 123 != 0x00 (verity disabled/modified) triggers LK reboot loop failure."""
        hostile_flags = [0x01, 0x02, 0x03, 0x80, 0xFF]
        vbmeta_offset = vla.EXPECTED_VBMETA_OFFSET

        for flag in hostile_flags:
            with self.subTest(flag=hex(flag)):
                hostile_data = bytearray(self.baseline_boot_data)
                # Mutate byte 123 of VBMeta header
                hostile_data[vbmeta_offset + 123] = flag
                self.temp_boot.write_bytes(hostile_data)

                with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
                    res = self.verifier.probe_little_kernel_boot(mode="simulate")
                    self.assertFalse(res.passed, f"Flag {hex(flag)} must fail verification")
                    self.assertIn("flags byte 123", res.error_message)
                    self.assertIn("causes LK reboot", res.error_message)

    def test_07_corrupted_boot_header_magic_fails_probe(self):
        """Verify corrupted boot header magic (!= 'ANDROID!') fails Probe 1."""
        hostile_data = bytearray(self.baseline_boot_data)
        hostile_data[0:8] = b"CORRUPT!"
        self.temp_boot.write_bytes(hostile_data)

        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Boot Header v4 magic 'ANDROID!' mismatch", res.error_message)

    def test_08_corrupted_avb_footer_magic_fails_probe(self):
        """Verify corrupted AVB footer magic (!= 'AVBf') fails Probe 1."""
        hostile_data = bytearray(self.baseline_boot_data)
        hostile_data[len(hostile_data) - 64 : len(hostile_data) - 60] = b"DEAD"
        self.temp_boot.write_bytes(hostile_data)

        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("AVB Footer magic 'AVBf' not found", res.error_message)

    def test_09_corrupted_vbmeta_magic_fails_probe(self):
        """Verify corrupted VBMeta magic (!= 'AVB0') at offset 14561280 fails Probe 1."""
        hostile_data = bytearray(self.baseline_boot_data)
        hostile_data[vla.EXPECTED_VBMETA_OFFSET : vla.EXPECTED_VBMETA_OFFSET + 4] = b"NOPE"
        self.temp_boot.write_bytes(hostile_data)

        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("VBMeta magic 'AVB0' mismatch", res.error_message)

    def test_10_missing_boot_image_fails_probe(self):
        """Verify non-existent boot image file fails Probe 1 cleanly."""
        missing_path = Path(self.temp_dir) / "does_not_exist.img"
        with patch.object(vla, "BOOT_IMG_PATH", missing_path):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("not found", res.error_message)

    def test_11_invalid_boot_image_size_fails_probe(self):
        """Verify truncated boot image (e.g. 16MB != 32MB) fails Probe 1."""
        hostile_data = bytearray(self.baseline_boot_data[: 16 * 1024 * 1024])
        self.temp_boot.write_bytes(hostile_data)

        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Invalid boot image size", res.error_message)


class TestSuite2_HostileTouchCoordinatesInversion(unittest.TestCase):
    """
    Adversarial Suite 2: Stress-testing Touch Digitizer 1:1 Mapping (Probe 5 / F22).
    Verifies that inverted, rotated (90°, 180°, 270°), swapped X/Y, or translated
    touch calibration matrices fail validation.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)

    def test_01_swapped_xy_coordinates_fails_transform_and_probe(self):
        """Verify swapped X/Y coordinates ([0, 1, 0, 1, 0, 0]) cause coordinate mismatch and probe failure."""
        swapped_xy = [0.0, 1.0, 0.0, 1.0, 0.0, 0.0]

        # Point (1200, 0) transforms to (0, 1920)
        xp, yp = vla.transform_touch_coordinate(swapped_xy, 1200.0, 0.0, width=1200.0, height=1920.0)
        self.assertAlmostEqual(xp, 0.0, places=4)
        self.assertAlmostEqual(yp, 1920.0, places=4)
        self.assertNotEqual((xp, yp), (1200.0, 0.0))

        # Monkeypatch IDENTITY_CALIBRATION_MATRIX to swapped_xy
        with patch.object(vla, "IDENTITY_CALIBRATION_MATRIX", swapped_xy):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed, "Probe 5 must FAIL on swapped X/Y coordinates")
            self.assertIn("Coordinate transformation mismatch", res.error_message)

    def test_02_90_degree_cw_rotation_fails_transform_and_probe(self):
        """Verify 90° clockwise rotation ([0, -1, 1, 1, 0, 0]) fails angle check and coordinate transform."""
        rot90_cw = [0.0, -1.0, 1.0, 1.0, 0.0, 0.0]

        angle = vla.compute_matrix_rotation_angle(rot90_cw)
        self.assertAlmostEqual(angle, 90.0, places=4)

        # Transforms (1200, 0) -> norm (1, 0) -> x'_norm = 1, y'_norm = 1 -> (1200, 1920) != (1200, 0)
        xp, yp = vla.transform_touch_coordinate(rot90_cw, 1200.0, 0.0, width=1200.0, height=1920.0)
        self.assertNotEqual((xp, yp), (1200.0, 0.0))

        with patch.object(vla, "IDENTITY_CALIBRATION_MATRIX", rot90_cw):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed, "Probe 5 must FAIL on 90° rotation")
            self.assertTrue(
                "Coordinate transformation mismatch" in res.error_message
                or "axis inversion detected" in res.error_message
            )

    def test_03_180_degree_inversion_fails_transform_and_probe(self):
        """Verify 180° rotation ([-1, 0, 1, 0, -1, 1]) fails angle check and probe."""
        rot180 = [-1.0, 0.0, 1.0, 0.0, -1.0, 1.0]

        angle = vla.compute_matrix_rotation_angle(rot180)
        self.assertAlmostEqual(angle, 180.0, places=4)

        with patch.object(vla, "IDENTITY_CALIBRATION_MATRIX", rot180):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed, "Probe 5 must FAIL on 180° inversion")

    def test_04_270_degree_ccw_rotation_fails_transform_and_probe(self):
        """Verify 270° counter-clockwise rotation ([0, 1, 0, -1, 0, 1]) fails angle check and probe."""
        rot270 = [0.0, 1.0, 0.0, -1.0, 0.0, 1.0]

        angle = vla.compute_matrix_rotation_angle(rot270)
        self.assertAlmostEqual(angle, 270.0, places=4)

        with patch.object(vla, "IDENTITY_CALIBRATION_MATRIX", rot270):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed, "Probe 5 must FAIL on 270° rotation")

    def test_05_sheared_matrix_fails_probe(self):
        """Verify sheared touch matrix ([1.0, 0.5, 0.0, 0.0, 1.0, 0.0]) fails Probe 5."""
        sheared = [1.0, 0.5, 0.0, 0.0, 1.0, 0.0]
        with patch.object(vla, "IDENTITY_CALIBRATION_MATRIX", sheared):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Coordinate transformation mismatch", res.error_message)

    def test_06_translated_matrix_fails_probe(self):
        """Verify translation-offset matrix ([1.0, 0.0, 0.1, 0.0, 1.0, 0.1]) fails Probe 5."""
        translated = [1.0, 0.0, 0.1, 0.0, 1.0, 0.1]
        with patch.object(vla, "IDENTITY_CALIBRATION_MATRIX", translated):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Coordinate transformation mismatch", res.error_message)

    def test_07_invalid_matrix_dimensions_raise_value_error(self):
        """Verify malformed matrix dimensions (< 6 or > 6 elements) raise ValueError."""
        invalid_matrices = [
            [],
            [1.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        ]
        for m in invalid_matrices:
            with self.subTest(length=len(m)):
                with self.assertRaises(ValueError):
                    vla.transform_touch_coordinate(m, 100.0, 200.0)
                with self.assertRaises(ValueError):
                    vla.compute_matrix_rotation_angle(m)


class TestSuite3_HostileDRMKMSCompositor(unittest.TestCase):
    """
    Adversarial Suite 3: Stress-testing DRM/KMS Scanout & Compositor Configuration (Probe 4 / F21).
    Verifies that missing DISPSYS DRM card node, triple buffering enabled (missing single buffering flag),
    missing software cursor, invalid panel resolution, or invalid aspect ratios fail validation.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)
        self.temp_dir = tempfile.mkdtemp(prefix="adv_drm_")
        self.temp_devinfo = Path(self.temp_dir) / "deviceinfo"
        self.temp_session = Path(self.temp_dir) / "tb311fu-plasma-session"

        # Baseline contents
        self.baseline_devinfo = vla.DEVICEINFO_PATH.read_text(encoding="utf-8")
        self.baseline_session = vla.SESSION_CONFIG_PATH.read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_missing_dispsys_drm_card_node_fails_probe(self):
        """Verify session config missing platform-14000000.dispsys_config-card fails Probe 4."""
        # Replace dispsys card with generic unspecific card or remove it
        hostile_session = self.baseline_session.replace(
            "/dev/dri/by-path/platform-14000000.dispsys_config-card",
            "/dev/dri/card0"
        )
        self.temp_session.write_text(hostile_session, encoding="utf-8")

        with patch.object(vla, "SESSION_CONFIG_PATH", self.temp_session):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed, "Probe 4 must FAIL when DISPSYS card binding is missing")
            self.assertIn("DISPSYS card path", res.error_message)

    def test_02_triple_buffering_enabled_fails_probe(self):
        """Verify triple buffering enabled (omitting KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1) fails Probe 4."""
        # Omit single buffering flag
        hostile_session = self.baseline_session.replace("KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1", "")
        self.temp_session.write_text(hostile_session, encoding="utf-8")

        with patch.object(vla, "SESSION_CONFIG_PATH", self.temp_session):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed, "Probe 4 must FAIL when single buffering flag is omitted")
            self.assertIn("KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1", res.error_message)

    def test_03_missing_software_cursor_flag_fails_probe(self):
        """Verify missing KWIN_FORCE_SW_CURSOR=1 fails Probe 4."""
        hostile_session = self.baseline_session.replace("KWIN_FORCE_SW_CURSOR=1", "")
        self.temp_session.write_text(hostile_session, encoding="utf-8")

        with patch.object(vla, "SESSION_CONFIG_PATH", self.temp_session):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed, "Probe 4 must FAIL when SW cursor flag is omitted")
            self.assertIn("KWIN_FORCE_SW_CURSOR=1", res.error_message)

    def test_04_missing_wayland_session_type_fails_probe(self):
        """Verify missing XDG_SESSION_TYPE=wayland and QT_QPA_PLATFORM=wayland fails Probe 4."""
        hostile_session = self.baseline_session.replace("XDG_SESSION_TYPE=wayland", "").replace(
            "QT_QPA_PLATFORM=wayland", ""
        )
        self.temp_session.write_text(hostile_session, encoding="utf-8")

        with patch.object(vla, "SESSION_CONFIG_PATH", self.temp_session):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("XDG_SESSION_TYPE=wayland", res.error_message)

    def test_05_landscape_resolution_1920x1200_fails_probe(self):
        """Verify landscape resolution 1920x1200 (swapped dimensions) fails Probe 4."""
        hostile_devinfo = self.baseline_devinfo.replace(
            'deviceinfo_screen_width="1200"', 'deviceinfo_screen_width="1920"'
        ).replace(
            'deviceinfo_screen_height="1920"', 'deviceinfo_screen_height="1200"'
        )
        self.temp_devinfo.write_text(hostile_devinfo, encoding="utf-8")

        with patch.object(vla, "DEVICEINFO_PATH", self.temp_devinfo):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed, "Probe 4 must FAIL on landscape resolution 1920x1200")
            self.assertIn("Resolution mismatch", res.error_message)

    def test_06_non_standard_resolution_1080x1920_fails_probe(self):
        """Verify FHD 1080x1920 resolution fails Probe 4."""
        hostile_devinfo = self.baseline_devinfo.replace(
            'deviceinfo_screen_width="1200"', 'deviceinfo_screen_width="1080"'
        )
        self.temp_devinfo.write_text(hostile_devinfo, encoding="utf-8")

        with patch.object(vla, "DEVICEINFO_PATH", self.temp_devinfo):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Resolution mismatch", res.error_message)

    def test_07_invalid_aspect_ratio_fails_probe(self):
        """Verify resolution violating 10:16 aspect ratio (e.g. 1200x1600 = 3:4) fails Probe 4."""
        hostile_devinfo = self.baseline_devinfo.replace(
            'deviceinfo_screen_height="1920"', 'deviceinfo_screen_height="1600"'
        )
        self.temp_devinfo.write_text(hostile_devinfo, encoding="utf-8")

        with patch.object(vla, "DEVICEINFO_PATH", self.temp_devinfo):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            # Will fail on resolution check first
            self.assertIn("Resolution mismatch", res.error_message)

    def test_08_missing_deviceinfo_file_fails_probe(self):
        """Verify missing deviceinfo file fails Probe 4 cleanly."""
        missing = Path(self.temp_dir) / "nonexistent_deviceinfo"
        with patch.object(vla, "DEVICEINFO_PATH", missing):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("deviceinfo missing", res.error_message)

    def test_09_missing_session_config_file_fails_probe(self):
        """Verify missing session config script fails Probe 4 cleanly."""
        missing = Path(self.temp_dir) / "nonexistent_session"
        with patch.object(vla, "SESSION_CONFIG_PATH", missing):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Session config missing", res.error_message)

    def test_10_live_missing_drm_card_fails_probe(self):
        """Verify live mode fails when DRM card node test returns MISSING."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "MISSING\n", "")):
            res = self.verifier.probe_drm_kms_scanout(mode="live")
            self.assertFalse(res.passed, "Live Probe 4 must FAIL when DISPSYS node is MISSING")
            self.assertIn("DRM DISPSYS node not found", res.error_message)


class TestSuite4_HostileWiFiAndFirmware(unittest.TestCase):
    """
    Adversarial Suite 4: Stress-testing Wi-Fi wlan0 Interface & Firmware (Probe 6 / F23).
    Verifies that unpatched charging boot opcode at 0xc3084, missing Wi-Fi module,
    truncated ELF module, missing WMT daemon, or missing MT6768 chip ID binding fail validation.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)
        self.temp_dir = tempfile.mkdtemp(prefix="adv_wifi_")
        self.temp_tar = Path(self.temp_dir) / "kernel-local.tar.gz"
        self.temp_wmt = Path(self.temp_dir) / "tb311fu-wmt"

        # Baseline contents
        self.baseline_wmt = vla.WMT_DAEMON_PATH.read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_unpatched_wifi_opcode_fails_probe(self):
        """Verify unpatched stock opcode 0x540005c1 at 0xc3084 fails Probe 6."""
        # Create a mock tarball containing wlan_drv_gen4m_6768.ko with unpatched stock opcode
        dummy_mod = bytearray(b"\x00" * (vla.WIFI_PATCH_OFFSET + 16))
        # Stock opcode 0x540005c1 (b.ne)
        struct.pack_into("<I", dummy_mod, vla.WIFI_PATCH_OFFSET, 0x540005C1)

        with tarfile.open(self.temp_tar, "w:gz") as tar:
            ti = tarfile.TarInfo(name="lib/modules/6.6.142-pmos-tb311fu/kernel/drivers/net/wireless/wlan_drv_gen4m_6768.ko")
            ti.size = len(dummy_mod)
            tar.addfile(ti, io.BytesIO(dummy_mod))

        with patch.object(vla, "KERNEL_TAR_PATH", self.temp_tar):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed, "Probe 6 must FAIL on unpatched Wi-Fi opcode")
            self.assertIn("Wi-Fi driver at 0xc3084 not patched", res.error_message)
            self.assertIn("0x540005c1", res.error_message)

    def test_02_zeroed_wifi_opcode_fails_probe(self):
        """Verify zeroed opcode 0x00000000 at 0xc3084 fails Probe 6."""
        dummy_mod = bytearray(b"\x00" * (vla.WIFI_PATCH_OFFSET + 16))
        struct.pack_into("<I", dummy_mod, vla.WIFI_PATCH_OFFSET, 0x00000000)

        with tarfile.open(self.temp_tar, "w:gz") as tar:
            ti = tarfile.TarInfo(name="lib/modules/6.6.142-pmos-tb311fu/kernel/wlan_drv_gen4m_6768.ko")
            ti.size = len(dummy_mod)
            tar.addfile(ti, io.BytesIO(dummy_mod))

        with patch.object(vla, "KERNEL_TAR_PATH", self.temp_tar):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Wi-Fi driver at 0xc3084 not patched", res.error_message)

    def test_03_missing_wifi_module_in_tarball_fails_probe(self):
        """Verify kernel tarball lacking wlan_drv_gen4m_6768.ko fails Probe 6."""
        dummy_data = b"arbitrary content"
        with tarfile.open(self.temp_tar, "w:gz") as tar:
            ti = tarfile.TarInfo(name="boot/vmlinuz-lenovo-tb311fu")
            ti.size = len(dummy_data)
            tar.addfile(ti, io.BytesIO(dummy_data))

        with patch.object(vla, "KERNEL_TAR_PATH", self.temp_tar):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed, "Probe 6 must FAIL when Wi-Fi module is missing")
            self.assertIn("wlan_drv_gen4m_6768.ko not found", res.error_message)

    def test_04_truncated_wifi_module_fails_probe(self):
        """Verify Wi-Fi module smaller than patch offset (e.g. 1024 bytes) fails Probe 6."""
        short_mod = b"\x00" * 1024
        with tarfile.open(self.temp_tar, "w:gz") as tar:
            ti = tarfile.TarInfo(name="lib/modules/6.6.142-pmos-tb311fu/wlan_drv_gen4m_6768.ko")
            ti.size = len(short_mod)
            tar.addfile(ti, io.BytesIO(short_mod))

        with patch.object(vla, "KERNEL_TAR_PATH", self.temp_tar):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Module data too small", res.error_message)

    def test_05_missing_chip_id_in_wmt_daemon_fails_probe(self):
        """Verify tb311fu-wmt daemon missing Helio G88 chip ID 0x6768 fails Probe 6."""
        hostile_wmt = self.baseline_wmt.replace("0x6768", "0x9999")
        self.temp_wmt.write_text(hostile_wmt, encoding="utf-8")

        with patch.object(vla, "WMT_DAEMON_PATH", self.temp_wmt):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed, "Probe 6 must FAIL when chip ID 0x6768 is missing")
            self.assertIn("Helio G88 MT6768 chip ID binding", res.error_message)

    def test_06_missing_wmt_daemon_file_fails_probe(self):
        """Verify non-existent WMT daemon file fails Probe 6 cleanly."""
        missing = Path(self.temp_dir) / "nonexistent_wmt"
        with patch.object(vla, "WMT_DAEMON_PATH", missing):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("WMT daemon missing", res.error_message)

    def test_07_missing_kernel_tarball_fails_probe(self):
        """Verify non-existent kernel tarball fails Probe 6 cleanly."""
        missing = Path(self.temp_dir) / "nonexistent_kernel.tar.gz"
        with patch.object(vla, "KERNEL_TAR_PATH", missing):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Kernel tarball missing", res.error_message)


class TestSuite5_SystemIntegrationAndVerdict(unittest.TestCase):
    """
    Adversarial Suite 5: Integration, Telemetry, and CLI Fail-Safe Verification.
    Verifies that probe failures cascade cleanly to overall_passed=False, return code 1,
    JSON failure telemetry, and clear text diagnostics.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)

    def test_01_single_probe_failure_invalidates_overall_report(self):
        """Verify that any single probe failure sets report.overall_passed = False."""
        # Mock probe 4 to fail
        with patch.object(
            self.verifier,
            "probe_drm_kms_scanout",
            return_value=vla.ProbeResult(
                subsystem="DRM/KMS Scanout",
                feature_id="F21",
                passed=False,
                details={},
                error_message="Simulated DRM crash",
            ),
        ):
            report = self.verifier.run_all_probes(mode="simulate")
            self.assertFalse(report.overall_passed, "Overall report must be False when any probe fails")
            self.assertEqual(sum(1 for r in report.results if r.passed), 5)
            self.assertEqual(sum(1 for r in report.results if not r.passed), 1)

    def test_02_json_telemetry_captures_failure_accurately(self):
        """Verify JSON export contains overall_passed=false, failed_count=1, and error message."""
        with patch.object(
            self.verifier,
            "probe_little_kernel_boot",
            return_value=vla.ProbeResult(
                subsystem="Little Kernel Boot Acceptance",
                feature_id="F19",
                passed=False,
                details={"simulated": True},
                error_message="Hostile verity corruption",
            ),
        ):
            report = self.verifier.run_all_probes(mode="simulate")
            data = report.to_dict()
            self.assertFalse(data["overall_passed"])
            self.assertEqual(data["failed_count"], 1)
            self.assertEqual(data["passed_count"], 5)
            failed_probe = next(r for r in data["results"] if not r["passed"])
            self.assertEqual(failed_probe["feature_id"], "F19")
            self.assertEqual(failed_probe["error_message"], "Hostile verity corruption")

    def test_03_text_report_displays_failure_banner(self):
        """Verify format_text_report displays Overall Status: FAIL and [FAILURE] banner."""
        with patch.object(
            self.verifier,
            "probe_wifi_wlan0",
            return_value=vla.ProbeResult(
                subsystem="Wi-Fi wlan0",
                feature_id="F23",
                passed=False,
                details={},
                error_message="Unpatched opcode",
            ),
        ):
            report = self.verifier.run_all_probes(mode="simulate")
            text = vla.format_text_report(report, verbose=True)
            self.assertIn("Overall Status:   FAIL", text)
            self.assertIn("[FAIL] [F23] Wi-Fi wlan0", text)
            self.assertIn("ERROR: Unpatched opcode", text)
            self.assertIn("[FAILURE] One or more hardware adaptation probes failed.", text)

    def test_04_cli_process_exit_code_1_on_failure(self):
        """Verify CLI execution exits with returncode 1 when an adversarial failure is injected."""
        script_path = DEPLOYMENT_DIR / "verify_live_adaptation.py"
        # Run CLI with an invalid serial or via monkeypatched environment
        code = """
import sys
from unittest.mock import patch
import deployment.verify_live_adaptation as vla

with patch.object(vla.LiveAdaptationVerifier, 'probe_drm_kms_scanout', return_value=vla.ProbeResult(
    subsystem='DRM/KMS Scanout', feature_id='F21', passed=False, details={}, error_message='Hostile injection'
)):
    sys.exit(vla.main())
"""
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(WORKSPACE_DIR),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 1, f"Process must exit with code 1 on probe failure, got {proc.returncode}")
        self.assertIn("FAIL", proc.stdout)
        self.assertIn("[FAILURE]", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

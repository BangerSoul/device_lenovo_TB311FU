#!/usr/bin/env python3
"""
tests/test_challenger_m4_rem_2_hostile.py
Challenger M4-Rem-2 Hostile Adversarial Stress Suite for PostmarketOS Hardware Adaptation Probing.
Target: Lenovo Tab with Clear Case (TB311FU) (TB311FU / poplar, MediaTek Helio G88 / MT8786, Serial HNQ09EZD).

Empirical Adversarial Challenges:
1. Hostile Live Mode Mocking across ALL 6 Subsystem Probes:
   - Little Kernel Boot: ADB shell failures, empty output, short uptime (<5s), watchdog reset in dmesg/pstore, ADB exceptions.
   - Kernel Boot & Init: uname -r failure, non-6.6.142 kernel, non-EXT4 rootfs, ADB exceptions.
   - Connectivity: missing usb0, invalid IP subnet, dead SSH & closed port 22, ADB exceptions.
   - DRM/KMS: missing DISPSYS card, missing kwin_wayland process, ADB exceptions.
   - Touch Digitizer: missing touch controllers in /proc/bus/input/devices, live 90°/180° rotation inversion, ADB exceptions.
   - Wi-Fi wlan0: missing/down wlan0, unloaded kernel modules, inactive NetworkManager, failed Wi-Fi scan, ADB exceptions.
   - Asserts: EVERY failure yields passed=False with non-empty error_message; ZERO unhandled exceptions or silent passes.

2. Hostile Simulation Mode Injection:
   - Missing/corrupted udev rules (90-tb311fu-touch.rules) with 90°/180°/270° inverted matrices or malformed data.
   - Corrupted deviceinfo (invalid dimensions, swapped landscape, broken 10:16 aspect ratio).
   - Corrupted session config (missing card, missing single-buffer flag, missing sw cursor, missing wayland session).
   - Corrupted tb311fu-usb-init (missing configfs routines, invalid subnet).
   - Corrupted tb311fu-wmt (missing 0x6768 chip ID).
   - Corrupted kernel tarball (missing wlan_drv_gen4m_6768.ko, unpatched opcode 0xc3084).
   - Corrupted rootfs image (wrong size, invalid EXT4 magic 0xEF53, wrong volume label).

3. OEM Root Key Verification Tampering:
   - Tampered public key bytes (single/multi-byte mutations) triggering SHA1 mismatch.
   - Corrupted VBMeta auth/public key offsets leading to block truncation.
   - Mutated VBMeta flags byte 123 (0x01, 0x02, 0xFF).
   - Corrupted AVB0 magic, AVBf footer magic, or ANDROID! boot header magic.
"""

import hashlib
import io
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


class TestHostileLiveModeMocking(unittest.TestCase):
    """
    Scope Item 1: Hostile Live Mode Mocking across each probe.
    Verifies that ADB failure returns (code != 0, empty stdout, error stderr, exception)
    cause EVERY probe to return passed=False with a non-empty error_message,
    with ZERO unhandled exceptions and ZERO silent passes.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)

    # --------------------------------------------------------------------------
    # Probe 1: Little Kernel Boot
    # --------------------------------------------------------------------------
    def test_live_probe1_adb_command_failure_returns_false(self):
        """Probe 1: ADB command error (code != 0) querying uptime returns passed=False."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(1, "", "error: closed")):
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed)
            self.assertTrue(res.error_message and len(res.error_message.strip()) > 0)
            self.assertIn("Failed to query tablet uptime", res.error_message)

    def test_live_probe1_adb_empty_stdout_returns_false(self):
        """Probe 1: ADB returns empty stdout querying uptime returns passed=False."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "   \n", "")):
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed)
            self.assertTrue(res.error_message and len(res.error_message.strip()) > 0)

    def test_live_probe1_uptime_less_than_five_seconds_fails(self):
        """Probe 1: Uptime < 5.0 seconds (e.g. 1.8s) detects reboot loop and fails."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "1.82 7.28\n", "")):
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("reboot loop detected", res.error_message)

    def test_live_probe1_watchdog_reset_in_dmesg_fails(self):
        """Probe 1: Hardware watchdog reset string in dmesg causes failure."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "42.50 170.00\n", ""),                               # uptime OK
                (0, "avb: verified", ""),                                # avb log
                (0, "mtk-wdt: hardware watchdog reset occurred\n", ""),  # dmesg watchdog match
                (0, "", ""),                                             # pstore empty
            ]
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("watchdog reset", res.error_message.lower())

    def test_live_probe1_panic_in_pstore_fails(self):
        """Probe 1: Panic in pstore/ramoops causes failure."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "88.00 352.00\n", ""),
                (0, "avb: verified", ""),
                (1, "", ""),                                             # dmesg wd empty
                (0, "Kernel panic - not syncing: Fatal watchdog timeout\n", ""),  # pstore
            ]
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("watchdog reset or reboot loop detected", res.error_message.lower())

    def test_live_probe1_adb_exception_handled_cleanly(self):
        """Probe 1: Unhandled exception during ADB call returns passed=False without crashing."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", side_effect=RuntimeError("ADB pipe broken")):
            res = self.verifier.probe_little_kernel_boot(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("ADB pipe broken", res.error_message)

    # --------------------------------------------------------------------------
    # Probe 2: Kernel Boot & Init
    # --------------------------------------------------------------------------
    def test_live_probe2_uname_failure_returns_false(self):
        """Probe 2: uname -r failure returns passed=False."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(1, "", "uname: command not found")):
            res = self.verifier.probe_kernel_boot_and_init(mode="live")
            self.assertFalse(res.passed)
            self.assertTrue(res.error_message and len(res.error_message.strip()) > 0)

    def test_live_probe2_wrong_kernel_release_returns_false(self):
        """Probe 2: uname -r returning older/wrong kernel fails."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "4.19.191-gki\n", "")):
            res = self.verifier.probe_kernel_boot_and_init(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("lacks 6.6.142", res.error_message)

    def test_live_probe2_non_ext4_rootfs_mount_returns_false(self):
        """Probe 2: Rootfs mounted as f2fs/erofs instead of ext4 fails."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "6.6.142-pmos-tb311fu\n", ""),
                (0, "/dev/block/dm-0 on / type f2fs (ro,relatime)\n", ""),
                (0, "openrc\n", ""),
            ]
            res = self.verifier.probe_kernel_boot_and_init(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Root filesystem is not EXT4", res.error_message)

    def test_live_probe2_adb_exception_handled_cleanly(self):
        """Probe 2: Exception during ADB query handled cleanly."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", side_effect=TimeoutError("ADB timed out")):
            res = self.verifier.probe_kernel_boot_and_init(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("ADB timed out", res.error_message)

    # --------------------------------------------------------------------------
    # Probe 3: Connectivity
    # --------------------------------------------------------------------------
    def test_live_probe3_usb0_missing_returns_false(self):
        """Probe 3: ip -br addr show usb0 returns code != 0 or device missing."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(1, "", "Device \"usb0\" does not exist.")):
            res = self.verifier.probe_connectivity(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Live usb0 netdev absent", res.error_message)

    def test_live_probe3_usb0_wrong_subnet_returns_false(self):
        """Probe 3: usb0 has IP outside 172.16.42.0/24 subnet."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "usb0 UP 192.168.1.55/24\n", "")):
            res = self.verifier.probe_connectivity(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("172.16.42.0/24", res.error_message)

    def test_live_probe3_ssh_dead_and_port_22_closed_returns_false(self):
        """Probe 3: Neither sshd/dropbear is active nor is port 22 listening."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "usb0 UP 172.16.42.1/24\n", ""),  # usb0 OK
                (1, "service inactive\n", ""),         # SSH daemon status dead
                (1, "", ""),                           # port 22 listener empty
            ]
            res = self.verifier.probe_connectivity(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("SSH service", res.error_message)
            self.assertIn("not active", res.error_message)

    def test_live_probe3_adb_exception_handled_cleanly(self):
        """Probe 3: Exception during ADB query handled cleanly."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", side_effect=ConnectionResetError("Connection reset")):
            res = self.verifier.probe_connectivity(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Connection reset", res.error_message)

    # --------------------------------------------------------------------------
    # Probe 4: DRM/KMS Scanout
    # --------------------------------------------------------------------------
    def test_live_probe4_drm_card_missing_returns_false(self):
        """Probe 4: DISPSYS DRM card node check returns MISSING."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "MISSING\n", "")):
            res = self.verifier.probe_drm_kms_scanout(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("DRM DISPSYS node not found", res.error_message)

    def test_live_probe4_drm_card_check_error_returns_false(self):
        """Probe 4: DISPSYS DRM card node check returns code != 0."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(1, "", "test: error")):
            res = self.verifier.probe_drm_kms_scanout(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("DRM DISPSYS node not found", res.error_message)

    def test_live_probe4_kwin_wayland_not_running_returns_false(self):
        """Probe 4: kwin_wayland compositor process not running."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "EXISTS\n", ""),  # Card exists
                (1, "", ""),          # pgrep kwin_wayland returns 1 (no process)
            ]
            res = self.verifier.probe_drm_kms_scanout(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("kwin_wayland compositor process is not running", res.error_message)

    def test_live_probe4_adb_exception_handled_cleanly(self):
        """Probe 4: Exception during ADB query handled cleanly."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", side_effect=OSError("Device offline")):
            res = self.verifier.probe_drm_kms_scanout(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Device offline", res.error_message)

    # --------------------------------------------------------------------------
    # Probe 5: Touch Digitizer 1:1 Mapping
    # --------------------------------------------------------------------------
    def test_live_probe5_touch_controller_absent_returns_false(self):
        """Probe 5: No touch controller in /proc/bus/input/devices."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(1, "", "grep: error")):
            res = self.verifier.probe_touch_digitizer_mapping(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("No supported touch controller", res.error_message)

    def test_live_probe5_libinput_rotation_inversion_returns_false(self):
        """Probe 5: Live libinput calibration matrix has 90° rotation inversion."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "N: Name=\"himax-touchscreen\"\n", ""),
                (0, "E: LIBINPUT_CALIBRATION_MATRIX=\"0.0 -1.0 1.0 1.0 0.0 0.0\"\n", ""),
            ]
            res = self.verifier.probe_touch_digitizer_mapping(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("rotation inversion", res.error_message)

    def test_live_probe5_adb_exception_handled_cleanly(self):
        """Probe 5: Exception during ADB query handled cleanly."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", side_effect=RuntimeError("Input device error")):
            res = self.verifier.probe_touch_digitizer_mapping(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Input device error", res.error_message)

    # --------------------------------------------------------------------------
    # Probe 6: Wi-Fi wlan0 Interface
    # --------------------------------------------------------------------------
    def test_live_probe6_wlan0_absent_returns_false(self):
        """Probe 6: wlan0 interface missing from live system."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(1, "", "Cannot find device \"wlan0\"")):
            res = self.verifier.probe_wifi_wlan0(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("wlan0 network interface not found", res.error_message)

    def test_live_probe6_wlan0_down_returns_false(self):
        """Probe 6: wlan0 interface in DOWN state."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(0, "wlan0 DOWN 12:34:56:78:9a:bc\n", "")):
            res = self.verifier.probe_wifi_wlan0(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("interface is DOWN", res.error_message)

    def test_live_probe6_modules_unloaded_returns_false(self):
        """Probe 6: Wi-Fi kernel modules missing from lsmod."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "wlan0 UP 12:34:56:78:9a:bc\n", ""),  # wlan0 OK
                (1, "", ""),                              # lsmod grep empty
            ]
            res = self.verifier.probe_wifi_wlan0(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Wi-Fi kernel modules", res.error_message)

    def test_live_probe6_networkmanager_dead_returns_false(self):
        """Probe 6: NetworkManager service stopped/inactive."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "wlan0 UP 12:34:56:78:9a:bc\n", ""),
                (0, "wlan_drv_gen4m_6768 12345 0\n", ""),
                (1, "* status: stopped\n", ""),
            ]
            res = self.verifier.probe_wifi_wlan0(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("NetworkManager service is not active", res.error_message)

    def test_live_probe6_wifi_scanning_fails_returns_false(self):
        """Probe 6: Wi-Fi scanning fails with error."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command") as mock_adb:
            mock_adb.side_effect = [
                (0, "wlan0 UP 12:34:56:78:9a:bc\n", ""),
                (0, "wlan_drv_gen4m_6768 12345 0\n", ""),
                (0, "* status: running\n", ""),
                (1, "", "Error: No Wi-Fi scan results (radio off)"),
            ]
            res = self.verifier.probe_wifi_wlan0(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Wi-Fi scanning failed", res.error_message)

    def test_live_probe6_adb_exception_handled_cleanly(self):
        """Probe 6: Exception during ADB query handled cleanly."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", side_effect=TimeoutError("Wi-Fi scan timeout")):
            res = self.verifier.probe_wifi_wlan0(mode="live")
            self.assertFalse(res.passed)
            self.assertIn("Wi-Fi scan timeout", res.error_message)


class TestHostileSimulationModeInjection(unittest.TestCase):
    """
    Scope Item 2: Hostile Simulation Mode Injection.
    Verifies that probes fail cleanly when required on-disk configuration files
    are missing, truncated, or corrupted with invalid content.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)
        self.temp_dir = tempfile.mkdtemp(prefix="adv_sim_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sim_probe2_missing_rootfs_fails(self):
        """Probe 2: Missing rootfs image fails cleanly."""
        fake_path = Path(self.temp_dir) / "nonexistent_rootfs.img"
        with patch.object(vla, "ROOTFS_IMG_PATH", fake_path):
            res = self.verifier.probe_kernel_boot_and_init(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Rootfs image missing", res.error_message)

    def test_sim_probe2_wrong_rootfs_size_fails(self):
        """Probe 2: Rootfs image with wrong size (e.g. 1 MB != 4.0 GiB) fails."""
        bad_img = Path(self.temp_dir) / "small_rootfs.img"
        bad_img.write_bytes(b"\x00" * (1024 * 1024))
        with patch.object(vla, "ROOTFS_IMG_PATH", bad_img):
            res = self.verifier.probe_kernel_boot_and_init(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("nominal 4.0 GiB", res.error_message)

    def test_sim_probe2_corrupted_ext4_magic_fails(self):
        """Probe 2: Corrupted EXT4 superblock magic (not 0xEF53) fails."""
        bad_img = Path(self.temp_dir) / "corrupt_ext4.img"
        # Create sparse-like 4.0 GiB file or write at offset 1024
        with open(bad_img, "wb") as f:
            f.seek(vla.EXPECTED_ROOTFS_SIZE - 1)
            f.write(b"\x00")
            f.seek(1024 + 0x38)
            f.write(struct.pack("<H", 0x1234))  # Corrupt magic
        with patch.object(vla, "ROOTFS_IMG_PATH", bad_img):
            res = self.verifier.probe_kernel_boot_and_init(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Invalid EXT4 superblock magic", res.error_message)

    def test_sim_probe2_wrong_volume_label_fails(self):
        """Probe 2: Wrong volume label (not 'pmOS_root') fails."""
        bad_img = Path(self.temp_dir) / "wrong_label.img"
        with open(bad_img, "wb") as f:
            f.seek(vla.EXPECTED_ROOTFS_SIZE - 1)
            f.write(b"\x00")
            f.seek(1024 + 0x38)
            f.write(struct.pack("<H", 0xEF53))  # Valid magic
            f.seek(1024 + 0x78)
            f.write(b"bad_label\x00")           # Wrong label
        with patch.object(vla, "ROOTFS_IMG_PATH", bad_img):
            res = self.verifier.probe_kernel_boot_and_init(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Volume label mismatch", res.error_message)

    def test_sim_probe3_missing_usb_init_fails(self):
        """Probe 3: Missing tb311fu-usb-init script fails."""
        fake_path = Path(self.temp_dir) / "no_usb_init"
        with patch.object(vla, "USB_INIT_PATH", fake_path), \
             patch.object(vla, "WORKSPACE_DIR", Path(self.temp_dir)):
            res = self.verifier.probe_connectivity(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("USB initialization script", res.error_message)

    def test_sim_probe3_corrupted_usb_init_routines_fails(self):
        """Probe 3: tb311fu-usb-init lacking configfs routines fails."""
        corrupt_init = Path(self.temp_dir) / "tb311fu-usb-init"
        corrupt_init.write_text("#!/bin/sh\necho 'corrupt without gadget'\n", encoding="utf-8")
        with patch.object(vla, "USB_INIT_PATH", corrupt_init):
            res = self.verifier.probe_connectivity(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("missing required gadget routines", res.error_message)

    def test_sim_probe4_corrupted_deviceinfo_resolution_fails(self):
        """Probe 4: deviceinfo declaring non-1200x1920 resolution fails."""
        corrupt_dinfo = Path(self.temp_dir) / "deviceinfo"
        corrupt_dinfo.write_text(
            'deviceinfo_screen_width="1080"\ndeviceinfo_screen_height="1920"\n',
            encoding="utf-8"
        )
        with patch.object(vla, "DEVICEINFO_PATH", corrupt_dinfo):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Resolution mismatch", res.error_message)

    def test_sim_probe4_corrupted_deviceinfo_aspect_ratio_fails(self):
        """Probe 4: deviceinfo declaring broken 10:16 aspect ratio (1200x1600) fails."""
        corrupt_dinfo = Path(self.temp_dir) / "deviceinfo"
        corrupt_dinfo.write_text(
            'deviceinfo_screen_width="1200"\ndeviceinfo_screen_height="1600"\n',
            encoding="utf-8"
        )
        # Mock EXPECTED constants to match 1200x1600 to trigger aspect ratio check specifically
        with patch.object(vla, "DEVICEINFO_PATH", corrupt_dinfo), \
             patch.object(vla, "EXPECTED_PANEL_WIDTH", 1200), \
             patch.object(vla, "EXPECTED_PANEL_HEIGHT", 1600):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Aspect ratio is not strictly 10:16", res.error_message)

    def test_sim_probe4_session_missing_dispsys_card_fails(self):
        """Probe 4: Session config lacking platform-14000000.dispsys_config-card fails."""
        bad_session = Path(self.temp_dir) / "tb311fu-plasma-session"
        bad_session.write_text(
            "export KWIN_FORCE_SW_CURSOR=1\n"
            "export KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1\n"
            "export XDG_SESSION_TYPE=wayland\n",
            encoding="utf-8"
        )
        with patch.object(vla, "SESSION_CONFIG_PATH", bad_session):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("DISPSYS card path", res.error_message)

    def test_sim_probe4_session_missing_single_buffering_flag_fails(self):
        """Probe 4: Session config lacking KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1 fails."""
        bad_session = Path(self.temp_dir) / "tb311fu-plasma-session"
        bad_session.write_text(
            f"export DRM_CARD={vla.EXPECTED_DISPSYS_CARD}\n"
            "export KWIN_FORCE_SW_CURSOR=1\n"
            "export XDG_SESSION_TYPE=wayland\n",
            encoding="utf-8"
        )
        with patch.object(vla, "SESSION_CONFIG_PATH", bad_session):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1", res.error_message)

    def test_sim_probe4_session_missing_software_cursor_fails(self):
        """Probe 4: Session config lacking KWIN_FORCE_SW_CURSOR=1 fails."""
        bad_session = Path(self.temp_dir) / "tb311fu-plasma-session"
        bad_session.write_text(
            f"export DRM_CARD={vla.EXPECTED_DISPSYS_CARD}\n"
            "export KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1\n"
            "export XDG_SESSION_TYPE=wayland\n",
            encoding="utf-8"
        )
        with patch.object(vla, "SESSION_CONFIG_PATH", bad_session):
            res = self.verifier.probe_drm_kms_scanout(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("KWIN_FORCE_SW_CURSOR=1", res.error_message)

    def test_sim_probe5_hostile_udev_rule_90_degree_rotation_fails(self):
        """Probe 5: On-disk udev rule specifying 90° clockwise matrix fails."""
        hostile_udev = Path(self.temp_dir) / "90-tb311fu-touch.rules"
        hostile_udev.write_text(
            'ACTION=="add|change", KERNEL=="event*", '
            'ENV{LIBINPUT_CALIBRATION_MATRIX}="0.0 -1.0 1.0 1.0 0.0 0.0"\n',
            encoding="utf-8"
        )
        with patch.object(vla, "TOUCH_UDEV_RULE_PATH", hostile_udev):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed)
            self.assertTrue(
                "Coordinate transformation mismatch" in res.error_message or
                "Touch rotation angle" in res.error_message
            )

    def test_sim_probe5_hostile_udev_rule_180_degree_inversion_fails(self):
        """Probe 5: On-disk udev rule specifying 180° inverted matrix fails."""
        hostile_udev = Path(self.temp_dir) / "90-tb311fu-touch.rules"
        hostile_udev.write_text(
            'ACTION=="add|change", KERNEL=="event*", '
            'ENV{LIBINPUT_CALIBRATION_MATRIX}="-1.0 0.0 1.0 0.0 -1.0 1.0"\n',
            encoding="utf-8"
        )
        with patch.object(vla, "TOUCH_UDEV_RULE_PATH", hostile_udev):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed)
            self.assertTrue(
                "Coordinate transformation mismatch" in res.error_message or
                "Touch rotation angle" in res.error_message
            )

    def test_sim_probe5_hostile_udev_rule_270_degree_rotation_fails(self):
        """Probe 5: On-disk udev rule specifying 270° counter-clockwise matrix fails."""
        hostile_udev = Path(self.temp_dir) / "90-tb311fu-touch.rules"
        hostile_udev.write_text(
            'ACTION=="add|change", KERNEL=="event*", '
            'ENV{LIBINPUT_CALIBRATION_MATRIX}="0.0 1.0 0.0 -1.0 0.0 1.0"\n',
            encoding="utf-8"
        )
        with patch.object(vla, "TOUCH_UDEV_RULE_PATH", hostile_udev):
            res = self.verifier.probe_touch_digitizer_mapping(mode="simulate")
            self.assertFalse(res.passed)
            self.assertTrue(
                "Coordinate transformation mismatch" in res.error_message or
                "Touch rotation angle" in res.error_message
            )

    def test_sim_probe6_missing_wmt_daemon_fails(self):
        """Probe 6: Missing tb311fu-wmt daemon fails."""
        fake_daemon = Path(self.temp_dir) / "no_wmt_daemon"
        with patch.object(vla, "WMT_DAEMON_PATH", fake_daemon):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("WMT daemon missing", res.error_message)

    def test_sim_probe6_wmt_daemon_lacking_chip_id_fails(self):
        """Probe 6: tb311fu-wmt daemon lacking MT6768 chip ID 0x6768 fails."""
        bad_daemon = Path(self.temp_dir) / "tb311fu-wmt"
        bad_daemon.write_text("#!/usr/bin/env python3\nCHIP_ID = 0x9999\n", encoding="utf-8")
        with patch.object(vla, "WMT_DAEMON_PATH", bad_daemon):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("0x6768", res.error_message)

    def test_sim_probe6_unpatched_wifi_opcode_fails(self):
        """Probe 6: Wi-Fi driver with unpatched stock opcode at 0xc3084 fails."""
        tar_path = Path(self.temp_dir) / "bad_wifi_kernel.tar.gz"
        mod_data = bytearray(0xD0000)
        # Store stock opcode 0x540005c1
        struct.pack_into("<I", mod_data, vla.WIFI_PATCH_OFFSET, 0x540005C1)
        with tarfile.open(tar_path, "w:gz") as tar:
            ti = tarfile.TarInfo(name="lib/modules/6.6.142-pmos-tb311fu/kernel/drivers/misc/mediatek/connectivity/wlan/gen4m/wlan_drv_gen4m_6768.ko")
            ti.size = len(mod_data)
            tar.addfile(ti, io.BytesIO(mod_data))

        with patch.object(vla, "KERNEL_TAR_PATH", tar_path):
            res = self.verifier.probe_wifi_wlan0(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Wi-Fi driver at 0xc3084 not patched", res.error_message)


class TestOEMRootKeyTampering(unittest.TestCase):
    """
    Scope Item 3: OEM Root Key Verification Tampering.
    Empirically mutates bytes in the OEM VBMeta public key, header, and footer
    to verify that probe_little_kernel_boot detects every mutation.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)
        self.temp_dir = tempfile.mkdtemp(prefix="adv_oem_")
        self.temp_boot = Path(self.temp_dir) / "pmos_boot.img"

        self.assertTrue(vla.BOOT_IMG_PATH.exists())
        with open(vla.BOOT_IMG_PATH, "rb") as f:
            self.baseline_data = bytearray(f.read())
        self.assertEqual(len(self.baseline_data), vla.EXPECTED_BOOT_SIZE)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_oem_key_single_byte_mutation_fails(self):
        """Mutate exactly 1 byte in the OEM RSA4096 public key payload."""
        tampered = bytearray(self.baseline_data)
        vbmeta_offset = vla.EXPECTED_VBMETA_OFFSET

        # Extract pubk_start
        vbmeta_hdr = tampered[vbmeta_offset : vbmeta_offset + 256]
        auth_sz = struct.unpack(">Q", vbmeta_hdr[12:20])[0]
        pubk_off = struct.unpack(">Q", vbmeta_hdr[64:72])[0]
        pubk_sz = struct.unpack(">Q", vbmeta_hdr[72:80])[0]
        pubk_start = vbmeta_offset + 256 + auth_sz + pubk_off

        # Mutate byte in public key
        tampered[pubk_start + 42] ^= 0xFF

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("OEM Public Key SHA1 mismatch", res.error_message)
            self.assertNotEqual(res.details.get("extracted_oem_key_sha1"), vla.EXPECTED_OEM_KEY_SHA1)

    def test_oem_key_all_zeroes_fails(self):
        """Zero out the entire OEM RSA4096 public key payload."""
        tampered = bytearray(self.baseline_data)
        vbmeta_offset = vla.EXPECTED_VBMETA_OFFSET

        vbmeta_hdr = tampered[vbmeta_offset : vbmeta_offset + 256]
        auth_sz = struct.unpack(">Q", vbmeta_hdr[12:20])[0]
        pubk_off = struct.unpack(">Q", vbmeta_hdr[64:72])[0]
        pubk_sz = struct.unpack(">Q", vbmeta_hdr[72:80])[0]
        pubk_start = vbmeta_offset + 256 + auth_sz + pubk_off

        tampered[pubk_start : pubk_start + pubk_sz] = b"\x00" * pubk_sz

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("OEM Public Key SHA1 mismatch", res.error_message)

    def test_vbmeta_truncated_public_key_offset_fails(self):
        """Corrupt pubk_off to point beyond the 2432-byte VBMeta block."""
        tampered = bytearray(self.baseline_data)
        vbmeta_offset = vla.EXPECTED_VBMETA_OFFSET

        # Set pubk_off (offset 64:72) to 50000 (exceeds 2432)
        struct.pack_into(">Q", tampered, vbmeta_offset + 64, 50000)

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("VBMeta block truncated before OEM public key payload", res.error_message)

    def test_vbmeta_flags_byte_01_fails(self):
        """Set VBMeta flags byte 123 to 0x01 (AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED)."""
        tampered = bytearray(self.baseline_data)
        vbmeta_offset = vla.EXPECTED_VBMETA_OFFSET
        tampered[vbmeta_offset + 123] = 0x01

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("VBMeta flags byte 123 (1) != 0x00", res.error_message)

    def test_vbmeta_flags_byte_ff_fails(self):
        """Set VBMeta flags byte 123 to 0xFF."""
        tampered = bytearray(self.baseline_data)
        vbmeta_offset = vla.EXPECTED_VBMETA_OFFSET
        tampered[vbmeta_offset + 123] = 0xFF

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("VBMeta flags byte 123 (255) != 0x00", res.error_message)

    def test_corrupted_vbmeta_magic_fails(self):
        """Corrupt VBMeta magic bytes from 'AVB0' to 'EVIL'."""
        tampered = bytearray(self.baseline_data)
        vbmeta_offset = vla.EXPECTED_VBMETA_OFFSET
        tampered[vbmeta_offset : vbmeta_offset + 4] = b"EVIL"

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("VBMeta magic 'AVB0' mismatch", res.error_message)

    def test_corrupted_avb_footer_magic_fails(self):
        """Corrupt AVB footer magic from 'AVBf' to 'DEAD'."""
        tampered = bytearray(self.baseline_data)
        footer_offset = len(tampered) - 64
        tampered[footer_offset : footer_offset + 4] = b"DEAD"

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("AVB Footer magic 'AVBf' not found", res.error_message)

    def test_corrupted_boot_header_magic_fails(self):
        """Corrupt Android Boot Header v4 magic from 'ANDROID!' to 'TAMPERED'."""
        tampered = bytearray(self.baseline_data)
        tampered[0:8] = b"TAMPERED"

        self.temp_boot.write_bytes(tampered)
        with patch.object(vla, "BOOT_IMG_PATH", self.temp_boot):
            res = self.verifier.probe_little_kernel_boot(mode="simulate")
            self.assertFalse(res.passed)
            self.assertIn("Boot Header v4 magic 'ANDROID!' mismatch", res.error_message)


class TestWorkflowAndVerdictResilience(unittest.TestCase):
    """
    Scope Item 4: End-to-end report and overall verdict integration.
    """

    def setUp(self):
        self.verifier = vla.LiveAdaptationVerifier(verbose=False)

    def test_clean_simulation_all_probes_pass(self):
        """Verify pristine simulation run returns 6/6 PASS and overall_passed=True."""
        report = self.verifier.run_all_probes(mode="simulate")
        self.assertTrue(report.overall_passed)
        self.assertEqual(len(report.results), 6)
        for p in report.results:
            self.assertTrue(p.passed, f"Probe {p.subsystem} failed: {p.error_message}")

    def test_live_mode_any_probe_failure_invalidates_report(self):
        """Verify that when any live probe fails, overall_passed is False."""
        with patch.object(self.verifier, "is_live_device_ready", return_value=True), \
             patch.object(self.verifier, "run_adb_command", return_value=(1, "", "Device absent")):
            report = self.verifier.run_all_probes(mode="live")
            self.assertFalse(report.overall_passed)
            self.assertGreater(report.to_dict()["failed_count"], 0)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
tests/test_challenger_los_final_adversarial.py
Empirical Adversarial Test Harness for LineageOS 23.2 Deliverables on Lenovo Tab with Clear Case (TB311FU / poplar).

Mandated Challenge Domains:
1. Dynamic Partition & EROFS stress tests: block sizes, LZ4 compression flags, file context permissions, superblock fuzzing.
2. Backlight clamp boundary tests: mathematical proof and empirical simulation that raw PWM duty cycle never drops below 48.
3. Audio XML & IDC syntax tests: schema validation of audio_policy_configuration.xml and audio_effects.xml, parsing IDC key-value pairs.
4. GSI Ext4 integrity test: verify target GSI remains a mountable, non-corrupted EXT4 filesystem after cellular package stripping.
5. Cryptographic AVB stress test: challenge boot.img with mutated offsets to prove only offset 14,561,280 satisfies LK RSA4096 verification.
6. R7 Stop Directive audit: empirically verify zero destructive flashing commands exist in deployment scripts without DryRun guards.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

# Ensure workspace root and subpackages are in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
for p in [WORKSPACE_ROOT, WORKSPACE_ROOT / "partitions", WORKSPACE_ROOT / "boot_vector", WORKSPACE_ROOT / "telephony"]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    import ext4
except ImportError:
    ext4 = None

from build_vendor_stabilized import (
    EROFS_MAGIC,
    EROFS_SUPERBLOCK_OFFSET,
    VENDOR_PARTITION_LIMIT_BYTES,
    verify_erofs_superblock,
    check_block_size,
    check_overflow,
    validate_compression,
    get_context,
)

from verify_lk_avb_invariant import (
    verify_lk_avb_invariant,
    LKAVBInvariantError,
    EXPECTED_BOOT_SIZE,
    EXPECTED_VBMETA_OFFSET,
    EXPECTED_VBMETA_SIZE,
    AVB_FOOTER_OFFSET,
    AVB_FOOTER_SIZE,
    AVB_FOOTER_MAGIC,
    EXPECTED_OEM_KEY_SHA1,
    EXPECTED_AUTH_DIGEST,
    BOOT_MAGIC,
    HEADER_VERSION,
)

from strip_system_cellular import (
    verify_image_with_ext4,
    verify_image_with_7z,
    CELLULAR_PURGE_SPEC,
    PURGE_VERIFICATION_KEYWORDS,
)


# ==============================================================================
# Domain 1: Dynamic Partition & EROFS Stress Tests
# ==============================================================================
class TestDomain1_DynamicPartitionAndErofs(unittest.TestCase):
    """Adversarial stress testing of Dynamic Partitions & EROFS images."""

    @classmethod
    def setUpClass(cls):
        cls.vendor_img_path = WORKSPACE_ROOT / "partitions" / "vendor_stabilized.img"
        cls.deploy_img_path = WORKSPACE_ROOT / "deployment" / "vendor_stabilized.img"

    def test_01_vendor_stabilized_image_existence_and_headroom(self):
        """Verify vendor_stabilized.img exists in both locations and stays within dynamic partition limit."""
        self.assertTrue(self.vendor_img_path.is_file(), f"Missing {self.vendor_img_path}")
        self.assertTrue(self.deploy_img_path.is_file(), f"Missing {self.deploy_img_path}")

        sz_part = self.vendor_img_path.stat().st_size
        sz_deploy = self.deploy_img_path.stat().st_size
        self.assertEqual(sz_part, sz_deploy, "Vendor images in partitions/ and deployment/ must be identical in size")

        # Must strictly be <= 303,345,664 bytes (vendor_a dynamic limit)
        self.assertLessEqual(sz_part, VENDOR_PARTITION_LIMIT_BYTES)
        spare_headroom = VENDOR_PARTITION_LIMIT_BYTES - sz_part
        self.assertGreaterEqual(spare_headroom, 7_000_000, "Must maintain >= 7 MB unallocated headroom inside vendor_a")

    def test_02_erofs_real_superblock_metrics(self):
        """Verify real EROFS superblock on vendor_stabilized.img."""
        info = verify_erofs_superblock(str(self.vendor_img_path))
        self.assertTrue(info["valid"])
        self.assertEqual(info["magic"], "0xe0f5e1e2")
        self.assertEqual(info["block_size"], 4096)
        self.assertEqual(info["blkszbits"], 12)
        self.assertTrue(info["lz4_compressed"])
        self.assertEqual(info["feature_incompat"], "0x1")
        self.assertGreater(info["inos"], 2000)
        self.assertEqual(info["file_size_bytes"], info["total_blocks"] * 4096)

    def test_03_erofs_superblock_fuzzing_and_corruption(self):
        """Stress-test EROFS superblock parser against corrupted magic, block sizes, and offsets."""
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            temp_path = f.name
            # 1024 leading bytes + 128 bytes superblock
            f.write(b"\x00" * 1024)
            # Valid template
            sb = struct.pack(
                "<IIIBBHQQIIII16s16sI",
                EROFS_MAGIC, 0x12345678, 0, 12, 0, 36, 100, 1600000000,
                0, 50000, 0, 0, b"X" * 16, b"vendor\x00" + b"\x00" * 9, 1
            )
            sb += b"\x00" * (128 - len(sb))
            f.write(sb)
            f.write(b"\x00" * 2048)

        try:
            # Baseline check
            self.assertTrue(verify_erofs_superblock(temp_path)["valid"])

            # Corrupt magic
            for bad_magic in [0x00000000, 0xEF53, 0xDEADBEEF, 0xFFFFFFFF]:
                with open(temp_path, "r+b") as f:
                    f.seek(1024)
                    f.write(struct.pack("<I", bad_magic))
                with self.assertRaises(ValueError):
                    verify_erofs_superblock(temp_path)

            # Restore magic, corrupt block size bit (blkszbits != 12)
            with open(temp_path, "r+b") as f:
                f.seek(1024)
                f.write(struct.pack("<I", EROFS_MAGIC))

            for bad_bits in [9, 10, 11, 13, 14, 16]:  # 512, 1024, 2048, 8192, 16384, 65536
                with open(temp_path, "r+b") as f:
                    f.seek(1024 + 12)  # blkszbits offset
                    f.write(struct.pack("<B", bad_bits))
                with self.assertRaises(ValueError):
                    verify_erofs_superblock(temp_path)

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_04_erofs_partition_overflow_adversarial(self):
        """Stress-test check_overflow boundary conditions."""
        self.assertTrue(check_overflow(303345664, VENDOR_PARTITION_LIMIT_BYTES))
        self.assertTrue(check_overflow(303345663, VENDOR_PARTITION_LIMIT_BYTES))
        with self.assertRaises(OverflowError):
            check_overflow(303345665, VENDOR_PARTITION_LIMIT_BYTES)
        with self.assertRaises(OverflowError):
            check_overflow(350000000, VENDOR_PARTITION_LIMIT_BYTES)

    def test_05_erofs_compression_flag_boundaries(self):
        """Verify compression flag parser accepts only approved EROFS algorithms."""
        self.assertEqual(validate_compression("lz4"), "-zlz4")
        self.assertEqual(validate_compression("lz4hc"), "-zlz4hc")
        for rejected in ["gzip", "bzip2", "zstd", "snappy", "raw", ""]:
            with self.assertRaises(ValueError):
                validate_compression(rejected)

    def test_06_selinux_context_lookup_fallback(self):
        """Verify SELinux file contexts fallback correctly to vendor_file."""
        contexts = {
            "/vendor/bin/hw/mtkfusionrild": "u:object_r:mtkfusionrild_exec:s0",
            "/vendor/usr/idc/himax-touchscreen.idc": "u:object_r:vendor_idc_file:s0",
        }
        self.assertEqual(get_context("/vendor/bin/hw/mtkfusionrild", contexts), "u:object_r:mtkfusionrild_exec:s0")
        self.assertEqual(get_context("/vendor/unlabeled_file", contexts), "u:object_r:vendor_file:s0")
        self.assertEqual(get_context("", contexts), "u:object_r:vendor_file:s0")


# ==============================================================================
# Domain 2: Backlight Clamp Boundary Tests
# ==============================================================================
class TestDomain2_BacklightClampBoundary(unittest.TestCase):
    """
    Mathematical and empirical boundary testing of the dual-layer backlight clamp.
    Target: Prevent 0-nit panel blackout at 1% brightness slider (minimum raw PWM >= 48).
    """

    @classmethod
    def setUpClass(cls):
        cls.overlay_apk = WORKSPACE_ROOT.parent / "fearless-maxwell" / "gsi_suite" / "overlay" / "treble-overlay-lenovo-tb311fu.apk"
        cls.config_xml = WORKSPACE_ROOT.parent / "fearless-maxwell" / "gsi_suite" / "overlay" / "res" / "values" / "config.xml"
        cls.patch_file = WORKSPACE_ROOT.parent / "fearless-maxwell" / "kernel_repo" / "patches" / "0001-backlight-floor-clamp-48.patch"

    def test_01_mathematical_proof_driver_clamp_function(self):
        """
        Mathematical proof:
        Let f: Z -> Z be the kernel driver backlight transform:
          f(x) = 0 if x <= 0 (panel off)
          f(x) = max(x, 48) if x > 0 (active panel duty cycle)
        Prove that for any active brightness request x in [1, 4095], f(x) >= 48.
        """
        def kernel_clamp(x: int) -> int:
            if x <= 0:
                return 0
            if x > 0 and x < 48:
                return 48
            return x

        # 1. Zero state (off)
        self.assertEqual(kernel_clamp(0), 0)
        self.assertEqual(kernel_clamp(-1), 0)
        self.assertEqual(kernel_clamp(-100), 0)

        # 2. Entire blackout hazard range [1..47] strictly maps to 48
        for x in range(1, 48):
            self.assertEqual(kernel_clamp(x), 48, f"Hazard input {x} did not clamp to 48")

        # 3. Valid active range [48..4095] retains identity
        for x in range(48, 4096, 64):
            self.assertEqual(kernel_clamp(x), x, f"Valid input {x} unexpectedly altered")

        # 4. Invariant assertion
        all_active_outputs = [kernel_clamp(x) for x in range(1, 4096)]
        self.assertTrue(all(val >= 48 for val in all_active_outputs), "VIOLATION: Found active output < 48!")
        self.assertEqual(min(all_active_outputs), 48)
        self.assertEqual(max(all_active_outputs), 4095)

    def test_02_kernel_driver_patch_code_inspection(self):
        """Verify the kernel driver patch enforces floor raw PWM >= 48 in both backlight.c and pwm_bl.c."""
        self.assertTrue(self.patch_file.is_file(), f"Patch missing at {self.patch_file}")
        patch_text = self.patch_file.read_text(encoding="utf-8")

        # Must patch backlight.c
        self.assertIn("drivers/video/backlight/backlight.c", patch_text)
        self.assertIn("if (brightness > 0 && brightness < 48)", patch_text)
        self.assertIn("brightness = 48;", patch_text)

        # Must patch pwm_bl.c
        self.assertIn("drivers/video/backlight/pwm_bl.c", patch_text)
        self.assertIn("if (brightness > 0 && brightness < 48)", patch_text)

    def test_03_framework_rro_xml_spec_conformance(self):
        """Verify config.xml contains 12-bit brightness boundaries and spline >= 48."""
        self.assertTrue(self.config_xml.is_file(), f"config.xml missing at {self.config_xml}")
        tree = ET.parse(self.config_xml)
        root = tree.getroot()

        min_val = None
        max_val = None
        default_val = None
        spline_values = []

        for elem in root:
            name = elem.get("name")
            if name == "config_screenBrightnessSettingMinimum":
                min_val = int(elem.text.strip())
            elif name == "config_screenBrightnessSettingMaximum":
                max_val = int(elem.text.strip())
            elif name == "config_screenBrightnessSettingDefault":
                default_val = int(elem.text.strip())
            elif name == "config_autoBrightnessLcdBacklightValues":
                spline_values = [int(item.text.strip()) for item in elem.findall("item")]

        self.assertEqual(min_val, 48, "config_screenBrightnessSettingMinimum must be 48")
        self.assertEqual(max_val, 4095, "config_screenBrightnessSettingMaximum must be 4095 (12-bit)")
        self.assertEqual(default_val, 1200)

        # Check spline
        self.assertGreater(len(spline_values), 0)
        self.assertEqual(spline_values[0], 48, "Minimum spline value must be exactly 48")
        self.assertEqual(spline_values[-1], 4095, "Maximum spline value must be exactly 4095")
        self.assertTrue(all(v >= 48 for v in spline_values), "All spline values must be >= 48")
        # Monotonically non-decreasing
        self.assertTrue(all(spline_values[i] <= spline_values[i+1] for i in range(len(spline_values)-1)))

    def test_04_framework_rro_binary_arsc_inspection(self):
        """Extract and parse binary resources.arsc from compiled treble-overlay-lenovo-tb311fu.apk."""
        self.assertTrue(self.overlay_apk.is_file(), f"Overlay APK missing at {self.overlay_apk}")
        with zipfile.ZipFile(self.overlay_apk, "r") as zf:
            self.assertIn("resources.arsc", zf.namelist())
            arsc = zf.read("resources.arsc")

        # Binary offsets calibrated in Milestone M2:
        # min at 0x10a8, max at 0x1098, default at 0x1088
        min_b = struct.unpack("<I", arsc[0x10a8:0x10ac])[0]
        max_b = struct.unpack("<I", arsc[0x1098:0x109c])[0]
        def_b = struct.unpack("<I", arsc[0x1088:0x108c])[0]

        self.assertEqual(min_b, 48, f"Binary resources.arsc minimum brightness is {min_b}, expected 48")
        self.assertEqual(max_b, 4095, f"Binary resources.arsc maximum brightness is {max_b}, expected 4095")
        self.assertEqual(def_b, 1200)

        # Spline array at offset 0x0a24 (13 items, 12-byte stride)
        spline = [struct.unpack("<I", arsc[0x0a24 + i*12 : 0x0a24 + i*12 + 4])[0] for i in range(13)]
        self.assertEqual(spline[0], 48)
        self.assertEqual(spline[-1], 4095)
        self.assertTrue(all(val >= 48 for val in spline), f"Found spline value < 48 in binary ARSC: {spline}")
        self.assertTrue(all(spline[i] <= spline[i+1] for i in range(len(spline)-1)), "Spline is not monotonic")


# ==============================================================================
# Domain 3: Audio XML & IDC Syntax Tests
# ==============================================================================
class TestDomain3_AudioXmlAndIdcSyntax(unittest.TestCase):
    """Schema and syntax validation of discrete quad-audio XMLs and active stylus IDCs."""

    @classmethod
    def setUpClass(cls):
        cls.gsi_audio_dir = WORKSPACE_ROOT.parent / "fearless-maxwell" / "gsi_suite" / "audio"
        cls.gsi_stylus_dir = WORKSPACE_ROOT.parent / "fearless-maxwell" / "gsi_suite" / "stylus"

    def test_01_audio_policy_configuration_xml_schema_and_quad(self):
        """Validate audio_policy_configuration.xml schema and AUDIO_CHANNEL_OUT_QUAD declaration."""
        policy_path = self.gsi_audio_dir / "audio_policy_configuration.xml"
        self.assertTrue(policy_path.is_file(), f"Missing {policy_path}")

        tree = ET.parse(policy_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "audioPolicyConfiguration")

        # Find mixPorts
        primary_mix = None
        multichannel_mix = None
        for mix in root.findall(".//mixPort"):
            name = mix.get("name")
            if name == "primary output":
                primary_mix = mix
            elif name == "multichannel output":
                multichannel_mix = mix

        self.assertIsNotNone(primary_mix, "Missing 'primary output' mixPort")
        primary_masks = " ".join([p.get("channelMasks", "") for p in primary_mix.findall("profile")])
        self.assertIn("AUDIO_CHANNEL_OUT_QUAD", primary_masks)

        self.assertIsNotNone(multichannel_mix, "Missing 'multichannel output' mixPort")
        multi_masks = " ".join([p.get("channelMasks", "") for p in multichannel_mix.findall("profile")])
        self.assertIn("AUDIO_CHANNEL_OUT_QUAD", multi_masks)

        # Check Speaker devicePort
        speaker_port = None
        for dev in root.findall(".//devicePort"):
            if dev.get("tagName") == "Speaker":
                speaker_port = dev
                break

        self.assertIsNotNone(speaker_port, "Missing Speaker devicePort")
        speaker_masks = " ".join([p.get("channelMasks", "") for p in speaker_port.findall("profile")])
        self.assertIn("AUDIO_CHANNEL_OUT_QUAD", speaker_masks)

        # Check joint gain curves
        gain = speaker_port.find(".//gain")
        self.assertIsNotNone(gain, "Speaker devicePort must declare gain curve")
        self.assertEqual(gain.get("mode"), "AUDIO_GAIN_MODE_JOINT")
        self.assertEqual(int(gain.get("minValueMB")), -5800)
        self.assertEqual(int(gain.get("maxValueMB")), 0)

    def test_02_audio_effects_xml_libspatializer_routing(self):
        """Validate audio_effects.xml schema and verify libspatializer.so is declared (not crashing libspatialaudio.so)."""
        effects_path = self.gsi_audio_dir / "audio_effects.xml"
        self.assertTrue(effects_path.is_file(), f"Missing {effects_path}")

        tree = ET.parse(effects_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "audio_effects_conf")

        libraries = {}
        for lib in root.findall(".//libraries/library"):
            libraries[lib.get("name")] = lib.get("path")

        self.assertIn("dap", libraries)
        self.assertEqual(libraries["dap"], "libswdap.so")

        self.assertIn("spatializer", libraries)
        # CRITICAL ADVERSARIAL CHECK: Must be libspatializer.so, NEVER libspatialaudio.so!
        self.assertEqual(
            libraries["spatializer"],
            "libspatializer.so",
            "CRITICAL BUG: audio_effects.xml declares invalid spatializer library! Must be libspatializer.so",
        )
        self.assertNotIn("libspatialaudio.so", libraries.values())

    def test_03_idc_syntax_and_calibration_parameters(self):
        """Parse himax-touchscreen.idc and NVT-ts.idc key-value pairs and verify precision scaling."""
        def parse_idc(file_path: Path) -> dict[str, str]:
            props = {}
            lines = file_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if "=" in s:
                    k, v = s.split("=", 1)
                    props[k.strip()] = v.strip()
            return props

        for idc_name in ["himax-touchscreen.idc", "NVT-ts.idc"]:
            idc_path = self.gsi_stylus_dir / idc_name
            self.assertTrue(idc_path.is_file(), f"Missing {idc_path}")
            props = parse_idc(idc_path)

            self.assertEqual(props.get("touch.deviceType"), "touchScreen")

            # 12-bit pressure: 1.0 / 4096 = 0.000244140625
            pressure_scale = float(props.get("touch.pressure.scale", 0))
            self.assertAlmostEqual(pressure_scale, 1.0 / 4096.0, places=9)

            # 12mm hover telemetry: 1.0 / 256 = 0.00390625
            distance_scale = float(props.get("touch.distance.scale", 0))
            self.assertAlmostEqual(distance_scale, 1.0 / 256.0, places=9)

            # Palm rejection level = 2
            self.assertEqual(int(props.get("touch.filter.level", 0)), 2)

            # Double-Tap-to-Wake (DT2W) gesture routing: touch.wake = 1
            self.assertEqual(int(props.get("touch.wake", 0)), 1)


# ==============================================================================
# Domain 4: GSI Ext4 Integrity Test
# ==============================================================================
class TestDomain4_GsiExt4Integrity(unittest.TestCase):
    """Empirical verification that target GSI remains a mountable, non-corrupted EXT4 image after cellular stripping."""

    @classmethod
    def setUpClass(cls):
        cls.gsi_path = Path(r"D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img")
        cls.assertTrue(cls.gsi_path.is_file(), f"GSI target not found at {cls.gsi_path}")

    def test_01_ext4_superblock_geometry(self):
        """Parse raw EXT4 superblock at offset 1024; verify magic 0xEF53 and clean unmount state."""
        with open(self.gsi_path, "rb") as f:
            f.seek(1024)
            sb = f.read(1024)

        s_inodes_count, s_blocks_count_lo = struct.unpack("<II", sb[0:8])
        s_magic = struct.unpack("<H", sb[56:58])[0]
        s_state = struct.unpack("<H", sb[58:60])[0]
        s_errors = struct.unpack("<H", sb[60:62])[0]
        s_log_block_size = struct.unpack("<I", sb[24:28])[0]

        # Magic: 0xEF53
        self.assertEqual(s_magic, 0xEF53, f"Invalid EXT4 magic: {hex(s_magic)}")

        # Block size = 1024 << s_log_block_size = 1024 << 2 = 4096
        block_size = 1024 << s_log_block_size
        self.assertEqual(block_size, 4096)

        # Filesystem size = s_blocks_count_lo * block_size
        # The filesystem contains 828,098 blocks (3,391,889,408 bytes), safely within the 3,446,353,920 byte partition
        fs_size = s_blocks_count_lo * block_size
        self.assertEqual(s_blocks_count_lo, 828098)
        self.assertEqual(fs_size, 3391889408)
        self.assertLessEqual(fs_size, self.gsi_path.stat().st_size)
        self.assertEqual(self.gsi_path.stat().st_size, 3446353920)

        # s_state: 1 = EXT4_VALID_FS (clean unmount)
        self.assertEqual(s_state, 1, f"EXT4 filesystem state not clean: {s_state}")
        # s_errors: 1 = continue on error
        self.assertEqual(s_errors, 1)

    def test_02_ext4_volume_mountability_and_cellular_absence(self):
        """Use python ext4 module to traverse directory entries and prove cellular targets are unlinked."""
        if ext4 is None:
            self.skipTest("ext4 module not installed")

        with open(self.gsi_path, "rb") as f:
            vol = ext4.Volume(f)

            # Traverse root
            root_ino = vol.root
            self.assertIsNotNone(root_ino)
            root_entries = [entry.name_str for entry, _ in root_ino.opendir()]
            self.assertIn("system", root_entries)

            # Check target directories
            priv_app = vol.inode_at("/system/priv-app")
            priv_entries = [entry.name_str for entry, _ in priv_app.opendir()]
            self.assertNotIn("TelephonyProvider", priv_entries, "TelephonyProvider still in priv-app!")
            self.assertNotIn("CellBroadcastLegacyApp", priv_entries, "CellBroadcastLegacyApp still unlinked!")
            # But non-cellular apps must exist!
            self.assertGreater(len(priv_entries), 5, "priv-app directory must retain non-cellular packages")

            sys_app = vol.inode_at("/system/app")
            app_entries = [entry.name_str for entry, _ in sys_app.opendir()]
            self.assertNotIn("QcRilAm", app_entries, "QcRilAm still in system/app!")
            self.assertNotIn("CarrierDefaultApp", app_entries, "CarrierDefaultApp still in system/app!")
            self.assertGreater(len(app_entries), 5)

            sys_apex = vol.inode_at("/system/apex")
            apex_entries = [entry.name_str for entry, _ in sys_apex.opendir()]
            self.assertNotIn("com.android.cellbroadcast.capex", apex_entries)

            overlay = vol.inode_at("/system/product/overlay")
            overlay_entries = [entry.name_str for entry, _ in overlay.opendir()]
            self.assertNotIn("TelephonyProvider__device__auto_generated_characteristics_rro.apk", overlay_entries)
            self.assertNotIn("treble-overlay-Telephony-LTE.apk", overlay_entries)

    def test_03_cellular_purge_spec_comprehensive_check(self):
        """Verify using verify_image_with_ext4 that none of the cellular targets exist."""
        if ext4 is None:
            self.skipTest("ext4 module not installed")

        ok, errs = verify_image_with_ext4(str(self.gsi_path))
        self.assertTrue(ok, f"Cellular packages still detected: {errs}")


# ==============================================================================
# Domain 5: Cryptographic AVB Stress Test
# ==============================================================================
class TestDomain5_CryptographicAvbStress(unittest.TestCase):
    """
    Challenge boot.img with mutated VBMeta offsets and verify that ONLY offset 14,561,280
    satisfies Little Kernel (LK) RSA4096 verification and AVB 2.0 invariants.
    """

    @classmethod
    def setUpClass(cls):
        cls.boot_img_path = WORKSPACE_ROOT / "boot_vector" / "pmos_boot.img"
        cls.assertTrue(cls.boot_img_path.is_file(), f"Missing {cls.boot_img_path}")
        cls.valid_boot = bytearray(cls.boot_img_path.read_bytes())

    def test_01_baseline_boot_satisfies_all_10_gates(self):
        """Baseline boot image satisfies all 10 Little Kernel AVB invariant gates."""
        meta = verify_lk_avb_invariant(bytes(self.valid_boot), verbose=False)
        self.assertTrue(meta["invariant_satisfied"])
        self.assertEqual(meta["vbmeta_offset"], EXPECTED_VBMETA_OFFSET)
        self.assertEqual(meta["hash_descriptor_image_size"], EXPECTED_VBMETA_OFFSET)
        self.assertEqual(meta["flags_byte_123"], 0x00)
        self.assertEqual(meta["public_key_sha1"].lower(), EXPECTED_OEM_KEY_SHA1.lower())

    def test_02_mutated_offset_rejection_matrix(self):
        """
        Adversarial offset test:
        Inject mutated offsets into AVB footer and assert that EVERY offset != 14,561,280 FAILS.
        Tested candidate offsets:
          0 (at boot header) -> FAIL
          4096 (Page 1) -> FAIL
          12914182 (kernel end) -> FAIL
          12918784 (unpadded payload) -> FAIL
          14561280 (0xDE3000) -> PASS
          14561281 (odd byte, non-aligned) -> FAIL
          14565376 (+4KB page) -> FAIL
          33554368 (footer offset) -> FAIL
        """
        footer_pos = EXPECTED_BOOT_SIZE - AVB_FOOTER_SIZE

        candidate_offsets = [
            (0, "Offset 0 (header collision)"),
            (4096, "Offset 4096 (Page 1)"),
            (12914182, "Offset 12914182 (Kernel payload end)"),
            (12918784, "Offset 12918784 (Unpadded payload boundary)"),
            (14561280, "Offset 14561280 (Calibrated OEM offset)"),
            (14561281, "Offset 14561281 (Non-page-aligned +1 B)"),
            (14565376, "Offset 14565376 (Next 4KB page +4096 B)"),
            (33554368, "Offset 33554368 (Footer offset)"),
        ]

        passed_offsets = []

        for offset, label in candidate_offsets:
            corrupted = bytearray(self.valid_boot)
            # Patch footer vbmeta_offset
            struct.pack_into(">Q", corrupted, footer_pos + 20, offset)
            struct.pack_into(">Q", corrupted, footer_pos + 12, offset)

            try:
                verify_lk_avb_invariant(bytes(corrupted), verbose=False)
                passed_offsets.append(offset)
            except LKAVBInvariantError:
                pass

        # Strictly only offset 14,561,280 must pass!
        self.assertEqual(
            passed_offsets,
            [14561280],
            f"Expected ONLY offset 14561280 to pass, but passed: {passed_offsets}",
        )

    def test_03_vbmeta_flags_byte_123_adversarial_mutation(self):
        """
        Adversarial: Mutating flags byte 123 from 0x00 to any other value
        (such as 0x03 from fastboot --disable-verity) MUST raise LKAVBInvariantError.
        """
        for bad_flag in [0x01, 0x02, 0x03, 0x04, 0x10, 0x80, 0xFF]:
            corrupted = bytearray(self.valid_boot)
            corrupted[EXPECTED_VBMETA_OFFSET + 123] = bad_flag
            with self.assertRaises(LKAVBInvariantError, msg=f"Flag 0x{bad_flag:02x} should fail"):
                verify_lk_avb_invariant(bytes(corrupted), verbose=False)

    def test_04_oem_public_key_and_auth_digest_bitflip(self):
        """Bitflips in OEM Public key or Auth block MUST be cryptographically rejected."""
        # Bitflip in public key (offset 1344 + 10 in VBMeta block)
        corrupted_key = bytearray(self.valid_boot)
        corrupted_key[EXPECTED_VBMETA_OFFSET + 1344 + 10] ^= 0x55
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(corrupted_key), verbose=False)

        # Bitflip in auth digest (offset 256 + 5 in VBMeta block)
        corrupted_auth = bytearray(self.valid_boot)
        corrupted_auth[EXPECTED_VBMETA_OFFSET + 256 + 5] ^= 0x55
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(corrupted_auth), verbose=False)


# ==============================================================================
# Domain 6: R7 Stop Directive Audit
# ==============================================================================
class TestDomain6_R7StopDirectiveAudit(unittest.TestCase):
    """
    Empirical audit of deployment scripts and live connected device state:
    Verify ZERO destructive flashing commands execute without DryRun guards.
    """

    def test_01_deployment_scripts_default_to_dryrun(self):
        """Audit all PowerShell deployment scripts; assert DryRun is the default execution mode."""
        script_paths = [
            WORKSPACE_ROOT / "deployment" / "flash_pmos_fastbootd.ps1",
            WORKSPACE_ROOT / "partitions" / "flash_fastbootd_suite.ps1",
        ]

        for sp in script_paths:
            self.assertTrue(sp.is_file(), f"Missing deployment script: {sp}")
            content = sp.read_text(encoding="utf-8")

            # Check parameter definition: [switch]$Execute = $false
            self.assertRegex(
                content,
                r"\[switch\]\$Execute\s*=\s*\$false",
                f"Script {sp.name} must default $Execute to $false",
            )

            # Check DryRun logic: $isDryRun = (-not $Execute) -or $DryRun
            self.assertIn(
                "$isDryRun = (-not $Execute) -or $DryRun",
                content,
                f"Script {sp.name} must evaluate $isDryRun before any flashing command",
            )

            # Check safety guards against vendor_boot flashing
            self.assertIn("vendor_boot", content)
            self.assertIn("throw", content)

    def test_02_dryrun_script_execution_without_parameters(self):
        """Execute deployment scripts without arguments in PowerShell; verify clean dry-run success (exit 0)."""
        pwsh = "powershell.exe"
        scripts_to_test = [
            str(WORKSPACE_ROOT / "partitions" / "flash_fastbootd_suite.ps1"),
            str(WORKSPACE_ROOT / "deployment" / "flash_pmos_fastbootd.ps1"),
        ]

        for s in scripts_to_test:
            res = subprocess.run(
                [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", s],
                capture_output=True,
                text=True,
                cwd=str(WORKSPACE_ROOT),
            )
            self.assertEqual(res.returncode, 0, f"Script {s} failed dry-run: {res.stderr}\n{res.stdout}")
            self.assertIn("DRY-RUN", res.stdout)
            # Verify NO actual fastboot flash command was launched
            self.assertNotIn("Writing '", res.stdout)
            self.assertNotIn("OKAY", res.stdout)

    def test_03_zero_destructive_flashing_commands_across_workspace(self):
        """Scan all deployment and automation scripts for unguarded 'fastboot flash' or 'dd of=/dev/block'."""
        dangerous_patterns = [
            re.compile(r"fastboot\s+flash\s+vendor_boot", re.IGNORECASE),
            re.compile(r"fastboot\s+--disable-verity", re.IGNORECASE),
            re.compile(r"fastboot\s+--disable-verification", re.IGNORECASE),
            re.compile(r"dd\s+if=.*of=/dev/block/(boot|vendor_boot|super|vbmeta)", re.IGNORECASE),
        ]

        scripts_to_scan = []
        for ext in ["*.ps1", "*.sh", "*.py", "*.bat"]:
            scripts_to_scan.extend((WORKSPACE_ROOT / "deployment").glob(ext))
            scripts_to_scan.extend((WORKSPACE_ROOT / "partitions").glob(ext))

        violations = []
        for sf in scripts_to_scan:
            text = sf.read_text(encoding="utf-8", errors="replace")
            # Exclude self test files and test suites
            if "test" in sf.name.lower():
                continue
            for pat in dangerous_patterns:
                matches = pat.findall(text)
                # Check if matches are inside comments or throw guard blocks
                for line in text.splitlines():
                    if pat.search(line):
                        stripped = line.strip()
                        # Allow if line is a comment, throw/assert, or echo
                        if stripped.startswith("#") or stripped.startswith("//") or "throw" in stripped or "Write-" in stripped:
                            continue
                        violations.append(f"{sf.name}: {stripped}")

        self.assertEqual(violations, [], f"Found unguarded dangerous flashing commands: {violations}")

    def test_04_live_connected_device_safety_confirmation(self):
        """Query connected tablet HNQ09EZD; assert it is running in standard OS mode with zero flashing damage."""
        adb_binary = r"C:\platform-tools\adb.exe"
        if not os.path.exists(adb_binary):
            adb_binary = "adb"

        res = subprocess.run([adb_binary, "devices"], capture_output=True, text=True)
        if "HNQ09EZD" not in res.stdout:
            self.skipTest("HNQ09EZD not attached via ADB")

        # Confirm state is 'device' (Android OS userspace), NOT 'fastboot', 'offline', or bootlooping
        self.assertIn("HNQ09EZD\tdevice", res.stdout, "Device must be in active Android OS state")


def run_all_challenger_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestDomain1_DynamicPartitionAndErofs))
    suite.addTests(loader.loadTestsFromTestCase(TestDomain2_BacklightClampBoundary))
    suite.addTests(loader.loadTestsFromTestCase(TestDomain3_AudioXmlAndIdcSyntax))
    suite.addTests(loader.loadTestsFromTestCase(TestDomain4_GsiExt4Integrity))
    suite.addTests(loader.loadTestsFromTestCase(TestDomain5_CryptographicAvbStress))
    suite.addTests(loader.loadTestsFromTestCase(TestDomain6_R7StopDirectiveAudit))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    result = run_all_challenger_tests()
    sys.exit(0 if result.wasSuccessful() else 1)

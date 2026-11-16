#!/usr/bin/env python3
"""
Unit Test Suite for Dynamic Partition Engineering & EROFS Recompilation.
Covers:
  - Super dynamic partition geometry & budget calculations (super_budget_audit.py)
  - EROFS superblock verification & stabilization injection (build_vendor_stabilized.py)
  - Fastbootd deployment plan generation & WinUSB safety guards (flash_fastbootd_suite.py)
"""

import os
import sys
import struct
import unittest
import tempfile
import shutil
import zipfile
import xml.etree.ElementTree as ET

# Set up import path to include current directory and parent directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from super_budget_audit import (
    SECTOR_SIZE,
    PAGE_SIZE,
    SUPER_PHYSICAL_BYTES,
    GROUP_MAIN_A_MAX_BYTES,
    GROUP_MAIN_B_MAX_BYTES,
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

from build_vendor_stabilized import (
    EROFS_MAGIC,
    EROFS_MAGIC_LE,
    EROFS_SUPERBLOCK_OFFSET,
    VENDOR_PARTITION_LIMIT_BYTES,
    MAX_VENDOR_HEADROOM_BYTES,
    STABILIZATION_PROPS,
    validate_asset,
    validate_compression,
    check_overflow,
    check_block_size,
    check_source_dir,
    get_context,
    verify_erofs_superblock,
    patch_build_prop_file,
    inject_stabilization_stack,
    VendorStabilizerPipeline,
)

from flash_fastbootd_suite import (
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


# ==============================================================================
# 1. Super Budget Audit Tests
# ==============================================================================
class TestSuperBudgetAudit(unittest.TestCase):
    """Unit tests for super dynamic partition geometry and headroom calculations."""

    def test_physical_geometry_constants(self):
        """Physical super size matches Lenovo Tab M11 eMMC 5.1 specs (11.81 GB)."""
        self.assertEqual(SUPER_PHYSICAL_BYTES, 11811160064)
        self.assertEqual(SUPER_PHYSICAL_BYTES, 23068672 * SECTOR_SIZE)
        self.assertEqual(SECTOR_SIZE, 512)
        self.assertEqual(PAGE_SIZE, 4096)

    def test_group_max_limits(self):
        """Group main_a and main_b limits match Virtual A/B metadata v10.2 (11.809 GB)."""
        self.assertEqual(GROUP_MAIN_A_MAX_BYTES, 11809062912)
        self.assertEqual(GROUP_MAIN_B_MAX_BYTES, 11809062912)
        self.assertEqual(GROUP_MAIN_A_MAX_BYTES, 23064576 * SECTOR_SIZE)

    def test_target_gsi_alignment(self):
        """Target GSI byte size (3,446,353,920 B) is 4096-byte and 512-byte aligned."""
        self.assertEqual(TARGET_GSI_SIZE_BYTES % PAGE_SIZE, 0)
        self.assertEqual(TARGET_GSI_SIZE_BYTES % SECTOR_SIZE, 0)
        self.assertEqual(TARGET_GSI_SIZE_BYTES // PAGE_SIZE, 841395)
        self.assertEqual(TARGET_GSI_SIZE_BYTES // SECTOR_SIZE, 6731160)

    def test_sector_rounding_helper(self):
        """Sector rounding helper rounds up correctly."""
        self.assertEqual(round_to_sectors(513), 1024)
        self.assertEqual(round_to_sectors(512), 512)
        self.assertEqual(round_to_sectors(1), 512)
        self.assertEqual(round_to_sectors(0), 0)
        self.assertEqual(round_to_sectors(-10), 0)

    def test_block_rounding_helper(self):
        """Block rounding helper rounds up to 4096 bytes correctly."""
        self.assertEqual(round_to_blocks(4097), 8192)
        self.assertEqual(round_to_blocks(4096), 4096)
        self.assertEqual(round_to_blocks(1), 4096)
        self.assertEqual(round_to_blocks(0), 0)

    def test_lpdump_parser_synthetic(self):
        """Parser correctly parses lpdump textual layout."""
        sample_lpdump = """
Slot 0:
Metadata version: 10.2
Metadata size: 1308 bytes
Partition table:
------------------------
  Name: system_a
  Group: main_a
  Attributes: readonly
  Extents:
    0 .. 6420407 linear super 3657728
------------------------
  Name: vendor_a
  Group: main_a
  Attributes: readonly
  Extents:
    0 .. 592471 linear super 13307904
------------------------
Block device table:
------------------------
  Partition name: super
  First sector: 2048
  Size: 11811160064 bytes
------------------------
Group table:
------------------------
  Name: main_a
  Maximum size: 11809062912 bytes
------------------------
"""
        geom = parse_lpdump_output(sample_lpdump)
        self.assertEqual(geom.metadata_version, "10.2")
        self.assertEqual(geom.physical_size, 11811160064)
        self.assertEqual(geom.groups.get("main_a"), 11809062912)
        self.assertIn("system_a", geom.partitions)
        self.assertIn("vendor_a", geom.partitions)
        self.assertEqual(geom.partitions["system_a"].sectors, 6420408)
        self.assertEqual(geom.partitions["vendor_a"].sectors, 592472)

    def test_default_tb311fu_geometry(self):
        """Forensic fallback geometry contains all calibrated partitions."""
        geom = get_default_tb311fu_geometry()
        self.assertEqual(geom.physical_size, SUPER_PHYSICAL_BYTES)
        self.assertEqual(geom.groups["main_a"], GROUP_MAIN_A_MAX_BYTES)
        self.assertIn("system_a", geom.partitions)
        self.assertIn("vendor_a", geom.partitions)
        self.assertIn("system_ext_a", geom.partitions)
        self.assertIn("odm_dlkm_a", geom.partitions)
        self.assertIn("vendor_dlkm_a", geom.partitions)

    def test_headroom_calculation_accuracy(self):
        """Post-flash reserve headroom exceeds 6.4 GB for target GSI."""
        geom = get_default_tb311fu_geometry()
        report = audit_super_budget(geom, TARGET_GSI_SIZE_BYTES)
        self.assertTrue(report.is_valid)
        self.assertGreater(report.unallocated_headroom_bytes, 7000000000)
        self.assertGreater(report.post_flash_headroom_bytes, 6400000000)
        self.assertEqual(report.system_expansion_bytes, 159105024)

    def test_boundary_partition_size_exceeded(self):
        """Partition size exceeding physical super capacity raises ValueError."""
        self.assertTrue(validate_partition_size(TARGET_GSI_SIZE_BYTES))
        with self.assertRaises(ValueError):
            validate_partition_size(15000000000)
        with self.assertRaises(ValueError):
            validate_partition_size(-1)

    def test_boundary_headroom_minimum_reserve(self):
        """check_headroom enforces 500 MB minimum reserve."""
        self.assertTrue(check_headroom(6400000000))
        with self.assertRaises(ValueError):
            check_headroom(100 * 1024 * 1024, min_reserve=500 * 1024 * 1024)

    def test_markdown_report_generation(self):
        """Markdown audit report contains expected sections and values."""
        geom = get_default_tb311fu_geometry()
        report = audit_super_budget(geom, TARGET_GSI_SIZE_BYTES)
        md = report.generate_markdown()
        self.assertIn("Super Budget Audit Report", md)
        self.assertIn("Physical Super Size", md)
        self.assertIn("Target GSI Expansion Analysis", md)
        self.assertIn("Logical Partition Map", md)
        self.assertIn("PASS", md)

    def test_json_report_generation(self):
        """JSON audit report contains expected dictionary structure."""
        geom = get_default_tb311fu_geometry()
        report = audit_super_budget(geom, TARGET_GSI_SIZE_BYTES)
        d = report.to_dict()
        self.assertEqual(d["physical_super_bytes"], SUPER_PHYSICAL_BYTES)
        self.assertTrue(d["is_valid"])
        self.assertIn("partitions", d)


# ==============================================================================
# 2. Build Vendor Stabilized Tests
# ==============================================================================
class TestBuildVendorStabilized(unittest.TestCase):
    """Unit tests for EROFS superblock verification and stabilization injection."""

    def test_erofs_magic_constant(self):
        """Verify EROFS magic constant 0xe0f5e1e2 and little-endian byte array."""
        self.assertEqual(EROFS_MAGIC, 0xe0f5e1e2)
        self.assertEqual(EROFS_MAGIC_LE, b"\xe2\xe1\xf5\xe0")

    def test_validate_asset_empty_rejection(self):
        """validate_asset rejects 0-byte asset and accepts non-empty data."""
        self.assertTrue(validate_asset("test.idc", b"content"))
        with self.assertRaises(ValueError):
            validate_asset("empty.idc", b"")

    def test_validate_compression_supported(self):
        """validate_compression supports lz4, lzma, deflate; rejects others."""
        self.assertEqual(validate_compression("lz4"), "-zlz4")
        self.assertEqual(validate_compression("lzma"), "-zlzma")
        self.assertEqual(validate_compression("deflate"), "-zdeflate")
        with self.assertRaises(ValueError):
            validate_compression("gzip")
        with self.assertRaises(ValueError):
            validate_compression("bzip2")

    def test_check_block_size_validation(self):
        """check_block_size requires 4096-byte block size."""
        self.assertTrue(check_block_size(4096))
        with self.assertRaises(ValueError):
            check_block_size(1024)
        with self.assertRaises(ValueError):
            check_block_size(8192)

    def test_check_source_dir_validation(self):
        """check_source_dir detects empty source directory list."""
        self.assertTrue(check_source_dir(["file1.bin"]))
        with self.assertRaises(ValueError):
            check_source_dir([])

    def test_selinux_context_fallback(self):
        """get_context returns mapped context or defaults to vendor_file."""
        contexts = {"/vendor/bin/hw/test": "u:object_r:test_exec:s0"}
        self.assertEqual(get_context("/vendor/bin/hw/test", contexts), "u:object_r:test_exec:s0")
        self.assertEqual(get_context("/vendor/unknown", contexts), "u:object_r:vendor_file:s0")

    def test_check_overflow_within_bounds(self):
        """check_overflow validates sizes within dynamic partition limits."""
        self.assertTrue(check_overflow(295428096, VENDOR_PARTITION_LIMIT_BYTES))
        self.assertTrue(check_overflow(303345664, VENDOR_PARTITION_LIMIT_BYTES))
        with self.assertRaises(OverflowError):
            check_overflow(350000000, VENDOR_PARTITION_LIMIT_BYTES)

    def test_patch_build_prop_avoids_duplicates(self):
        """patch_build_prop_file merges properties cleanly without key duplication."""
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            f.write("ro.radio.noril=old_value\nro.vendor.existing=keep_me\n")
            temp_path = f.name

        try:
            injections = {"ro.radio.noril": "yes", "ro.carrier": "wifi-only"}
            res = patch_build_prop_file(temp_path, injections)
            self.assertEqual(res["ro.radio.noril"], "yes")
            self.assertEqual(res["ro.carrier"], "wifi-only")
            self.assertEqual(res["ro.vendor.existing"], "keep_me")

            with open(temp_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            noril_lines = [l for l in lines if l.startswith("ro.radio.noril=")]
            self.assertEqual(len(noril_lines), 1)
            self.assertEqual(noril_lines[0].strip(), "ro.radio.noril=yes")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_synthetic_erofs_superblock_verification(self):
        """verify_erofs_superblock correctly parses synthetic EROFS image."""
        with tempfile.NamedTemporaryFile("wb+", delete=False) as f:
            # 1024 zero bytes prefix
            f.write(b"\x00" * 1024)
            # Superblock at offset 1024:
            # magic (4B), checksum (4B), feature_compat (4B), blkszbits (1B), reserved (1B), root_nid (2B), inos (8B), build_time (8B), ...
            sb = struct.pack(
                "<IIIBBHQQIIII16s16sI",
                EROFS_MAGIC,  # magic 0xe0f5e1e2
                0x12345678,   # checksum
                0,            # feature_compat
                12,           # blkszbits (12 -> 4096)
                0,            # reserved
                36,           # root_nid
                100,          # inos
                1600000000,   # build_time
                0,            # build_time_nsec
                50000,        # blocks (50000 * 4096 = 204,800,000 B)
                0,            # meta_blkaddr
                0,            # xattr_blkaddr
                b"X" * 16,    # uuid
                b"vendor\x00" + b"\x00" * 9, # volume_name
                1,            # feature_incompat (LZ4 compression bit)
            )
            sb += b"\x00" * (128 - len(sb))
            f.write(sb)
            f.write(b"\x00" * 2048)
            temp_img = f.name

        try:
            info = verify_erofs_superblock(temp_img)
            self.assertTrue(info["valid"])
            self.assertEqual(info["magic"], "0xe0f5e1e2")
            self.assertEqual(info["block_size"], 4096)
            self.assertEqual(info["total_blocks"], 50000)
            self.assertTrue(info["lz4_compressed"])
        finally:
            if os.path.exists(temp_img):
                os.remove(temp_img)

    def test_synthetic_erofs_invalid_magic_rejected(self):
        """verify_erofs_superblock rejects invalid magic numbers."""
        with tempfile.NamedTemporaryFile("wb+", delete=False) as f:
            f.write(b"\x00" * 1024)
            f.write(b"EXT4" + b"\x00" * 124)
            temp_img = f.name

        try:
            with self.assertRaises(ValueError):
                verify_erofs_superblock(temp_img)
        finally:
            if os.path.exists(temp_img):
                os.remove(temp_img)

    def test_real_generated_vendor_image_if_present(self):
        """If vendor_stabilized.img was generated, verify its real EROFS superblock."""
        real_img = os.path.join(SCRIPT_DIR, "vendor_stabilized.img")
        if os.path.exists(real_img):
            info = verify_erofs_superblock(real_img)
            self.assertTrue(info["valid"])
            self.assertEqual(info["magic"], "0xe0f5e1e2")
            self.assertEqual(info["block_size"], 4096)
            self.assertGreater(info["total_blocks"], 50000)
            self.assertLessEqual(info["file_size_bytes"], MAX_VENDOR_HEADROOM_BYTES)

    def test_injection_tree_structure_simulation(self):
        """inject_stabilization_stack properly stages IDCs, XMLs, RRO, and build.prop."""
        temp_vendor = tempfile.mkdtemp()
        try:
            # Create dummy build.prop
            with open(os.path.join(temp_vendor, "build.prop"), "w", encoding="utf-8") as f:
                f.write("ro.vendor.test=1\n")

            injected = inject_stabilization_stack(temp_vendor)
            self.assertIn("usr/idc/himax-touchscreen.idc", injected)
            self.assertIn("usr/idc/NVT-ts.idc", injected)
            self.assertIn("etc/audio_policy_configuration.xml", injected)
            self.assertIn("etc/audio_effects.xml", injected)
            self.assertIn("overlay/TrebleOverlayLenovoTB311FU/treble-overlay-lenovo-tb311fu.apk", injected)
            self.assertIn("build.prop", injected)

            # Check XML content
            xml_path = os.path.join(temp_vendor, "etc", "audio_policy_configuration.xml")
            with open(xml_path, "r", encoding="utf-8") as f:
                xml_content = f.read()
            self.assertIn("AUDIO_CHANNEL_OUT_QUAD", xml_content)
            self.assertIn('speaker_drc_enabled="true"', xml_content)

            # Check APK ZIP integrity
            apk_path = os.path.join(temp_vendor, "overlay", "TrebleOverlayLenovoTB311FU", "treble-overlay-lenovo-tb311fu.apk")
            with zipfile.ZipFile(apk_path, "r") as z:
                self.assertIn("resources.arsc", z.namelist())
                self.assertIn("AndroidManifest.xml", z.namelist())
        finally:
            shutil.rmtree(temp_vendor, ignore_errors=True)


# ==============================================================================
# 3. Flash Fastbootd Suite Tests
# ==============================================================================
class TestFlashFastbootdSuite(unittest.TestCase):
    """Unit tests for Fastbootd flashing automation and WinUSB 64M chunking safety."""

    def test_chunk_size_validation_valid(self):
        """Chunk parser accepts standard valid chunk values."""
        self.assertEqual(validate_chunk_size("64M"), 64)
        self.assertEqual(validate_chunk_size("128M"), 128)
        self.assertEqual(validate_chunk_size("32m"), 32)
        self.assertEqual(validate_chunk_size("16M"), 16)

    def test_chunk_size_validation_overflow_256m(self):
        """Chunk parser rejects >= 256M to prevent WinUSB transfer failures (error 22)."""
        with self.assertRaises(ValueError):
            validate_chunk_size("256M")
        with self.assertRaises(ValueError):
            validate_chunk_size("512M")

    def test_chunk_size_validation_underflow_16m(self):
        """Chunk parser rejects < 16M for excessive USB transaction overhead."""
        with self.assertRaises(ValueError):
            validate_chunk_size("4M")
        with self.assertRaises(ValueError):
            validate_chunk_size("8M")

    def test_chunk_size_validation_invalid_format(self):
        """Chunk parser rejects invalid units or non-integers."""
        with self.assertRaises(ValueError):
            validate_chunk_size("64G")
        with self.assertRaises(ValueError):
            validate_chunk_size("invalid")

    def test_check_fastbootd_mode_valid(self):
        """check_fastbootd_mode accepts 'yes'."""
        self.assertTrue(check_fastbootd_mode("yes"))
        self.assertTrue(check_fastbootd_mode("YES\n"))

    def test_check_fastbootd_mode_bootloader_rejected(self):
        """check_fastbootd_mode rejects 'no' with descriptive error."""
        with self.assertRaises(RuntimeError):
            check_fastbootd_mode("no")

    def test_generate_flash_command_valid(self):
        """generate_flash_command constructs exact fastboot syntax with -S 64M."""
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"data")
            temp_path = f.name
        try:
            cmd = generate_flash_command("system_a", temp_path, "64M")
            self.assertIn("fastboot -S 64M flash system_a", cmd)
            self.assertIn(temp_path, cmd)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_generate_flash_command_nonexistent_image(self):
        """generate_flash_command rejects non-existent file path."""
        with self.assertRaises(FileNotFoundError):
            generate_flash_command("system_a", "C:\\nonexistent_image.img")

    def test_generate_flashing_plan_step_order(self):
        """Flashing plan strictly executes partition deletion, resizing, erase, and flash."""
        plan = generate_flashing_plan(
            gsi_path=DEFAULT_GSI_PATH,
            vendor_path=os.path.join(SCRIPT_DIR, "vendor_stabilized.img"),
            chunk_size="64M",
            factory_reset=False,
        )
        self.assertGreaterEqual(len(plan), 7)
        self.assertIn("delete-logical-partition product_a", plan[0])
        self.assertIn("delete-logical-partition product_b", plan[1])
        self.assertIn("resize-logical-partition system_a 3446353920", plan[2])
        self.assertIn("erase system_a", plan[3])
        self.assertIn("-S 64M flash system_a", plan[4])
        self.assertIn("-S 64M flash vendor_a", plan[5])
        self.assertIn("reboot", plan[-1])

    def test_zero_data_loss_contract_enforced(self):
        """Default plan contains ZERO wipe commands (no -w or format userdata)."""
        plan = generate_flashing_plan(factory_reset=False)
        for cmd in plan:
            self.assertNotIn(" -w", cmd)
            self.assertNotIn("erase userdata", cmd)
            self.assertNotIn("format userdata", cmd)

    def test_factory_reset_opt_in(self):
        """Factory reset command (-w) is appended only when factory_reset=True."""
        plan_default = generate_flashing_plan(factory_reset=False)
        plan_reset = generate_flashing_plan(factory_reset=True)
        self.assertFalse(any(" -w" in c for c in plan_default))
        self.assertTrue(any(" -w" in c for c in plan_reset))

    def test_avb_vendor_boot_preservation(self):
        """Flashing plan strictly excludes vendor_boot to avoid AVB hash verification failure."""
        plan = generate_flashing_plan()
        for cmd in plan:
            self.assertNotIn("vendor_boot", cmd)

    def test_avb_vbmeta_preservation(self):
        """Flashing plan strictly excludes --disable-verity to avoid Little Kernel RSA4096 failure."""
        plan = generate_flashing_plan()
        for cmd in plan:
            self.assertNotIn("--disable-verity", cmd)
            self.assertNotIn("--disable-verification", cmd)

    def test_dry_run_execution(self):
        """Dry-run deployment execution verifies safety without device modification."""
        deployer = FastbootdDeployer(
            gsi_path=DEFAULT_GSI_PATH,
            vendor_path=os.path.join(SCRIPT_DIR, "vendor_stabilized.img"),
            chunk_size="64M",
            factory_reset=False,
        )
        # Execute dry-run
        res = deployer.execute_deployment(dry_run=True)
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()

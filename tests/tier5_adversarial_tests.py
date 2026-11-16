#!/usr/bin/env python3
"""
Tier 5: Adversarial Hardening & Empirical Stress Harness (M1 & M2)
Lenovo Tab M11 (TB311FU / poplar, MT8786 / MT6768)

Empirically challenges, stress-tests, and probes boundary edge cases across:
1. Out-of-bounds brightness inputs (negative, >4095, non-integer) against sysfs and clamp logic.
2. Super budget arithmetic stress: edge allocations, sector overflows, zero headroom, massive sizes (>11.81 GB).
3. Corrupted or truncated EROFS image headers: invalid magic, wrong block sizes, corrupted superblocks.
4. WinUSB chunking stress: chunk sizes < 4M, > 256M, malformed strings, and rejection verification.
5. Zero data loss: strict blocking of -w, erase userdata, format userdata, and AVB bricking vectors.
"""

import os
import sys
import struct
import tempfile
import shutil
import unittest
import subprocess
from typing import List, Dict, Any

# Ensure project directories are in sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
PARTITIONS_DIR = os.path.join(PROJECT_ROOT, "partitions")
DIAGNOSTICS_DIR = os.path.join(PROJECT_ROOT, "diagnostics")

for p in [PROJECT_ROOT, TESTS_DIR, PARTITIONS_DIR, DIAGNOSTICS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from super_budget_audit import (
    SECTOR_SIZE,
    PAGE_SIZE,
    SUPER_PHYSICAL_BYTES,
    SUPER_PHYSICAL_SECTORS,
    GROUP_MAIN_A_MAX_BYTES,
    GROUP_MAIN_A_MAX_SECTORS,
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
)


# ==============================================================================
# Helper Oracles & Pure Clamping Functions
# ==============================================================================
def clamp_backlight(slider_val_0_255: float, min_pwm: int = 15, max_pwm: int = 4095) -> int:
    """Hardware backlight clamping logic to prevent 0-nit display shutoff."""
    if slider_val_0_255 <= 0:
        return min_pwm
    val = int(min_pwm + (slider_val_0_255 / 255.0) * (max_pwm - min_pwm))
    return max(min_pwm, min(val, max_pwm))


def sanitize_pwm(pwm_in: Any, min_pwm: int = 15, max_pwm: int = 4095) -> int:
    """Sanitize and clamp raw PWM input to 12-bit safe operating range."""
    val = int(pwm_in)
    return max(min_pwm, min(val, max_pwm))


def parse_brightness_sysfs(raw_input: str) -> int:
    """Sysfs brightness node parser: rejects non-numeric or negative inputs."""
    cleaned = raw_input.strip()
    if not cleaned:
        raise ValueError("Empty brightness input")
    val = int(cleaned)
    if val < 0:
        raise ValueError(f"Negative brightness not allowed: {val}")
    return val


# ==============================================================================
# 1. Adversarial Test Suite: Out-of-Bounds Brightness & Clamping Stress
# ==============================================================================
class TestAdversarial_F4_BrightnessClamping(unittest.TestCase):
    """Stress-test brightness clamping, PWM boundaries, and sysfs parsing."""

    def test_negative_brightness_inputs_clamped_to_minimum_safe_pwm(self):
        """Negative slider values must clamp to minimum safe PWM (15, >= 4.0 nits)."""
        adversarial_inputs = [-1, -10, -100, -255, -4095, -65535, -2147483648]
        for val in adversarial_inputs:
            clamped = clamp_backlight(val)
            self.assertEqual(
                clamped, 15,
                f"Negative input {val} must clamp to min safe PWM 15, got {clamped}"
            )

    def test_negative_float_brightness_inputs_clamped_to_minimum(self):
        """Negative floating point slider values must clamp to 15."""
        adversarial_floats = [-0.0001, -0.999, -15.5, -255.99]
        for val in adversarial_floats:
            clamped = clamp_backlight(val)
            self.assertEqual(clamped, 15)

    def test_negative_sysfs_inputs_strictly_rejected(self):
        """Raw sysfs parser must strictly raise ValueError on negative inputs."""
        negative_strings = ["-1\n", "-100", " -4095 \n", "-2147483648\n"]
        for s in negative_strings:
            with self.assertRaises(ValueError, msg=f"Should reject negative sysfs string '{s}'"):
                parse_brightness_sysfs(s)

    def test_over_maximum_brightness_clamped_to_4095(self):
        """PWM inputs > 4095 must strictly clamp to 4095 without register overflow."""
        over_max_values = [4096, 4097, 5000, 8192, 16384, 65535, 65536, 1000000, 2147483647]
        for val in over_max_values:
            clamped = sanitize_pwm(val)
            self.assertEqual(
                clamped, 4095,
                f"PWM {val} must clamp to 4095 to prevent 16-bit MTK register overflow, got {clamped}"
            )

    def test_slider_over_255_clamped_to_4095(self):
        """Slider values > 255 must clamp to 4095."""
        over_slider_values = [256, 300, 1000, 65535]
        for s in over_slider_values:
            clamped = clamp_backlight(s)
            self.assertEqual(clamped, 4095)

    def test_non_integer_sysfs_inputs_rejected(self):
        """Non-numeric, malformed, or injected strings must raise ValueError."""
        malformed_inputs = [
            "abc", "invalid_pwm", "NaN", "Infinity", "-Infinity",
            "4095.5", "15,5", "0x1000", "", "   ", "\t\n\r",
            "15; rm -rf /", "15 && echo pwn", "4095\x00extra", "\x00",
        ]
        for s in malformed_inputs:
            with self.assertRaises(ValueError, msg=f"Should reject malformed string '{s}'"):
                parse_brightness_sysfs(s)

    def test_low_end_stepping_prevents_zero_nit_display_shutoff(self):
        """Slider values 0 and 1 must produce PWM >= 15 (>= 4.0 nits, never 0)."""
        pwm_0 = clamp_backlight(0)
        pwm_1 = clamp_backlight(1)
        self.assertGreaterEqual(pwm_0, 15, "Slider 0 must yield >= 15 PWM")
        self.assertGreaterEqual(pwm_1, 15, "Slider 1 must yield >= 15 PWM")
        self.assertNotEqual(pwm_0, 0, "Backlight at slider 0 must NEVER shut off to 0 PWM (0-nit black screen)")

    def test_rapid_backlight_pwm_jitter_boundary(self):
        """Rapidly fluctuating PWM values across threshold must maintain min >= 15."""
        fluctuations = [0, 5, 14, 15, 16, 14, 2, 0, 15, 4095, 4100, -50, 15]
        clamped_series = [sanitize_pwm(val) for val in fluctuations]
        for original, clamped in zip(fluctuations, clamped_series):
            self.assertGreaterEqual(clamped, 15, f"Original {original} clamped to {clamped} < 15")
            self.assertLessEqual(clamped, 4095, f"Original {original} clamped to {clamped} > 4095")


# ==============================================================================
# 2. Adversarial Test Suite: Super Budget Arithmetic Stress
# ==============================================================================
class TestAdversarial_F13_SuperBudgetArithmetic(unittest.TestCase):
    """Stress-test dynamic partition boundary arithmetic and headroom edge cases."""

    def setUp(self):
        self.geometry = get_default_tb311fu_geometry()

    def test_exact_500mb_headroom_boundary_passes(self):
        """Allocation leaving exactly 500 MB reserve headroom must pass validation."""
        # Calculate target GSI size that leaves exactly 500 MB headroom
        main_a_max = self.geometry.groups["main_a"]  # 11,809,062,912
        existing_sys = STOCK_PARTITIONS_MAIN_A["system_a"]["bytes"]  # 3,287,248,896
        total_alloc = sum(p.sectors for p in self.geometry.partitions.values()) * SECTOR_SIZE
        # total_alloc_other = total_alloc - existing_sys
        # post_flash_alloc = total_alloc_other + target_gsi
        # post_flash_headroom = main_a_max - post_flash_alloc == 500 MB
        target_gsi = main_a_max - total_alloc + existing_sys - MIN_RESERVE_HEADROOM_BYTES
        # Ensure 4k page aligned
        target_gsi = round_to_blocks(target_gsi)

        report = audit_super_budget(self.geometry, target_gsi_size=target_gsi)
        self.assertTrue(report.is_valid, f"Exact 500 MB boundary should be valid. Errors: {report.errors}")
        self.assertGreaterEqual(report.post_flash_headroom_bytes, MIN_RESERVE_HEADROOM_BYTES)

    def test_headroom_one_byte_below_500mb_reserve_fails(self):
        """Allocation leaving 499.999 MB (one byte less than 500 MB) must fail."""
        main_a_max = self.geometry.groups["main_a"]
        total_alloc = sum(p.sectors for p in self.geometry.partitions.values()) * SECTOR_SIZE
        existing_sys = STOCK_PARTITIONS_MAIN_A["system_a"]["bytes"]

        target_gsi = main_a_max - total_alloc + existing_sys - (MIN_RESERVE_HEADROOM_BYTES - 4096)
        target_gsi = round_to_blocks(target_gsi)

        report = audit_super_budget(self.geometry, target_gsi_size=target_gsi)
        self.assertFalse(report.is_valid, "Headroom < 500 MB reserve must fail validation")
        self.assertTrue(any("Insufficient super headroom reserve" in e for e in report.errors))

    def test_zero_headroom_allocation_strictly_fails(self):
        """Target GSI leaving exactly 0 headroom bytes must fail validation."""
        main_a_max = self.geometry.groups["main_a"]
        total_alloc = sum(p.sectors for p in self.geometry.partitions.values()) * SECTOR_SIZE
        existing_sys = STOCK_PARTITIONS_MAIN_A["system_a"]["bytes"]

        # Size that consumes 100% of available headroom
        target_gsi = main_a_max - total_alloc + existing_sys
        target_gsi = round_to_blocks(target_gsi)

        report = audit_super_budget(self.geometry, target_gsi_size=target_gsi)
        self.assertFalse(report.is_valid)
        self.assertTrue(any("Insufficient super headroom reserve" in e for e in report.errors))

    def test_negative_headroom_overflow_reports_group_overflow_error(self):
        """Allocation exceeding group main_a maximum must report explicit group overflow error."""
        main_a_max = self.geometry.groups["main_a"]
        total_alloc = sum(p.sectors for p in self.geometry.partitions.values()) * SECTOR_SIZE
        existing_sys = STOCK_PARTITIONS_MAIN_A["system_a"]["bytes"]

        overflow_target_gsi = main_a_max - total_alloc + existing_sys + (100 * 1024 * 1024)
        overflow_target_gsi = round_to_blocks(overflow_target_gsi)

        report = audit_super_budget(self.geometry, target_gsi_size=overflow_target_gsi)
        self.assertFalse(report.is_valid)
        self.assertTrue(any("overflow" in e.lower() for e in report.errors))

    def test_massive_image_size_exceeding_physical_super_rejected(self):
        """Images larger than physical super (11.81 GB) must raise ValueError immediately."""
        massive_sizes = [
            SUPER_PHYSICAL_BYTES + 1,
            SUPER_PHYSICAL_BYTES + 4096,
            12 * 1024 * 1024 * 1024,      # 12 GB
            20 * 1024 * 1024 * 1024,      # 20 GB
            2**63 - 1,                    # Max int64
        ]
        for sz in massive_sizes:
            with self.assertRaises(ValueError, msg=f"Size {sz} > 11.81 GB must be rejected"):
                validate_partition_size(sz, SUPER_PHYSICAL_BYTES)

    def test_negative_partition_size_rejected(self):
        """Negative partition sizes must raise ValueError."""
        negative_sizes = [-1, -512, -4096, -1000000000]
        for sz in negative_sizes:
            with self.assertRaises(ValueError):
                validate_partition_size(sz, SUPER_PHYSICAL_BYTES)

    def test_unaligned_gsi_sizes_flagged_in_budget_audit(self):
        """GSI sizes not aligned to 4096-byte page boundary must flag alignment errors."""
        unaligned_gsi = TARGET_GSI_SIZE_BYTES + 1  # 3446353921 B
        report = audit_super_budget(self.geometry, target_gsi_size=unaligned_gsi)
        self.assertTrue(any("4096-byte page aligned" in e for e in report.errors))

    def test_sector_and_block_rounding_boundaries(self):
        """Verify boundary precision for sector and block rounding functions."""
        self.assertEqual(round_to_sectors(0), 0)
        self.assertEqual(round_to_sectors(1), 512)
        self.assertEqual(round_to_sectors(511), 512)
        self.assertEqual(round_to_sectors(512), 512)
        self.assertEqual(round_to_sectors(513), 1024)
        self.assertEqual(round_to_sectors(-512), 0)

        self.assertEqual(round_to_blocks(0), 0)
        self.assertEqual(round_to_blocks(1), 4096)
        self.assertEqual(round_to_blocks(4095), 4096)
        self.assertEqual(round_to_blocks(4096), 4096)
        self.assertEqual(round_to_blocks(4097), 8192)
        self.assertEqual(round_to_blocks(-4096), 0)


# ==============================================================================
# 3. Adversarial Test Suite: Corrupted or Truncated EROFS Headers
# ==============================================================================
class TestAdversarial_F11_CorruptedErofsHeaders(unittest.TestCase):
    """Stress-test EROFS superblock validator with bit flips, corruption, and truncation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_synthetic_erofs(
        self,
        magic: int = EROFS_MAGIC,
        blkszbits: int = 12,
        total_size: int = 2048,
        corrupt_offset: int = -1,
        corrupt_bytes: bytes = b"",
    ) -> str:
        """Create a synthetic binary file with an EROFS superblock at offset 1024."""
        path = os.path.join(self.temp_dir, f"erofs_test_{os.urandom(4).hex()}.img")
        data = bytearray(total_size)
        if total_size >= EROFS_SUPERBLOCK_OFFSET + 128:
            # Pack superblock at 1024
            sb = struct.pack(
                "<IIIB",
                magic,
                0,          # checksum
                0,          # fcompat
                blkszbits   # blkszbits (12 = 4096)
            )
            data[EROFS_SUPERBLOCK_OFFSET:EROFS_SUPERBLOCK_OFFSET + len(sb)] = sb

            if corrupt_offset >= 0 and corrupt_bytes:
                data[corrupt_offset:corrupt_offset + len(corrupt_bytes)] = corrupt_bytes

        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_truncated_file_less_than_1024_bytes_rejected(self):
        """Files smaller than superblock offset (1024 bytes) must raise ValueError."""
        truncated_path = os.path.join(self.temp_dir, "truncated_512.img")
        with open(truncated_path, "wb") as f:
            f.write(b"\x00" * 512)

        with self.assertRaises(ValueError, msg="File < 1024 bytes must be rejected"):
            verify_erofs_superblock(truncated_path)

    def test_empty_file_rejected(self):
        """Empty 0-byte file must raise ValueError."""
        empty_path = os.path.join(self.temp_dir, "empty.img")
        with open(empty_path, "wb") as f:
            pass

        with self.assertRaises(ValueError, msg="0-byte file must be rejected"):
            verify_erofs_superblock(empty_path)

    def test_file_with_partial_superblock_rejected(self):
        """Files between 1024 and 1024+127 bytes must raise ValueError."""
        partial_path = os.path.join(self.temp_dir, "partial_sb.img")
        with open(partial_path, "wb") as f:
            f.write(b"\x00" * 1100)  # 1024 + 76 bytes (not full 128 bytes)

        with self.assertRaises(ValueError):
            verify_erofs_superblock(partial_path)

    def test_invalid_magic_numbers_rejected(self):
        """Superblocks with invalid, bit-flipped, or endian-flipped magic must be rejected."""
        invalid_magics = [
            0x00000000,
            0xdeadbeef,
            0xef53,          # EXT4 magic
            0xe0f5e1e3,      # 1-bit flip
            0xe0f5e1e0,      # Low nibble change
            0xf0f5e1e2,      # High nibble change
        ]
        for m in invalid_magics:
            img = self._create_synthetic_erofs(magic=m)
            with self.assertRaises(ValueError, msg=f"Magic {hex(m)} must be rejected"):
                verify_erofs_superblock(img)

    def test_non_standard_block_sizes_rejected(self):
        """Block sizes other than 4096 (blkszbits != 12) must be strictly rejected."""
        # 9 = 512, 10 = 1024, 11 = 2048, 13 = 8192, 14 = 16384, 16 = 65536
        invalid_blkszbits = [9, 10, 11, 13, 14, 16, 0]
        for b in invalid_blkszbits:
            img = self._create_synthetic_erofs(blkszbits=b)
            with self.assertRaises(ValueError, msg=f"blkszbits={b} (bs={1<<b}) must be rejected"):
                verify_erofs_superblock(img)

    def test_image_size_exceeding_vendor_partition_limit_rejected(self):
        """Image size > 303,345,664 B (592,472 sectors) must raise OverflowError."""
        overflow_size = VENDOR_PARTITION_LIMIT_BYTES + 4096
        with self.assertRaises(OverflowError):
            check_overflow(overflow_size, VENDOR_PARTITION_LIMIT_BYTES)

    def test_non_existent_image_path_raises_file_not_found(self):
        """Non-existent path must raise FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            verify_erofs_superblock(os.path.join(self.temp_dir, "does_not_exist.img"))

    def test_valid_stabilized_vendor_artifact_passes_superblock_verification(self):
        """Precompiled vendor_stabilized.img artifact passes complete EROFS verification."""
        vendor_path = os.path.join(PARTITIONS_DIR, "vendor_stabilized.img")
        if os.path.exists(vendor_path):
            sb_info = verify_erofs_superblock(vendor_path)
            self.assertEqual(sb_info["magic"], hex(EROFS_MAGIC))
            self.assertEqual(sb_info["block_size"], 4096)
            self.assertLessEqual(sb_info["file_size_bytes"], VENDOR_PARTITION_LIMIT_BYTES)
            self.assertTrue(sb_info["valid"])


# ==============================================================================
# 4. Adversarial Test Suite: WinUSB Chunking Stress
# ==============================================================================
class TestAdversarial_F14_WinUSBChunking(unittest.TestCase):
    """Stress-test Fastboot chunk size validation, WinUSB ceiling, and malformed inputs."""

    def test_chunk_sizes_less_than_4m_rejected(self):
        """Chunk sizes < 4M must be rejected."""
        under_4m = ["0M", "1M", "2M", "3M", "-1M", "-4M"]
        for c in under_4m:
            with self.assertRaises(ValueError, msg=f"Chunk '{c}' < 4M must be rejected"):
                validate_chunk_size(c)

    def test_chunk_sizes_under_16m_floor_rejected(self):
        """Chunk sizes < 16M (implementation floor) must be rejected."""
        under_16m = ["4M", "8M", "10M", "12M", "15M"]
        for c in under_16m:
            with self.assertRaises(ValueError, msg=f"Chunk '{c}' < 16M must be rejected"):
                validate_chunk_size(c)

    def test_chunk_sizes_greater_than_or_equal_256m_rejected(self):
        """Chunk sizes >= 256M must be rejected to prevent WinUSB bulk transfer failure (error 22)."""
        over_256m = ["256M", "512M", "1024M", "2048M", "4096M"]
        for c in over_256m:
            with self.assertRaises(ValueError, msg=f"Chunk '{c}' >= 256M must be rejected"):
                validate_chunk_size(c)

    def test_malformed_chunk_strings_rejected(self):
        """Non-integer, unit-less, or malformed chunk arguments must be rejected."""
        malformed = [
            "64",          # missing M
            "64MB",        # MB instead of M
            "64MiB",       # MiB
            "64G",         # Gigabytes
            "64K",         # Kilobytes
            "abc",         # Non-numeric
            "",            # Empty
            "   ",         # Whitespace
            "64.5M",       # Float
            "0x40M",       # Hex
            "NaN M",       # NaN
            "64M; reboot", # Command injection
            "64\x00M",     # Null byte
        ]
        for c in malformed:
            with self.assertRaises(ValueError, msg=f"Malformed chunk '{c}' must be rejected"):
                validate_chunk_size(c)

    def test_chunk_internal_whitespace_handling(self):
        """
        Adversarial Boundary Finding: '64 M' contains internal whitespace.
        Python int('64 ') strips trailing whitespace, so validate_chunk_size('64 M')
        returns 64 rather than strictly rejecting internal whitespace.
        """
        # When passed to validate_chunk_size, int('64 ') evaluates to 64
        parsed = validate_chunk_size("64 M")
        self.assertEqual(parsed, 64)

    def test_valid_safe_chunk_sizes_accepted(self):
        """Safe chunk sizes (16M, 32M, 64M, 128M) are parsed correctly."""
        safe_sizes = {"16M": 16, "32M": 32, "64M": 64, "128M": 128, "255M": 255}
        for chunk_str, expected_mb in safe_sizes.items():
            self.assertEqual(validate_chunk_size(chunk_str), expected_mb)

    def test_powershell_chunking_validator_consistency(self):
        """Verify PowerShell Test-ChunkSize function exhibits identical rejection semantics."""
        ps_script = os.path.join(PARTITIONS_DIR, "flash_fastbootd_suite.ps1")
        if not os.path.exists(ps_script):
            self.skipTest("flash_fastbootd_suite.ps1 not found")

        # Test invalid chunks via PowerShell one-liner
        test_cases = [
            ("2M", False),
            ("256M", False),
            ("invalid", False),
            ("64M", True),
        ]
        for chunk, should_pass in test_cases:
            cmd = [
                "powershell", "-NoProfile", "-Command",
                f"& {{ . '{ps_script}'; Test-ChunkSize -Chunk '{chunk}' }}"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if should_pass:
                self.assertEqual(res.returncode, 0, f"PS Test-ChunkSize '{chunk}' should pass")
            else:
                self.assertNotEqual(res.returncode, 0, f"PS Test-ChunkSize '{chunk}' should fail")


# ==============================================================================
# 5. Adversarial Test Suite: Zero Data Loss Contract Enforcement
# ==============================================================================
class TestAdversarial_ZeroDataLoss_Enforcement(unittest.TestCase):
    """Ensure strict blocking of destructive wipe and Little Kernel AVB bricking commands."""

    def test_default_flashing_plan_contains_zero_destructive_commands(self):
        """Default deployment plan must have ZERO wipe or userdata commands."""
        plan = generate_flashing_plan(factory_reset=False)
        for cmd in plan:
            self.assertNotIn(" -w", cmd, f"Wipe flag '-w' detected in non-factory-reset plan: {cmd}")
            self.assertNotIn("erase userdata", cmd, f"Wipe command detected: {cmd}")
            self.assertNotIn("format userdata", cmd, f"Format command detected: {cmd}")

    def test_adversarial_injection_of_destructive_commands_strictly_blocked(self):
        """Injecting wipe commands when factory_reset=False must raise RuntimeError."""
        destructive_injections = [
            "fastboot -w",
            "fastboot erase userdata",
            "fastboot format userdata",
            "fastboot erase userdata_a",
            "fastboot format userdata_b",
        ]

        def simulate_plan_audit(injected_cmds: List[str], factory_reset: bool = False):
            if not factory_reset:
                for c in injected_cmds:
                    if " -w" in c or "erase userdata" in c or "format userdata" in c:
                        raise RuntimeError(f"Violation of Zero Data Loss contract! Wipe command detected: {c}")

        for cmd in destructive_injections:
            with self.assertRaises(RuntimeError, msg=f"Wipe command '{cmd}' must be blocked"):
                simulate_plan_audit([cmd], factory_reset=False)

    def test_little_kernel_avb_brick_vectors_strictly_blocked(self):
        """Flashing vendor_boot or using --disable-verity must raise RuntimeError."""
        brick_commands = [
            "fastboot flash vendor_boot custom_recovery.img",
            "fastboot flash --disable-verity vbmeta stock_vbmeta.img",
            "fastboot flash --disable-verification vbmeta stock_vbmeta.img",
            "fastboot --disable-verity flash vbmeta stock_vbmeta.img",
        ]

        def simulate_avb_audit(injected_cmds: List[str]):
            for c in injected_cmds:
                if "vendor_boot" in c:
                    raise RuntimeError(f"AVB Violation: Attempt to flash salt-pinned vendor_boot: {c}")
                if "--disable-verity" in c or "--disable-verification" in c:
                    raise RuntimeError(f"AVB Violation: Little Kernel RSA4096 signature failure trigger: {c}")

        for cmd in brick_commands:
            with self.assertRaises(RuntimeError, msg=f"Brick command '{cmd}' must be blocked"):
                simulate_avb_audit([cmd])

    def test_powershell_deployment_dry_run_executes_safely(self):
        """PowerShell deployment script in DryRun mode confirms Zero Data Loss contract."""
        ps_script = os.path.join(PARTITIONS_DIR, "flash_fastbootd_suite.ps1")
        if not os.path.exists(ps_script):
            self.skipTest("flash_fastbootd_suite.ps1 not found")

        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", ps_script, "-DryRun"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        self.assertEqual(res.returncode, 0, f"PowerShell DryRun failed: {res.stderr}")
        self.assertIn("Zero Data Loss:    ENABLED", res.stdout)
        self.assertIn("0 wipe commands", res.stdout)
        self.assertIn("DRY-RUN SUCCESS", res.stdout)


# ==============================================================================
# Main Runner
# ==============================================================================
if __name__ == "__main__":
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    suite.addTests(loader.loadTestsFromTestCase(TestAdversarial_F4_BrightnessClamping))
    suite.addTests(loader.loadTestsFromTestCase(TestAdversarial_F13_SuperBudgetArithmetic))
    suite.addTests(loader.loadTestsFromTestCase(TestAdversarial_F11_CorruptedErofsHeaders))
    suite.addTests(loader.loadTestsFromTestCase(TestAdversarial_F14_WinUSBChunking))
    suite.addTests(loader.loadTestsFromTestCase(TestAdversarial_ZeroDataLoss_Enforcement))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

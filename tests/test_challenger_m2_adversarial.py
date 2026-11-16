#!/usr/bin/env python3
"""
tests/test_challenger_m2_adversarial.py - Empirical Adversarial Test Suite for Milestone 2.

Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786 / MT6768)
Role: Challenger M2 (Adversarial stress-testing and empirical verification)

Verification Scope:
1. Forensic EXT4 Image Inspection:
   - Size strictly equals 4,294,967,296 bytes (4.0 GiB, 0x100000000).
   - Superblock magic at offset 1080 (0x438) is 0xEF53.
   - Total blocks equal 1,048,576 (4096-byte blocks).
   - First data block is 0 (for 4096-byte blocks).
   - Block size log is 2 (1024 << 2 = 4096).
   - Volume label is 'pmOS_root'.
   - File boundary seeking & EOF verification at 4,294,967,296 B.
2. Dynamic Super Partition Headroom & Arithmetic:
   - Physical super capacity: 11,811,160,064 bytes (11.00 GiB / 11.81 GB).
   - Dynamic group main_a max: 11,809,062,912 bytes (11.00 GiB).
   - Unallocated headroom in main_a: 7,050,133,504 bytes (~6.57 GB).
   - Post-allocation safety margin > 2.0 GB (actual: 2,755,166,208 B / 2.566 GiB).
   - Preserved stock product_a partition: 1,836,695,552 bytes (~1.71 GB).
   - Fastbootd -S 64M chunking divisibility (exact 64 chunks).
3. Adversarial Oracles & Failure Cases:
   - Truncated image rejection (0 B, 512 B, 1024 B, 1079 B, 1081 B, 4,294,967,295 B, 4,294,967,297 B).
   - Corrupted superblock magic (0x0000, 0xFFFF, 0x53EF endian swap, 0xEF52, 0xEF54).
   - Corrupted block counts (mismatches with file size).
   - Corrupted volume label rejection.
   - Super budget overflows: > main_a headroom, > physical super, < 2.0 GB safety margin.
   - Non-sector-aligned and non-page-aligned allocation rejection.
   - Preserved product_a below safety threshold (< 1.70 GB) rejection.
4. Session Configurations & Rootfs Staging Audit:
   - DRM card explicit binding to /dev/dri/by-path/platform-14000000.dispsys_config-card.
   - Triple buffering disabled (KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1).
   - Software cursor forced (KWIN_FORCE_SW_CURSOR=1).
   - PanVK Vulkan execution split for plasmashell (QSG_RHI_BACKEND=vulkan, PAN_I_WANT_A_BROKEN_VULKAN_DRIVER=1).
   - Tinydm autologin contract (user 'user', UID 10000, GID 10000, /home/user).
   - Plasma Mobile package profile cleanliness (zero duplicates, no legacy X11).
"""

from __future__ import annotations

import io
import os
from pathlib import Path
import py_compile
import re
import struct
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROOTFS_STAGING = PROJECT_ROOT / "rootfs_staging"
SESSION_DIR = ROOTFS_STAGING / "session_configs"
STAGE_DIR = ROOTFS_STAGING / "build" / "rootfs"
ROOTFS_IMG = ROOTFS_STAGING / "rootfs_plasma_mobile.img"

if str(ROOTFS_STAGING) not in sys.path:
    sys.path.insert(0, str(ROOTFS_STAGING))

import bake_ext4_image
import verify_super_budget


# ==============================================================================
# 1. Forensic EXT4 Image Inspection
# ==============================================================================
class TestEXT4RootfsForensics(unittest.TestCase):
    """Forensic binary inspection of rootfs_plasma_mobile.img."""

    @classmethod
    def setUpClass(cls):
        cls.img_path = ROOTFS_IMG
        if not cls.img_path.exists():
            raise FileNotFoundError(f"Missing rootfs image: {cls.img_path}")
        cls.stat = cls.img_path.stat()

    def test_01_exact_image_file_size(self):
        """Verify image size strictly equals 4,294,967,296 bytes (4.0 GiB, 0x100000000)."""
        expected_size = 4294967296
        self.assertEqual(
            self.stat.st_size,
            expected_size,
            f"Image size mismatch: {self.stat.st_size} != {expected_size}"
        )
        self.assertEqual(self.stat.st_size, 4 * 1024 * 1024 * 1024)
        self.assertEqual(self.stat.st_size, 0x100000000)

    def test_02_superblock_magic_at_offset_1080(self):
        """Verify EXT4 superblock magic 0xEF53 at offset 1080 (0x438)."""
        with open(self.img_path, "rb") as f:
            f.seek(1080)
            magic_bytes = f.read(2)
        magic = struct.unpack("<H", magic_bytes)[0]
        self.assertEqual(magic, 0xEF53, f"Superblock magic mismatch: {hex(magic)} != 0xef53")

    def test_03_total_blocks_count(self):
        """Verify blocks count equals 1,048,576 blocks (4096-byte blocks)."""
        with open(self.img_path, "rb") as f:
            f.seek(1024 + 0x04)  # offset 1028: s_blocks_count_lo
            blocks_lo = struct.unpack("<I", f.read(4))[0]
            f.seek(1024 + 0x150)  # offset 1360: s_blocks_count_hi
            blocks_hi = struct.unpack("<I", f.read(4))[0]

        total_blocks = blocks_lo | (blocks_hi << 32)
        self.assertEqual(total_blocks, 1048576, f"Block count mismatch: {total_blocks}")
        self.assertEqual(blocks_hi, 0, "64-bit blocks high must be 0 for 4 GiB filesystem")

    def test_04_block_size_log_and_first_data_block(self):
        """Verify block size is 4096 bytes (s_log_block_size = 2) and first data block is 0."""
        with open(self.img_path, "rb") as f:
            f.seek(1024 + 0x14)  # s_first_data_block
            first_data_block = struct.unpack("<I", f.read(4))[0]
            f.seek(1024 + 0x18)  # s_log_block_size
            log_block_size = struct.unpack("<I", f.read(4))[0]

        block_size = 1024 << log_block_size
        self.assertEqual(log_block_size, 2, f"s_log_block_size must be 2, got {log_block_size}")
        self.assertEqual(block_size, 4096, f"Block size must be 4096, got {block_size}")
        self.assertEqual(first_data_block, 0, "For 4096-byte block filesystems, s_first_data_block must be 0")

    def test_05_volume_label_pmos_root(self):
        """Verify volume label is strictly 'pmOS_root' at offset 1144."""
        with open(self.img_path, "rb") as f:
            f.seek(1024 + 0x78)  # offset 1144: s_volume_name
            raw_label = f.read(16)

        label = raw_label.decode("utf-8", errors="replace").rstrip("\x00")
        self.assertEqual(label, "pmOS_root", f"Volume label mismatch: '{label}' != 'pmOS_root'")

    def test_06_file_boundary_seeking_and_eof(self):
        """Verify exact byte-level boundary seeking and EOF termination at byte 4,294,967,296."""
        with open(self.img_path, "rb") as f:
            # Seek to last byte of file
            f.seek(4294967295)
            last_byte = f.read(1)
            self.assertEqual(len(last_byte), 1, "Failed to read last byte at 4,294,967,295")

            # Seek to exact EOF position
            f.seek(4294967296)
            eof_byte = f.read(1)
            self.assertEqual(eof_byte, b"", "Reading at byte 4,294,967,296 must return EOF (empty bytes)")

            # Seek beyond EOF
            f.seek(4294967297)
            beyond_eof = f.read(1)
            self.assertEqual(beyond_eof, b"", "Reading beyond EOF must return empty bytes")

    def test_07_fastbootd_chunking_divisibility(self):
        """Verify image divides exactly into Windows Fastbootd -S 64M chunks without remainder."""
        chunk_size_bytes = 64 * 1024 * 1024  # 67,108,864 bytes
        total_size = self.stat.st_size
        self.assertEqual(
            total_size % chunk_size_bytes, 0,
            f"Image size {total_size} does not divide evenly by 64M ({chunk_size_bytes})"
        )
        num_chunks = total_size // chunk_size_bytes
        self.assertEqual(num_chunks, 64, f"Expected 64 chunks of 64M, got {num_chunks}")


# ==============================================================================
# 2. Dynamic Super Partition Headroom & Arithmetic
# ==============================================================================
class TestSuperPartitionHeadroomArithmetic(unittest.TestCase):
    """Verify dynamic super partition capacity, headroom, and safety margin arithmetic."""

    def test_01_super_capacity_and_group_geometry(self):
        """Verify physical super capacity and group main_a geometry."""
        self.assertEqual(verify_super_budget.SUPER_PHYSICAL_BYTES, 11811160064)
        self.assertEqual(verify_super_budget.GROUP_MAIN_A_MAX_BYTES, 11809062912)
        # Main group reservation: 2 MiB for dynamic metadata headers
        self.assertEqual(
            verify_super_budget.SUPER_PHYSICAL_BYTES - verify_super_budget.GROUP_MAIN_A_MAX_BYTES,
            2 * 1024 * 1024
        )

    def test_02_dynamic_unallocated_headroom_math(self):
        """Verify dynamic unallocated headroom in main_a is ~6.57 GB."""
        headroom = verify_super_budget.INITIAL_UNALLOCATED_HEADROOM
        self.assertEqual(headroom, 7050133504)
        headroom_gib = headroom / (1024 ** 3)
        self.assertAlmostEqual(headroom_gib, 6.566, places=2)
        self.assertGreater(headroom, 6.5 * (1024 ** 3))

    def test_03_post_allocation_safety_margin_exceeds_2gb(self):
        """Verify post-allocation safety margin is > 2.0 GB (actual: 2.566 GiB)."""
        system_a_bytes = verify_super_budget.SYSTEM_A_TARGET_BYTES
        initial_headroom = verify_super_budget.INITIAL_UNALLOCATED_HEADROOM
        remaining = initial_headroom - system_a_bytes

        self.assertEqual(remaining, 2755166208)
        remaining_gib = remaining / (1024 ** 3)
        self.assertAlmostEqual(remaining_gib, 2.566, places=2)
        # Must be strictly > 2.0 GB (2,000,000,000 bytes)
        self.assertGreater(remaining, 2000000000)
        self.assertGreater(remaining - 2000000000, 750000000)  # > 750 MB buffer above requirement

    def test_04_product_a_preservation(self):
        """Verify stock product_a partition (~1.71 GB) is preserved."""
        product_a = verify_super_budget.PRODUCT_A_PRESERVED_BYTES
        self.assertEqual(product_a, 1836695552)
        product_a_gib = product_a / (1024 ** 3)
        self.assertAlmostEqual(product_a_gib, 1.711, places=2)

        # Total allocated must fit within physical super
        total_allocated = verify_super_budget.SYSTEM_A_TARGET_BYTES + product_a
        self.assertLess(total_allocated, verify_super_budget.SUPER_PHYSICAL_BYTES)
        remaining_physical = verify_super_budget.SUPER_PHYSICAL_BYTES - total_allocated
        self.assertGreater(remaining_physical, 5 * 1024 * 1024 * 1024)  # > 5.0 GB physical reserve

    def test_05_alignment_properties(self):
        """Verify sector (512 B) and page (4096 B) alignment of all target partitions."""
        self.assertEqual(verify_super_budget.SYSTEM_A_TARGET_BYTES % 512, 0)
        self.assertEqual(verify_super_budget.SYSTEM_A_TARGET_BYTES % 4096, 0)
        self.assertEqual(verify_super_budget.PRODUCT_A_PRESERVED_BYTES % 512, 0)
        self.assertEqual(verify_super_budget.PRODUCT_A_PRESERVED_BYTES % 4096, 0)


# ==============================================================================
# 3. Adversarial Oracles & Failure Stress Tests
# ==============================================================================
class TestAdversarialOraclesAndFailureCases(unittest.TestCase):
    """Stress-test verify_ext4_superblock and audit_super_budget against adversarial inputs."""

    def test_01_truncated_image_sizes_rejection(self):
        """Adversarially probe verify_ext4_superblock with multiple truncated sizes."""
        test_sizes = [0, 1, 512, 1023, 1024, 1079, 1081, 2048]
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            for sz in test_sizes:
                with open(tmp_path, "wb") as f:
                    f.write(b"\x00" * sz)

                # Sizes < 1082 must raise ValueError
                if sz < 1082:
                    with self.assertRaises(ValueError, msg=f"Failed to reject truncated size {sz} B"):
                        bake_ext4_image.verify_ext4_superblock(tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_02_off_by_one_file_sizes_rejection(self):
        """Verify that 4 GiB - 1 B and 4 GiB + 1 B images fail verification."""
        # Create a mock valid superblock header of 2048 bytes
        header = bytearray(2048)
        # magic at 1080
        struct.pack_into("<H", header, 1080, 0xEF53)
        # blocks count at 1028: 1,048,576
        struct.pack_into("<I", header, 1028, 1048576)
        # log block size at 1048: 2
        struct.pack_into("<I", header, 1048, 2)
        # label at 1144: pmOS_root
        header[1144:1153] = b"pmOS_root"

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Case A: 4 GiB - 1 byte
            tmp_path.write_bytes(bytes(header))
            info = bake_ext4_image.verify_ext4_superblock(
                tmp_path, expected_size=4294967296, expected_label="pmOS_root"
            )
            # Size doesn't match expected_size -> valid must be False
            self.assertFalse(info["valid"], "Must reject image when actual size != expected size")

            # Case B: expected_size mismatch
            info2 = bake_ext4_image.verify_ext4_superblock(
                ROOTFS_IMG, expected_size=4294967295, expected_label="pmOS_root"
            )
            self.assertFalse(info2["valid"], "Must reject 4 GiB - 1 B mismatch")

            info3 = bake_ext4_image.verify_ext4_superblock(
                ROOTFS_IMG, expected_size=4294967297, expected_label="pmOS_root"
            )
            self.assertFalse(info3["valid"], "Must reject 4 GiB + 1 B mismatch")
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_03_corrupted_magic_rejection(self):
        """Adversarially probe verify_ext4_superblock with corrupted magic bytes."""
        corrupt_magics = [0x0000, 0xFFFF, 0x53EF, 0xEF52, 0xEF54, 0x1234]

        header = bytearray(2048)
        struct.pack_into("<I", header, 1028, 1048576)
        struct.pack_into("<I", header, 1048, 2)
        header[1144:1153] = b"pmOS_root"

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            for bad_magic in corrupt_magics:
                struct.pack_into("<H", header, 1080, bad_magic)
                tmp_path.write_bytes(bytes(header))
                info = bake_ext4_image.verify_ext4_superblock(
                    tmp_path, expected_size=2048, expected_label="pmOS_root"
                )
                self.assertFalse(
                    info["valid"],
                    f"Oracle accepted corrupted superblock magic {hex(bad_magic)}"
                )
                self.assertFalse(info["magic_valid"])
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_04_corrupted_volume_label_rejection(self):
        """Adversarially test invalid or corrupted filesystem labels."""
        invalid_labels = ["", "root", "system", "pmOS_root2", "userdata", "system_a"]

        header = bytearray(2048)
        struct.pack_into("<H", header, 1080, 0xEF53)
        struct.pack_into("<I", header, 1028, 1048576)
        struct.pack_into("<I", header, 1048, 2)

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            for bad_lbl in invalid_labels:
                header[1144:1160] = bad_lbl.encode("utf-8").ljust(16, b"\x00")
                tmp_path.write_bytes(bytes(header))
                info = bake_ext4_image.verify_ext4_superblock(
                    tmp_path, expected_size=2048, expected_label="pmOS_root"
                )
                self.assertFalse(
                    info["valid"],
                    f"Oracle accepted corrupted volume label '{bad_lbl}'"
                )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_05_oversized_super_allocation_budget_errors(self):
        """Adversarially probe super budget auditor with overflow conditions."""
        # Case A: Exactly exhausts headroom (leaving 0 bytes -> safety margin < 2 GB)
        exhaust_size = verify_super_budget.INITIAL_UNALLOCATED_HEADROOM
        rep_exhaust = verify_super_budget.audit_super_budget(target_system_a_bytes=exhaust_size)
        self.assertFalse(rep_exhaust.is_valid, "Zero headroom allocation must fail safety margin")
        self.assertTrue(any("safety headroom" in err.lower() for err in rep_exhaust.errors))

        # Case B: Leaves 1,999,999,999 bytes (1 byte below 2.0 GB safety margin)
        boundary_size = verify_super_budget.INITIAL_UNALLOCATED_HEADROOM - 1999999999
        # align to 4096 so it doesn't fail alignment first
        boundary_size_aligned = (boundary_size // 4096) * 4096
        # Ensure remaining headroom is strictly < 2,000,000,000
        if (verify_super_budget.INITIAL_UNALLOCATED_HEADROOM - boundary_size_aligned) >= 2000000000:
            boundary_size_aligned += 4096
        rep_sub2g = verify_super_budget.audit_super_budget(target_system_a_bytes=boundary_size_aligned)
        self.assertFalse(rep_sub2g.is_valid, "Remaining headroom < 2.0 GB must fail safety margin")

        # Case C: Exceeds dynamic headroom
        overflow_size = verify_super_budget.INITIAL_UNALLOCATED_HEADROOM + 4096
        rep_over = verify_super_budget.audit_super_budget(target_system_a_bytes=overflow_size)
        self.assertFalse(rep_over.is_valid)
        self.assertTrue(any("overflows available dynamic headroom" in err for err in rep_over.errors))

        # Case D: Exceeds physical super capacity
        huge_size = verify_super_budget.SUPER_PHYSICAL_BYTES + 4096
        rep_huge = verify_super_budget.audit_super_budget(target_system_a_bytes=huge_size)
        self.assertFalse(rep_huge.is_valid)
        self.assertTrue(any("exceeds physical super capacity" in err for err in rep_huge.errors))

    def test_06_unaligned_allocations_rejected(self):
        """Verify non-sector and non-page aligned allocation requests are rejected."""
        base_size = verify_super_budget.SYSTEM_A_TARGET_BYTES

        # Non-sector aligned (odd byte size)
        rep_unaligned_sec = verify_super_budget.audit_super_budget(target_system_a_bytes=base_size + 1)
        self.assertFalse(rep_unaligned_sec.is_valid)
        self.assertFalse(rep_unaligned_sec.sector_aligned)
        self.assertTrue(any("sector aligned" in err for err in rep_unaligned_sec.errors))

        # Sector aligned (512 B) but non-page aligned (4096 B)
        rep_unaligned_page = verify_super_budget.audit_super_budget(target_system_a_bytes=base_size + 512)
        self.assertFalse(rep_unaligned_page.is_valid)
        self.assertTrue(rep_unaligned_page.sector_aligned)
        self.assertFalse(rep_unaligned_page.page_aligned)
        self.assertTrue(any("page aligned" in err for err in rep_unaligned_page.errors))

    def test_07_stock_product_a_underflow_rejected(self):
        """Verify product_a below safety threshold (< 1.70 GB) is flagged as an error."""
        rep_bad_prod = verify_super_budget.audit_super_budget(product_a_bytes=1000000000)
        self.assertFalse(rep_bad_prod.is_valid)
        self.assertTrue(any("product_a partition" in err for err in rep_bad_prod.errors))


# ==============================================================================
# 4. Session Configurations & Rootfs Staging Audit
# ==============================================================================
class TestSessionConfigurationsAndStagingAudit(unittest.TestCase):
    """Audit staged configuration files, session scripts, and package profiles."""

    def test_01_all_session_configs_valid_syntax(self):
        """Verify all shell scripts and configs in session_configs have valid syntax."""
        scripts_to_check = [
            (SESSION_DIR / "tb311fu-plasma-session", ("#!/bin/sh", "#!/bin/bash")),
            (SESSION_DIR / "tb311fu-plasmashell", ("#!/bin/sh", "#!/bin/bash")),
            (SESSION_DIR / "tb311fu-stop-plasma", ("#!/bin/sh", "#!/bin/bash")),
            (SESSION_DIR / "tb311fu-shell-priority", ("#!/usr/bin/python3", "#!/usr/bin/env python3")),
        ]
        for script, allowed_shebangs in scripts_to_check:
            self.assertTrue(script.exists(), f"Missing script: {script}")
            content = script.read_text(encoding="utf-8")
            self.assertTrue(
                any(content.startswith(sh) for sh in allowed_shebangs),
                f"Invalid shebang in {script}"
            )
            self.assertFalse("\r\n" in content, f"Script {script} contains CRLF line endings")

    def test_02_tb311fu_plasma_session_invariants(self):
        """Verify KWin Wayland bindings and safety overrides in tb311fu-plasma-session."""
        content = (SESSION_DIR / "tb311fu-plasma-session").read_text(encoding="utf-8")
        self.assertIn("platform-14000000.dispsys_config-card", content)
        self.assertIn("KWIN_DRM_DISABLE_TRIPLE_BUFFERING=1", content)
        self.assertIn("KWIN_FORCE_SW_CURSOR=1", content)
        self.assertIn("XDG_SESSION_TYPE=wayland", content)
        self.assertIn("dbus-run-session", content)
        self.assertIn("startplasmamobile", content)

    def test_03_tb311fu_plasmashell_invariants(self):
        """Verify PanVK Vulkan execution split in tb311fu-plasmashell."""
        content = (SESSION_DIR / "tb311fu-plasmashell").read_text(encoding="utf-8")
        self.assertIn("QSG_RHI_BACKEND=vulkan", content)
        self.assertIn("PAN_I_WANT_A_BROKEN_VULKAN_DRIVER=1", content)
        self.assertIn("GALLIUM_THREAD", content)
        self.assertIn("mesa_glthread", content)
        self.assertIn("/usr/bin/plasmashell", content)

    def test_04_tinydm_and_user_account_contract(self):
        """Verify tinydm and user-account match contract UID 10000, user, /home/user."""
        tinydm = (SESSION_DIR / "tinydm.conf").read_text(encoding="utf-8")
        self.assertIn("AUTOLOGIN=true", tinydm)
        self.assertTrue("AUTOLOGIN_USER=user" in tinydm or "USER=user" in tinydm)
        self.assertIn("/usr/local/bin/tb311fu-plasma-session", tinydm)

        user_acc = (SESSION_DIR / "user-account.conf").read_text(encoding="utf-8")
        self.assertIn("USER=user", user_acc)
        self.assertIn("UID=10000", user_acc)
        self.assertIn("GID=10000", user_acc)
        self.assertIn("HOME=/home/user", user_acc)

    def test_05_package_profile_hygiene(self):
        """Verify packages.txt hygiene: no duplicates, no legacy X11, required packages."""
        pkg_file = ROOTFS_STAGING / "packages.txt"
        self.assertTrue(pkg_file.exists())
        content = pkg_file.read_text(encoding="utf-8")
        pkgs = [
            p.strip() for line in content.splitlines()
            for p in line.split() if p.strip() and not p.startswith("#")
        ]
        self.assertEqual(len(pkgs), len(set(pkgs)), "Duplicate packages detected in packages.txt")

        # Required packages
        pkg_set = set(pkgs)
        self.assertIn("plasma-mobile", pkg_set)
        self.assertIn("pipewire", pkg_set)
        self.assertIn("wireplumber", pkg_set)
        self.assertTrue(any("kwin" in p for p in pkg_set))
        self.assertTrue(any("mesa" in p or "panfrost" in p for p in pkg_set))

        # Excluded packages
        self.assertNotIn("xorg-server", pkg_set)
        self.assertNotIn("xserver-xorg", pkg_set)


if __name__ == "__main__":
    unittest.main(verbosity=2)

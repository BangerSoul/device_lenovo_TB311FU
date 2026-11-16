#!/usr/bin/env python3
"""
tests/test_m4_kernel_crypto_deliverables.py - Comprehensive Verification Test Suite
Milestone M4: Custom Linux 6.6 Kernel & Cryptographic Invariants
Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek MT8786 / Helio G88)

Covers Authoritative Requirements:
- R6.1: Permissive dm-verity patch (0002-permissive-dm-verity.patch, dm-verity-target.c, build-kernel.yml),
        KernelSU-Next integration, module signature bypass (kernel/module/signing.c)
- R6.2: AVB 2.0 Boot Image Assembly (assemble_pmos_boot.py, 32 MB geometry, 4096-alignment,
        Offset == Size == 14,561,280, flags byte 123 = 0x00, OEM RSA4096 signature)
- R6.3: Factory stock partition preservation (stock_vbmeta, stock_vbmeta_vendor,
        stock_vbmeta_system, stock_vendor_boot)
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BOOT_VECTOR_DIR = WORKSPACE_ROOT / "boot_vector"
KERNEL_RECOVERY_DIR = WORKSPACE_ROOT / "kernel_recovery"
KERNEL_REPO_DIR = WORKSPACE_ROOT.parent / "fearless-maxwell" / "kernel_repo"

for path_dir in [BOOT_VECTOR_DIR, KERNEL_RECOVERY_DIR, WORKSPACE_ROOT]:
    if str(path_dir) not in sys.path:
        sys.path.insert(0, str(path_dir))

from assemble_pmos_boot import (
    assemble_pmos_boot,
    build_avb_footer,
    build_boot_header_v4,
    extract_kernel_payload,
    extract_oem_vbmeta_block,
    AVB_FOOTER_MAGIC,
    AVB_FOOTER_OFFSET,
    AVB_FOOTER_SIZE,
    BOOT_HEADER_PAGE_SIZE,
    BOOT_HEADER_V4_SIZE,
    BOOT_MAGIC,
    EXPECTED_AUTH_DIGEST,
    EXPECTED_BOOT_SIZE,
    EXPECTED_OEM_KEY_SHA1,
    HEADER_VERSION,
    VBMETA_MAGIC,
    VBMETA_OFFSET,
    VBMETA_SIZE,
)

from verify_lk_avb_invariant import (
    parse_avb_descriptors,
    verify_file as verify_boot_file,
    verify_lk_avb_invariant,
    LKAVBInvariantError,
)

from verify_stock_preservation import (
    parse_vbmeta_descriptors,
    verify_all_stock_preservation,
    verify_vbmeta_preservation,
    verify_vbmeta_system_preservation,
    verify_vbmeta_vendor_preservation,
    verify_vendor_boot_preservation,
    StockPreservationError,
    AVB_SALT_HEX,
    EXPECTED_VBMETA_SYSTEM_AUTH_DIGEST,
    EXPECTED_VBMETA_SYSTEM_KEY_SHA1,
    EXPECTED_VBMETA_VENDOR_AUTH_DIGEST,
    EXPECTED_VBMETA_VENDOR_KEY_SHA1,
    PINNED_HASH_DESCRIPTORS,
    PINNED_HASHTREE_PRODUCT,
    PINNED_HASHTREE_SYSTEM,
    PINNED_HASHTREE_VENDOR,
    VBMETA_SIZE,
    VBMETA_SUB_SIZE,
    VENDOR_BOOT_MAGIC,
    VENDOR_BOOT_PINNED_HASH,
    VENDOR_BOOT_PINNED_SIZE,
    VENDOR_BOOT_SIZE,
)

from verify_avb_chain import (
    verify_avb_chain,
    verify_vendor_boot_hash,
    AVBVerificationError,
)


class TestSuite1_PermissiveDmVerity(unittest.TestCase):
    """R6.1: Permissive dm-verity patch and drivers/md/dm-verity-target.c implementation."""

    def test_01_patch_file_exists_and_content(self):
        """Verify 0002-permissive-dm-verity.patch exists and targets verity_handle_err."""
        patch_path = KERNEL_REPO_DIR / "patches" / "0002-permissive-dm-verity.patch"
        self.assertTrue(patch_path.is_file(), f"Patch file missing at {patch_path}")

        patch_txt = patch_path.read_text(encoding="utf-8")
        self.assertIn("drivers/md/dm-verity-target.c", patch_txt)
        self.assertIn("static int verity_handle_err(", patch_txt)
        self.assertIn("pr_warn_ratelimited", patch_txt)
        self.assertIn("return 0;", patch_txt)
        self.assertIn("Signed-off-by:", patch_txt)

    def test_02_source_file_exists_and_implements_permissive_mode(self):
        """Verify drivers/md/dm-verity-target.c implements permissive return 0 in verity_handle_err."""
        src_path = KERNEL_REPO_DIR / "drivers" / "md" / "dm-verity-target.c"
        self.assertTrue(src_path.is_file(), f"Source file missing at {src_path}")

        src_txt = src_path.read_text(encoding="utf-8")
        self.assertIn("static int verity_handle_err(", src_txt)
        self.assertIn("pr_warn_ratelimited", src_txt)
        self.assertIn("dm-verity corruption at block %llu ignored (permissive mode)", src_txt)
        self.assertIn("return 0;", src_txt)
        self.assertIn("kernel_restart(\"dm-verity device corrupted\");", src_txt)

    def test_03_permissive_return_precedes_restart(self):
        """Verify that return 0 occurs before kernel_restart in verity_handle_err."""
        src_path = KERNEL_REPO_DIR / "drivers" / "md" / "dm-verity-target.c"
        src_txt = src_path.read_text(encoding="utf-8")

        func_start = src_txt.find("static int verity_handle_err(")
        self.assertGreater(func_start, 0)
        func_body = src_txt[func_start : func_start + 1500]

        return_pos = func_body.find("return 0;")
        restart_pos = func_body.find("kernel_restart(")
        self.assertGreater(return_pos, 0)
        self.assertGreater(restart_pos, 0)
        self.assertLess(return_pos, restart_pos, "Permissive return 0 must precede kernel_restart!")


class TestSuite2_KernelBuildWorkflow(unittest.TestCase):
    """R6.1: Kernel CI pipeline integration in .github/workflows/build-kernel.yml."""

    @classmethod
    def setUpClass(cls):
        cls.yml_path = KERNEL_REPO_DIR / ".github" / "workflows" / "build-kernel.yml"
        cls.assertTrue(cls.yml_path.is_file(), f"build-kernel.yml missing at {cls.yml_path}")
        cls.yml_txt = cls.yml_path.read_text(encoding="utf-8")

    def test_01_workflow_contains_dm_verity_patch_in_both_jobs(self):
        """Verify build-kernel.yml applies permissive dm-verity in build and build-halium jobs."""
        patch_refs = self.yml_txt.count("0002-permissive-dm-verity.patch")
        self.assertGreaterEqual(patch_refs, 2, "dm-verity patch must be integrated in both jobs")
        self.assertIn("Patching drivers/md/dm-verity-target.c", self.yml_txt)

    def test_02_workflow_contains_module_signature_bypass(self):
        """Verify build-kernel.yml patches kernel/module/signing.c with info->sig_ok = true."""
        self.assertIn("Patching kernel/module/signing.c", self.yml_txt)
        self.assertIn("info->sig_ok = true;", self.yml_txt)
        self.assertIn("return 0;", self.yml_txt)

    def test_03_workflow_contains_module_vermagic_and_symbol_bypasses(self):
        """Verify build-kernel.yml patches kernel/module/main.c and version.c."""
        self.assertIn("kernel/module/main.c", self.yml_txt)
        self.assertIn("is_vendor_module = 0;", self.yml_txt)
        self.assertIn("kernel/module/version.c", self.yml_txt)
        self.assertIn("check_version", self.yml_txt)

    def test_04_workflow_contains_kernelsu_next_integration(self):
        """Verify build-kernel.yml includes KernelSU-Next setup and required kconfigs."""
        self.assertIn("KernelSU-Next", self.yml_txt)
        self.assertIn("CONFIG_KPROBES=y", self.yml_txt)
        self.assertIn("CONFIG_OVERLAY_FS=y", self.yml_txt)
        self.assertIn("CONFIG_RFKILL=m", self.yml_txt)


class TestSuite3_AVB20BootGeometry(unittest.TestCase):
    """R6.2: Android Boot Header v4 boot vector geometry and Little Kernel AVB invariants."""

    @classmethod
    def setUpClass(cls):
        cls.boot_img_path = WORKSPACE_ROOT / "boot_vector" / "pmos_boot.img"
        if not cls.boot_img_path.is_file():
            assemble_pmos_boot(output_path=cls.boot_img_path, verbose=False)
        cls.boot_data = cls.boot_img_path.read_bytes()

    def test_01_total_partition_size_exact_32mb(self):
        """Verify total partition size is strictly 33,554,432 bytes (32 MB)."""
        self.assertEqual(len(self.boot_data), EXPECTED_BOOT_SIZE)
        self.assertEqual(len(self.boot_data), 33554432)

    def test_02_android_boot_header_v4_page_zero(self):
        """Verify Page 0 has magic ANDROID!, header version 4, and size 1584."""
        hdr = self.boot_data[:BOOT_HEADER_PAGE_SIZE]
        self.assertEqual(hdr[:8], BOOT_MAGIC)
        k_sz, r_sz = struct.unpack("<II", hdr[8:16])
        hdr_sz = struct.unpack("<I", hdr[20:24])[0]
        hdr_ver = struct.unpack("<I", hdr[40:44])[0]
        self.assertGreater(k_sz, 0)
        self.assertEqual(hdr_sz, BOOT_HEADER_V4_SIZE)
        self.assertEqual(hdr_ver, HEADER_VERSION)

    def test_03_vbmeta_offset_4096_page_aligned(self):
        """Verify VBMeta offset is strictly 4096-byte page aligned at 14,561,280 (0xDE3000)."""
        self.assertEqual(VBMETA_OFFSET, 14561280)
        self.assertEqual(VBMETA_OFFSET % BOOT_HEADER_PAGE_SIZE, 0)

    def test_04_core_lk_invariant_offset_equals_image_size(self):
        """Verify Core LK Invariant: VBMeta Offset == HashDescriptor.image_size == 14,561,280."""
        meta = verify_lk_avb_invariant(self.boot_data, verbose=False)
        self.assertEqual(meta["vbmeta_offset"], 14561280)
        self.assertEqual(meta["hash_descriptor_image_size"], 14561280)
        self.assertEqual(meta["vbmeta_offset"], meta["hash_descriptor_image_size"])
        self.assertTrue(meta["invariant_satisfied"])

    def test_05_flags_byte_123_strictly_zero(self):
        """Verify flags byte 123 is strictly 0x00 (no --disable-verity)."""
        flags = struct.unpack(">I", self.boot_data[VBMETA_OFFSET + 120 : VBMETA_OFFSET + 124])[0]
        flags_byte_123 = self.boot_data[VBMETA_OFFSET + 123]
        self.assertEqual(flags, 0x00000000)
        self.assertEqual(flags_byte_123, 0x00)

    def test_06_oem_rsa4096_public_key_and_signature_integrity(self):
        """Verify OEM RSA4096 public key SHA1 and Auth Block SHA256 integrity."""
        meta = verify_lk_avb_invariant(self.boot_data, verbose=False)
        self.assertEqual(meta["public_key_sha1"].lower(), EXPECTED_OEM_KEY_SHA1.lower())
        self.assertEqual(meta["auth_digest"].lower(), EXPECTED_AUTH_DIGEST.lower())

    def test_07_avb_footer_points_to_vbmeta_offset(self):
        """Verify AVB footer at offset 33,554,368 points to VBMeta offset 14,561,280."""
        footer_pos = EXPECTED_BOOT_SIZE - AVB_FOOTER_SIZE
        footer = self.boot_data[footer_pos : footer_pos + AVB_FOOTER_SIZE]
        f_magic, f_maj, f_min, orig_sz, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])
        self.assertEqual(f_magic, AVB_FOOTER_MAGIC)
        self.assertEqual(vb_off, 14561280)
        self.assertEqual(orig_sz, 14561280)
        self.assertEqual(vb_sz, 2432)  # OEM embedded VBMeta block size is exactly 2,432 bytes


class TestSuite4_StockPartitionsPreservation(unittest.TestCase):
    """R6.3: Factory stock partition preservation on flash."""

    def test_01_stock_vbmeta_intact(self):
        """Verify stock_vbmeta.img retains OEM RSA4096 key and flags byte 123 == 0x00."""
        meta = verify_vbmeta_preservation(verbose=False)
        self.assertEqual(meta["size"], VBMETA_SIZE)
        self.assertEqual(meta["flags_byte_123"], 0x00)
        self.assertEqual(meta["public_key_sha1"].lower(), EXPECTED_OEM_KEY_SHA1.lower())
        self.assertTrue(meta["preserved"])

    def test_02_stock_vbmeta_vendor_intact(self):
        """Verify stock_vbmeta_vendor.img retains OEM key, flags=0x00, and vendor hashtree."""
        meta = verify_vbmeta_vendor_preservation(verbose=False)
        self.assertEqual(meta["size"], VBMETA_SUB_SIZE)
        self.assertEqual(meta["flags_byte_123"], 0x00)
        self.assertEqual(meta["public_key_sha1"].lower(), EXPECTED_VBMETA_VENDOR_KEY_SHA1.lower())
        self.assertIn("vendor", meta["descriptors"])
        desc = meta["descriptors"]["vendor"]
        self.assertEqual(desc["image_size"], PINNED_HASHTREE_VENDOR["image_size"])
        self.assertEqual(desc["root_digest"], PINNED_HASHTREE_VENDOR["root_digest"])
        self.assertTrue(meta["preserved"])

    def test_03_stock_vbmeta_system_intact(self):
        """Verify stock_vbmeta_system.img retains key, flags=0x00, and system hashtree."""
        meta = verify_vbmeta_system_preservation(verbose=False)
        self.assertEqual(meta["size"], VBMETA_SUB_SIZE)
        self.assertEqual(meta["flags_byte_123"], 0x00)
        self.assertEqual(meta["public_key_sha1"].lower(), EXPECTED_VBMETA_SYSTEM_KEY_SHA1.lower())
        self.assertIn("system", meta["descriptors"])
        desc = meta["descriptors"]["system"]
        self.assertEqual(desc["image_size"], PINNED_HASHTREE_SYSTEM["image_size"])
        self.assertEqual(desc["root_digest"], PINNED_HASHTREE_SYSTEM["root_digest"])
        self.assertTrue(meta["preserved"])

    def test_04_stock_vendor_boot_salted_hash_intact(self):
        """Verify stock_vendor_boot.img retains 25,047,040-byte salted SHA-256 hash."""
        meta = verify_vendor_boot_preservation(verbose=False)
        self.assertEqual(meta["size"], VENDOR_BOOT_SIZE)
        self.assertEqual(meta["magic"], "VNDRBOOT")
        self.assertEqual(meta["pinned_size"], VENDOR_BOOT_PINNED_SIZE)
        self.assertEqual(meta["computed_digest"], VENDOR_BOOT_PINNED_HASH)
        self.assertTrue(meta["preserved"])

    def test_05_all_stock_preservation_aggregate(self):
        """Verify verify_all_stock_preservation() validates all 4 stock partitions."""
        res = verify_all_stock_preservation(verbose=False)
        self.assertTrue(res["all_passed"])
        self.assertTrue(res["vendor_boot"]["preserved"])
        self.assertTrue(res["vbmeta"]["preserved"])
        self.assertTrue(res["vbmeta_vendor"]["preserved"])
        self.assertTrue(res["vbmeta_system"]["preserved"])


class TestSuite5_AdversarialCryptoAndVerity(unittest.TestCase):
    """Adversarial stress testing and boundary violation enforcement."""

    @classmethod
    def setUpClass(cls):
        boot_img_path = WORKSPACE_ROOT / "boot_vector" / "pmos_boot.img"
        cls.valid_boot = bytearray(boot_img_path.read_bytes())

    def test_01_mutated_flags_byte_123_rejected(self):
        """Adversarial: Mutating byte 123 in VBMeta block must raise LKAVBInvariantError."""
        for val in [0x01, 0x02, 0x03, 0x80, 0xFF]:
            corrupted = bytearray(self.valid_boot)
            corrupted[VBMETA_OFFSET + 123] = val
            with self.assertRaises(LKAVBInvariantError):
                verify_lk_avb_invariant(bytes(corrupted), verbose=False)

    def test_02_misaligned_vbmeta_offset_rejected(self):
        """Adversarial: Non-4096-aligned VBMeta offset in footer must raise error."""
        footer_pos = EXPECTED_BOOT_SIZE - AVB_FOOTER_SIZE
        for bad_offset in [VBMETA_OFFSET + 1, VBMETA_OFFSET + 4, VBMETA_OFFSET + 2048]:
            corrupted = bytearray(self.valid_boot)
            struct.pack_into(">Q", corrupted, footer_pos + 20, bad_offset)
            with self.assertRaises(LKAVBInvariantError):
                verify_lk_avb_invariant(bytes(corrupted), verbose=False)

    def test_03_mismatched_offset_vs_size_rejected(self):
        """Adversarial: Mismatched offset != image_size must raise error."""
        footer_pos = EXPECTED_BOOT_SIZE - AVB_FOOTER_SIZE
        corrupted = bytearray(self.valid_boot)
        struct.pack_into(">Q", corrupted, footer_pos + 20, 12918784)
        struct.pack_into(">Q", corrupted, footer_pos + 12, 12918784)
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(corrupted), verbose=False)

    def test_04_corrupted_vendor_boot_payload_rejected(self):
        """Adversarial: Bitflip in vendor_boot payload must raise StockPreservationError."""
        stock_path = Path(r"C:\platform-tools\stock_vendor_boot.img")
        if stock_path.is_file():
            vb_data = bytearray(stock_path.read_bytes())
            vb_data[500] ^= 0x80
            with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
                tmp.write(vb_data)
                tmp_path = Path(tmp.name)
            try:
                with self.assertRaises(StockPreservationError):
                    verify_vendor_boot_preservation(tmp_path, verbose=False)
            finally:
                tmp_path.unlink(missing_ok=True)


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestSuite1_PermissiveDmVerity))
    suite.addTests(loader.loadTestsFromTestCase(TestSuite2_KernelBuildWorkflow))
    suite.addTests(loader.loadTestsFromTestCase(TestSuite3_AVB20BootGeometry))
    suite.addTests(loader.loadTestsFromTestCase(TestSuite4_StockPartitionsPreservation))
    suite.addTests(loader.loadTestsFromTestCase(TestSuite5_AdversarialCryptoAndVerity))

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == "__main__":
    result = run_tests()
    sys.exit(0 if result.wasSuccessful() else 1)

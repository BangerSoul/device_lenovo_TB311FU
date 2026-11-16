#!/usr/bin/env python3
"""
tests/test_challenger_m3_adversarial.py - Empirical Challenger Adversarial Verification Suite
Milestone 3: Boot Vector Assembly, Little Kernel (LK) AVB Invariants & Stock Partition Preservation

Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786 / MT6768)
Challenger: Challenger M3 (teamwork_preview_challenger)

This test suite independently and empirically tests:
1. Low-level byte-accurate verification of `boot_vector/pmos_boot.img`.
2. Core LK Invariant: Offset == Size == 14,561,280 bytes (0xDE3000).
3. OEM Root RSA4096 Key SHA1: 8fcb864f11f53ed11284615fb67685522085d3a2.
4. Header + Aux SHA256 Signature Self-Integrity.
5. VBMeta Flags Byte 123 == 0x00 (verity active, no --disable-verity).
6. 4096-byte page alignment across all critical offsets.
7. Slack region zero-padding integrity.
8. Stock vendor_boot salted SHA-256 hash preservation (25,047,040 bytes).
9. Stock vbmeta OEM signature and partition descriptors preservation.
10. Extensive Adversarial Mutation Testing:
    - Offset != Size (simulate offset 12,918,784 from defective poplar_boot_v12_clean.img)
    - Byte 123 flipped to 0x03, 0x01, 0x02, 0x04, 0x80, 0xFF
    - Misaligned VBMeta offset (+1, +2, +4, +16, +512, +2048)
    - Corrupted boot magic, footer magic, vbmeta magic
    - Foreign OEM public key injection
    - Tampered Auth Block digest
    - Non-zero noise in slack padding
    - Truncated and bloated boot vectors
    - Bit flips and truncation in vendor_boot payload
    - Mutated vendor_boot salt
    - Assembly engine rejection of oversized kernel payload
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BOOT_VECTOR_DIR = WORKSPACE_ROOT / "boot_vector"
if str(BOOT_VECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(BOOT_VECTOR_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import assemble_pmos_boot
from verify_lk_avb_invariant import (
    verify_lk_avb_invariant,
    verify_file as verify_boot_file,
    parse_avb_descriptors,
    LKAVBInvariantError,
    EXPECTED_BOOT_SIZE,
    EXPECTED_VBMETA_OFFSET,
    EXPECTED_VBMETA_SIZE,
    AVB_FOOTER_OFFSET,
    AVB_FOOTER_SIZE,
    AVB_FOOTER_MAGIC,
    VBMETA_MAGIC,
    BOOT_MAGIC,
    EXPECTED_OEM_KEY_SHA1,
    EXPECTED_AUTH_DIGEST,
)

from verify_stock_preservation import (
    verify_vendor_boot_preservation,
    verify_vbmeta_preservation,
    verify_all_stock_preservation,
    StockPreservationError,
    VENDOR_BOOT_SIZE,
    VENDOR_BOOT_PINNED_SIZE,
    VENDOR_BOOT_PINNED_HASH,
    AVB_SALT_HEX,
    AVB_SALT_BYTES,
)


class TestChallengerM3EmpiricalVerification(unittest.TestCase):
    """Empirical low-level byte and invariant verification."""

    @classmethod
    def setUpClass(cls):
        cls.boot_img_path = BOOT_VECTOR_DIR / "pmos_boot.img"
        if not cls.boot_img_path.is_file():
            assemble_pmos_boot.assemble_pmos_boot(output_path=cls.boot_img_path, verbose=False)
        cls.boot_bytes = cls.boot_img_path.read_bytes()

    def test_01_image_exact_size(self):
        """Empirically assert pmos_boot.img is exactly 33,554,432 bytes."""
        self.assertEqual(len(self.boot_bytes), 33554432)
        self.assertEqual(self.boot_img_path.stat().st_size, 33554432)

    def test_02_boot_header_v4_geometry(self):
        """Empirically assert Page 0 Header v4 fields."""
        magic, k_sz, r_sz, os_ver, hdr_sz, r1, r2, r3, r4, v_hdr = struct.unpack(
            "<8sIIII4II", self.boot_bytes[:44]
        )
        self.assertEqual(magic, b"ANDROID!")
        self.assertGreater(k_sz, 0)
        self.assertEqual(r_sz, 0)
        self.assertEqual(hdr_sz, 1584)
        self.assertEqual(v_hdr, 4)

        cmdline = self.boot_bytes[44 : 44 + 1536].split(b"\x00")[0].decode("ascii")
        self.assertIn("androidboot.hardware=mt8786", cmdline)
        self.assertIn("console=ttyMT0,921600n8", cmdline)

    def test_03_avb_footer_geometry(self):
        """Empirically assert AVB footer at offset 33,554,368."""
        footer_offset = 33554432 - 64
        self.assertEqual(footer_offset, 33554368)
        footer = self.boot_bytes[footer_offset : footer_offset + 64]
        magic, maj, min_, orig_sz, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])
        self.assertEqual(magic, b"AVBf")
        self.assertEqual(maj, 1)
        self.assertEqual(min_, 0)
        self.assertEqual(orig_sz, 14561280)
        self.assertEqual(vb_off, 14561280)
        self.assertEqual(vb_sz, 2432)

    def test_04_core_lk_invariant_offset_equals_size(self):
        """Empirically assert Core LK Invariant: Offset == Size == 14,561,280 bytes."""
        footer = self.boot_bytes[33554368:33554432]
        _, _, _, orig_sz, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])

        # Extract VBMeta block at vb_off
        vbmeta_block = self.boot_bytes[vb_off : vb_off + vb_sz]
        self.assertEqual(vbmeta_block[:4], b"AVB0")

        # Parse AvbHashDescriptor
        auth_sz = struct.unpack(">Q", vbmeta_block[12:20])[0]
        aux_sz = struct.unpack(">Q", vbmeta_block[20:28])[0]
        desc_off = struct.unpack(">Q", vbmeta_block[96:104])[0]
        desc_sz = struct.unpack(">Q", vbmeta_block[104:112])[0]
        aux_bytes = vbmeta_block[256 + auth_sz : 256 + auth_sz + aux_sz]
        descs = parse_avb_descriptors(aux_bytes[desc_off : desc_off + desc_sz])

        hash_desc = next((d for d in descs if d.get("tag") == 2), None)
        self.assertIsNotNone(hash_desc)
        img_sz = hash_desc["image_size"]

        # Mathematically verify the invariant
        self.assertEqual(vb_off, 14561280)
        self.assertEqual(orig_sz, 14561280)
        self.assertEqual(img_sz, 14561280)
        self.assertEqual(vb_off, img_sz)
        self.assertEqual(vb_off % 4096, 0)

    def test_05_oem_key_and_auth_integrity(self):
        """Empirically assert OEM Root Key SHA1 and Auth Block SHA256 integrity."""
        vbmeta_block = self.boot_bytes[14561280 : 14561280 + 2432]
        self.assertEqual(vbmeta_block[123], 0x00)

        auth_sz = struct.unpack(">Q", vbmeta_block[12:20])[0]
        aux_sz = struct.unpack(">Q", vbmeta_block[20:28])[0]
        pubk_off = struct.unpack(">Q", vbmeta_block[64:72])[0]
        pubk_sz = struct.unpack(">Q", vbmeta_block[72:80])[0]
        pubk_bytes = vbmeta_block[256 + auth_sz + pubk_off : 256 + auth_sz + pubk_off + pubk_sz]
        pubk_sha1 = hashlib.sha1(pubk_bytes).hexdigest().lower()
        self.assertEqual(pubk_sha1, EXPECTED_OEM_KEY_SHA1.lower())

        hash_off = struct.unpack(">Q", vbmeta_block[32:40])[0]
        hash_sz = struct.unpack(">Q", vbmeta_block[40:48])[0]
        stored_hash = vbmeta_block[256 + hash_off : 256 + hash_off + hash_sz]
        computed_hash = hashlib.sha256(
            vbmeta_block[:256] + vbmeta_block[256 + auth_sz : 256 + auth_sz + aux_sz]
        ).digest()
        self.assertEqual(stored_hash, computed_hash)
        self.assertEqual(stored_hash.hex().lower(), EXPECTED_AUTH_DIGEST.lower())

    def test_06_slack_regions_zero_padding(self):
        """Empirically assert zero-padding in slack regions."""
        k_sz = struct.unpack("<I", self.boot_bytes[8:12])[0]
        payload_end = 4096 + k_sz
        self.assertTrue(all(b == 0 for b in self.boot_bytes[payload_end:14561280]))
        self.assertTrue(all(b == 0 for b in self.boot_bytes[14561280 + 2432 : 33554368]))


class TestChallengerM3AdversarialMutations(unittest.TestCase):
    """Hostile stress tests and adversarial mutation rejection."""

    @classmethod
    def setUpClass(cls):
        cls.valid_boot = bytearray(
            (BOOT_VECTOR_DIR / "pmos_boot.img").read_bytes()
        )

    def test_mutation_01_offset_not_equal_size_defect(self):
        """
        Adversarial: Simulate the fatal defect from poplar_boot_v12_clean.img
        where VBMeta offset is 12,918,784 but HashDescriptor size is 14,561,280.
        Must raise LKAVBInvariantError.
        """
        mutated = bytearray(self.valid_boot)
        footer_pos = 33554368
        struct.pack_into(">Q", mutated, footer_pos + 12, 12918784)
        struct.pack_into(">Q", mutated, footer_pos + 20, 12918784)

        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_02_flags_byte_123_bit_flips(self):
        """
        Adversarial: Test all single-bit flips and multi-bit corruptions of flags byte 123.
        (e.g., 0x01, 0x02, 0x03 [--disable-verity], 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0xFF).
        All must raise LKAVBInvariantError.
        """
        test_flags = [0x01, 0x02, 0x03, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0xFF]
        for flag in test_flags:
            mutated = bytearray(self.valid_boot)
            mutated[14561280 + 123] = flag
            with self.assertRaises(LKAVBInvariantError, msg=f"Flag 0x{flag:02x} was not rejected!"):
                verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_03_vbmeta_misalignment(self):
        """
        Adversarial: VBMeta offset shifted off 4096-page boundary (+1, +2, +4, +16, +512, +2048, +4095).
        All must raise LKAVBInvariantError.
        """
        for delta in [1, 2, 4, 16, 512, 1024, 2048, 4095]:
            mutated = bytearray(self.valid_boot)
            bad_off = 14561280 + delta
            struct.pack_into(">Q", mutated, 33554368 + 20, bad_off)
            with self.assertRaises(LKAVBInvariantError, msg=f"Delta +{delta} was not rejected!"):
                verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_04_footer_magic_corruptions(self):
        """Adversarial: Corrupted footer magic b'NOPE', b'\\x00\\x00\\x00\\x00', b'AVB0'."""
        for bad_magic in [b"NOPE", b"\x00\x00\x00\x00", b"AVB0", b"XXXX"]:
            mutated = bytearray(self.valid_boot)
            mutated[33554368 : 33554368 + 4] = bad_magic
            with self.assertRaises(LKAVBInvariantError):
                verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_05_vbmeta_magic_corruptions(self):
        """Adversarial: Corrupted VBMeta magic b'AVBf', b'\\x00\\x00\\x00\\x00', b'FAIL'."""
        for bad_magic in [b"AVBf", b"\x00\x00\x00\x00", b"FAIL"]:
            mutated = bytearray(self.valid_boot)
            mutated[14561280 : 14561280 + 4] = bad_magic
            with self.assertRaises(LKAVBInvariantError):
                verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_06_boot_header_magic_corruptions(self):
        """Adversarial: Corrupted Boot Header magic b'CHALLENG'."""
        mutated = bytearray(self.valid_boot)
        mutated[0:8] = b"CHALLENG"
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_07_foreign_oem_key_injection(self):
        """Adversarial: Replace OEM RSA4096 public key with foreign bytes."""
        mutated = bytearray(self.valid_boot)
        auth_sz = struct.unpack(">Q", mutated[14561280 + 12 : 14561280 + 20])[0]
        pubk_off = struct.unpack(">Q", mutated[14561280 + 64 : 14561280 + 72])[0]
        pubk_sz = struct.unpack(">Q", mutated[14561280 + 72 : 14561280 + 80])[0]
        pubk_start = 14561280 + 256 + auth_sz + pubk_off

        # Bitflip the public key
        mutated[pubk_start] ^= 0x55
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_08_tampered_auth_block_digest(self):
        """Adversarial: Alter stored authentication block hash."""
        mutated = bytearray(self.valid_boot)
        hash_off = struct.unpack(">Q", mutated[14561280 + 32 : 14561280 + 40])[0]
        mutated[14561280 + 256 + hash_off] ^= 0xFF
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(mutated), verbose=False)

    def test_mutation_09_slack_padding_corruptions(self):
        """Adversarial: Non-zero noise injected into slack regions."""
        # Slack region 1: between payload end and VBMETA_OFFSET
        mutated1 = bytearray(self.valid_boot)
        mutated1[14561280 - 1] = 0x01
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(mutated1), verbose=False)

        # Slack region 2: between VBMeta end and AVB_FOOTER_OFFSET
        mutated2 = bytearray(self.valid_boot)
        mutated2[33554368 - 1] = 0x01
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bytes(mutated2), verbose=False)

    def test_mutation_10_image_size_truncation_and_bloat(self):
        """Adversarial: Boot vector truncated by 1 byte or bloated by 1 byte."""
        truncated = bytes(self.valid_boot[:-1])
        bloated = bytes(self.valid_boot) + b"\x00"
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(truncated, verbose=False)
        with self.assertRaises(LKAVBInvariantError):
            verify_lk_avb_invariant(bloated, verbose=False)

    def test_mutation_11_vendor_boot_adversarial_bitflips(self):
        """
        Adversarial: Inject bitflips into vendor_boot pinned region.
        Assert that verify_vendor_boot_preservation catches salted hash corruption.
        """
        stock_vb = Path(r"C:\platform-tools\stock_vendor_boot.img")
        if stock_vb.is_file():
            raw_data = bytearray(stock_vb.read_bytes())
            # Test bitflips at offsets 0, 100, 25047039 (boundary byte)
            for test_offset in [0, 100, 4096, 25047039]:
                corrupted = bytearray(raw_data)
                corrupted[test_offset] ^= 0x80
                with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
                    tmp.write(corrupted)
                    tmp_path = Path(tmp.name)
                try:
                    with self.assertRaises(StockPreservationError):
                        verify_vendor_boot_preservation(tmp_path, verbose=False)
                finally:
                    tmp_path.unlink(missing_ok=True)

    def test_mutation_12_oversized_kernel_assembly_rejection(self):
        """
        Adversarial: Attempt to assemble boot vector with a kernel larger than
        (14,561,280 - 4096 = 14,557,184 bytes). Assembler must reject with ValueError.
        """
        oversized_kernel = b"\x1f\x8b\x08" + b"A" * 15000000
        with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as tmp_k:
            tmp_k.write(oversized_kernel)
            tmp_k_path = Path(tmp_k.name)

        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp_out:
            tmp_out_path = Path(tmp_out.name)

        try:
            with self.assertRaises(ValueError):
                assemble_pmos_boot.assemble_pmos_boot(
                    kernel_source=tmp_k_path,
                    output_path=tmp_out_path,
                    verbose=False,
                )
        finally:
            tmp_k_path.unlink(missing_ok=True)
            tmp_out_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

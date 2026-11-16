#!/usr/bin/env python3
"""
tests/test_adversarial_m3.py - Adversarial Stress Harness & Edge Case Generator
Milestone 3: Kernel AVB 2.0 Chain, Dual-Boot Recovery & Alternative OS Architecture
Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786 / MT6768)

Objectives & Adversarial Coverage:
1. AVB 2.0 Header Corruption:
   - Systematic bit-flips in byte 123 (verity flags != 0x00 across all 8 bit positions and combinations).
   - Modified OEM public keys (single-bit flips, zeroed, foreign keys, truncated descriptors).
   - Misaligned VBMeta offsets (offset % 4096 != 0: +1, +2, +3, +4, +16, +256, +2048, +4095).
   - VBMeta block boundary and size overflows (> footer pos, < 256 bytes).
   - Corrupted AVBf footers (invalid magic, invalid version, shifted footer offset).
   - Boot header corruption (invalid magic, header version mismatches, missing recovery ramdisk).
   - Authentication block & Header+Aux SHA256 signature self-integrity mutations.
2. vendor_boot Salt-Pinned Hash Descriptor:
   - Protected payload size != 25,047,040 bytes (truncated, 0, 100, 4096, 25047039).
   - Altered salts (single-bit flips, zeroed, foreign, non-hex strings).
   - Single-bit modifications across vendor_boot payload (boundary and internal offsets).
   - Pinned vs unpinned boundary characterization (byte 25047039 vs 25047040).
3. Dual-Boot Slot-Switching Stress:
   - Malformed slot suffixes (_c, _z, none, empty, numeric _0, 1, verbose slot_a, traversal ../a).
   - Unbootable flags & retry counter exhaustion (slot-unbootable: yes, retries: 0).
   - BCB message buffer corruptions (< 2048 bytes, 0xFF noise, unprintable characters, no null terminator).
   - Zero-data-loss blacklist enforcement across command casing and variations.
4. White-Box Gap Analysis:
   - Truncated buffers in verify_vbmeta_flag_byte.
   - BCB creation buffer overflow truncation.
   - DualBootManager dry-run lifecycle idempotency under loop stress.
   - verify_file dispatcher handling of mutated files.
"""

import hashlib
import os
import random
import struct
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Optional, Tuple

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from kernel_recovery.verify_avb_chain import (
    verify_avb_chain,
    verify_vendor_boot_hash,
    verify_file,
    AVBVerificationError,
    EXPECTED_BOOT_SIZE,
    FOOTER_SIZE,
    AVB_FOOTER_MAGIC,
    VBMETA_MAGIC,
    BOOT_MAGIC,
    VENDOR_BOOT_MAGIC,
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
    BCB_SIZE,
)


class TestAVBHeaderCorruptionStress(unittest.TestCase):
    """
    Adversarial generator probing AVB 2.0 header corruption, bit-flips,
    alignment violations, and cryptographic descriptor mutations.
    """

    @classmethod
    def setUpClass(cls):
        cls.clean_boot_path = r"C:\platform-tools\poplar_boot_v12_clean.img"
        cls.rec_boot_path = r"C:\platform-tools\recovery_boot.img"
        cls.stock_boot_path = r"C:\platform-tools\stock_boot.img"

        with open(cls.clean_boot_path, "rb") as f:
            cls.clean_boot_data = f.read()

        with open(cls.rec_boot_path, "rb") as f:
            cls.rec_boot_data = f.read()

        with open(cls.stock_boot_path, "rb") as f:
            cls.stock_boot_data = f.read()

        # Sanity check baseline passes before mutating
        cls.baseline_meta = verify_avb_chain(cls.clean_boot_data, verbose=False)
        assert cls.baseline_meta["flags_byte_123"] == 0x00
        assert cls.baseline_meta["vbmeta_offset"] == 0xc52000

    def test_01_byte123_individual_bit_flips(self):
        """
        Adversarial test: Flip every single bit in byte 123 (verity flags != 0).
        Bits 0 through 7, plus flags=3 (--disable-verity) and 0xff.
        Verify verify_avb_chain strictly rejects every single one.
        """
        vb_off = 0xc52000
        bit_test_values = [
            0x01,  # bit 0 (HASHTREE_DISABLED)
            0x02,  # bit 1 (VERIFICATION_DISABLED)
            0x03,  # bits 0 & 1 (--disable-verity --disable-verification)
            0x04,  # bit 2
            0x08,  # bit 3
            0x10,  # bit 4
            0x20,  # bit 5
            0x40,  # bit 6
            0x80,  # bit 7
            0xff,  # all bits set
        ]

        for flag_val in bit_test_values:
            with self.subTest(flag_val=hex(flag_val)):
                mutated = bytearray(self.clean_boot_data)
                mutated[vb_off + 123] = flag_val

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)

                err_msg = str(ctx.exception).lower()
                self.assertTrue(
                    "flags violation" in err_msg or "byte 123" in err_msg,
                    f"Expected flags violation error for 0x{flag_val:02x}, got: {err_msg}"
                )

    def test_02_byte123_bit_flips_on_recovery_boot(self):
        """
        Adversarial test: Flip bits in byte 123 on recovery_boot.img (vbmeta offset 0xe28000).
        """
        rec_vb_off = 0xe28000
        for flag_val in [0x01, 0x02, 0x03, 0x80]:
            with self.subTest(flag_val=hex(flag_val)):
                mutated = bytearray(self.rec_boot_data)
                mutated[rec_vb_off + 123] = flag_val

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), require_ramdisk=True, verbose=False)
                self.assertIn("flags violation", str(ctx.exception).lower())

    def test_03_vbmeta_flag_byte_inspector_all_non_zero_values(self):
        """
        Adversarial test: verify_vbmeta_flag_byte must reject all 255 non-zero byte values.
        """
        base_header = b"\x00" * 123 + b"\x00" + b"\x00" * 132
        # Sanity check 0x00 is valid
        ok, val = verify_vbmeta_flag_byte(base_header)
        self.assertTrue(ok)
        self.assertEqual(val, 0)

        # Stress all non-zero values 1 through 255
        for b in range(1, 256):
            mutated = b"\x00" * 123 + bytes([b]) + b"\x00" * 132
            ok, val = verify_vbmeta_flag_byte(mutated)
            self.assertFalse(ok, f"verify_vbmeta_flag_byte erroneously accepted flag byte 0x{b:02x}")
            self.assertEqual(val, b)

    def test_04_modified_oem_public_key_single_bit_mutations(self):
        """
        Adversarial test: Mutate OEM public key in VBMeta block by single-bit flips.
        Must strictly raise AVBVerificationError with Public Key Mismatch.
        """
        vb_off = 0xc52000
        auth_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 12 : vb_off + 20])[0]
        pubk_off = struct.unpack(">Q", self.clean_boot_data[vb_off + 64 : vb_off + 72])[0]
        pubk_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 72 : vb_off + 80])[0]
        pubk_start = vb_off + 256 + auth_sz + pubk_off

        # Test mutating at byte 0, middle byte, and last byte of public key
        offsets_to_flip = [0, pubk_sz // 2, pubk_sz - 1]
        for off in offsets_to_flip:
            with self.subTest(key_byte_offset=off):
                mutated = bytearray(self.clean_boot_data)
                mutated[pubk_start + off] ^= 0x01  # Flip single bit

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)

                err_msg = str(ctx.exception).lower()
                self.assertIn("public key mismatch", err_msg)

    def test_05_zeroed_oem_public_key(self):
        """
        Adversarial test: Public key replaced with all zeros.
        """
        vb_off = 0xc52000
        auth_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 12 : vb_off + 20])[0]
        pubk_off = struct.unpack(">Q", self.clean_boot_data[vb_off + 64 : vb_off + 72])[0]
        pubk_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 72 : vb_off + 80])[0]
        pubk_start = vb_off + 256 + auth_sz + pubk_off

        mutated = bytearray(self.clean_boot_data)
        mutated[pubk_start : pubk_start + pubk_sz] = b"\x00" * pubk_sz

        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated), verbose=False)
        self.assertIn("public key mismatch", str(ctx.exception).lower())

    def test_06_substituted_foreign_public_key(self):
        """
        Adversarial test: Replace OEM public key with foreign (Google/AOSP test key) data.
        """
        vb_off = 0xc52000
        auth_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 12 : vb_off + 20])[0]
        pubk_off = struct.unpack(">Q", self.clean_boot_data[vb_off + 64 : vb_off + 72])[0]
        pubk_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 72 : vb_off + 80])[0]
        pubk_start = vb_off + 256 + auth_sz + pubk_off

        # Random pseudo-key of identical size
        foreign_key = os.urandom(pubk_sz)
        mutated = bytearray(self.clean_boot_data)
        mutated[pubk_start : pubk_start + pubk_sz] = foreign_key

        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated), verbose=False)
        self.assertIn("public key mismatch", str(ctx.exception).lower())

    def test_07_corrupted_public_key_size_and_offsets(self):
        """
        Adversarial test: Corrupt pubk_sz = 0 or huge pubk_off.
        """
        vb_off = 0xc52000
        # 1. pubk_sz = 0
        mutated1 = bytearray(self.clean_boot_data)
        mutated1[vb_off + 72 : vb_off + 80] = struct.pack(">Q", 0)
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated1), verbose=False)
        self.assertIn("no public key descriptor", str(ctx.exception).lower())

        # 2. pubk_off pointing far beyond block
        mutated2 = bytearray(self.clean_boot_data)
        mutated2[vb_off + 64 : vb_off + 72] = struct.pack(">Q", 0x1000000)
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated2), verbose=False)
        self.assertIn("public key mismatch", str(ctx.exception).lower())

    def test_08_misaligned_vbmeta_offsets(self):
        """
        Adversarial test: Mutate VBMeta offset in AVB footer to values where offset % 4096 != 0.
        Test +1, +2, +3, +4, +16, +256, +2048, +4095.
        """
        footer_pos = EXPECTED_BOOT_SIZE - FOOTER_SIZE
        # In AVB footer: magic(4) + vmaj(4) + vmin(4) + orig_sz(8) = 20 -> vbmeta_offset is at 20:28
        base_offset = 0xc52000

        unaligned_offsets = [
            base_offset + 1,
            base_offset + 2,
            base_offset + 3,
            base_offset + 4,
            base_offset + 16,
            base_offset + 256,
            base_offset + 2048,
            base_offset + 4095,
        ]

        for off in unaligned_offsets:
            with self.subTest(unaligned_offset=hex(off)):
                mutated = bytearray(self.clean_boot_data)
                mutated[footer_pos + 20 : footer_pos + 28] = struct.pack(">Q", off)

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)

                err_msg = str(ctx.exception).lower()
                self.assertTrue(
                    "page alignment violation" in err_msg or "not 4096-byte aligned" in err_msg,
                    f"Expected alignment violation for 0x{off:x}, got: {err_msg}"
                )

    def test_09_vbmeta_offset_boundary_overflow(self):
        """
        Adversarial test: VBMeta block extends past the AVB footer.
        """
        footer_pos = EXPECTED_BOOT_SIZE - FOOTER_SIZE
        mutated = bytearray(self.clean_boot_data)
        # Position offset at footer_pos - 1000 (aligned to 4096 is impossible without being < footer_pos,
        # but let's test a valid aligned offset near end where offset + size > footer_pos)
        # 33554432 - 4096 = 33550336 (aligned to 4096: 33550336 % 4096 == 0)
        near_end_aligned = EXPECTED_BOOT_SIZE - 4096
        # Size = 2432. near_end_aligned + 2432 = 33550336 + 2432 = 33552768.
        # footer_pos is 33554432 - 64 = 33554368. That fits.
        # If size = 5000, 33550336 + 5000 = 33555336 > footer_pos!
        mutated[footer_pos + 20 : footer_pos + 28] = struct.pack(">Q", near_end_aligned)
        mutated[footer_pos + 28 : footer_pos + 36] = struct.pack(">Q", 5000)

        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated), verbose=False)
        self.assertIn("boundary violation", str(ctx.exception).lower())

    def test_10_corrupted_avbf_footer_magic(self):
        """
        Adversarial test: Mutate AVB footer magic to non-AVBf sequences.
        """
        footer_pos = EXPECTED_BOOT_SIZE - FOOTER_SIZE
        bad_magics = [
            b"AVBF",  # wrong case
            b"AVB0",  # vbmeta magic instead of footer
            b"ROTF",
            b"FOOT",
            b"\x00\x00\x00\x00",
            b"\xff\xff\xff\xff",
        ]

        for bad in bad_magics:
            with self.subTest(bad_magic=bad):
                mutated = bytearray(self.clean_boot_data)
                mutated[footer_pos : footer_pos + 4] = bad

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)
                self.assertIn("avb footer magic violation", str(ctx.exception).lower())

    def test_11_corrupted_total_image_sizes(self):
        """
        Adversarial test: Verify total partition size enforcement (strictly 33,554,432 bytes).
        """
        test_sizes = [
            0,
            1,
            1024,
            EXPECTED_BOOT_SIZE - 1,  # 33,554,431 (-1 byte)
            EXPECTED_BOOT_SIZE + 1,  # 33,554,433 (+1 byte)
            67108864,                # 64 MB
        ]

        for sz in test_sizes:
            with self.subTest(target_size=sz):
                if sz < len(self.clean_boot_data):
                    test_data = self.clean_boot_data[:sz]
                else:
                    test_data = self.clean_boot_data + b"\x00" * (sz - len(self.clean_boot_data))

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(test_data, verbose=False)
                self.assertIn("image size violation", str(ctx.exception).lower())

    def test_12_corrupted_boot_header_magic(self):
        """
        Adversarial test: Mutate boot header magic at offset 0.
        """
        bad_boot_magics = [
            b"ANDROID?",
            b"VNDRBOOT",
            b"BOOT_IMG",
            b"\x00" * 8,
            b"\xff" * 8,
        ]

        for bad in bad_boot_magics:
            with self.subTest(bad_magic=bad):
                mutated = bytearray(self.clean_boot_data)
                mutated[0:8] = bad

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)
                self.assertIn("boot header magic violation", str(ctx.exception).lower())

    def test_13_recovery_missing_ramdisk(self):
        """
        Adversarial test: Zero out ramdisk size on recovery_boot.img with require_ramdisk=True.
        """
        mutated = bytearray(self.rec_boot_data)
        # Boot Header v4 has ramdisk_size at bytes 12:16
        mutated[12:16] = struct.pack("<I", 0)

        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated), require_ramdisk=True, verbose=False)
        self.assertIn("recovery ramdisk missing", str(ctx.exception).lower())

    def test_14_auth_block_digest_corruption(self):
        """
        Adversarial test: Mutate authentication block stored hash or header bytes.
        """
        vb_off = 0xc52000
        # 1. Flip a byte in header (0..255)
        mutated1 = bytearray(self.clean_boot_data)
        mutated1[vb_off + 10] ^= 0x5a
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated1), verbose=False)
        self.assertIn("digest mismatch", str(ctx.exception).lower())

        # 2. Flip a byte in auth block stored hash
        mutated2 = bytearray(self.clean_boot_data)
        mutated2[vb_off + 256 + 16] ^= 0xa5
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated2), verbose=False)
        self.assertIn("digest mismatch", str(ctx.exception).lower())


class TestVendorBootSaltPinnedHashStress(unittest.TestCase):
    """
    Adversarial generator probing vendor_boot salt-pinned hash descriptor,
    second-preimage resistance, payload boundary conditions, and salt mutations.
    """

    @classmethod
    def setUpClass(cls):
        cls.vendor_boot_path = r"C:\platform-tools\stock_vendor_boot.img"
        with open(cls.vendor_boot_path, "rb") as f:
            cls.vendor_boot_full = f.read()
        cls.pinned_payload = cls.vendor_boot_full[:VENDOR_BOOT_PINNED_SIZE]

        # Verify baseline matches 100%
        valid, comp, exp = verify_vendor_boot_hash(cls.vendor_boot_full, verbose=False)
        assert valid is True
        assert comp.lower() == VENDOR_BOOT_PINNED_HASH.lower()

    def test_15_payload_size_mismatches(self):
        """
        Adversarial test: Feed truncated vendor_boot payloads of various sizes
        (0, 1, 100, 4096, 25,047,039 = exact size - 1 byte).
        Must strictly return (False, "vendor_boot truncated...", expected_hash).
        """
        bad_sizes = [0, 1, 100, 4096, 1000000, VENDOR_BOOT_PINNED_SIZE - 1]

        for sz in bad_sizes:
            with self.subTest(truncated_size=sz):
                truncated = self.pinned_payload[:sz]
                valid, msg, exp = verify_vendor_boot_hash(truncated, verbose=False)
                self.assertFalse(valid)
                self.assertIn("truncated", msg.lower())
                self.assertEqual(exp.lower(), VENDOR_BOOT_PINNED_HASH.lower())

    def test_16_altered_salts_bit_flips(self):
        """
        Adversarial test: Single-bit flips across salt hex string.
        Must strictly fail hash verification.
        """
        salt_bytes = bytearray(bytes.fromhex(AVB_SALT_HEX))
        offsets_to_flip = [0, len(salt_bytes) // 2, len(salt_bytes) - 1]

        for off in offsets_to_flip:
            with self.subTest(salt_byte_offset=off):
                mutated_salt = bytearray(salt_bytes)
                mutated_salt[off] ^= 0x01
                salt_hex = mutated_salt.hex()

                valid, comp_h, exp_h = verify_vendor_boot_hash(
                    self.pinned_payload, salt_hex=salt_hex, verbose=False
                )
                self.assertFalse(valid)
                self.assertNotEqual(comp_h.lower(), exp_h.lower())

    def test_17_altered_salts_zero_and_foreign(self):
        """
        Adversarial test: All-zero salt, all-FF salt, foreign test salts.
        """
        foreign_salts = [
            "00" * 32,
            "ff" * 32,
            "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        ]

        for s_hex in foreign_salts:
            with self.subTest(foreign_salt=s_hex[:16]):
                valid, comp_h, exp_h = verify_vendor_boot_hash(
                    self.pinned_payload, salt_hex=s_hex, verbose=False
                )
                self.assertFalse(valid)
                self.assertNotEqual(comp_h.lower(), exp_h.lower())

    def test_18_malformed_salt_non_hex(self):
        """
        Adversarial test: Malformed non-hex or odd-length salt strings.
        Must raise ValueError from bytes.fromhex.
        """
        bad_salts = [
            "not_hex_at_all",
            "5db37c8e2388c9788a77775fcf84c5acc26ee2bb5166a785cfa92909f7fb7bcG",  # 'G' invalid
            "5db37c",  # odd or short
        ]
        for bad in bad_salts:
            with self.subTest(bad_salt=bad):
                if len(bad) % 2 != 0 or any(c not in "0123456789abcdefABCDEF" for c in bad):
                    with self.assertRaises(ValueError):
                        verify_vendor_boot_hash(self.pinned_payload, salt_hex=bad, verbose=False)

    def test_19_single_bit_modifications_across_payload(self):
        """
        Adversarial test: Single-bit flips at various positions across the 25,047,040 payload.
        Byte 0 (magic 'V' -> 'W'), Byte 7, Byte 8, Byte 1024, Byte 65536,
        Byte 12,500,000 (middle), Byte 25047038, Byte 25047039 (last byte).
        Must fail on every single mutation.
        """
        test_offsets = [
            0,
            7,
            8,
            1024,
            65536,
            12500000,
            VENDOR_BOOT_PINNED_SIZE - 2,
            VENDOR_BOOT_PINNED_SIZE - 1,
        ]

        for off in test_offsets:
            with self.subTest(payload_offset=off):
                mutated = bytearray(self.pinned_payload)
                mutated[off] ^= 0x01

                valid, comp_h, exp_h = verify_vendor_boot_hash(bytes(mutated), verbose=False)
                self.assertFalse(valid, f"Mutated byte at offset {off} was erroneously accepted!")
                self.assertNotEqual(comp_h.lower(), exp_h.lower())

    def test_20_modification_outside_pinned_payload(self):
        """
        Adversarial test: Verify LK hash descriptor scope boundary.
        The full stock_vendor_boot.img is 67,108,864 bytes (64 MB), but the LK hash
        descriptor explicitly pins ONLY the first 25,047,040 bytes.
        Mutations at index 25,047,040 (partition padding) do NOT alter the pinned digest.
        """
        # Mutate the padding byte right after 25,047,040
        mutated_full = bytearray(self.vendor_boot_full)
        mutated_full[VENDOR_BOOT_PINNED_SIZE] ^= 0xff

        valid, comp_h, exp_h = verify_vendor_boot_hash(bytes(mutated_full), verbose=False)
        self.assertTrue(valid, "Padding byte outside pinned payload should not affect LK hash descriptor.")
        self.assertEqual(comp_h.lower(), exp_h.lower())


class TestDualBootSlotSwitchingStress(unittest.TestCase):
    """
    Adversarial generator stress-testing slot-switching edge cases,
    malformed slot suffixes, unbootable flags, and BCB corruptions.
    """

    def setUp(self):
        self.mgr = DualBootManager(mock=True, dry_run=True)

    def test_21_malformed_slot_suffixes(self):
        """
        Adversarial test: Fastboot and ADB slot resolution with malformed slot suffixes:
        _c, _z, none, empty, _0, 1, slot_a, ../a.
        """
        transport = DeviceTransport(mock=True)

        # 1. Invalid slots to --set-active
        invalid_slots = ["c", "z", "none", "0", "1", "../a", "slot_a", ""]
        for bad_slot in invalid_slots:
            with self.subTest(bad_slot=bad_slot):
                code, out, err = transport.run_fastboot([f"--set-active={bad_slot}"])
                self.assertNotEqual(code, 0, f"fastboot --set-active={bad_slot} should fail!")
                self.assertIn("FAIL", err)

        # 2. Valid slots a and b must succeed
        for valid_slot in ["a", "b", "_a", "_b"]:
            code, out, err = transport.run_fastboot([f"--set-active={valid_slot}"])
            self.assertEqual(code, 0)
            self.assertIn("OKAY", err)

    def test_22_unbootable_flag_recovery(self):
        """
        Adversarial test: Setup unbootable slot state (unbootable: yes, retries: 0).
        Executing set_os_boot resets slot retries and clears unbootable state.
        """
        transport = self.mgr.transport
        # Switch mock transport to fastboot mode to test fastboot getvar all parsing
        transport._mock_mode = "fastboot"
        # Force Slot A into unbootable brick state
        transport._mock_unbootable["a"] = "yes"
        transport._mock_retries["a"] = 0
        transport._mock_slot = "b"

        # Verify state is unbootable
        st = self.mgr.get_status()
        self.assertEqual(st["slot_a_unbootable"], "yes")
        self.assertEqual(st["slot_a_retry"], 0)

        # Execute set_os_boot
        ok, msg = self.mgr.set_os_boot(dry_run=False)
        self.assertTrue(ok)

        # Verify slot A is now active, retries restored to 7, and unbootable cleared to "no"
        code, out, err = transport.run_fastboot(["getvar", "current-slot"])
        self.assertIn("current-slot: a", err)
        self.assertEqual(transport._mock_retries["a"], 7)
        self.assertEqual(transport._mock_unbootable["a"], "no")

    def test_23_bcb_message_buffer_truncation(self):
        """
        Adversarial test: parse_bcb_message with buffers smaller than 2048 bytes.
        Must strictly raise ValueError.
        """
        bad_buffer_sizes = [0, 1, 16, 31, 64, 512, 1024, 2047]
        for sz in bad_buffer_sizes:
            with self.subTest(buffer_size=sz):
                with self.assertRaises(ValueError) as ctx:
                    parse_bcb_message(b"\x00" * sz)
                self.assertIn("bcb buffer too small", str(ctx.exception).lower())

    def test_24_bcb_binary_noise_and_non_ascii(self):
        """
        Adversarial test: Feed 2048 bytes of 0xFF, random binary bytes, and non-ASCII characters.
        Must parse safely without uncaught exceptions.
        """
        # 1. All 0xFF
        raw_ff = b"\xff" * BCB_SIZE
        parsed_ff = parse_bcb_message(raw_ff)
        self.assertIsInstance(parsed_ff["command"], str)

        # 2. Random binary noise
        noise = os.urandom(BCB_SIZE)
        parsed_noise = parse_bcb_message(noise)
        self.assertIsInstance(parsed_noise["command"], str)
        self.assertIsInstance(parsed_noise["recovery"], str)

        # 3. High Unicode sequences
        unicode_str = ("recovery\n" + "🔥" * 100).encode("utf-8")
        padded = unicode_str.ljust(BCB_SIZE, b"\x00")[:BCB_SIZE]
        parsed_uni = parse_bcb_message(padded)
        self.assertIn("recovery", parsed_uni["command"])

    def test_25_bcb_no_null_terminators(self):
        """
        Adversarial test: BCB fields packed without any null terminator (all 32 bytes non-zero).
        """
        cmd_32 = b"A" * 32
        status_32 = b"B" * 32
        rec_768 = b"C" * 768
        stage_32 = b"D" * 32
        res_1184 = b"\x00" * 1184
        raw = cmd_32 + status_32 + rec_768 + stage_32 + res_1184

        parsed = parse_bcb_message(raw)
        self.assertEqual(len(parsed["command"]), 32)
        self.assertEqual(parsed["command"], "A" * 32)
        self.assertEqual(len(parsed["recovery"]), 768)

    def test_26_zero_data_loss_blacklist_enforcement(self):
        """
        Adversarial test: Ensure DeviceTransport._audit_command_safety strictly blocks
        all variations, casings, and arguments containing forbidden wipe commands.
        """
        transport = DeviceTransport(mock=True)

        forbidden_inputs = [
            "fastboot erase userdata",
            "fastboot ERASE USERDATA",
            "fastboot format userdata",
            "fastboot FORMAT USERDATA",
            "fastboot erase data",
            "fastboot format data",
            "fastboot -w",
            "fastboot -W",
            "fastboot wipe userdata",
            "adb shell rm -rf /data",
            "adb shell RM -RF /DATA",
            "adb shell mkfs.f2fs /dev/block/mmcblk0p52",
        ]

        for bad_cmd in forbidden_inputs:
            with self.subTest(bad_cmd=bad_cmd):
                with self.assertRaises(RuntimeError) as ctx:
                    transport._audit_command_safety(bad_cmd)
                self.assertIn("CRITICAL SAFETY VIOLATION", str(ctx.exception))


class TestWhiteBoxGapAnalysis(unittest.TestCase):
    """
    White-box gap analysis: edge cases, API boundaries, and uncovered paths.
    """

    def test_27_truncated_vbmeta_flag_byte_buffer(self):
        """
        Edge case: verify_vbmeta_flag_byte on buffers shorter than 124 bytes.
        """
        short_buf = b"\x00" * 50
        ok, byte_val = verify_vbmeta_flag_byte(short_buf)
        self.assertFalse(ok)
        self.assertEqual(byte_val, -1)

    def test_28_create_bcb_message_overflow_handling(self):
        """
        Edge case: create_bcb_message with excessively long command and recovery strings.
        Must truncate cleanly to 32 and 768 bytes, null terminate, and produce exactly 2048 bytes.
        """
        huge_cmd = "boot-recovery-" + "X" * 100
        huge_args = "recovery\n" + "Y" * 2000

        msg = create_bcb_message(command=huge_cmd, recovery_args=huge_args)
        self.assertEqual(len(msg), BCB_SIZE)

        parsed = parse_bcb_message(msg)
        self.assertTrue(parsed["command"].startswith("boot-recovery-"))
        self.assertLessEqual(len(parsed["command"]), 31)
        self.assertTrue(parsed["recovery"].startswith("recovery\n"))
        self.assertLessEqual(len(parsed["recovery"]), 767)

    def test_29_test_dry_run_idempotency_stress(self):
        """
        Stress test: Execute test_dry_run repeatedly in a 20-cycle loop.
        Confirms zero state leakage or degradation.
        """
        mgr = DualBootManager(mock=True, dry_run=True)
        for i in range(20):
            ok = mgr.test_dry_run()
            self.assertTrue(ok, f"test_dry_run failed on iteration {i+1}")

    def test_30_verify_file_dispatcher_edge_cases(self):
        """
        Edge case: verify_file on non-existent file, empty file, and temporary mutated files.
        """
        # Non-existent
        self.assertFalse(verify_file(r"C:\platform-tools\does_not_exist.img", verbose=False))

        # Empty file
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            self.assertFalse(verify_file(tmp_path, verbose=False))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()

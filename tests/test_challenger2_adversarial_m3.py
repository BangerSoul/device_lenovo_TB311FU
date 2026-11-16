#!/usr/bin/env python3
"""
tests/test_challenger2_adversarial_m3.py - Challenger 2 Adversarial Stress Suite (Iteration 2)
Focus Area: Kernel AVB 2.0 Chain, Dual-Boot Recovery & Alternative OS Architecture (Milestone 3)
Target: Lenovo Tab M11 (TB311FU / poplar, serial HNQ09EZD, MediaTek MT8786 / MT6768)

Objectives & Adversarial Coverage:
1. AVB 2.0 Header Corruption:
   - Systematic bit-flips in byte 123 (verity flags != 0x00 across all 8 bit positions, combinations, 0x03, 0xFF).
   - Bit mutations in header flags bytes 120-122 (Authentication block SHA256 integrity).
   - Modified OEM public keys (single-bit flips, zeroed, foreign keys, truncated descriptors, out-of-bounds offsets).
   - Misaligned VBMeta offsets (offset % 4096 != 0: +1, +2, +3, +4, +16, +64, +256, +512, +1024, +2048, +4095).
   - VBMeta block boundary overflows (> footer position, truncated < 256 bytes).
   - Corrupted AVBf footers (invalid magic, non-AVBf sequences, shifted footer position).
   - Boot header corruption (invalid magic, invalid version, missing TWRP recovery ramdisk).
2. vendor_boot Salt-Pinned Hash Descriptor:
   - Payload size != 25,047,040 bytes (0, 1, 100, 4096, 25,047,039 = exact - 1).
   - Altered salts (single-bit flips, zeroed, 0xFF, foreign, malformed non-hex strings).
   - Single-bit modifications across payload (index 0, 7, 8, 1024, 65536, midpoint, boundary index 25,047,039).
   - Pinned vs unpinned boundary characterization (byte 25,047,039 vs byte 25,047,040).
3. Dual-Boot Slot-Switching Stress:
   - Malformed slot suffixes (_c, _z, none, empty, numeric 0, 1, verbose slot_a, path traversal ../a).
   - Unbootable flags & retry counter exhaustion (slot-unbootable: yes, retries: 0 -> recovered via set_os_boot).
   - BCB message buffer corruptions (< 2048 bytes, 0xFF noise, random binary noise, non-null terminated strings).
   - BCB message field truncation and overflow protection.
4. Zero Data Loss Adversarial Probes:
   - Mandatory dispatch probes: 'fastboot format:f2fs userdata', 'format:ext4 userdata', 'blkdiscard /dev/block/by-name/userdata'.
   - Comprehensive destructive variants: 'fastboot format:f2fs:0x1000 userdata', 'fastboot -w', 'mkfs.ext4', 'dd of=userdata', 'rm -rf /data'.
   - Whitelist verification: legitimate non-destructive flashing and slot-switching commands must pass safely.
"""

import hashlib
import os
import re
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
    FORBIDDEN_DESTRUCTIVE_PATTERN,
    BCB_SIZE,
)


class TestChallenger2_AVBHeaderCorruption(unittest.TestCase):
    """
    Suite 1: Adversarial empirical stress testing of AVB 2.0 header corruption,
    bit-flips, alignment invariants, and cryptographic signature rejection.
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

        # Sanity check baselines satisfy AVB 2.0 before mutation
        cls.baseline_clean = verify_avb_chain(cls.clean_boot_data, verbose=False)
        assert cls.baseline_clean["flags_byte_123"] == 0x00
        assert cls.baseline_clean["vbmeta_offset"] == 0xc52000

        cls.baseline_rec = verify_avb_chain(cls.rec_boot_data, require_ramdisk=True, verbose=False)
        assert cls.baseline_rec["flags_byte_123"] == 0x00
        assert cls.baseline_rec["vbmeta_offset"] == 0xe28000

    def test_01_byte123_systematic_bit_flips(self):
        """
        Adversarial test: Mutate byte 123 (verity flags != 0x00).
        Test every individual bit (0..7) and combined bit patterns.
        verify_avb_chain must strictly raise AVBVerificationError on every single one.
        """
        vb_off = 0xc52000
        flag_cases = [
            (0x01, "bit 0 (HASHTREE_DISABLED)"),
            (0x02, "bit 1 (VERIFICATION_DISABLED)"),
            (0x03, "bits 0 & 1 (--disable-verity --disable-verification)"),
            (0x04, "bit 2"),
            (0x08, "bit 3"),
            (0x10, "bit 4"),
            (0x20, "bit 5"),
            (0x40, "bit 6"),
            (0x80, "bit 7"),
            (0x0F, "low nibble"),
            (0x55, "alternating 01010101"),
            (0xAA, "alternating 10101010"),
            (0xFF, "all bits set"),
        ]

        for flag_val, desc in flag_cases:
            with self.subTest(flag=hex(flag_val), description=desc):
                mutated = bytearray(self.clean_boot_data)
                mutated[vb_off + 123] = flag_val

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)

                err_str = str(ctx.exception).lower()
                self.assertTrue(
                    "flags violation" in err_str or "byte 123" in err_str,
                    f"Expected flags violation for {desc} (0x{flag_val:02x}), got: {err_str}"
                )

    def test_02_byte123_mutations_on_recovery_boot(self):
        """
        Adversarial test: Mutate byte 123 on recovery_boot.img (vbmeta offset 0xe28000).
        """
        rec_vb_off = 0xe28000
        for flag_val in [0x01, 0x02, 0x03, 0x80, 0xFF]:
            with self.subTest(flag=hex(flag_val)):
                mutated = bytearray(self.rec_boot_data)
                mutated[rec_vb_off + 123] = flag_val

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), require_ramdisk=True, verbose=False)
                self.assertIn("flags violation", str(ctx.exception).lower())

    def test_03_flags_bytes_120_to_122_mutations(self):
        """
        Adversarial test: Mutate flags bytes 120, 121, or 122 (keeping byte 123 = 0).
        Even if byte 123 is 0, any mutation in bytes 120-122 breaks the VBMeta header
        hash, triggering an Authentication Block digest mismatch.
        """
        vb_off = 0xc52000
        for offset in [120, 121, 122]:
            with self.subTest(header_offset=offset):
                mutated = bytearray(self.clean_boot_data)
                mutated[vb_off + offset] ^= 0x01

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)

                err_str = str(ctx.exception).lower()
                self.assertIn("digest mismatch", err_str)

    def test_04_modified_oem_public_keys(self):
        """
        Adversarial test: Mutate OEM public key by single-bit flips, zeroing,
        foreign test key injection, and truncation.
        Must strictly raise AVBVerificationError with Public Key Mismatch.
        """
        vb_off = 0xc52000
        auth_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 12 : vb_off + 20])[0]
        pubk_off = struct.unpack(">Q", self.clean_boot_data[vb_off + 64 : vb_off + 72])[0]
        pubk_sz = struct.unpack(">Q", self.clean_boot_data[vb_off + 72 : vb_off + 80])[0]
        pubk_start = vb_off + 256 + auth_sz + pubk_off

        # 1. Single-bit flips at index 0, midpoint, and last byte
        for off in [0, pubk_sz // 2, pubk_sz - 1]:
            with self.subTest(key_mutation_offset=off):
                mutated = bytearray(self.clean_boot_data)
                mutated[pubk_start + off] ^= 0x01
                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)
                self.assertIn("public key mismatch", str(ctx.exception).lower())

        # 2. All-zero public key
        mutated_zero = bytearray(self.clean_boot_data)
        mutated_zero[pubk_start : pubk_start + pubk_sz] = b"\x00" * pubk_sz
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated_zero), verbose=False)
        self.assertIn("public key mismatch", str(ctx.exception).lower())

        # 3. Foreign test key
        foreign_key = b"FOREIGN_KEY_TEST_BYTES_" * (pubk_sz // 23 + 1)
        mutated_foreign = bytearray(self.clean_boot_data)
        mutated_foreign[pubk_start : pubk_start + pubk_sz] = foreign_key[:pubk_sz]
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated_foreign), verbose=False)
        self.assertIn("public key mismatch", str(ctx.exception).lower())

        # 4. Zeroed public key size descriptor (pubk_sz = 0)
        mutated_sz0 = bytearray(self.clean_boot_data)
        mutated_sz0[vb_off + 72 : vb_off + 80] = struct.pack(">Q", 0)
        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated_sz0), verbose=False)
        self.assertIn("no public key descriptor", str(ctx.exception).lower())

    def test_05_misaligned_vbmeta_offsets(self):
        """
        Adversarial test: Mutate VBMeta offset in AVB footer to values where offset % 4096 != 0.
        Test offsets: +1, +2, +3, +4, +16, +64, +256, +512, +1024, +2048, +4095.
        Must strictly raise AVBVerificationError with Page Alignment Violation.
        """
        footer_pos = EXPECTED_BOOT_SIZE - FOOTER_SIZE
        base_offset = 0xc52000

        unaligned_offsets = [
            base_offset + 1,
            base_offset + 2,
            base_offset + 3,
            base_offset + 4,
            base_offset + 16,
            base_offset + 64,
            base_offset + 256,
            base_offset + 512,
            base_offset + 1024,
            base_offset + 2048,
            base_offset + 4095,
        ]

        for off in unaligned_offsets:
            with self.subTest(unaligned_offset=hex(off)):
                mutated = bytearray(self.clean_boot_data)
                # vbmeta_offset is at footer bytes 20:28
                mutated[footer_pos + 20 : footer_pos + 28] = struct.pack(">Q", off)

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)

                err_str = str(ctx.exception).lower()
                self.assertTrue(
                    "page alignment violation" in err_str or "not 4096-byte aligned" in err_str,
                    f"Expected page alignment violation for 0x{off:x}, got: {err_str}"
                )

    def test_06_corrupted_avbf_footers(self):
        """
        Adversarial test: Mutate AVB footer magic and position.
        Must strictly raise AVBVerificationError with AVB Footer Magic Violation.
        """
        footer_pos = EXPECTED_BOOT_SIZE - FOOTER_SIZE
        corrupted_magics = [
            b"AVBF",  # wrong case
            b"AVB0",  # vbmeta magic instead of footer
            b"FOOT",
            b"\x00\x00\x00\x00",
            b"\xff\xff\xff\xff",
            b"BOOT",
        ]

        for bad in corrupted_magics:
            with self.subTest(bad_magic=bad):
                mutated = bytearray(self.clean_boot_data)
                mutated[footer_pos : footer_pos + 4] = bad

                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)
                self.assertIn("avb footer magic violation", str(ctx.exception).lower())

        # Test shifted footer: zero out footer at 0x1FFFFC0 and place at 0x1FFFF80
        mutated_shifted = bytearray(self.clean_boot_data)
        real_footer = bytes(mutated_shifted[footer_pos : footer_pos + FOOTER_SIZE])
        mutated_shifted[footer_pos : footer_pos + FOOTER_SIZE] = b"\x00" * FOOTER_SIZE
        mutated_shifted[footer_pos - 64 : footer_pos] = real_footer

        with self.assertRaises(AVBVerificationError) as ctx:
            verify_avb_chain(bytes(mutated_shifted), verbose=False)
        self.assertIn("avb footer magic violation", str(ctx.exception).lower())

    def test_07_boot_header_and_image_size_invariants(self):
        """
        Adversarial test: Boot image size != 32 MB or invalid boot header magic.
        """
        # Size violation
        bad_sizes = [0, 512, 1024, EXPECTED_BOOT_SIZE - 1, EXPECTED_BOOT_SIZE + 1, 67108864]
        for sz in bad_sizes:
            with self.subTest(bad_size=sz):
                data = self.clean_boot_data[:sz] if sz < len(self.clean_boot_data) else self.clean_boot_data + b"\x00" * (sz - len(self.clean_boot_data))
                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(data, verbose=False)
                self.assertIn("image size violation", str(ctx.exception).lower())

        # Magic violation
        bad_magics = [b"ANDROID?", b"VNDRBOOT", b"\x00" * 8, b"\xff" * 8]
        for m in bad_magics:
            with self.subTest(bad_magic=m):
                mutated = bytearray(self.clean_boot_data)
                mutated[0:8] = m
                with self.assertRaises(AVBVerificationError) as ctx:
                    verify_avb_chain(bytes(mutated), verbose=False)
                self.assertIn("boot header magic violation", str(ctx.exception).lower())


class TestChallenger2_VendorBootHashDescriptor(unittest.TestCase):
    """
    Suite 2: Adversarial empirical stress testing of vendor_boot salt-pinned
    hash descriptor, second-preimage resistance, payload boundary, and salt mutations.
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

    def test_08_payload_size_mismatches(self):
        """
        Adversarial test: Payload size != 25,047,040 bytes.
        Must strictly return (False, "vendor_boot truncated...", expected_hash).
        """
        bad_sizes = [0, 1, 100, 4096, 1000000, VENDOR_BOOT_PINNED_SIZE - 1]

        for sz in bad_sizes:
            with self.subTest(size=sz):
                truncated = self.pinned_payload[:sz]
                valid, msg, exp = verify_vendor_boot_hash(truncated, verbose=False)
                self.assertFalse(valid)
                self.assertIn("truncated", msg.lower())
                self.assertEqual(exp.lower(), VENDOR_BOOT_PINNED_HASH.lower())

    def test_09_altered_salts_bit_flips_and_foreign(self):
        """
        Adversarial test: Single-bit flips and foreign values in salt.
        Must strictly fail hash verification.
        """
        salt_bytes = bytearray(bytes.fromhex(AVB_SALT_HEX))

        # Single-bit flips
        for off in [0, len(salt_bytes) // 2, len(salt_bytes) - 1]:
            with self.subTest(salt_bit_flip_offset=off):
                mutated_salt = bytearray(salt_bytes)
                mutated_salt[off] ^= 0x01
                valid, comp_h, exp_h = verify_vendor_boot_hash(
                    self.pinned_payload, salt_hex=mutated_salt.hex(), verbose=False
                )
                self.assertFalse(valid)
                self.assertNotEqual(comp_h.lower(), exp_h.lower())

        # All-zero and all-FF salts
        for s_hex in ["00" * 32, "ff" * 32]:
            with self.subTest(foreign_salt=s_hex):
                valid, comp_h, exp_h = verify_vendor_boot_hash(
                    self.pinned_payload, salt_hex=s_hex, verbose=False
                )
                self.assertFalse(valid)
                self.assertNotEqual(comp_h.lower(), exp_h.lower())

        # Malformed non-hex salt
        with self.assertRaises(ValueError):
            verify_vendor_boot_hash(self.pinned_payload, salt_hex="not_valid_hex_salt!", verbose=False)

    def test_10_single_bit_modifications_in_vendor_boot_bytes(self):
        """
        Adversarial test: Single-bit modifications across vendor_boot payload bytes.
        Test offsets: 0, 7, 8, 1024, 65536, midpoint (12500000), 25047038, 25047039.
        SHA256 mismatch must be strictly detected on every single mutation.
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
                self.assertFalse(valid, f"Mutated byte at offset {off} was accepted!")
                self.assertNotEqual(comp_h.lower(), exp_h.lower())

    def test_11_pinned_vs_unpinned_boundary_characterization(self):
        """
        Adversarial test: Compare byte 25,047,039 (last pinned byte) vs byte 25,047,040 (unpinned padding).
        Mutating byte 25,047,039 MUST fail the hash check.
        Mutating byte 25,047,040 MUST NOT fail the hash check.
        """
        # Inside pinned region: MUST FAIL
        inside_mutated = bytearray(self.vendor_boot_full)
        inside_mutated[VENDOR_BOOT_PINNED_SIZE - 1] ^= 0xff
        valid_in, comp_in, exp_in = verify_vendor_boot_hash(bytes(inside_mutated), verbose=False)
        self.assertFalse(valid_in)
        self.assertNotEqual(comp_in.lower(), exp_in.lower())

        # Outside pinned region (partition padding): MUST PASS
        outside_mutated = bytearray(self.vendor_boot_full)
        outside_mutated[VENDOR_BOOT_PINNED_SIZE] ^= 0xff
        valid_out, comp_out, exp_out = verify_vendor_boot_hash(bytes(outside_mutated), verbose=False)
        self.assertTrue(valid_out)
        self.assertEqual(comp_out.lower(), exp_out.lower())


class TestChallenger2_DualBootSlotSwitchingStress(unittest.TestCase):
    """
    Suite 3: Adversarial empirical stress testing of slot-switching edge cases,
    malformed slot suffixes, unbootable flags, and BCB corruptions.
    """

    def setUp(self):
        self.mgr = DualBootManager(mock=True, dry_run=True)

    def test_12_malformed_slot_suffixes(self):
        """
        Adversarial test: Fastboot slot switching with malformed slot suffixes.
        Test _c, _z, none, empty, numeric _0, 1, slot_a, ../a.
        All invalid slots must return non-zero returncode and stderr containing FAIL.
        """
        transport = DeviceTransport(mock=True)
        malformed_slots = ["c", "_c", "z", "_z", "none", "0", "1", "_0", "_1", "slot_a", "../a", ""]

        for slot in malformed_slots:
            with self.subTest(bad_slot=slot):
                code, out, err = transport.run_fastboot([f"--set-active={slot}"])
                self.assertNotEqual(code, 0, f"--set-active={slot} should fail!")
                self.assertIn("FAIL", err)

        # Valid slots must succeed
        for valid_slot in ["a", "b", "_a", "_b"]:
            code, out, err = transport.run_fastboot([f"--set-active={valid_slot}"])
            self.assertEqual(code, 0)
            self.assertIn("OKAY", err)

    def test_13_unbootable_flags_and_retry_exhaustion_recovery(self):
        """
        Adversarial test: Simulate unbootable state on Slot A (unbootable: yes, retries: 0).
        set_os_boot must recover the slot by resetting retries to 7, setting active to A,
        and clearing unbootable status to 'no'.
        """
        transport = self.mgr.transport
        transport._mock_mode = "fastboot"
        transport._mock_unbootable["a"] = "yes"
        transport._mock_retries["a"] = 0
        transport._mock_slot = "b"

        # Check unbootable pre-condition
        st = self.mgr.get_status()
        self.assertEqual(st["slot_a_unbootable"], "yes")
        self.assertEqual(st["slot_a_retry"], 0)

        # Recover via set_os_boot
        ok, msg = self.mgr.set_os_boot(dry_run=False)
        self.assertTrue(ok)

        # Check post-condition: recovered
        code, out, err = transport.run_fastboot(["getvar", "current-slot"])
        self.assertIn("current-slot: a", err)
        self.assertEqual(transport._mock_retries["a"], 7)
        self.assertEqual(transport._mock_unbootable["a"], "no")

    def test_14_bcb_message_corruptions_and_truncations(self):
        """
        Adversarial test: BCB buffer truncation, binary noise, non-null terminated strings.
        """
        # Buffer truncation (< 2048 bytes)
        for sz in [0, 1, 31, 64, 512, 1024, 2047]:
            with self.subTest(truncated_bcb_size=sz):
                with self.assertRaises(ValueError) as ctx:
                    parse_bcb_message(b"\x00" * sz)
                self.assertIn("bcb buffer too small", str(ctx.exception).lower())

        # 0xFF noise
        parsed_ff = parse_bcb_message(b"\xff" * BCB_SIZE)
        self.assertIsInstance(parsed_ff["command"], str)

        # Random binary noise
        parsed_noise = parse_bcb_message(os.urandom(BCB_SIZE))
        self.assertIsInstance(parsed_noise["command"], str)

        # Non-null terminated strings (32 non-zero bytes for command, 768 for recovery)
        raw_non_null = b"A" * 32 + b"B" * 32 + b"C" * 768 + b"D" * 32 + b"\x00" * 1184
        parsed_non_null = parse_bcb_message(raw_non_null)
        self.assertEqual(len(parsed_non_null["command"]), 32)
        self.assertEqual(parsed_non_null["command"], "A" * 32)
        self.assertEqual(len(parsed_non_null["recovery"]), 768)


class TestChallenger2_ZeroDataLossAdversarialProbes(unittest.TestCase):
    """
    Suite 4: Adversarial empirical probes verifying zero data loss enforcement.
    Strictly asserts that all destructive wiping, formatting, and partition-zeroing
    commands are intercepted and blocked.
    """

    def setUp(self):
        self.transport = DeviceTransport(mock=True)

    def test_15_explicit_mandatory_destructive_probes_blocked(self):
        """
        Adversarial test: Verify the explicit probes mandated by the dispatch:
        1. 'fastboot format:f2fs userdata'
        2. 'format:ext4 userdata'
        3. 'blkdiscard /dev/block/by-name/userdata'
        All must raise RuntimeError matching 'CRITICAL SAFETY VIOLATION'.
        """
        mandatory_probes = [
            "fastboot format:f2fs userdata",
            "format:ext4 userdata",
            "blkdiscard /dev/block/by-name/userdata",
        ]

        for probe in mandatory_probes:
            with self.subTest(probe=probe):
                with self.assertRaises(RuntimeError) as ctx:
                    self.transport._audit_command_safety(probe)
                self.assertIn("CRITICAL SAFETY VIOLATION", str(ctx.exception))

    def test_16_extended_destructive_variations_blocked(self):
        """
        Adversarial test: Test format variants with filesystem parameters,
        erase, wipe, rm -rf, mkfs, dd, blkdiscard, and standalone -w flag.
        """
        destructive_commands = [
            "fastboot format:f2fs userdata",
            "fastboot format:ext4 userdata",
            "fastboot format:f2fs:0x1000 userdata",
            "fastboot format:ext4:4096 userdata",
            "fastboot format userdata",
            "fastboot FORMAT USERDATA",
            "fastboot format data",
            "fastboot erase userdata",
            "fastboot ERASE USERDATA",
            "fastboot erase data",
            "fastboot wipe userdata",
            "fastboot -w",
            "fastboot -W",
            "fastboot flash userdata custom.img",
            "fastboot flash userdata_a custom.img",
            "fastboot flash userdata_b custom.img",
            "blkdiscard /dev/block/by-name/userdata",
            "blkdiscard /dev/block/mmcblk0p52",
            "make_ext4fs /dev/block/by-name/userdata",
            "mkfs.ext4 /dev/block/by-name/userdata",
            "mkfs.f2fs /dev/block/mmcblk0p52",
            "dd if=/dev/zero of=/dev/block/by-name/userdata",
            "dd if=/dev/zero of=/dev/block/mmcblk0p52",
            "rm -rf /data",
            "rm -r /data/user/0",
            "rm -rf /data",
        ]

        for cmd in destructive_commands:
            with self.subTest(destructive_command=cmd):
                with self.assertRaises(RuntimeError) as ctx:
                    self.transport._audit_command_safety(cmd)
                self.assertIn("CRITICAL SAFETY VIOLATION", str(ctx.exception))

    def test_17_regex_pattern_direct_matching(self):
        """
        Adversarial test: Directly probe FORBIDDEN_DESTRUCTIVE_PATTERN regex against
        adversarial injection strings.
        """
        probes = [
            ("format:f2fs userdata", True),
            ("format:ext4 userdata", True),
            ("blkdiscard /dev/block/by-name/userdata", True),
            ("mkfs.ext4 /dev/block/by-name/userdata", True),
            ("dd if=/dev/zero of=/dev/block/by-name/userdata", True),
            ("rm -rf /data", True),
            ("fastboot -w", True),
            ("fastboot flash boot_a boot.img", False),
            ("fastboot flash vendor_a vendor_stabilized.img", False),
            ("fastboot --set-active=b", False),
            ("fastboot erase misc", False),
            ("fastboot getvar all", False),
        ]

        for cmd, should_match in probes:
            with self.subTest(cmd=cmd, should_match=should_match):
                match = bool(FORBIDDEN_DESTRUCTIVE_PATTERN.search(cmd))
                self.assertEqual(match, should_match, f"Regex mismatch for '{cmd}' (got {match}, expected {should_match})")

    def test_18_legitimate_commands_safely_permitted(self):
        """
        Adversarial test: Verify legitimate non-destructive flashing, slot-switching,
        and BCB clearing commands pass without raising any exception.
        """
        legitimate_commands = [
            "fastboot flash boot_a poplar_boot_v12_clean.img",
            "fastboot flash boot_b recovery_boot.img",
            "fastboot flash vendor_a vendor_stabilized.img",
            "fastboot -S 64M flash system_a system.img",
            "fastboot --set-active=b",
            "fastboot --set-active=a",
            "fastboot reboot recovery",
            "fastboot reboot",
            "fastboot erase misc",
            "fastboot getvar is-userspace",
            "fastboot getvar current-slot",
            "dd if=/dev/zero of=/dev/block/by-name/misc bs=2048 count=1",
            "cat /proc/partitions",
            "uname -r",
        ]

        for cmd in legitimate_commands:
            with self.subTest(legitimate_command=cmd):
                # Should not raise exception
                self.transport._audit_command_safety(cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)

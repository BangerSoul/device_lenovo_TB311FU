#!/usr/bin/env python3
"""
test_avb_patch.py - Comprehensive Unit Tests for AVB & Ramdisk Verity Patching.

Tests:
1. AVB 2.0 vbmeta header parsing and patching:
   - Setting flag |= 3 (HASHTREE_DISABLED | VERIFICATION_DISABLED) at offset 120
   - Preservation of all other header bytes (magic, versions, hashes, release string)
   - Bitwise-OR logic preserving pre-existing flags
   - Footer-based vbmeta offset location
   - Truncated and corrupt image error handling
   - Minimal empty vbmeta generation
   - Shell CLI subprocess execution of disable_avb.sh
2. Ramdisk fstab verity patching:
   - Stripping avb, avb=..., avb_keys=...
   - Stripping verify, verify=..., verify_at_boot
   - Converting forceencrypt=... and forcefde=... to encryptable=...
   - Converting lone stripped flags to 'defaults'
   - Preserving comments, blank lines, and column alignment
   - Directory recursion over ramdisk file trees
   - Shell CLI subprocess execution of patch_ramdisk_verity.sh
3. End-to-end multi-image pipeline integration
"""

import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

# Ensure the scripts directory is on sys.path for direct module import
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Import the patcher modules under test
from disable_avb import (
    AVB_FLAGS_OFFSET,
    AVB_FOOTER_MAGIC,
    AVB_HEADER_SIZE,
    AVB_MAGIC,
    AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED,
    AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED,
    DEFAULT_DISABLE_FLAGS,
    create_empty_vbmeta,
    describe_flags,
    find_vbmeta_header_offset,
    patch_vbmeta_data,
    patch_vbmeta_file,
    read_vbmeta_header,
)
from patch_ramdisk_verity import (
    convert_flag,
    filter_flags,
    is_avb_flag,
    is_verify_flag,
    patch_fstab_content,
    patch_fstab_file,
    patch_fstab_line,
    patch_ramdisk_directory,
)

SCRIPT_DIR = Path(__file__).resolve().parent
DISABLE_AVB_SH = SCRIPT_DIR / "disable_avb.sh"
PATCH_RAMDISK_SH = SCRIPT_DIR / "patch_ramdisk_verity.sh"


class TestAVBDisableHeader(unittest.TestCase):
    """Unit tests for AVB vbmeta header inspection and patching."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="avb_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_vbmeta(
        self,
        filename: str,
        initial_flags: int = 0,
        size: int = 4096,
        release: bytes = b"test_release_str\x00",
    ) -> Path:
        """Helper to create a binary file with valid AVB0 header."""
        path = Path(self.test_dir) / filename
        buf = bytearray(size)
        # Offset 0..3: "AVB0"
        buf[0:4] = AVB_MAGIC
        # Offset 4..7: Major version 1
        struct.pack_into(">I", buf, 4, 1)
        # Offset 8..11: Minor version 0
        struct.pack_into(">I", buf, 8, 0)
        # Offset 12..19: Auth block size
        struct.pack_into(">Q", buf, 12, 512)
        # Offset 20..27: Aux block size
        struct.pack_into(">Q", buf, 20, 1024)
        # Offset 120..123: flags
        struct.pack_into(">I", buf, AVB_FLAGS_OFFSET, initial_flags)
        # Offset 128..128+len: release string
        buf[128 : 128 + len(release)] = release

        with open(path, "wb") as f:
            f.write(buf)
        return path

    def test_avb_header_offset_120_patching(self):
        """Verify that offset 120 flags are patched to |= 3 and header stays valid."""
        img = self._create_mock_vbmeta("vbmeta.img", initial_flags=0)

        # Verify before
        flags_before, offset, hdr_before = read_vbmeta_header(str(img))
        self.assertEqual(flags_before, 0)
        self.assertEqual(offset, 0)
        self.assertEqual(hdr_before[:4], AVB_MAGIC)

        # Patch
        old_flags, new_flags, patched_offset = patch_vbmeta_file(str(img))
        self.assertEqual(old_flags, 0)
        self.assertEqual(new_flags, 3)
        self.assertEqual(patched_offset, 0)

        # Verify after
        flags_after, offset_after, hdr_after = read_vbmeta_header(str(img))
        self.assertEqual(flags_after, 3)
        self.assertEqual(offset_after, 0)

        # Verify exact bytes at 120..123
        with open(img, "rb") as f:
            f.seek(120)
            raw_flags = f.read(4)
        expected_bytes = struct.pack(">I", 3)
        self.assertEqual(raw_flags, expected_bytes)
        self.assertEqual(raw_flags, b"\x00\x00\x00\x03")

        # Verify all other header bytes before and after offset 120 are identical
        self.assertEqual(hdr_before[:120], hdr_after[:120])
        self.assertEqual(hdr_before[124:256], hdr_after[124:256])

    def test_bitwise_or_preserves_existing_flags(self):
        """Verify that bitwise OR preserves other flag bits."""
        # Case 1: Initial flag 0x04 (some vendor flag)
        img1 = self._create_mock_vbmeta("vbmeta_extra.img", initial_flags=0x04)
        old, new, _ = patch_vbmeta_file(str(img1))
        self.assertEqual(old, 0x04)
        self.assertEqual(new, 0x07)  # 0x04 | 0x03 == 0x07

        # Case 2: HASHTREE_DISABLED already set (0x01)
        img2 = self._create_mock_vbmeta("vbmeta_ht.img", initial_flags=0x01)
        old, new, _ = patch_vbmeta_file(str(img2))
        self.assertEqual(old, 0x01)
        self.assertEqual(new, 0x03)

        # Case 3: VERIFICATION_DISABLED already set (0x02)
        img3 = self._create_mock_vbmeta("vbmeta_vd.img", initial_flags=0x02)
        old, new, _ = patch_vbmeta_file(str(img3))
        self.assertEqual(old, 0x02)
        self.assertEqual(new, 0x03)

        # Case 4: Already fully disabled (0x03) -> Idempotent
        img4 = self._create_mock_vbmeta("vbmeta_already.img", initial_flags=0x03)
        old, new, _ = patch_vbmeta_file(str(img4))
        self.assertEqual(old, 0x03)
        self.assertEqual(new, 0x03)

    def test_multiple_images_patching(self):
        """Verify patching vbmeta.img, vbmeta_system.img, vbmeta_vendor.img together."""
        images = [
            self._create_mock_vbmeta("vbmeta.img", initial_flags=0),
            self._create_mock_vbmeta("vbmeta_system.img", initial_flags=0),
            self._create_mock_vbmeta("vbmeta_vendor.img", initial_flags=0),
        ]

        for img in images:
            old, new, offset = patch_vbmeta_file(str(img))
            self.assertEqual(old, 0)
            self.assertEqual(new, 3)
            flags, _, _ = read_vbmeta_header(str(img))
            self.assertEqual(flags, 3)

    def test_avb_footer_offset_detection(self):
        """Verify that vbmeta offset is correctly resolved when image has an AVB footer."""
        total_size = 65536
        vbmeta_offset = 32768
        buf = bytearray(total_size)

        # Place AVB0 header at 32768
        buf[vbmeta_offset : vbmeta_offset + 4] = AVB_MAGIC
        struct.pack_into(">I", buf, vbmeta_offset + 4, 1)
        struct.pack_into(">I", buf, vbmeta_offset + AVB_FLAGS_OFFSET, 0)

        # Place AVB footer at EOF (last 64 bytes)
        footer_pos = total_size - 64
        buf[footer_pos : footer_pos + 4] = AVB_FOOTER_MAGIC
        struct.pack_into(">I", buf, footer_pos + 4, 1)  # footer version major
        struct.pack_into(">Q", buf, footer_pos + 24, vbmeta_offset)  # vbmeta_offset
        struct.pack_into(">Q", buf, footer_pos + 32, 4096)  # vbmeta_size

        path = Path(self.test_dir) / "partition_with_footer.img"
        with open(path, "wb") as f:
            f.write(buf)

        # Read and patch
        flags_before, resolved_offset, _ = read_vbmeta_header(str(path))
        self.assertEqual(flags_before, 0)
        self.assertEqual(resolved_offset, vbmeta_offset)

        old, new, offset = patch_vbmeta_file(str(path))
        self.assertEqual(old, 0)
        self.assertEqual(new, 3)
        self.assertEqual(offset, vbmeta_offset)

        flags_after, _, _ = read_vbmeta_header(str(path))
        self.assertEqual(flags_after, 3)

    def test_invalid_and_corrupt_files(self):
        """Verify error handling on non-AVB or truncated files."""
        # Non-AVB file
        bad_magic_path = Path(self.test_dir) / "corrupt.img"
        with open(bad_magic_path, "wb") as f:
            f.write(b"NOT_AN_AVB_HEADER" + b"\x00" * 200)
        with self.assertRaises(ValueError):
            read_vbmeta_header(str(bad_magic_path))

        # Truncated file (< 124 bytes)
        short_path = Path(self.test_dir) / "short.img"
        with open(short_path, "wb") as f:
            f.write(b"AVB0" + b"\x00" * 20)
        with self.assertRaises(ValueError):
            read_vbmeta_header(str(short_path))

        # Non-existent file
        with self.assertRaises(FileNotFoundError):
            patch_vbmeta_file(str(Path(self.test_dir) / "missing.img"))

    def test_create_empty_vbmeta(self):
        """Verify create_empty_vbmeta creates a valid 4096-byte disabled vbmeta."""
        out_path = Path(self.test_dir) / "created_vbmeta.img"
        create_empty_vbmeta(str(out_path), size=4096, flags=3)
        self.assertTrue(out_path.is_file())
        self.assertEqual(out_path.stat().st_size, 4096)

        flags, offset, hdr = read_vbmeta_header(str(out_path))
        self.assertEqual(flags, 3)
        self.assertEqual(offset, 0)
        self.assertEqual(hdr[:4], AVB_MAGIC)

    def test_cli_disable_avb_sh(self):
        """Verify CLI execution of disable_avb.sh with multiple arguments and --check."""
        img1 = self._create_mock_vbmeta("cli_vbmeta.img", initial_flags=0)
        img2 = self._create_mock_vbmeta("cli_vbmeta_system.img", initial_flags=0)

        # Run disable_avb.sh
        cmd = ["bash", str(DISABLE_AVB_SH), str(img1), str(img2)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("0x00000000", res.stdout)
        self.assertIn("0x00000003", res.stdout)

        # Verify with --check
        check_cmd = ["bash", str(DISABLE_AVB_SH), "--check", str(img1), str(img2)]
        check_res = subprocess.run(check_cmd, capture_output=True, text=True)
        self.assertEqual(check_res.returncode, 0)
        self.assertIn("flags=0x00000003", check_res.stdout)


class TestRamdiskVerityPatch(unittest.TestCase):
    """Unit tests for fstab AVB/dm-verity flag removal and encryption conversion."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ramdisk_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_flag_detection_helpers(self):
        """Test is_avb_flag, is_verify_flag, and convert_flag functions."""
        # AVB flags
        self.assertTrue(is_avb_flag("avb"))
        self.assertTrue(is_avb_flag("avb=vbmeta"))
        self.assertTrue(is_avb_flag("avb=vbmeta_system"))
        self.assertTrue(is_avb_flag("avb=vbmeta_vendor"))
        self.assertTrue(is_avb_flag("avb_keys=/avb/q-gsi.avbpubkey"))
        self.assertTrue(is_avb_flag("avb_keys"))
        self.assertFalse(is_avb_flag("first_stage_mount"))
        self.assertFalse(is_avb_flag("wait"))

        # Verify flags
        self.assertTrue(is_verify_flag("verify"))
        self.assertTrue(is_verify_flag("verify=/etc/key"))
        self.assertTrue(is_verify_flag("verify_at_boot"))
        self.assertFalse(is_verify_flag("check"))

        # Encryption conversion
        conv, changed = convert_flag("forceencrypt=/metadata/vold/encryption")
        self.assertTrue(changed)
        self.assertEqual(conv, "encryptable=/metadata/vold/encryption")

        conv, changed = convert_flag("forceencrypt=footer")
        self.assertTrue(changed)
        self.assertEqual(conv, "encryptable=footer")

        conv, changed = convert_flag("forceencrypt")
        self.assertTrue(changed)
        self.assertEqual(conv, "encryptable")

        conv, changed = convert_flag("forcefde=/metadata")
        self.assertTrue(changed)
        self.assertEqual(conv, "encryptable=/metadata")

        conv, changed = convert_flag("fileencryption=aes-256-xts")
        self.assertFalse(changed)
        self.assertEqual(conv, "fileencryption=aes-256-xts")

    def test_strip_avb_and_keys(self):
        """Verify removing avb and avb_keys flags from fstab lines."""
        line = (
            "system /system erofs ro "
            "wait,slotselect,avb=vbmeta_system,logical,first_stage_mount,"
            "avb_keys=/avb/q-gsi.avbpubkey:/avb/r-gsi.avbpubkey\n"
        )
        patched, changes = patch_fstab_line(line)
        self.assertEqual(changes, 2)
        expected = "system /system erofs ro wait,slotselect,logical,first_stage_mount\n"
        self.assertEqual(patched, expected)

    def test_strip_standalone_avb(self):
        """Verify removing standalone avb flag."""
        line = "vendor /vendor erofs ro wait,slotselect,avb,logical,first_stage_mount\n"
        patched, changes = patch_fstab_line(line)
        self.assertEqual(changes, 1)
        expected = "vendor /vendor erofs ro wait,slotselect,logical,first_stage_mount\n"
        self.assertEqual(patched, expected)

    def test_strip_verify_flags(self):
        """Verify removing verify, verify=..., and verify_at_boot."""
        line1 = "product /product ext4 ro wait,verify,logical\n"
        patched1, c1 = patch_fstab_line(line1)
        self.assertEqual(c1, 1)
        self.assertEqual(patched1, "product /product ext4 ro wait,logical\n")

        line2 = "system /system ext4 ro wait,verify=/data/key,first_stage_mount\n"
        patched2, c2 = patch_fstab_line(line2)
        self.assertEqual(c2, 1)
        self.assertEqual(patched2, "system /system ext4 ro wait,first_stage_mount\n")

        line3 = "vendor /vendor ext4 ro wait,verify_at_boot,check\n"
        patched3, c3 = patch_fstab_line(line3)
        self.assertEqual(c3, 1)
        self.assertEqual(patched3, "vendor /vendor ext4 ro wait,check\n")

    def test_convert_forceencrypt_to_encryptable(self):
        """Verify converting forceencrypt to encryptable."""
        line = (
            "/dev/block/by-name/userdata /data f2fs noatime,nosuid,nodev "
            "forceencrypt=/metadata/vold/metadata_encryption,latemount,wait,check\n"
        )
        patched, changes = patch_fstab_line(line)
        self.assertEqual(changes, 1)
        self.assertIn("encryptable=/metadata/vold/metadata_encryption", patched)
        self.assertNotIn("forceencrypt", patched)
        self.assertIn("latemount,wait,check", patched)

    def test_empty_flags_become_defaults(self):
        """Verify that when all flags are stripped, the field becomes 'defaults'."""
        line = "vendor /vendor ext4 ro avb\n"
        patched, changes = patch_fstab_line(line)
        self.assertEqual(changes, 1)
        self.assertEqual(patched, "vendor /vendor ext4 ro defaults\n")

    def test_comments_and_whitespace_preservation(self):
        """Verify comments and blank lines are untouched."""
        comment = "# Android fstab for MediaTek MT6768\n"
        patched, changes = patch_fstab_line(comment)
        self.assertEqual(changes, 0)
        self.assertEqual(patched, comment)

        blank = "   \n"
        patched_b, changes_b = patch_fstab_line(blank)
        self.assertEqual(changes_b, 0)
        self.assertEqual(patched_b, blank)

    def test_real_world_tb311fu_recovery_fstab(self):
        """Test on actual entries from TB311FU recovery.fstab."""
        fstab_content = """# Lenovo TB311FU recovery fstab
system /system erofs ro wait,slotselect,avb=vbmeta_system,logical,first_stage_mount,avb_keys=/avb/q-gsi.avbpubkey:/avb/r-gsi.avbpubkey
vendor /vendor erofs ro wait,slotselect,avb,logical,first_stage_mount
product /product erofs ro wait,slotselect,avb,logical,first_stage_mount
vendor_dlkm /vendor_dlkm erofs ro wait,slotselect,avb,logical,first_stage_mount
odm_dlkm /odm_dlkm erofs ro wait,slotselect,avb,logical,first_stage_mount
system_dlkm /system_dlkm erofs ro wait,slotselect,avb,logical,first_stage_mount
/dev/block/by-name/vbmeta_system /vbmeta_system emmc defaults first_stage_mount,nofail,slotselect,avb=vbmeta
/dev/block/by-name/userdata /data f2fs noatime,nosuid forceencrypt=/metadata/vold/encryption,wait,check
/dev/block/by-name/metadata /metadata ext4 noatime wait,check,formattable,first_stage_mount
"""
        patched_content, total_changes = patch_fstab_content(fstab_content)
        self.assertGreater(total_changes, 0)
        self.assertNotIn("avb=vbmeta_system", patched_content)
        self.assertNotIn("avb_keys=", patched_content)
        self.assertNotIn("avb=vbmeta", patched_content)
        self.assertNotIn("forceencrypt=", patched_content)
        self.assertIn("encryptable=/metadata/vold/encryption", patched_content)
        self.assertIn("wait,check,formattable,first_stage_mount", patched_content)

    def test_directory_recursive_patching(self):
        """Verify recursive discovery and patching of all fstabs in a ramdisk tree."""
        ramdisk_dir = Path(self.test_dir) / "ramdisk"
        dir1 = ramdisk_dir / "first_stage_ramdisk"
        dir2 = ramdisk_dir / "etc"
        dir1.mkdir(parents=True)
        dir2.mkdir(parents=True)

        f1 = dir1 / "fstab.mt6768"
        f2 = dir2 / "recovery.fstab"

        content1 = "system /system erofs ro wait,avb=vbmeta_system,logical\n"
        content2 = "vendor /vendor ext4 ro avb,wait\n"

        f1.write_text(content1)
        f2.write_text(content2)

        results = patch_ramdisk_directory(str(ramdisk_dir))
        self.assertEqual(len(results), 2)

        p1_content = f1.read_text()
        p2_content = f2.read_text()

        self.assertNotIn("avb", p1_content)
        self.assertNotIn("avb", p2_content)
        self.assertIn("wait,logical", p1_content)
        self.assertIn("wait", p2_content)

    def test_cli_patch_ramdisk_verity_sh(self):
        """Verify CLI execution of patch_ramdisk_verity.sh with -d and in-place edit."""
        fstab_path = Path(self.test_dir) / "fstab.test"
        fstab_path.write_text(
            "system /system erofs ro wait,avb=vbmeta_system,logical\n"
            "/dev/block/by-name/userdata /data f2fs defaults forceencrypt=/meta,wait\n"
        )

        cmd = ["bash", str(PATCH_RAMDISK_SH), "-d", str(fstab_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        self.assertIn("encryptable=/meta", fstab_path.read_text())
        self.assertNotIn("avb=", fstab_path.read_text())


class TestFullPipelineIntegration(unittest.TestCase):
    """Integration test verifying full ROM packaging pipeline AVB & verity patching."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pipeline_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_complete_packaging_avb_disable_flow(self):
        """
        Simulates the exact ROM pipeline release workflow:
        1. Prepares vbmeta.img, vbmeta_system.img, vbmeta_vendor.img
        2. Prepares ramdisk fstab
        3. Executes disable_avb and patch_ramdisk_verity
        4. Validates all partitions and headers are completely verity-free
        """
        out_dir = Path(self.test_dir)

        # 1. Create vbmeta partitions
        vbmeta = out_dir / "vbmeta.img"
        vbmeta_sys = out_dir / "vbmeta_system.img"
        vbmeta_ven = out_dir / "vbmeta_vendor.img"

        create_empty_vbmeta(str(vbmeta), flags=0)
        create_empty_vbmeta(str(vbmeta_sys), flags=0)
        create_empty_vbmeta(str(vbmeta_ven), flags=0)

        # 2. Create ramdisk fstab
        fstab_file = out_dir / "fstab.mt6768"
        fstab_file.write_text(
            "system /system erofs ro wait,slotselect,avb=vbmeta_system,logical,first_stage_mount\n"
            "vendor /vendor erofs ro wait,slotselect,avb,logical,first_stage_mount\n"
            "product /product ext4 ro wait,verify,logical\n"
            "/dev/block/by-name/userdata /data f2fs defaults forceencrypt=/metadata/vold,wait\n"
        )

        # 3. Run disable_avb on all 3 images via disable_avb.sh
        cmd1 = [
            "bash",
            str(DISABLE_AVB_SH),
            str(vbmeta),
            str(vbmeta_sys),
            str(vbmeta_ven),
        ]
        res1 = subprocess.run(cmd1, capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0, msg=res1.stderr)

        # Verify all 3 have flags == 3
        for img in [vbmeta, vbmeta_sys, vbmeta_ven]:
            flags, offset, _ = read_vbmeta_header(str(img))
            self.assertEqual(
                flags,
                DEFAULT_DISABLE_FLAGS,
                msg=f"{img.name} flags={flags} expected {DEFAULT_DISABLE_FLAGS}",
            )
            self.assertEqual(offset, 0)

        # 4. Run patch_ramdisk_verity.sh on fstab
        cmd2 = ["bash", str(PATCH_RAMDISK_SH), str(fstab_file)]
        res2 = subprocess.run(cmd2, capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0, msg=res2.stderr)

        # Verify fstab is fully clean
        fstab_text = fstab_file.read_text()
        self.assertNotIn("avb", fstab_text)
        self.assertNotIn("verify", fstab_text)
        self.assertNotIn("forceencrypt", fstab_text)
        self.assertIn("encryptable=/metadata/vold", fstab_text)
        self.assertIn("wait,slotselect,logical,first_stage_mount", fstab_text)


if __name__ == "__main__":
    unittest.main()

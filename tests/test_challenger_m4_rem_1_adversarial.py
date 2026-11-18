#!/usr/bin/env python3
"""
tests/test_challenger_m4_rem_1_adversarial.py
Challenger M4-Rem-1 Empirical Adversarial Stress Suite for Fastbootd Deployment Runner.
Target: Lenovo Tab with Clear Case (TB311FU) (TB311FU / poplar, MediaTek Helio G88 / MT8786, Serial HNQ09EZD).

Covers Authoritative Adversarial Challenge Scope:
1. Hostile Chunk Size Testing on deployment/flash_pmos_fastbootd.ps1:
   - Chunk sizes: 65M, 128M, 256M, 512M, 0M, 10M, 15M, -10M, 64KB, invalid, fooM.
   - Verify that all values > 64M or < 16M throw terminating exceptions immediately.
   - Verify that -ChunkSize 16M, 32M, and 64M succeed.
2. Hostile Image Path Testing:
   - Pass non-existent paths for -RootfsPath: C:\\nonexistent\\fake_rootfs.img, relative/nonexistent.img, ""
   - Pass directory paths for -RootfsPath: rootfs_staging, "   "
   - Pass non-existent paths for -BootPath: C:\\nonexistent\\fake_boot.img, relative/nonexistent.img, ""
   - Verify that the script terminates with an error and NEVER falls back to default images or accepts directories.
3. Fastboot Command Sequence Validation:
   - Ensure the generated commands adhere strictly to the safe sequence without partition corruption.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
DEPLOYMENT_DIR = WORKSPACE_DIR / "deployment"
PS1_PATH = DEPLOYMENT_DIR / "flash_pmos_fastbootd.ps1"


class TestHostileChunkSizes(unittest.TestCase):
    """Suite 1: Hostile Chunk Size Testing on deployment/flash_pmos_fastbootd.ps1."""

    def run_with_chunk(self, chunk_val: str):
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-ChunkSize",
                chunk_val,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_chunk_65m_rejected(self):
        res = self.run_with_chunk("65M")
        self.assertNotEqual(res.returncode, 0, "Chunk size 65M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("exceeds safe limit", combined)
        self.assertIn("<= 64M", combined)

    def test_chunk_128m_rejected(self):
        res = self.run_with_chunk("128M")
        self.assertNotEqual(res.returncode, 0, "Chunk size 128M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("exceeds safe limit", combined)
        self.assertIn("<= 64M", combined)

    def test_chunk_256m_rejected(self):
        res = self.run_with_chunk("256M")
        self.assertNotEqual(res.returncode, 0, "Chunk size 256M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("exceeds safe limit", combined)
        self.assertIn("<= 64M", combined)

    def test_chunk_512m_rejected(self):
        res = self.run_with_chunk("512M")
        self.assertNotEqual(res.returncode, 0, "Chunk size 512M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("exceeds safe limit", combined)
        self.assertIn("<= 64M", combined)

    def test_chunk_0m_rejected(self):
        res = self.run_with_chunk("0M")
        self.assertNotEqual(res.returncode, 0, "Chunk size 0M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("too small", combined)
        self.assertIn("16M", combined)

    def test_chunk_10m_rejected(self):
        res = self.run_with_chunk("10M")
        self.assertNotEqual(res.returncode, 0, "Chunk size 10M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("too small", combined)
        self.assertIn("16M", combined)

    def test_chunk_15m_rejected(self):
        res = self.run_with_chunk("15M")
        self.assertNotEqual(res.returncode, 0, "Chunk size 15M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("too small", combined)
        self.assertIn("16M", combined)

    def test_chunk_negative_10m_rejected(self):
        res = self.run_with_chunk("-10M")
        self.assertNotEqual(res.returncode, 0, "Chunk size -10M must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("too small", combined)

    def test_chunk_64kb_rejected(self):
        res = self.run_with_chunk("64KB")
        self.assertNotEqual(res.returncode, 0, "Chunk size 64KB must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("Invalid chunk size", combined)

    def test_chunk_invalid_string_rejected(self):
        res = self.run_with_chunk("invalid")
        self.assertNotEqual(res.returncode, 0, "Chunk size 'invalid' must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("Invalid chunk size", combined)

    def test_chunk_foom_rejected(self):
        res = self.run_with_chunk("fooM")
        self.assertNotEqual(res.returncode, 0, "Chunk size 'fooM' must be rejected")

    def test_chunk_16m_accepted(self):
        res = self.run_with_chunk("16M")
        self.assertEqual(res.returncode, 0, f"Chunk size 16M must succeed:\n{res.stderr}")
        self.assertIn("-S 16M", res.stdout)
        self.assertIn("DRY-RUN SUCCESS", res.stdout)

    def test_chunk_32m_accepted(self):
        res = self.run_with_chunk("32M")
        self.assertEqual(res.returncode, 0, f"Chunk size 32M must succeed:\n{res.stderr}")
        self.assertIn("-S 32M", res.stdout)
        self.assertIn("DRY-RUN SUCCESS", res.stdout)

    def test_chunk_64m_accepted(self):
        res = self.run_with_chunk("64M")
        self.assertEqual(res.returncode, 0, f"Chunk size 64M must succeed:\n{res.stderr}")
        self.assertIn("-S 64M", res.stdout)
        self.assertIn("DRY-RUN SUCCESS", res.stdout)


class TestHostileImagePaths(unittest.TestCase):
    """Suite 2: Hostile Image Path Testing on deployment/flash_pmos_fastbootd.ps1."""

    def test_rootfs_nonexistent_absolute_path_rejected(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-RootfsPath",
                r"C:\nonexistent\fake_rootfs.img",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(res.returncode, 0, "Non-existent absolute RootfsPath must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("Target rootfs image not found", combined)

    def test_rootfs_nonexistent_relative_path_rejected(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-RootfsPath",
                r"relative/nonexistent.img",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(res.returncode, 0, "Non-existent relative RootfsPath must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("Target rootfs image not found", combined)

    def test_rootfs_empty_string_must_be_rejected(self):
        """Pass empty string '' for -RootfsPath: Must terminate with error, NOT exit 0 or flash workspace directory."""
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-RootfsPath",
                "",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(
            res.returncode,
            0,
            f"Adversarial Defect: -RootfsPath '' was accepted with exit code 0! Plan generated: {res.stdout}",
        )
        combined = res.stdout + res.stderr
        self.assertIn("cannot be empty or whitespace", combined)

    def test_rootfs_whitespace_string_must_be_rejected(self):
        """Pass whitespace string '   ' for -RootfsPath: Must terminate with error."""
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-RootfsPath",
                "   ",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(res.returncode, 0, "Whitespace RootfsPath must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("cannot be empty or whitespace", combined)

    def test_rootfs_directory_path_must_be_rejected(self):
        """Pass directory 'rootfs_staging' for -RootfsPath: Must terminate with error, NOT accept directory."""
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-RootfsPath",
                "rootfs_staging",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(
            res.returncode,
            0,
            f"Adversarial Defect: Directory 'rootfs_staging' was accepted as RootfsPath! Output: {res.stdout}",
        )
        combined = res.stdout + res.stderr
        self.assertIn("Target rootfs image not found", combined)

    def test_boot_nonexistent_absolute_path_rejected(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-BootPath",
                r"C:\nonexistent\fake_boot.img",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(res.returncode, 0, "Non-existent absolute BootPath must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("Target boot vector image not found", combined)

    def test_boot_nonexistent_relative_path_rejected(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-BootPath",
                r"relative/nonexistent.img",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(res.returncode, 0, "Non-existent relative BootPath must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("Target boot vector image not found", combined)

    def test_boot_empty_string_must_be_rejected(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-BootPath",
                "",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(res.returncode, 0, "Empty string BootPath must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("cannot be empty or whitespace", combined)

    def test_boot_directory_path_must_be_rejected(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-BootPath",
                "boot_vector",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertNotEqual(res.returncode, 0, "Directory path BootPath must be rejected")
        combined = res.stdout + res.stderr
        self.assertIn("Target boot vector image not found", combined)


class TestFastbootCommandSequenceValidation(unittest.TestCase):
    """Suite 3: Fastboot Command Sequence Validation."""

    def test_safe_sequence_order(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(res.returncode, 0)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip().startswith("Step")]
        self.assertEqual(len(lines), 6, f"Expected 6 steps, got {len(lines)}: {lines}")

        # Step 1: resize logical partition
        self.assertIn("resize-logical-partition system_a 4294967296", lines[0])
        # Step 2: erase target partition
        self.assertIn("erase system_a", lines[1])
        # Step 3: flash system_a with -S 64M
        self.assertIn("-S 64M flash system_a", lines[2])
        # Step 4: flash boot_a
        self.assertIn("flash boot_a", lines[3])
        # Step 5: userdata wipe
        self.assertIn("-w", lines[4])
        # Step 6: reboot
        self.assertIn("reboot", lines[5])

    def test_skip_wipe_omits_step5(self):
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PS1_PATH),
                "-DryRun",
                "-SkipWipe",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(res.returncode, 0)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip().startswith("Step")]
        self.assertEqual(len(lines), 5, f"Expected 5 steps with SkipWipe, got {len(lines)}: {lines}")
        for l in lines:
            self.assertNotIn(" -w", l)
        self.assertIn("reboot", lines[-1])


if __name__ == "__main__":
    unittest.main()

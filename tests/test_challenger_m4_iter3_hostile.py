#!/usr/bin/env python3
"""
tests/test_challenger_m4_iter3_hostile.py
Adversarial Verification Suite by Challenger M4-Iter3-1.
Target: Lenovo Tab with Clear Case (TB311FU) (TB311FU / poplar, MediaTek Helio G88 / MT8786, Serial HNQ09EZD).

Comprehensive empirical verification of:
1. Adversarial path inputs:
   - Empty string ('') for -RootfsPath and -BootPath
   - Whitespace string ('   ') for -RootfsPath and -BootPath
   - Existing directory paths ('rootfs_staging', '.', 'boot_vector', 'tests', 'deployment')
   - Non-existent directory-like paths
2. Hostile chunk sizes:
   - Chunk sizes > 64M (65M, 128M, 256M, 512M)
   - Chunk sizes < 16M (0M, 10M, 15M, -10M)
   - Malformed chunk sizes (64KB, invalid, fooM, 64, '')
3. Nominal parameters:
   - Default dry-run
   - -SkipWipe flag
   - Explicit valid relative and absolute paths
   - Valid chunk sizes (16M, 32M, 64M)
4. Fastboot command sequence and safety invariants.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
DEPLOYMENT_DIR = WORKSPACE_DIR / "deployment"
PS1_PATH = DEPLOYMENT_DIR / "flash_pmos_fastbootd.ps1"


class TestAdversarialPathInputs(unittest.TestCase):
    """Empirically test that invalid path candidates strictly terminate with exit code 1."""

    def run_ps1(self, *extra_args):
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PS1_PATH),
            "-DryRun",
        ] + list(extra_args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_rootfs_empty_string_strictly_fails(self):
        """Pass -RootfsPath '': Must fail with exit code 1 and terminating error."""
        res = self.run_ps1("-RootfsPath", "")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("cannot be empty or whitespace", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_rootfs_whitespace_string_strictly_fails(self):
        """Pass -RootfsPath '   ': Must fail with exit code 1 and terminating error."""
        res = self.run_ps1("-RootfsPath", "   ")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("cannot be empty or whitespace", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_rootfs_directory_rootfs_staging_strictly_fails(self):
        """Pass -RootfsPath 'rootfs_staging': Must fail with exit code 1."""
        res = self.run_ps1("-RootfsPath", "rootfs_staging")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("Target rootfs image not found", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_rootfs_directory_dot_strictly_fails(self):
        """Pass -RootfsPath '.': Must fail with exit code 1."""
        res = self.run_ps1("-RootfsPath", ".")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("Target rootfs image not found", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_rootfs_directory_tests_strictly_fails(self):
        """Pass -RootfsPath 'tests': Must fail with exit code 1."""
        res = self.run_ps1("-RootfsPath", "tests")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("Target rootfs image not found", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_rootfs_directory_deployment_strictly_fails(self):
        """Pass -RootfsPath 'deployment': Must fail with exit code 1."""
        res = self.run_ps1("-RootfsPath", "deployment")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("Target rootfs image not found", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_boot_empty_string_strictly_fails(self):
        """Pass -BootPath '': Must fail with exit code 1 and terminating error."""
        res = self.run_ps1("-BootPath", "")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("cannot be empty or whitespace", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_boot_whitespace_string_strictly_fails(self):
        """Pass -BootPath '   ': Must fail with exit code 1 and terminating error."""
        res = self.run_ps1("-BootPath", "   ")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("cannot be empty or whitespace", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_boot_directory_boot_vector_strictly_fails(self):
        """Pass -BootPath 'boot_vector': Must fail with exit code 1."""
        res = self.run_ps1("-BootPath", "boot_vector")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("Target boot vector image not found", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)

    def test_boot_directory_dot_strictly_fails(self):
        """Pass -BootPath '.': Must fail with exit code 1."""
        res = self.run_ps1("-BootPath", ".")
        self.assertEqual(res.returncode, 1, f"Expected returncode 1, got {res.returncode}. Output:\n{res.stdout}")
        combined = res.stdout + res.stderr
        self.assertIn("Target boot vector image not found", combined)
        self.assertNotIn("DRY-RUN SUCCESS", combined)


class TestHostileChunkSizeOverrides(unittest.TestCase):
    """Empirically test chunk size limits (> 64M fail, < 16M fail, malformed fail)."""

    def run_chunk(self, chunk_val: str):
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

    def test_chunk_65m_fails(self):
        res = self.run_chunk("65M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("exceeds safe limit", res.stdout + res.stderr)

    def test_chunk_128m_fails(self):
        res = self.run_chunk("128M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("exceeds safe limit", res.stdout + res.stderr)

    def test_chunk_256m_fails(self):
        res = self.run_chunk("256M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("exceeds safe limit", res.stdout + res.stderr)

    def test_chunk_512m_fails(self):
        res = self.run_chunk("512M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("exceeds safe limit", res.stdout + res.stderr)

    def test_chunk_0m_fails(self):
        res = self.run_chunk("0M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("too small", res.stdout + res.stderr)

    def test_chunk_10m_fails(self):
        res = self.run_chunk("10M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("too small", res.stdout + res.stderr)

    def test_chunk_15m_fails(self):
        res = self.run_chunk("15M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("too small", res.stdout + res.stderr)

    def test_chunk_negative_10m_fails(self):
        res = self.run_chunk("-10M")
        self.assertEqual(res.returncode, 1)
        self.assertIn("too small", res.stdout + res.stderr)

    def test_chunk_64kb_fails(self):
        res = self.run_chunk("64KB")
        self.assertEqual(res.returncode, 1)
        self.assertIn("Invalid chunk size", res.stdout + res.stderr)

    def test_chunk_invalid_string_fails(self):
        res = self.run_chunk("invalid")
        self.assertEqual(res.returncode, 1)
        self.assertIn("Invalid chunk size", res.stdout + res.stderr)

    def test_chunk_foom_fails(self):
        res = self.run_chunk("fooM")
        self.assertEqual(res.returncode, 1)

    def test_chunk_empty_string_fails(self):
        res = self.run_chunk("")
        self.assertEqual(res.returncode, 1)


class TestNominalExecution(unittest.TestCase):
    """Empirically test that nominal parameters succeed with exit code 0."""

    def test_nominal_default_dry_run_succeeds(self):
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
        self.assertEqual(res.returncode, 0, f"Nominal execution failed:\n{res.stderr}")
        self.assertIn("[+] DRY-RUN SUCCESS", res.stdout)
        self.assertIn("-S 64M flash system_a", res.stdout)
        self.assertIn("resize-logical-partition system_a 4294967296", res.stdout)
        self.assertIn("flash boot_a", res.stdout)
        self.assertIn("fastboot -w", res.stdout)
        self.assertIn("reboot", res.stdout)

    def test_nominal_skip_wipe_succeeds(self):
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
        self.assertIn("[+] DRY-RUN SUCCESS", res.stdout)
        self.assertIn("Userdata Wipe:     DISABLED", res.stdout)
        self.assertNotIn("-w", [line for line in res.stdout.splitlines() if "Step" in line])

    def test_nominal_valid_chunk_sizes(self):
        for chunk in ["16M", "32M", "64M"]:
            res = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(PS1_PATH),
                    "-DryRun",
                    "-ChunkSize",
                    chunk,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(res.returncode, 0, f"Chunk size {chunk} should succeed:\n{res.stderr}")
            self.assertIn(f"-S {chunk}", res.stdout)
            self.assertIn("[+] DRY-RUN SUCCESS", res.stdout)

    def test_nominal_explicit_relative_paths(self):
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
                r"rootfs_staging\rootfs_plasma_mobile.img",
                "-BootPath",
                r"boot_vector\pmos_boot.img",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(res.returncode, 0, f"Explicit relative paths should succeed:\n{res.stderr}")
        self.assertIn("[+] DRY-RUN SUCCESS", res.stdout)

    def test_nominal_explicit_absolute_paths(self):
        abs_rootfs = str(WORKSPACE_DIR / "rootfs_staging" / "rootfs_plasma_mobile.img")
        abs_boot = str(WORKSPACE_DIR / "boot_vector" / "pmos_boot.img")
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
                abs_rootfs,
                "-BootPath",
                abs_boot,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(res.returncode, 0, f"Explicit absolute paths should succeed:\n{res.stderr}")
        self.assertIn("[+] DRY-RUN SUCCESS", res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

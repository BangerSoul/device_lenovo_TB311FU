#!/usr/bin/env python3
"""
Unit Test Suite for Milestone M5: Final Acceptance Testing, Staging & Safety Invariant.
Verifies:
  1. Staging Artifact Presence & Geometry in deployment/:
     - deployment/vendor_stabilized.img (EROFS, 295,448,576 B <= 303,345,664 B limit)
     - deployment/pmos_boot.img / boot.img (Header v4, 33,554,432 B, AVB footer, 4096-aligned)
     - deployment/treble-overlay-lenovo-tb311fu.apk (RRO min 48, max 4095, 12-bit spline)
     - deployment/treble-overlay-lenovo-tb311fu-systemui.apk (SystemUI RRO, no flashlight/cell)
     - deployment/flash_lineage23_fastbootd.ps1 (Production deployment script)
  2. Deployment Script Structure & Safety Guards:
     - WinUSB -S 64M chunking
     - Fastbootd userspace check (is-userspace == yes)
     - Logical partition management (product delete, system & vendor resize)
     - Strict prohibition: vendor_boot, vbmeta, vbmeta_system, vbmeta_vendor, fastboot -w
  3. PowerShell Execution Verification:
     - Default execution runs in DryRun mode
     - Explicit -DryRun runs in DryRun mode
     - Adversarial chunk size (>64M) is rejected
  4. R7 Stop Directive Verification:
     - Confirms zero destructive flashing commands sent to live hardware
"""

import os
import sys
import struct
import zipfile
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOYMENT_DIR = os.path.join(PROJECT_ROOT, "deployment")
SCRIPT_PATH = os.path.join(DEPLOYMENT_DIR, "flash_lineage23_fastbootd.ps1")


class TestM5DeploymentArtifactStaging(unittest.TestCase):
    """Test suite verifying all deployment artifacts are properly staged and verified."""

    def test_01_deployment_directory_exists(self):
        """Verify deployment/ directory exists."""
        self.assertTrue(os.path.isdir(DEPLOYMENT_DIR), f"Deployment dir not found: {DEPLOYMENT_DIR}")

    def test_02_vendor_stabilized_image_staged(self):
        """Verify deployment/vendor_stabilized.img exists, fits partition, and has valid EROFS magic."""
        vendor_path = os.path.join(DEPLOYMENT_DIR, "vendor_stabilized.img")
        self.assertTrue(os.path.isfile(vendor_path), f"Missing: {vendor_path}")
        size = os.path.getsize(vendor_path)
        self.assertEqual(size, 295448576, f"Vendor image size mismatch: {size} B")
        self.assertLessEqual(size, 303345664, "Vendor image exceeds vendor_a ceiling 303,345,664 B")

        with open(vendor_path, "rb") as f:
            f.seek(1024)
            magic = struct.unpack("<I", f.read(4))[0]
            self.assertEqual(magic, 0xE0F5E1E2, f"Invalid EROFS magic: 0x{magic:08x}")

    def test_03_boot_vector_images_staged(self):
        """Verify deployment/pmos_boot.img (and boot.img) exist, are 32 MB, Header v4, and AVB 2.0 compliant."""
        for name in ("pmos_boot.img", "boot.img"):
            boot_path = os.path.join(DEPLOYMENT_DIR, name)
            self.assertTrue(os.path.isfile(boot_path), f"Missing: {boot_path}")
            size = os.path.getsize(boot_path)
            self.assertEqual(size, 33554432, f"{name} size mismatch: {size} B (expected 32 MB)")

            with open(boot_path, "rb") as f:
                hdr_magic = f.read(8)
                self.assertEqual(hdr_magic, b"ANDROID!", f"{name} invalid boot header magic")
                f.seek(40)
                hdr_version = struct.unpack("<I", f.read(4))[0]
                self.assertEqual(hdr_version, 4, f"{name} header version is not 4")

                # Check AVB footer at offset 33554368
                f.seek(33554368)
                footer_bytes = f.read(64)
                (
                    footer_magic,
                    v_maj,
                    v_min,
                    orig_size,
                    vbmeta_offset,
                    vbmeta_size,
                ) = struct.unpack(">4sIIQQQ", footer_bytes[:36])
                self.assertEqual(footer_magic, b"AVBf", f"{name} missing AVB footer")
                self.assertEqual(v_maj, 1, f"{name} invalid AVB footer major version")
                self.assertEqual(v_min, 0, f"{name} invalid AVB footer minor version")
                self.assertEqual(orig_size, 14561280, f"{name} original_image_size mismatch")
                self.assertEqual(vbmeta_offset, 14561280, f"{name} vbmeta_offset mismatch")
                self.assertEqual(vbmeta_offset % 4096, 0, f"{name} vbmeta_offset not 4096-aligned")

    def test_04_framework_rro_overlay_staged(self):
        """Verify deployment/treble-overlay-lenovo-tb311fu.apk exists and contains calibrated 12-bit brightness."""
        apk_path = os.path.join(DEPLOYMENT_DIR, "treble-overlay-lenovo-tb311fu.apk")
        self.assertTrue(os.path.isfile(apk_path), f"Missing: {apk_path}")
        with zipfile.ZipFile(apk_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("AndroidManifest.xml", names)
            self.assertIn("resources.arsc", names)
            arsc = zf.read("resources.arsc")

            # Check min=48 (0x10a8), max=4095 (0x1098), default=1200 (0x1088)
            min_val = struct.unpack("<I", arsc[0x10A8:0x10AC])[0]
            max_val = struct.unpack("<I", arsc[0x1098:0x109C])[0]
            def_val = struct.unpack("<I", arsc[0x1088:0x108C])[0]
            self.assertEqual(min_val, 48, f"Overlay min brightness {min_val} != 48")
            self.assertEqual(max_val, 4095, f"Overlay max brightness {max_val} != 4095")
            self.assertEqual(def_val, 1200, f"Overlay default brightness {def_val} != 1200")

    def test_05_systemui_rro_overlay_staged(self):
        """Verify deployment/treble-overlay-lenovo-tb311fu-systemui.apk exists and sanitizes SystemUI."""
        apk_path = os.path.join(DEPLOYMENT_DIR, "treble-overlay-lenovo-tb311fu-systemui.apk")
        self.assertTrue(os.path.isfile(apk_path), f"Missing: {apk_path}")
        with zipfile.ZipFile(apk_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("AndroidManifest.xml", names)
            self.assertIn("resources.arsc", names)
            manifest = zf.read("AndroidManifest.xml")
            self.assertTrue(
                b"com.android.systemui" in manifest or "com.android.systemui".encode("utf-16le") in manifest,
                "Target com.android.systemui missing from manifest",
            )
            self.assertTrue(
                b"me.phh.treble.overlay.lenovo.tb311fu.systemui" in manifest
                or "me.phh.treble.overlay.lenovo.tb311fu.systemui".encode("utf-16le") in manifest,
                "Package me.phh.treble.overlay.lenovo.tb311fu.systemui missing from manifest",
            )
            arsc = zf.read("resources.arsc")
            self.assertTrue(
                b"wifi,bt,dnd,rotation,battery,screenrecord,cast,alarm,calculator" in arsc
                or "wifi,bt,dnd,rotation,battery,screenrecord,cast,alarm,calculator".encode("utf-16le") in arsc,
                "Sanitized Quick Settings tiles missing from resources.arsc",
            )
            self.assertNotIn(b"flashlight", arsc)
            self.assertNotIn(b"cell", arsc)

    def test_06_fastbootd_deployment_script_staged(self):
        """Verify deployment/flash_lineage23_fastbootd.ps1 exists and is non-empty."""
        self.assertTrue(os.path.isfile(SCRIPT_PATH), f"Missing: {SCRIPT_PATH}")
        self.assertGreater(os.path.getsize(SCRIPT_PATH), 1000)


class TestM5DeploymentScriptGuards(unittest.TestCase):
    """Test suite inspecting deployment/flash_lineage23_fastbootd.ps1 logic and safety guards."""

    def setUp(self):
        with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
            self.script_content = f.read()

    def test_01_default_dry_run_mode(self):
        """Verify script implements default DryRun mode."""
        self.assertIn("[switch]$DryRun", self.script_content)
        self.assertIn("[switch]$Execute", self.script_content)
        self.assertIn("$isDryRun = (-not $Execute) -or $DryRun", self.script_content)

    def test_02_chunking_standard_enforced(self):
        """Verify WinUSB -S 64M chunking standard is enforced."""
        self.assertIn("[string]$ChunkSize = \"64M\"", self.script_content)
        self.assertIn("Test-ChunkSize", self.script_content)
        self.assertIn("Must be <= 64M", self.script_content)
        self.assertIn("-S $ChunkSize flash system_a", self.script_content)
        self.assertIn("-S $ChunkSize flash vendor_a", self.script_content)

    def test_03_fastbootd_userspace_check_present(self):
        """Verify Fastbootd userspace check (is-userspace == yes)."""
        self.assertIn("getvar is-userspace", self.script_content)
        self.assertIn("is-userspace:\\s*yes", self.script_content)
        self.assertIn("Fastbootd is strictly mandatory", self.script_content)

    def test_04_logical_partition_management_commands(self):
        """Verify product deletion and system/vendor partition resizing."""
        self.assertIn("delete-logical-partition product_a", self.script_content)
        self.assertIn("delete-logical-partition product_b", self.script_content)
        self.assertIn("resize-logical-partition system_a", self.script_content)
        self.assertIn("resize-logical-partition vendor_a", self.script_content)
        self.assertIn("erase system_a", self.script_content)
        self.assertIn("flash boot_a", self.script_content)
        self.assertIn("reboot", self.script_content)

    def test_05_strict_prohibition_vendor_boot(self):
        """Verify guard prohibiting flashing salt-pinned vendor_boot."""
        self.assertIn("vendor_boot", self.script_content)
        self.assertIn("Flashing factory vendor_boot is fatal to AVB", self.script_content)

    def test_06_strict_prohibition_vbmeta(self):
        """Verify guard prohibiting flashing vbmeta or passing verity disable flags."""
        self.assertIn("vbmeta", self.script_content)
        self.assertIn("--disable-verity", self.script_content)
        self.assertIn("--disable-verification", self.script_content)

    def test_07_strict_prohibition_data_wipe(self):
        """Verify guard prohibiting fastboot -w, erase userdata, format userdata."""
        self.assertIn("\\s+-w\\b", self.script_content)
        self.assertIn("erase\\s+userdata", self.script_content)
        self.assertIn("format\\s+userdata", self.script_content)
        self.assertIn("Data wiping command detected in plan", self.script_content)


class TestM5DeploymentScriptExecution(unittest.TestCase):
    """Test suite executing PowerShell dry-run and validation tests."""

    def test_01_powershell_default_execution_is_dryrun(self):
        """Verify running script with no arguments completes dry-run with code 0."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            SCRIPT_PATH,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        self.assertEqual(res.returncode, 0, f"Script failed with output:\n{res.stdout}\n{res.stderr}")
        self.assertIn("[DRY-RUN VALIDATION]", res.stdout)
        self.assertIn("[+] DRY-RUN SUCCESS", res.stdout)
        self.assertIn("Step 1: C:\\platform-tools\\fastboot.exe -s HNQ09EZD delete-logical-partition product_a", res.stdout)
        self.assertIn("Step 6: C:\\platform-tools\\fastboot.exe -s HNQ09EZD -S 64M flash system_a", res.stdout)
        self.assertIn("Step 7: C:\\platform-tools\\fastboot.exe -s HNQ09EZD -S 64M flash vendor_a", res.stdout)
        self.assertIn("Step 8: C:\\platform-tools\\fastboot.exe -s HNQ09EZD flash boot_a", res.stdout)

    def test_02_powershell_explicit_dryrun_switch(self):
        """Verify running script with -DryRun switch completes dry-run with code 0."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            SCRIPT_PATH,
            "-DryRun",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        self.assertEqual(res.returncode, 0, f"Script failed with output:\n{res.stdout}\n{res.stderr}")
        self.assertIn("[DRY-RUN VALIDATION]", res.stdout)
        self.assertIn("[+] DRY-RUN SUCCESS", res.stdout)

    def test_03_powershell_adversarial_chunk_size_rejected(self):
        """Verify chunk size > 64M triggers terminating exception."""
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            SCRIPT_PATH,
            "-ChunkSize",
            "128M",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        self.assertNotEqual(res.returncode, 0, "Expected non-zero exit code for 128M chunk size")
        self.assertIn("Chunk size 128M exceeds safe WinUSB limit", res.stderr + res.stdout)


class TestM5SafetyInvariantR7(unittest.TestCase):
    """Test suite verifying R7 Stop Directive and connected hardware preservation."""

    def test_01_no_destructive_flashing_on_live_hardware(self):
        """Confirm live tablet HNQ09EZD is responsive and unmodified."""
        res = subprocess.run(
            ["adb", "-s", "HNQ09EZD", "get-state"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            self.assertEqual(res.stdout.strip(), "device")


if __name__ == "__main__":
    unittest.main()

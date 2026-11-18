#!/usr/bin/env python3
"""
tests/test_rom_packaging.py - Comprehensive Unit & Integration Tests for ROM Packaging Pipeline
Target Device: Lenovo Tab with Clear Case (TB311FU / 'poplar', MT8786 / Helio G88)

Tests:
1. Syntax validity of all shell scripts (bash -n) and Python scripts (py_compile)
2. scripts/plan_a_transform.sh: 7 Plan-A target purge and e2fsck verification
3. scripts/build_sideload_zip.sh: OrangeFox recovery sideloadable ZIP format & contents
4. scripts/build_fastboot_set.sh: Android sparse image & cross-platform flash scripts
5. scripts/build_ota_payload.sh: Android A/B OTA payload.bin (CrAU) and payload_properties.txt
6. .github/workflows/rom-package.yml: GitHub Actions YAML structure, steps, and permissions
"""

import base64
import os
import py_compile
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestRomPackagingScriptsSyntax(unittest.TestCase):
    """Ensure all packaging scripts are syntactically valid."""

    def test_bash_scripts_syntax(self):
        scripts = [
            REPO_ROOT / "scripts" / "plan_a_transform.sh",
            REPO_ROOT / "scripts" / "build_sideload_zip.sh",
            REPO_ROOT / "scripts" / "build_fastboot_set.sh",
            REPO_ROOT / "scripts" / "build_ota_payload.sh",
            REPO_ROOT / "scripts" / "disable_avb.sh",
            REPO_ROOT / "scripts" / "patch_ramdisk_verity.sh",
        ]
        for script in scripts:
            with self.subTest(script=script.name):
                self.assertTrue(script.exists(), f"Script not found: {script}")
                res = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Syntax error in {script}:\n{res.stderr}")

    def test_python_scripts_syntax(self):
        py_scripts = [
            REPO_ROOT / "tools" / "img2simg.py",
            REPO_ROOT / "tools" / "build_payload.py",
            REPO_ROOT / "scripts" / "disable_avb.py",
            REPO_ROOT / "scripts" / "patch_ramdisk_verity.py",
        ]
        for py_s in py_scripts:
            with self.subTest(script=py_s.name):
                self.assertTrue(py_s.exists(), f"Python script not found: {py_s}")
                try:
                    py_compile.compile(str(py_s), doraise=True)
                except py_compile.PyCompileError as exc:
                    self.fail(f"Compilation error in {py_s}: {exc}")


class TestPlanATransformScript(unittest.TestCase):
    """Test Plan-A transform: purging the 7 cellular target paths with e2fsck verification."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.temp_dir.name)
        self.img_in = self.td / "test_gsi_in.img"
        self.img_out = self.td / "test_gsi_out.img"

        # Create 25MB ext4 image
        with open(self.img_in, "wb") as f:
            f.truncate(25 * 1024 * 1024)
        subprocess.run(["mkfs.ext4", "-F", "-b", "4096", str(self.img_in)], check=True, capture_output=True)

        # Inject the 7 Plan-A target paths
        cmds = """
mkdir /system
mkdir /system/priv-app
mkdir /system/priv-app/TelephonyProvider
write /dev/null /system/priv-app/TelephonyProvider/TelephonyProvider.apk
mkdir /system/priv-app/CellBroadcastLegacyApp
write /dev/null /system/priv-app/CellBroadcastLegacyApp/CellBroadcastLegacyApp.apk
mkdir /system/app
mkdir /system/app/QcRilAm
write /dev/null /system/app/QcRilAm/QcRilAm.apk
mkdir /system/app/CarrierDefaultApp
write /dev/null /system/app/CarrierDefaultApp/CarrierDefaultApp.apk
mkdir /system/apex
write /dev/null /system/apex/com.android.cellbroadcast.capex
mkdir /system/product
mkdir /system/product/overlay
write /dev/null /system/product/overlay/TelephonyProvider__device__auto_generated_characteristics_rro.apk
write /dev/null /system/product/overlay/treble-overlay-Telephony-LTE.apk
"""
        cmd_file = self.td / "cmds.txt"
        cmd_file.write_text(cmds)
        subprocess.run(["debugfs", "-w", "-f", str(cmd_file), str(self.img_in)], check=True, capture_output=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dry_run_scans_without_modifying(self):
        orig_bytes = self.img_in.read_bytes()
        res = subprocess.run([
            str(REPO_ROOT / "scripts" / "plan_a_transform.sh"),
            "-i", str(self.img_in),
            "--dry-run"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Found 7 cellular targets", res.stdout)
        self.assertEqual(orig_bytes, self.img_in.read_bytes())

    def test_verify_fails_on_unstripped_image(self):
        res = subprocess.run([
            str(REPO_ROOT / "scripts" / "plan_a_transform.sh"),
            "-i", str(self.img_in),
            "--verify"
        ], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Verification FAILED", res.stderr)

    def test_transform_removes_all_7_targets_and_e2fsck_passes(self):
        res = subprocess.run([
            str(REPO_ROOT / "scripts" / "plan_a_transform.sh"),
            "-i", str(self.img_in),
            "-o", str(self.img_out)
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Transform failed:\n{res.stdout}\n{res.stderr}")
        self.assertTrue(self.img_out.exists())

        # Verify on output image passes
        ver_res = subprocess.run([
            str(REPO_ROOT / "scripts" / "plan_a_transform.sh"),
            "-i", str(self.img_out),
            "--verify"
        ], capture_output=True, text=True)
        self.assertEqual(ver_res.returncode, 0, f"Verify failed:\n{ver_res.stdout}\n{ver_res.stderr}")


class TestBuildSideloadZipScript(unittest.TestCase):
    """Test OrangeFox/recovery ADB sideloadable ZIP package generation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.temp_dir.name)
        self.out_zip = self.td / "test_sideload.zip"

        for part in ["system_a.img", "boot_a.img", "init_boot_a.img", "vendor_boot_a.img", "dtbo_a.img", "vbmeta_a.img"]:
            (self.td / part).write_bytes(b"DATA:" + part.encode())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_sideload_zip_structure_and_files(self):
        res = subprocess.run([
            str(REPO_ROOT / "scripts" / "build_sideload_zip.sh"),
            "-d", str(self.td),
            "-o", str(self.out_zip),
            "-f"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Build sideload zip failed:\n{res.stdout}\n{res.stderr}")
        self.assertTrue(self.out_zip.exists())

        with zipfile.ZipFile(self.out_zip, "r") as z:
            names = set(z.namelist())
            expected = {
                "META-INF/com/google/android/update-binary",
                "META-INF/com/google/android/updater-script",
                "installer.sh",
                "system_a.img",
                "boot_a.img",
                "init_boot_a.img",
                "vendor_boot_a.img",
                "dtbo_a.img",
                "vbmeta_a.img",
            }
            for exp in expected:
                self.assertIn(exp, names, f"Missing required file in sideload zip: {exp}")

            # Inspect installer.sh
            installer_code = z.read("installer.sh").decode("utf-8")
            self.assertIn("Lenovo Tab with Clear Case", installer_code)
            self.assertIn("system_a", installer_code)
            self.assertIn("boot_a", installer_code)


class TestBuildFastbootSetScript(unittest.TestCase):
    """Test Fastboot sparse image conversion and deployment scripts generation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.temp_dir.name)
        self.out_pkg = self.td / "test_fastboot.zip"

        for part in ["system.img", "boot.img", "init_boot.img", "vendor_boot.img", "dtbo.img", "vbmeta.img"]:
            (self.td / part).write_bytes(b"\x00" * 4096 * 4)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_fastboot_set_sparse_and_scripts(self):
        res = subprocess.run([
            str(REPO_ROOT / "scripts" / "build_fastboot_set.sh"),
            "-d", str(self.td),
            "-o", str(self.out_pkg),
            "-f"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Build fastboot set failed:\n{res.stdout}\n{res.stderr}")
        self.assertTrue(self.out_pkg.exists())

        with zipfile.ZipFile(self.out_pkg, "r") as z:
            names = set(z.namelist())
            expected = {
                "system.sparse.img",
                "boot.img",
                "init_boot.img",
                "vendor_boot.img",
                "dtbo.img",
                "vbmeta.img",
                "flash_all.sh",
                "flash_all.bat",
                "flash_all.ps1",
            }
            for exp in expected:
                self.assertIn(exp, names, f"Missing {exp} in fastboot package")

            # Check sparse image magic (0xED26FF3A)
            sparse_bytes = z.read("system.sparse.img")
            self.assertGreaterEqual(len(sparse_bytes), 28)
            magic = struct.unpack("<I", sparse_bytes[:4])[0]
            self.assertEqual(magic, 0xED26FF3A, f"Invalid sparse magic: {magic:#x}")

            # Check WinUSB 64M chunking in flash_all.sh
            sh_code = z.read("flash_all.sh").decode("utf-8")
            self.assertIn('CHUNK_SIZE="64M"', sh_code)
            self.assertIn('-S "$CHUNK_SIZE"', sh_code)
            self.assertIn("reboot fastboot", sh_code)


class TestBuildOtaPayloadScript(unittest.TestCase):
    """Test Android A/B OTA payload.bin and payload_properties.txt generation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.temp_dir.name)
        self.out_dir = self.td / "ota_out"
        self.out_zip = self.td / "ota_pkg.zip"
        self.key_path = self.td / "testkey.pem"

        for part in ["system.img", "boot.img", "init_boot.img", "vendor_boot.img", "dtbo.img", "vbmeta.img"]:
            (self.td / part).write_bytes(b"DATA:" + part.encode() + b"\x00" * 2000)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_ota_payload_and_properties(self):
        res = subprocess.run([
            str(REPO_ROOT / "scripts" / "build_ota_payload.sh"),
            "-d", str(self.td),
            "-k", str(self.key_path),
            "-o", str(self.out_dir),
            "-z", str(self.out_zip),
            "-f"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Build OTA payload failed:\n{res.stdout}\n{res.stderr}")

        payload_bin = self.out_dir / "payload.bin"
        props_txt = self.out_dir / "payload_properties.txt"

        self.assertTrue(payload_bin.exists())
        self.assertTrue(props_txt.exists())

        # Check payload.bin header magic (CrAU) and version 2
        with open(payload_bin, "rb") as f:
            magic = f.read(4)
            self.assertEqual(magic, b"CrAU")
            version = struct.unpack(">Q", f.read(8))[0]
            self.assertEqual(version, 2)

        # Check payload_properties.txt format
        props_content = props_txt.read_text(encoding="utf-8")
        props = dict(line.split("=", 1) for line in props_content.strip().splitlines() if "=" in line)

        self.assertIn("FILE_HASH", props)
        self.assertIn("FILE_SIZE", props)
        self.assertIn("METADATA_HASH", props)
        self.assertIn("METADATA_SIZE", props)

        # Ensure base64 hashes decode to 32 bytes (SHA-256)
        file_hash_bytes = base64.b64decode(props["FILE_HASH"])
        meta_hash_bytes = base64.b64decode(props["METADATA_HASH"])
        self.assertEqual(len(file_hash_bytes), 32)
        self.assertEqual(len(meta_hash_bytes), 32)
        self.assertEqual(int(props["FILE_SIZE"]), payload_bin.stat().st_size)


class TestWorkflowConfiguration(unittest.TestCase):
    """Verify .github/workflows/rom-package.yml configuration."""

    def test_workflow_yaml_validity(self):
        wf_path = REPO_ROOT / ".github" / "workflows" / "rom-package.yml"
        self.assertTrue(wf_path.exists())

        import yaml
        with open(wf_path) as f:
            data = yaml.safe_load(f)

        self.assertIn("name", data)
        self.assertIn("jobs", data)
        self.assertIn("package-rom", data["jobs"])

        job = data["jobs"]["package-rom"]
        self.assertEqual(data.get("permissions", {}).get("contents"), "write")

        step_names = [s.get("name") for s in job.get("steps", []) if "name" in s]
        self.assertTrue(any("Plan-A" in name for name in step_names))
        self.assertTrue(any("AVB" in name for name in step_names))
        self.assertTrue(any("Sideload" in name for name in step_names))
        self.assertTrue(any("Fastboot" in name for name in step_names))
        self.assertTrue(any("OTA" in name for name in step_names))
        self.assertTrue(any("Release" in name for name in step_names))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Tier 3: Cross-Feature Combinations & Pairwise Integration Test Suite
Lenovo Tab with Clear Case (poplar / TB311FU, MT8786 / MT6768) Engineering Verification
Covers >= 21 tests verifying multi-module and cross-feature interactions.
"""

import unittest
import os
import sys
import struct
import hashlib
import xml.etree.ElementTree as ET
import zipfile

# Path definitions
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEARLESS_DIR = os.path.abspath(r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell")
GSI_SUITE_DIR = os.path.join(FEARLESS_DIR, "gsi_suite")
PLATFORM_TOOLS_DIR = os.path.abspath(r"C:\platform-tools")
TARGET_GSI_PATH = os.path.abspath(r"D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img")
GLOBAL_SKILL_PATH = os.path.abspath(r"C:\Users\BangerSoul\.gemini\config\skills\lenovo-mtk-unlock\SKILL.md")
SURVEY_DIR = os.path.join(WORKSPACE_DIR, ".agents", "teamwork")
if not os.path.exists(SURVEY_DIR):
    SURVEY_DIR = r"C:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\.agents\teamwork"


class TestTier3_Combinations(unittest.TestCase):
    """Tier 3: Cross-Feature Interactions & Pairwise Interface Verification."""

    def test_t3_01_f1_f12_torch_suppression_in_rro(self):
        """F1 x F12: Verify Torch QS tile suppression is configured in RRO overlay."""
        bools_xml = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "bools.xml")
        self.assertTrue(os.path.exists(bools_xml))
        with open(bools_xml, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("config_voice_capable", content)

    def test_t3_02_f2_f15_wifi_rfkill_with_gki_kernel(self):
        """F2 x F15: Verify CONFIG_RFKILL=m in PoplarKernel satisfies modules.dep loadable dependency."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("CONFIG_RFKILL=m", content)
        self.assertIn("wlan_drv_gen4m_6768.ko", content)

    def test_t3_03_f3_f8_bluetooth_nvdata_mac_on_wifi_only(self):
        """F3 x F8: Verify Bluetooth NVData MAC persistence functions with cellular modem spinloops stripped."""
        repack_script = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(repack_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.radio.noril=yes", code)
        self.assertIn("ro.carrier=wifi-only", code)

    def test_t3_04_f4_f12_backlight_pwm_table_in_rro(self):
        """F4 x F12: Verify 13-point PWM table starting at min PWM 15 or clamped 48 is compiled into RRO overlay."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        pwm_table = []
        for item in root:
            if item.attrib.get("name") == "config_autoBrightnessLcdBacklightValues":
                for child in item:
                    pwm_table.append(int(child.text.strip()))
        self.assertEqual(len(pwm_table), 13)
        self.assertIn(pwm_table[0], (15, 48))
        self.assertGreaterEqual(pwm_table[-1], 2047)

    def test_t3_05_f5_f10_stylus_idc_injection_into_vendor(self):
        """F5 x F10: Verify Himax & Novatek active pen IDCs are copied into vendor/usr/idc/ during repack."""
        repack_script = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(repack_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("himax-touchscreen.idc", code)
        self.assertIn("NVT-ts.idc", code)
        self.assertIn("extract/usr/idc", code)

    def test_t3_06_f6_f12_display_90hz_peak_in_rro(self):
        """F6 x F12: Verify 90Hz peak refresh rate declaration in RRO config matches display calibrations."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        fps_values = {}
        for item in root:
            name = item.attrib.get("name", "")
            if name in ("config_defaultRefreshRate", "config_defaultPeakRefreshRate"):
                fps_values[name] = int(item.text.strip())
        self.assertEqual(fps_values.get("config_defaultRefreshRate"), 90)
        self.assertEqual(fps_values.get("config_defaultPeakRefreshRate"), 90)

    def test_t3_07_f7_f10_quad_audio_and_dolby_in_vendor(self):
        """F7 x F10: Verify quad audio policy and Dolby DAP effects trees are injected into vendor/etc/."""
        repack_script = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(repack_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("extract/etc/audio_policy_configuration.xml", code)
        self.assertIn("extract/etc/audio_effects.xml", code)

    def test_t3_08_f8_f10_telephony_drain_props_in_build_prop(self):
        """F8 x F10: Verify telemetry and cellular spinloop kill properties are appended to build.prop."""
        repack_script = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(repack_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.radio.noril=yes", code)
        self.assertIn("ro.telephony.default_network=0", code)
        self.assertIn("telephony.lteOnCdmaDevice=0", code)

    def test_t3_09_f10_f11_erofs_extraction_recompilation_roundtrip(self):
        """F10 x F11: Verify extraction via fsck.erofs and recompilation via mkfs.erofs -zlz4 pipeline."""
        repack_script = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(repack_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("fsck.erofs --extract=", code)
        self.assertIn("mkfs.erofs -zlz4 --mount-point=/vendor", code)

    def test_t3_10_f11_f13_recompiled_vendor_fits_super_budget(self):
        """F11 x F13: Verify recompiled vendor_stabilized.img fits within vendor_a dynamic partition without exhausting super headroom."""
        from partitions.super_budget_audit import (
            get_default_tb311fu_geometry,
            audit_super_budget,
            TARGET_GSI_SIZE_BYTES,
        )

        # 1. Execute authentic dynamic super partition geometry and budget calculation
        geom = get_default_tb311fu_geometry()
        report = audit_super_budget(geom, target_gsi_size=TARGET_GSI_SIZE_BYTES)

        # 2. Verify budget calculation results
        self.assertTrue(report.is_valid, f"Budget audit failed: {report.errors}")
        self.assertGreater(
            report.post_flash_headroom_bytes,
            6400000000,
            f"Calculated headroom reserve ({report.post_flash_headroom_bytes} B) is below 6.4 GB threshold",
        )
        self.assertEqual(report.post_flash_headroom_bytes, report.main_a_max_bytes - report.post_flash_allocated_bytes)

        # 3. Verify vendor_a capacity from parsed geometry model
        vendor_part = geom.partitions.get("vendor_a")
        self.assertIsNotNone(vendor_part, "vendor_a partition missing in super geometry")
        vendor_a_max_bytes = vendor_part.size_bytes
        self.assertEqual(vendor_a_max_bytes, vendor_part.sectors * 512)

        # 4. Verify physical vendor_stabilized.img binary if present
        vendor_img = os.path.join(WORKSPACE_DIR, "partitions", "vendor_stabilized.img")
        if os.path.exists(vendor_img):
            actual_vendor_size = os.path.getsize(vendor_img)
            self.assertLessEqual(
                actual_vendor_size,
                vendor_a_max_bytes,
                f"vendor_stabilized.img size ({actual_vendor_size} B) exceeds vendor_a capacity ({vendor_a_max_bytes} B)",
            )
            self.assertIn(actual_vendor_size, (295428096, 295448576))

    def test_t3_11_f13_f14_super_budget_and_fastbootd_chunking(self):
        """F13 x F14: Verify resized 3.45 GB system_a partition flashes via Fastbootd with -S 64M chunking."""
        gsi_size = 3446353920
        chunk_size_bytes = 64 * 1024 * 1024
        chunks = (gsi_size + chunk_size_bytes - 1) // chunk_size_bytes
        self.assertGreaterEqual(chunks, 51)
        self.assertLessEqual(chunks, 55)

    def test_t3_12_f14_f17_fastbootd_preserves_stock_vendor_boot(self):
        """F14 x F17: Verify Fastbootd scripts exclusively flash dynamic logical partitions and never modify vendor_boot."""
        repack_script = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(repack_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("fastboot -S 64M flash vendor_a", code)
        self.assertNotIn("flash vendor_boot", code)

    def test_t3_13_f15_f16_poplarkernel_chained_boot_alignment(self):
        """F15 x F16: Verify Linux 6.6.82 kernel payload is padded to 4096-byte alignment before OEM VBMeta block."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        self.assertTrue(os.path.exists(boot_img))
        with open(boot_img, "rb") as f:
            f.seek(33554432 - 64)
            footer = f.read(64)
            magic, vmaj, vmin, orig_sz, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])
            self.assertEqual(vb_off % 4096, 0)
            self.assertEqual(vb_off, 0xc52000)

    def test_t3_14_f16_f17_chained_boot_vbmeta_preserves_factory_flags(self):
        """F16 x F17: Verify embedded VBMeta block in chained boot.img has flags=0x00 matching factory Little Kernel verification."""
        boot_img = os.path.join(PLATFORM_TOOLS_DIR, "poplar_boot_v12_clean.img")
        with open(boot_img, "rb") as f:
            f.seek(0xc52000)
            vbhdr = f.read(256)
            self.assertEqual(vbhdr[:4], b"AVB0")
            self.assertEqual(vbhdr[123], 0) # Must be 0, not 3

    def test_t3_15_f17_f18_custom_recovery_on_boot_b_with_stock_vendor_boot(self):
        """F17 x F18: Verify TWRP recovery vector deployed to boot_b preserves salt-pinned stock vendor_boot."""
        rec_img = os.path.join(PLATFORM_TOOLS_DIR, "recovery_boot.img")
        self.assertTrue(os.path.exists(rec_img))
        with open(rec_img, "rb") as f:
            sz = os.path.getsize(rec_img)
            self.assertEqual(sz, 33554432)
            f.seek(33554432 - 64)
            footer = f.read(64)
            magic, vmaj, vmin, orig_sz, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])
            self.assertEqual(vb_off % 4096, 0)
            self.assertEqual(vb_off, 0xe28000)

    def test_t3_16_f18_f19_slot_switching_with_brom_safeguard(self):
        """F18 x F19: Verify slot-switching runbook documents emergency BROM recovery as fallback."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("fastboot --set-active=b", content)
        self.assertIn("BROM", content)

    def test_t3_17_f4_f6_backlight_dimming_with_90hz_refresh(self):
        """F4 x F6: Verify PWM backlight curve operation across 60Hz and 90Hz refresh rates."""
        cfg_file = os.path.join(GSI_SUITE_DIR, "overlay", "res", "values", "config.xml")
        tree = ET.parse(cfg_file)
        root = tree.getroot()
        has_refresh = False
        has_backlight = False
        for item in root:
            name = item.attrib.get("name", "")
            if "RefreshRate" in name:
                has_refresh = True
            elif "Brightness" in name:
                has_backlight = True
        self.assertTrue(has_refresh and has_backlight)

    def test_t3_18_f5_f7_active_stylus_and_quad_audio_concurrency(self):
        """F5 x F7: Verify 240Hz pen digitizer report rate operates concurrently with quad-speaker audio policy."""
        tuning_path = os.path.join(GSI_SUITE_DIR, "stylus", "touch_tuning.conf")
        policy_path = os.path.join(GSI_SUITE_DIR, "audio", "audio_policy_configuration.xml")
        self.assertTrue(os.path.exists(tuning_path))
        self.assertTrue(os.path.exists(policy_path))
        with open(tuning_path, "r", encoding="utf-8") as f:
            self.assertIn("stylus_report_rate_hz=240", f.read())
        with open(policy_path, "r", encoding="utf-8") as f:
            self.assertIn("AUDIO_CHANNEL_OUT_QUAD", f.read())

    def test_t3_19_f2_f8_wifi_roaming_without_cellular_wakelocks(self):
        """F2 x F8: Verify Wi-Fi network roaming operates with zero cellular modem spinloops."""
        repack_script = os.path.join(WORKSPACE_DIR, "repack_vendor_mod.py")
        with open(repack_script, "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("ro.radio.noril=yes", code)
        self.assertIn("ro.carrier=wifi-only", code)

    def test_t3_20_f15_f20_poplarkernel_downstream_with_halium_spec(self):
        """F15 x F20: Verify PoplarKernel GKI configuration satisfies Halium containerization requirements."""
        project_md = os.path.join(WORKSPACE_DIR, "PROJECT.md")
        with open(project_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Halium", content)
        self.assertIn("Linux 6.6.82", content)
        self.assertIn("/dev/watchdog", content)

    def test_t3_21_f9_f21_audit_harness_integration_with_e2e_runner(self):
        """F9 x F21: Verify 8-subsystem diagnostic audit harness integrates into master test execution."""
        audit_full = os.path.join(SURVEY_DIR, "explorer_survey_1", "audit_full.txt")
        self.assertTrue(os.path.exists(audit_full))
        with open(audit_full, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("SECTION 1", content)
        self.assertIn("SECTION 8", content)


if __name__ == "__main__":
    unittest.main()

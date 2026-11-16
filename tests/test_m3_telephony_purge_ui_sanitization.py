#!/usr/bin/env python3
"""
tests/test_m3_telephony_purge_ui_sanitization.py - Comprehensive Unit & Boundary Test Suite
Milestone M3: Aggressive Telephony Purge & UI Sanitization
Target: Lenovo Tab M11 (TB311FU / 'poplar', MediaTek MT8786 / Helio G88)

Requirements Under Test:
- R5.1: Vendor Build Properties Injection (ro.radio.noril, ro.carrier, telephony.lteOnCdmaDevice, ro.telephony.default_network)
- R5.2: Modem Services Disabling (ccci_mdinit, ccci_fsd, vendor.ril-daemon-mtk override disabled)
- R5.3: System_a Cellular Stripping (TelephonyProvider, QcRilAm, CarrierDefaultApp, CellBroadcastLegacyApp, capex)
- R5.4: UI Sanitization & Quick Settings Pruning (prune flashlight/cell, mask No-Service and carrier text)
"""

from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Deliverables Under Test
from telephony.patch_telephony import (
    validate_telephony_properties,
    inject_telephony_properties,
    patch_build_prop_file,
    validate_modem_services_override,
    inject_modem_services_override,
    patch_init_connectivity_rc,
    MANDATORY_TELEPHONY_PROPS,
    ALL_TELEPHONY_PROPS,
    MANDATORY_MODEM_SERVICES,
)

from partitions.strip_system_cellular import (
    CELLULAR_PURGE_SPEC,
    PURGE_VERIFICATION_KEYWORDS,
    Ext4DirectorySurgery,
    strip_directory_staging,
    verify_image_with_ext4,
    verify_image_with_7z,
)

from ui_sanitization.build_systemui_overlay import (
    validate_source_tree,
    build_pure_python_overlay_apk,
    verify_systemui_overlay_apk,
    FORBIDDEN_TILES,
    EXPECTED_DEFAULT_TILES,
)


class TestVendorBuildPropertiesR51(unittest.TestCase):
    """Test Requirement R5.1: Vendor build properties for RIL & cellular suppression."""

    def test_vendor_telephony_prop_template_exists(self):
        """Verify telephony/vendor_telephony.prop exists and is non-empty."""
        prop_path = WORKSPACE_ROOT / "telephony" / "vendor_telephony.prop"
        self.assertTrue(prop_path.exists(), f"Missing {prop_path}")
        content = prop_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 50)

    def test_mandatory_telephony_properties_content(self):
        """Verify all mandatory R5.1 properties are present with exact required values."""
        prop_path = WORKSPACE_ROOT / "telephony" / "vendor_telephony.prop"
        content = prop_path.read_text(encoding="utf-8")
        valid, errors = validate_telephony_properties(content, strict=True)
        self.assertTrue(valid, f"Validation failed: {errors}")

    def test_individual_property_values(self):
        """Explicitly assert each R5.1 required key-value pair."""
        prop_path = WORKSPACE_ROOT / "telephony" / "vendor_telephony.prop"
        content = prop_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines() if "=" in l and not l.startswith("#")]
        pdict = dict(l.split("=", 1) for l in lines)

        self.assertEqual(pdict.get("ro.radio.noril"), "yes")
        self.assertEqual(pdict.get("ro.carrier"), "wifi-only")
        self.assertEqual(pdict.get("telephony.lteOnCdmaDevice"), "0")
        self.assertEqual(pdict.get("ro.telephony.default_network"), "0")
        self.assertEqual(pdict.get("persist.radio.noril"), "1")
        self.assertEqual(pdict.get("persist.sys.phh.no_telephony"), "true")
        self.assertEqual(pdict.get("config.disable_telephony"), "true")

    def test_injection_engine_idempotency(self):
        """Verify injecting telephony properties twice does not duplicate lines."""
        sample_prop = "ro.build.display.id=TB311FU_SAMPLE\nro.product.model=TB311FU\n"
        pass1 = inject_telephony_properties(sample_prop)
        pass2 = inject_telephony_properties(pass1)
        self.assertEqual(pass1, pass2)

    def test_validator_rejects_missing_or_corrupted_properties(self):
        """Verify validator flags missing keys and wrong values."""
        corrupted = "ro.radio.noril=no\nro.carrier=verizon\n"
        valid, errors = validate_telephony_properties(corrupted, strict=False)
        self.assertFalse(valid)
        self.assertTrue(any("ro.radio.noril" in e for e in errors))
        self.assertTrue(any("ro.carrier" in e for e in errors))
        self.assertTrue(any("telephony.lteOnCdmaDevice" in e for e in errors))


class TestModemServicesDisablingR52(unittest.TestCase):
    """Test Requirement R5.2: Modem services disabling in init.connectivity.rc."""

    def test_init_connectivity_rc_template_exists(self):
        """Verify telephony/init.connectivity.rc template exists."""
        rc_path = WORKSPACE_ROOT / "telephony" / "init.connectivity.rc"
        self.assertTrue(rc_path.exists(), f"Missing {rc_path}")
        content = rc_path.read_text(encoding="utf-8")
        self.assertGreater(len(content), 50)

    def test_mandatory_modem_services_declared(self):
        """Verify ccci_mdinit, ccci_fsd, and vendor.ril-daemon-mtk have override & disabled."""
        rc_path = WORKSPACE_ROOT / "telephony" / "init.connectivity.rc"
        content = rc_path.read_text(encoding="utf-8")
        valid, errors = validate_modem_services_override(content)
        self.assertTrue(valid, f"Validation failed: {errors}")

    def test_exact_service_stanzas(self):
        """Verify exact service binary commands and flags in init.connectivity.rc."""
        rc_path = WORKSPACE_ROOT / "telephony" / "init.connectivity.rc"
        content = rc_path.read_text(encoding="utf-8")

        self.assertIn("service ccci_mdinit /vendor/bin/ccci_mdinit 0", content)
        self.assertIn("service ccci_fsd /vendor/bin/ccci_fsd 0", content)
        self.assertIn("service vendor.ril-daemon-mtk /vendor/bin/hw/mtkfusionrild -l libmtk-ril.so", content)

    def test_init_patching_idempotency(self):
        """Verify patch_init_connectivity_rc produces idempotent output."""
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".rc") as tmp:
            tmp.write("import /vendor/etc/init/hw/init_connectivity.rc\n")
            tmp_path = tmp.name

        try:
            patch_init_connectivity_rc(tmp_path)
            content1 = Path(tmp_path).read_text(encoding="utf-8")
            valid, _ = validate_modem_services_override(content1)
            self.assertTrue(valid)

            # Second patch should not alter content
            patch_init_connectivity_rc(tmp_path)
            content2 = Path(tmp_path).read_text(encoding="utf-8")
            self.assertEqual(content1, content2)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


class TestSystemCellularStrippingR53(unittest.TestCase):
    """Test Requirement R5.3: System_a cellular package stripping script and verification."""

    @classmethod
    def setUpClass(cls):
        cls.target_gsi = Path(r"D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img")

    def test_stripping_script_exists(self):
        """Verify partitions/strip_system_cellular.py exists."""
        script_path = WORKSPACE_ROOT / "partitions" / "strip_system_cellular.py"
        self.assertTrue(script_path.exists())

    def test_purge_spec_includes_all_required_packages(self):
        """Verify CELLULAR_PURGE_SPEC covers all R5.3 packages."""
        priv_apps = CELLULAR_PURGE_SPEC.get("/system/priv-app", [])
        self.assertIn("TelephonyProvider", priv_apps)
        self.assertIn("CellBroadcastLegacyApp", priv_apps)

        apps = CELLULAR_PURGE_SPEC.get("/system/app", [])
        self.assertIn("QcRilAm", apps)
        self.assertIn("CarrierDefaultApp", apps)

        apexes = CELLULAR_PURGE_SPEC.get("/system/apex", [])
        self.assertIn("com.android.cellbroadcast.capex", apexes)

    def test_directory_staging_purger(self):
        """Test strip_directory_staging on a temporary simulated staging directory."""
        with tempfile.TemporaryDirectory() as staging:
            # Create mock structure
            priv_dir = os.path.join(staging, "system", "priv-app", "TelephonyProvider")
            os.makedirs(priv_dir, exist_ok=True)
            with open(os.path.join(priv_dir, "TelephonyProvider.apk"), "wb") as f:
                f.write(b"MOCK_APK")

            app_dir = os.path.join(staging, "system", "app", "QcRilAm")
            os.makedirs(app_dir, exist_ok=True)
            with open(os.path.join(app_dir, "QcRilAm.apk"), "wb") as f:
                f.write(b"MOCK_APK")

            apex_dir = os.path.join(staging, "system", "apex")
            os.makedirs(apex_dir, exist_ok=True)
            capex_file = os.path.join(apex_dir, "com.android.cellbroadcast.capex")
            with open(capex_file, "wb") as f:
                f.write(b"MOCK_CAPEX")

            # Execute staging purge
            removed = strip_directory_staging(staging)
            self.assertEqual(len(removed), 3)
            self.assertFalse(os.path.exists(priv_dir))
            self.assertFalse(os.path.exists(app_dir))
            self.assertFalse(os.path.exists(capex_file))

    def test_target_gsi_ext4_verification(self):
        """Verify target GSI is 100% clean of all cellular targets via ext4 module."""
        if not self.target_gsi.exists():
            self.skipTest(f"GSI {self.target_gsi} not accessible on this system.")

        ok, errors = verify_image_with_ext4(str(self.target_gsi))
        self.assertTrue(ok, f"Cellular packages still detected in GSI: {errors}")

    def test_target_gsi_7z_verification(self):
        """Verify target GSI is 100% clean of cellular keywords in 7-Zip listing."""
        if not self.target_gsi.exists():
            self.skipTest(f"GSI {self.target_gsi} not accessible on this system.")

        ok, errors = verify_image_with_7z(str(self.target_gsi))
        self.assertTrue(ok, f"7-Zip detected cellular packages in GSI: {errors}")


class TestUISanitizationAndQuickSettingsR54(unittest.TestCase):
    """Test Requirement R5.4: UI Sanitization, QS tile pruning, carrier text blanking."""

    def test_systemui_overlay_source_validity(self):
        """Verify SystemUI overlay XML source files pass schema & rule validation."""
        src_dir = WORKSPACE_ROOT / "ui_sanitization" / "systemui_overlay"
        valid, errors = validate_source_tree(str(src_dir))
        self.assertTrue(valid, f"SystemUI overlay source validation failed: {errors}")

    def test_systemui_overlay_apk_built_and_valid(self):
        """Verify treble-overlay-lenovo-tb311fu-systemui.apk satisfies R5.4."""
        apk_path = WORKSPACE_ROOT / "ui_sanitization" / "treble-overlay-lenovo-tb311fu-systemui.apk"
        self.assertTrue(apk_path.exists(), f"APK not found: {apk_path}")

        valid, errors = verify_systemui_overlay_apk(str(apk_path))
        self.assertTrue(valid, f"APK verification failed: {errors}")

    def test_systemui_overlay_staged_in_deployment(self):
        """Verify SystemUI overlay APK is staged into deployment/ directory."""
        deploy_apk = WORKSPACE_ROOT / "deployment" / "treble-overlay-lenovo-tb311fu-systemui.apk"
        self.assertTrue(deploy_apk.exists(), f"Missing {deploy_apk}")
        valid, errors = verify_systemui_overlay_apk(str(deploy_apk))
        self.assertTrue(valid, f"Deployment APK verification failed: {errors}")

    def test_systemui_overlay_staged_in_gsi_suite(self):
        """Verify SystemUI overlay APK is staged into fearless-maxwell/gsi_suite/overlay/."""
        gsi_apk = WORKSPACE_ROOT.parent / "fearless-maxwell" / "gsi_suite" / "overlay" / "treble-overlay-lenovo-tb311fu-systemui.apk"
        self.assertTrue(gsi_apk.exists(), f"Missing {gsi_apk}")
        valid, errors = verify_systemui_overlay_apk(str(gsi_apk))
        self.assertTrue(valid, f"gsi_suite APK verification failed: {errors}")

    def test_systemui_overlay_binary_axml_and_arsc_invariants(self):
        """Enforce strict binary AXML and binary ARSC invariants directly on the APK."""
        for apk_path in [
            WORKSPACE_ROOT / "ui_sanitization" / "treble-overlay-lenovo-tb311fu-systemui.apk",
            WORKSPACE_ROOT / "deployment" / "treble-overlay-lenovo-tb311fu-systemui.apk",
        ]:
            self.assertTrue(apk_path.exists(), f"APK not found: {apk_path}")
            with zipfile.ZipFile(apk_path, "r") as zf:
                namelist = zf.namelist()

                # 1. No uncompiled source files
                for uncompiled in ["res/values/strings.xml", "res/values/dimens.xml", "res/values/bools.xml"]:
                    self.assertNotIn(uncompiled, namelist, f"{apk_path} contains uncompiled source {uncompiled}")

                # 2. Binary resources.arsc
                self.assertIn("resources.arsc", namelist)
                info = zf.getinfo("resources.arsc")
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED, "resources.arsc must be ZIP_STORED")
                arsc_data = zf.read("resources.arsc")
                table_type, header_size, chunk_size = struct.unpack("<HHI", arsc_data[:8])
                self.assertEqual(table_type, 0x0002, f"Invalid ARSC table type: {hex(table_type)}")
                self.assertEqual(chunk_size, len(arsc_data), "ARSC chunk size mismatch")

                # Semantic contents in ARSC
                self.assertTrue(
                    b"quick_settings_tiles_stock" in arsc_data or "quick_settings_tiles_stock".encode("utf-16le") in arsc_data,
                    "quick_settings_tiles_stock key missing from ARSC",
                )
                self.assertTrue(
                    b"wifi,bt,dnd,rotation,battery" in arsc_data or "wifi,bt,dnd,rotation,battery".encode("utf-16le") in arsc_data,
                    "Sanitized tile list missing from ARSC",
                )
                for forbidden in [b"flashlight", b"torch", b"cell"]:
                    self.assertNotIn(forbidden, arsc_data, f"Forbidden tile {forbidden} in ARSC")

                for ckey in [b"keyguard_carrier_text", b"shade_carrier_text", b"no_carrier_text"]:
                    self.assertTrue(
                        ckey in arsc_data or ckey.decode().encode("utf-16le") in arsc_data,
                        f"Missing carrier blanking key {ckey} in ARSC",
                    )

                # 3. Binary AndroidManifest.xml
                self.assertIn("AndroidManifest.xml", namelist)
                manifest_data = zf.read("AndroidManifest.xml")
                axml_magic = struct.unpack("<I", manifest_data[:4])[0]
                self.assertEqual(axml_magic, 0x00080003, f"Invalid AXML magic: {hex(axml_magic)}")
                self.assertFalse(manifest_data.startswith(b"<?xml"), "AndroidManifest.xml must not be text XML")
                self.assertTrue(
                    b"com.android.systemui" in manifest_data or "com.android.systemui".encode("utf-16le") in manifest_data,
                    "AndroidManifest.xml does not target com.android.systemui",
                )

                # 4. Authentic PKCS#7 signature
                rsa_files = [n for n in namelist if n.startswith("META-INF/") and n.endswith(".RSA")]
                self.assertTrue(len(rsa_files) >= 1, "Missing META-INF/*.RSA signature")
                rsa_data = zf.read(rsa_files[0])
                self.assertGreaterEqual(len(rsa_data), 500, "RSA signature suspiciously small")
                self.assertEqual(rsa_data[0], 0x30, "Signature not DER SEQUENCE")
                self.assertLess(rsa_data.count(b"\x00"), 50, "Excessive null bytes in signature")

                # Max consecutive zeros < 16
                consec = max_zeros = 0
                for b in rsa_data:
                    if b == 0:
                        consec += 1
                        max_zeros = max(max_zeros, consec)
                    else:
                        consec = 0
                self.assertLess(max_zeros, 16, f"Synthetic zero padding in signature ({max_zeros} consecutive zeros)")

    def test_quick_settings_prunes_flashlight_and_cell(self):
        """Verify QS default tiles do NOT contain flashlight, torch, or cell."""
        strings_path = WORKSPACE_ROOT / "ui_sanitization" / "systemui_overlay" / "res" / "values" / "strings.xml"
        tree = ET.parse(strings_path)
        root = tree.getroot()
        sdict = {i.attrib.get("name"): (i.text or "").strip() for i in root.findall("string")}

        tiles = [t.strip() for t in sdict.get("quick_settings_tiles_stock", "").split(",")]
        self.assertNotIn("flashlight", tiles)
        self.assertNotIn("cell", tiles)
        self.assertNotIn("torch", tiles)

        # Confirm essential tablet tiles are present
        self.assertIn("wifi", tiles)
        self.assertIn("bt", tiles)
        self.assertIn("rotation", tiles)
        self.assertIn("battery", tiles)

    def test_carrier_text_blanking_strings(self):
        """Verify carrier text string resources are explicitly blanked."""
        strings_path = WORKSPACE_ROOT / "ui_sanitization" / "systemui_overlay" / "res" / "values" / "strings.xml"
        tree = ET.parse(strings_path)
        root = tree.getroot()
        sdict = {i.attrib.get("name"): (i.text or "").strip() for i in root.findall("string")}

        self.assertEqual(sdict.get("keyguard_carrier_text"), "")
        self.assertEqual(sdict.get("shade_carrier_text"), "")
        self.assertEqual(sdict.get("no_carrier_text"), "")

    def test_framework_overlay_carrier_and_sim_blanking(self):
        """Verify framework-res overlay in gsi_suite/overlay blanks lockscreen carrier strings."""
        fw_strings = Path(r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell\gsi_suite\overlay\res\values\strings.xml")
        self.assertTrue(fw_strings.exists())
        tree = ET.parse(fw_strings)
        root = tree.getroot()
        sdict = {i.attrib.get("name"): (i.text or "").strip() for i in root.findall("string")}

        self.assertEqual(sdict.get("lockscreen_carrier_default"), "")
        self.assertEqual(sdict.get("emergency_calls_only"), "")
        self.assertEqual(sdict.get("lockscreen_missing_sim_message_short"), "")

    def test_framework_overlay_cellular_booleans_disabled(self):
        """Verify framework-res bools.xml disables voice, sms, and cell broadcast."""
        fw_bools = Path(r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell\gsi_suite\overlay\res\values\bools.xml")
        self.assertTrue(fw_bools.exists())
        tree = ET.parse(fw_bools)
        root = tree.getroot()
        bdict = {i.attrib.get("name"): (i.text or "").strip() for i in root.findall("bool")}

        self.assertEqual(bdict.get("config_voice_capable"), "false")
        self.assertEqual(bdict.get("config_sms_capable"), "false")
        self.assertEqual(bdict.get("config_cellBroadcastAppLinks"), "false")
        self.assertEqual(bdict.get("config_showEmergencyButton"), "false")
        self.assertEqual(bdict.get("config_showOperatorNameInStatusBar"), "false")

    def test_settings_provisioning_scripts_exist(self):
        """Verify sanitize_ui_settings.sh and .ps1 exist and contain required keys."""
        sh_path = WORKSPACE_ROOT / "ui_sanitization" / "sanitize_ui_settings.sh"
        ps_path = WORKSPACE_ROOT / "ui_sanitization" / "sanitize_ui_settings.ps1"

        self.assertTrue(sh_path.exists())
        self.assertTrue(ps_path.exists())

        sh_content = sh_path.read_text(encoding="utf-8")
        self.assertIn("settings put secure sysui_qs_tiles", sh_content)
        self.assertIn("settings put global airplane_mode_radios", sh_content)
        self.assertIn("settings put global mobile_data 0", sh_content)

        ps_content = ps_path.read_text(encoding="utf-8")
        self.assertIn("settings put secure sysui_qs_tiles", ps_content)
        self.assertIn("settings put global airplane_mode_radios", ps_content)


class TestVendorRepackIntegration(unittest.TestCase):
    """Test integration contract between M3 and M1 vendor repackaging."""

    def test_build_vendor_stabilized_injects_telephony_stack(self):
        """Verify build_vendor_stabilized.py references telephony purge and SystemUI overlay."""
        vendor_script = WORKSPACE_ROOT / "partitions" / "build_vendor_stabilized.py"
        self.assertTrue(vendor_script.exists())
        content = vendor_script.read_text(encoding="utf-8")

        # Telephony build.prop keys
        self.assertIn("ro.radio.noril", content)
        self.assertIn("ro.carrier", content)
        self.assertIn("telephony.lteOnCdmaDevice", content)

        # Modem service overrides in init.connectivity.rc
        self.assertIn("inject_modem_services_override", content)
        self.assertIn("init.connectivity.rc", content)

        # SystemUI overlay APK
        self.assertIn("treble-overlay-lenovo-tb311fu-systemui.apk", content)


if __name__ == "__main__":
    unittest.main()

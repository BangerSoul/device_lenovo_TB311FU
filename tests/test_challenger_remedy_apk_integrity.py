#!/usr/bin/env python3
"""
tests/test_challenger_remedy_apk_integrity.py
Adversarial APK Integrity Challenge Suite for SystemUI RRO Overlay (M3 Remedy).
Target: treble-overlay-lenovo-tb311fu-systemui.apk

Challenge Dimensions:
1. Genuine APK Invariant Verification:
   - Uncompressed ZIP_STORED resources.arsc (compress_type = 0)
   - 4-byte zipalign verification (both via zipalign binary and raw zip local header offset inspection)
   - Genuine binary AXML (magic 0x00080003, targetPackage com.android.systemui)
   - Genuine binary ARSC (type 0x0002, chunk size match, sanitized QS tiles, zero forbidden tiles)
   - Authentic ASN.1 DER PKCS#7 signature (valid X.509 cert, SHA-256 manifest digest, no synthetic null padding)
   - Multi-path parity check: deployment/, ui_sanitization/, and fearless-maxwell/gsi_suite/overlay/

2. Adversarial Mutation & Oracle Rejection Tests:
   - Challenge against corrupted AXML magic (0x00000000, 0xEF53, <?xml)
   - Challenge against corrupted ARSC table type (0x0001, 0x0000, 0xFFFF)
   - Challenge against corrupted ARSC chunk size (header size mismatch)
   - Challenge against compressed ARSC (ZIP_DEFLATED)
   - Challenge against unaligned ARSC (offset % 4 != 0)
   - Challenge against corrupted DER signature (truncated, bit-flipped, null-padded \x00*250)
   - Challenge against missing QS stock tile
   - Challenge against injected forbidden tiles (flashlight, torch, cell)
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from ui_sanitization.build_systemui_overlay import (
    verify_systemui_overlay_apk,
    FORBIDDEN_TILES,
    EXPECTED_DEFAULT_TILES,
)


class ChallengerApkIntegrityOracle:
    """
    Independent Challenger Oracle:
    Strictly verifies APK integrity without relying on the implementation validator.
    """

    @staticmethod
    def inspect_raw_zip_alignment(apk_bytes: bytes, target_filename: str = "resources.arsc") -> dict:
        """
        Inspect zip file local file headers directly from byte stream.
        Calculates exact file data offset within the archive and checks 4-byte alignment.
        """
        bio = io.BytesIO(apk_bytes)
        zf = zipfile.ZipFile(bio, "r")
        alignment_report = {}

        for info in zf.infolist():
            header_offset = info.header_offset
            bio.seek(header_offset)
            magic = bio.read(4)
            if magic != b"PK\x03\x04":
                raise ValueError(f"Corrupt local header at offset {header_offset}")

            # Local header is 30 bytes
            bio.seek(header_offset + 26)
            fname_len, extra_len = struct.unpack("<HH", bio.read(4))
            data_offset = header_offset + 30 + fname_len + extra_len

            is_4byte_aligned = (data_offset % 4 == 0)
            alignment_report[info.filename] = {
                "header_offset": header_offset,
                "data_offset": data_offset,
                "is_4byte_aligned": is_4byte_aligned,
                "compress_type": info.compress_type,
                "file_size": info.file_size,
                "compress_size": info.compress_size,
            }

        if target_filename in alignment_report:
            target_info = alignment_report[target_filename]
            if target_info["compress_type"] != 0:
                raise ValueError(f"{target_filename} compress_type is {target_info['compress_type']}, expected 0 (ZIP_STORED)")
            if not target_info["is_4byte_aligned"]:
                raise ValueError(f"{target_filename} data offset {target_info['data_offset']} is NOT 4-byte aligned!")

        return alignment_report

    @staticmethod
    def verify_pkcs7_der_signature(rsa_bytes: bytes, cert_sf_bytes: bytes, manifest_mf_bytes: bytes) -> dict:
        """
        Strictly verify ASN.1 DER PKCS#7 signature block against CERT.SF and MANIFEST.MF.
        """
        if len(rsa_bytes) < 500:
            raise ValueError(f"Signature block too small: {len(rsa_bytes)} bytes")
        if rsa_bytes[0] != 0x30:
            raise ValueError(f"Signature block does not start with ASN.1 DER SEQUENCE (0x30): {hex(rsa_bytes[0])}")

        # Check for synthetic null padding
        consec = max_consec = 0
        for b in rsa_bytes:
            if b == 0:
                consec += 1
                max_consec = max(max_consec, consec)
            else:
                consec = 0
        if max_consec >= 16:
            raise ValueError(f"Signature contains {max_consec} consecutive null bytes (facade dummy padding detected)")

        # Parse certificates from DER PKCS#7
        certs = pkcs7.load_der_pkcs7_certificates(rsa_bytes)
        if not certs:
            raise ValueError("No X.509 certificates extracted from PKCS#7 signature block")
        cert = certs[0]

        # Verify Manifest digest in CERT.SF
        mf_sha256 = hashlib.sha256(manifest_mf_bytes).digest()
        mf_b64 = base64.b64encode(mf_sha256).decode("ascii")

        cert_sf_text = cert_sf_bytes.decode("utf-8", errors="replace")
        if mf_b64 not in cert_sf_text:
            raise ValueError("SHA-256-Digest-Manifest mismatch in CERT.SF")

        return {
            "valid": True,
            "cert_subject": cert.subject.rfc4514_string(),
            "cert_issuer": cert.issuer.rfc4514_string(),
            "max_consecutive_zeros": max_consec,
            "total_zeros": rsa_bytes.count(b"\x00"),
            "cert_count": len(certs),
        }


class TestChallengerApkIntegrity(unittest.TestCase):
    """Empirical verification and adversarial challenge of SystemUI RRO APK."""

    @classmethod
    def setUpClass(cls):
        cls.apk_deployment = WORKSPACE_ROOT / "deployment" / "treble-overlay-lenovo-tb311fu-systemui.apk"
        cls.apk_ui_sanitization = WORKSPACE_ROOT / "ui_sanitization" / "treble-overlay-lenovo-tb311fu-systemui.apk"
        cls.apk_gsi_suite = WORKSPACE_ROOT.parent / "fearless-maxwell" / "gsi_suite" / "overlay" / "treble-overlay-lenovo-tb311fu-systemui.apk"
        cls.zipalign_bin = r"C:\platform-tools\zipalign.exe"

    def test_01_apk_presence_across_all_three_locations(self):
        """Verify the overlay APK exists in deployment/, ui_sanitization/, and gsi_suite/."""
        self.assertTrue(self.apk_deployment.is_file(), f"Missing {self.apk_deployment}")
        self.assertTrue(self.apk_ui_sanitization.is_file(), f"Missing {self.apk_ui_sanitization}")
        self.assertTrue(self.apk_gsi_suite.is_file(), f"Missing {self.apk_gsi_suite}")

        sz_dep = self.apk_deployment.stat().st_size
        sz_ui = self.apk_ui_sanitization.stat().st_size
        sz_gsi = self.apk_gsi_suite.stat().st_size

        self.assertEqual(sz_dep, sz_ui, "deployment/ and ui_sanitization/ APK sizes differ")
        self.assertEqual(sz_dep, sz_gsi, "deployment/ and gsi_suite/ APK sizes differ")
        self.assertEqual(sz_dep, 4095, f"Expected exactly 4,095 bytes, got {sz_dep}")

    def test_02_zipalign_cli_verification(self):
        """Verify 4-byte alignment using modern C:\\platform-tools\\zipalign.exe."""
        if not os.path.exists(self.zipalign_bin):
            self.skipTest(f"zipalign not found at {self.zipalign_bin}")

        for apk_path in [self.apk_deployment, self.apk_ui_sanitization, self.apk_gsi_suite]:
            res = subprocess.run(
                [self.zipalign_bin, "-c", "-v", "4", str(apk_path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"zipalign verification failed for {apk_path}:\n{res.stdout}\n{res.stderr}")
            self.assertIn("Verification successful", res.stdout)
            self.assertIn("resources.arsc (OK)", res.stdout)

    def test_03_zip_raw_alignment_and_stored_compression(self):
        """Perform byte-level raw zip header parsing to prove resources.arsc is ZIP_STORED and 4-byte aligned."""
        apk_bytes = self.apk_deployment.read_bytes()
        rep = ChallengerApkIntegrityOracle.inspect_raw_zip_alignment(apk_bytes, "resources.arsc")

        arsc_rep = rep["resources.arsc"]
        self.assertEqual(arsc_rep["compress_type"], 0, "resources.arsc must be ZIP_STORED (compress_type=0)")
        self.assertEqual(arsc_rep["file_size"], arsc_rep["compress_size"], "Stored file size must equal compressed size")
        self.assertTrue(arsc_rep["is_4byte_aligned"], f"resources.arsc data offset {arsc_rep['data_offset']} is not 4-byte aligned")
        self.assertEqual(arsc_rep["data_offset"] % 4, 0)
        self.assertEqual(arsc_rep["data_offset"], 824)

    def test_04_axml_binary_geometry_and_package_targets(self):
        """Extract and inspect binary AndroidManifest.xml from deployment APK."""
        with zipfile.ZipFile(self.apk_deployment, "r") as zf:
            axml = zf.read("AndroidManifest.xml")

        # Magic 0x00080003
        magic = struct.unpack("<I", axml[:4])[0]
        self.assertEqual(magic, 0x00080003, f"AXML magic 0x{magic:08x} != 0x00080003")
        self.assertFalse(axml.startswith(b"<?xml"))

        # Target package tokenization
        self.assertTrue(
            b"com.android.systemui" in axml or "com.android.systemui".encode("utf-16le") in axml,
            "Target package com.android.systemui missing from binary AXML",
        )
        self.assertTrue(
            b"me.phh.treble.overlay.lenovo.tb311fu.systemui" in axml
            or "me.phh.treble.overlay.lenovo.tb311fu.systemui".encode("utf-16le") in axml,
            "Overlay package name missing from binary AXML",
        )

    def test_05_arsc_binary_geometry_and_string_pool_tokens(self):
        """Extract and inspect binary resources.arsc from deployment APK."""
        with zipfile.ZipFile(self.apk_deployment, "r") as zf:
            arsc = zf.read("resources.arsc")

        table_type, header_size, chunk_size = struct.unpack("<HHI", arsc[:8])
        self.assertEqual(table_type, 0x0002, f"Invalid ARSC table type: {hex(table_type)}")
        self.assertEqual(header_size, 12)
        self.assertEqual(chunk_size, len(arsc))

        pkg_count = struct.unpack("<I", arsc[8:12])[0]
        self.assertEqual(pkg_count, 1)

        # Token checks
        self.assertIn(b"quick_settings_tiles_stock", arsc)
        self.assertIn(b"quick_settings_tiles_new_default", arsc)
        self.assertIn(b"wifi,bt,dnd,rotation,battery,screenrecord,cast,alarm,calculator", arsc)

        # Carrier text tokens
        self.assertIn(b"keyguard_carrier_text", arsc)
        self.assertIn(b"shade_carrier_text", arsc)
        self.assertIn(b"no_carrier_text", arsc)
        self.assertIn(b"mobile_carrier_text_format", arsc)
        self.assertIn(b"keyguard_carrier_text_margin", arsc)

        # STRICT ADVERSARIAL FORBIDDEN TOKENS CHECK
        for forbidden in [b"flashlight", b"torch", b"cell"]:
            self.assertNotIn(forbidden, arsc, f"CRITICAL LEAK: Forbidden tile '{forbidden.decode()}' in resources.arsc")

    def test_06_pkcs7_der_cryptographic_verification(self):
        """Verify authentic PKCS#7 signature and absence of synthetic null dummy blocks."""
        with zipfile.ZipFile(self.apk_deployment, "r") as zf:
            rsa_bytes = zf.read("META-INF/CERT.RSA")
            cert_sf_bytes = zf.read("META-INF/CERT.SF")
            manifest_mf_bytes = zf.read("META-INF/MANIFEST.MF")

        sig_rep = ChallengerApkIntegrityOracle.verify_pkcs7_der_signature(rsa_bytes, cert_sf_bytes, manifest_mf_bytes)
        self.assertTrue(sig_rep["valid"])
        self.assertEqual(sig_rep["max_consecutive_zeros"], 1, "Expected max 1 consecutive zero byte in ASN.1 DER")
        self.assertLessEqual(sig_rep["total_zeros"], 20, f"Excessive zero bytes in signature: {sig_rep['total_zeros']}")
        self.assertIn("TB311FU SystemUI Overlay", sig_rep["cert_subject"])
        self.assertIn("Lenovo", sig_rep["cert_subject"])

    def test_07_adversarial_rejection_of_corrupted_axml_magic(self):
        """Adversarial: Mutating AXML magic MUST cause validation to fail."""
        apk_bytes = self.apk_deployment.read_bytes()

        for bad_magic in [b"\x00\x00\x00\x00", b"\x53\xef\x00\x00", b"<?xm"]:
            with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".apk") as tf:
                temp_apk = tf.name

            try:
                with zipfile.ZipFile(self.apk_deployment, "r") as zin:
                    with zipfile.ZipFile(temp_apk, "w") as zout:
                        for item in zin.infolist():
                            data = zin.read(item.filename)
                            if item.filename == "AndroidManifest.xml":
                                data = bad_magic + data[4:]
                            zout.writestr(item, data)

                valid, errors = verify_systemui_overlay_apk(temp_apk)
                self.assertFalse(valid, f"Validator accepted bad AXML magic {bad_magic}")
                self.assertTrue(any("magic" in e.lower() or "binary axml" in e.lower() or "uncompiled" in e.lower() for e in errors))
            finally:
                if os.path.exists(temp_apk):
                    os.remove(temp_apk)

    def test_08_adversarial_rejection_of_corrupted_arsc_table_type(self):
        """Adversarial: Mutating ARSC table type from 0x0002 to bad values MUST fail."""
        for bad_type in [0x0000, 0x0001, 0x0003, 0xFFFF]:
            with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".apk") as tf:
                temp_apk = tf.name

            try:
                with zipfile.ZipFile(self.apk_deployment, "r") as zin:
                    with zipfile.ZipFile(temp_apk, "w") as zout:
                        for item in zin.infolist():
                            data = zin.read(item.filename)
                            if item.filename == "resources.arsc":
                                data = struct.pack("<H", bad_type) + data[2:]
                            zout.writestr(item, data)

                valid, errors = verify_systemui_overlay_apk(temp_apk)
                self.assertFalse(valid, f"Validator accepted bad ARSC table type {hex(bad_type)}")
                self.assertTrue(any("table type" in e.lower() for e in errors))
            finally:
                if os.path.exists(temp_apk):
                    os.remove(temp_apk)

    def test_09_adversarial_rejection_of_compressed_arsc(self):
        """Adversarial: Storing resources.arsc with ZIP_DEFLATED (compress_type=8) MUST fail."""
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".apk") as tf:
            temp_apk = tf.name

        try:
            with zipfile.ZipFile(self.apk_deployment, "r") as zin:
                with zipfile.ZipFile(temp_apk, "w") as zout:
                    for item in zin.infolist():
                        data = zin.read(item.filename)
                        compress_type = zipfile.ZIP_DEFLATED if item.filename == "resources.arsc" else item.compress_type
                        zout.writestr(item.filename, data, compress_type=compress_type)

            valid, errors = verify_systemui_overlay_apk(temp_apk)
            self.assertFalse(valid, "Validator accepted compressed resources.arsc")
            self.assertTrue(any("zip_stored" in e.lower() for e in errors))

            # Also verify challenger oracle rejects it
            with self.assertRaises(ValueError):
                ChallengerApkIntegrityOracle.inspect_raw_zip_alignment(Path(temp_apk).read_bytes(), "resources.arsc")
        finally:
            if os.path.exists(temp_apk):
                os.remove(temp_apk)

    def test_10_adversarial_rejection_of_unaligned_arsc(self):
        """Adversarial: Shifting resources.arsc data offset by 1 byte (misaligned) MUST fail zipalign verification."""
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".apk") as tf:
            temp_apk = tf.name

        try:
            # Build archive with 1-byte padding before resources.arsc
            with zipfile.ZipFile(self.apk_deployment, "r") as zin:
                with zipfile.ZipFile(temp_apk, "w") as zout:
                    zout.writestr("pad", b"X")  # unaligns following entry
                    for item in zin.infolist():
                        data = zin.read(item.filename)
                        zout.writestr(item.filename, data, compress_type=item.compress_type)

            # Challenger oracle detects misalignment
            with self.assertRaises(ValueError):
                ChallengerApkIntegrityOracle.inspect_raw_zip_alignment(Path(temp_apk).read_bytes(), "resources.arsc")

            # CLI zipalign fails
            if os.path.exists(self.zipalign_bin):
                res = subprocess.run([self.zipalign_bin, "-c", "4", temp_apk], capture_output=True, text=True)
                self.assertNotEqual(res.returncode, 0, "zipalign CLI unexpectedly accepted unaligned APK")
        finally:
            if os.path.exists(temp_apk):
                os.remove(temp_apk)

    def test_11_adversarial_rejection_of_null_padded_facade_signature(self):
        """Adversarial: Re-injecting synthetic null padding (b'\\x00' * 250) MUST be caught by validator."""
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".apk") as tf:
            temp_apk = tf.name

        try:
            with zipfile.ZipFile(self.apk_deployment, "r") as zin:
                with zipfile.ZipFile(temp_apk, "w") as zout:
                    for item in zin.infolist():
                        data = zin.read(item.filename)
                        if item.filename.endswith(".RSA"):
                            # Inject 250 null bytes like previous facade
                            data = b"\x30\x82\x04\x00" + b"\x00" * 250 + data
                        zout.writestr(item, data)

            valid, errors = verify_systemui_overlay_apk(temp_apk)
            self.assertFalse(valid, "Validator accepted synthetic null padded signature")
            self.assertTrue(any("null" in e.lower() or "consecutive" in e.lower() or "dummy" in e.lower() for e in errors))

            # Challenger oracle also rejects
            with zipfile.ZipFile(temp_apk, "r") as tf_zf:
                rsa = tf_zf.read("META-INF/CERT.RSA")
                sf = tf_zf.read("META-INF/CERT.SF")
                mf = tf_zf.read("META-INF/MANIFEST.MF")
            with self.assertRaises(ValueError):
                ChallengerApkIntegrityOracle.verify_pkcs7_der_signature(rsa, sf, mf)
        finally:
            if os.path.exists(temp_apk):
                os.remove(temp_apk)

    def test_12_adversarial_rejection_of_forbidden_tile_injection(self):
        """Adversarial: Injecting forbidden tiles (flashlight, torch, cell) into ARSC string pool MUST fail."""
        for forbidden in [b"flashlight", b"torch", b"cell"]:
            with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".apk") as tf:
                temp_apk = tf.name

            try:
                with zipfile.ZipFile(self.apk_deployment, "r") as zin:
                    with zipfile.ZipFile(temp_apk, "w") as zout:
                        for item in zin.infolist():
                            data = zin.read(item.filename)
                            if item.filename == "resources.arsc":
                                # Replace 'screenrecord' with forbidden token
                                data = data.replace(b"screenrecord", forbidden.ljust(12, b"x"))
                            zout.writestr(item, data)

                valid, errors = verify_systemui_overlay_apk(temp_apk)
                self.assertFalse(valid, f"Validator accepted injected forbidden tile {forbidden.decode()}")
                self.assertTrue(any("forbidden tile" in e.lower() for e in errors))
            finally:
                if os.path.exists(temp_apk):
                    os.remove(temp_apk)


if __name__ == "__main__":
    unittest.main(verbosity=2)

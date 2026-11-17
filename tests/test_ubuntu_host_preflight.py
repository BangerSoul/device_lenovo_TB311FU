import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "ubuntu-usb" / "host-preflight.ps1"
EXPECTED_ISO_SHA256 = "601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f"


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required for host preflight")
class UbuntuHostPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default_result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(SCRIPT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if not cls.default_result.stdout.strip().startswith("{"):
            raise AssertionError(
                f"preflight did not emit JSON; stdout={cls.default_result.stdout!r}, "
                f"stderr={cls.default_result.stderr!r}"
            )
        cls.default_report = json.loads(cls.default_result.stdout)

    def run_preflight(self, iso_path=None):
        command = ["pwsh", "-NoProfile", "-File", str(SCRIPT)]
        if iso_path is not None:
            command.extend(["-IsoPath", str(iso_path)])
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    def parse_report(self, result):
        self.assertTrue(
            result.stdout.strip().startswith("{"),
            f"preflight did not emit JSON; stdout={result.stdout!r}, stderr={result.stderr!r}",
        )
        return json.loads(result.stdout)

    def test_preflight_reports_host_fields_and_pinned_iso(self):
        report = self.default_report
        self.assertIn("windowsVersion", report)
        self.assertIn("cpu", report)
        self.assertIn("virtualizationFirmwareEnabled", report["cpu"])
        self.assertIn("hypervisorPresent", report["cpu"])
        self.assertIn("distributions", report["wsl"])
        self.assertGreater(report["cFreeBytes"], 0)
        self.assertEqual(report["iso"]["sha256"], EXPECTED_ISO_SHA256)
        self.assertTrue(report["iso"]["matchesExpected"])

    def test_preflight_exit_code_matches_reported_status(self):
        self.assertEqual(self.default_result.returncode, self.default_report["exitCode"])
        self.assertIn(self.default_result.returncode, (0, 2))

    def test_iso_hash_mismatch_is_fatal(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            wrong_iso = Path(temporary_directory) / "wrong.iso"
            wrong_iso.write_bytes(b"not the pinned Ubuntu image")
            result = self.run_preflight(wrong_iso)

        report = self.parse_report(result)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["exitCode"], 1)
        self.assertFalse(report["iso"]["matchesExpected"])


if __name__ == "__main__":
    unittest.main()

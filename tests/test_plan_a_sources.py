import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
VALIDATOR = REPO / "tools" / "validate_plan_a_sources.py"
RELEASE_URL = "https://github.com/MisterZtr/LineageOS_gsi/releases/tag/v2026.05.24-lineage23.2"
ARCHIVE_URL = (
    "https://sourceforge.net/projects/misterztr-gsi/files/LineageOS/"
    "Android%2016/LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z/download"
)
REPOSITORY_NAMES = {
    "device_lenovo_TB311FU",
    "vendor_lenovo_TB311FU",
    "kernel_lenovo_TB311FU",
    "recovery_lenovo_TB311FU",
    "linux-lenovo-tb311fu",
    "local_manifests",
    "crave_aosp_builder",
}


def valid_manifest():
    return {
        "device": {"manufacturer": "Lenovo", "model": "TB311FU", "codename": "poplar"},
        "source": {
            "project": "MisterZtr/LineageOS_gsi",
            "tag": "v2026.05.24-lineage23.2",
            "commit": "7bf212f",
            "release_url": RELEASE_URL,
            "archive_url": ARCHIVE_URL,
            "archive_filename": "LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z",
            "variant": "Android 16 QPR2; A/B; GAPPS; EXT4",
            "archive_sha256": None,
            "status": "pending_first_download",
        },
        "artifacts": {
            "gsi": {"redistribute": False},
            "google_apps": {"redistribute": False},
        },
        "repositories": [
            {
                "name": name,
                "url": f"https://github.com/BangerSoul/{name}",
                "role": f"{name} source role",
            }
            for name in sorted(REPOSITORY_NAMES)
        ],
        "local_artifacts": [
            {
                "name": "vibrant-hertz workspace",
                "classification": "local-only / inventory required",
            }
        ],
    }


class PlanASourceManifestTests(unittest.TestCase):
    def validate(self, data):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(manifest_path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_source_pin_matches_release(self):
        result = self.validate(valid_manifest())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        changes = (
            ("tag", "latest"),
            ("commit", "unknown"),
            ("release_url", "https://example.invalid/release"),
            ("archive_url", "https://example.invalid/gsi.7z"),
            ("archive_filename", "wrong.7z"),
            ("variant", "Android 15; A-only; VANILLA; EXT4"),
        )
        for field, value in changes:
            with self.subTest(field=field):
                changed = valid_manifest()
                changed["source"][field] = value
                self.assertEqual(1, self.validate(changed).returncode)

    def test_archive_hash_state_is_consistent(self):
        changed = valid_manifest()
        changed["source"]["status"] = "pinned"
        self.assertEqual(1, self.validate(changed).returncode)

        changed["source"]["status"] = "pending_first_download"
        changed["source"]["archive_sha256"] = "a" * 64
        self.assertEqual(1, self.validate(changed).returncode)

    def test_pinned_hash_is_64_lowercase_hex(self):
        pinned = valid_manifest()
        pinned["source"]["status"] = "pinned"
        pinned["source"]["archive_sha256"] = "a" * 64
        self.assertEqual(0, self.validate(pinned).returncode)

        pinned["source"]["archive_sha256"] = "A" * 64
        self.assertEqual(1, self.validate(pinned).returncode)

    def test_gsi_and_google_apps_are_not_publishable(self):
        for artifact in ("gsi", "google_apps"):
            with self.subTest(artifact=artifact):
                changed = valid_manifest()
                changed["artifacts"][artifact]["redistribute"] = True
                self.assertEqual(1, self.validate(changed).returncode)

    def test_required_repositories_have_url_and_role(self):
        changed = valid_manifest()
        changed["repositories"][0].pop("url")
        self.assertEqual(1, self.validate(changed).returncode)

        changed = valid_manifest()
        changed["repositories"][0]["url"] = "https://example.invalid/wrong-repository"
        self.assertEqual(1, self.validate(changed).returncode)

        changed = valid_manifest()
        changed["repositories"][0]["role"] = ""
        self.assertEqual(1, self.validate(changed).returncode)


if __name__ == "__main__":
    unittest.main()


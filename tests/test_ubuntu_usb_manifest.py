import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tools" / "ubuntu-usb" / "manifest.json"
VALIDATOR_PATH = ROOT / "tools" / "ubuntu-usb" / "validate_manifest.py"
EXPECTED_ISO_SHA256 = "601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f"


def load_project_files(test_case):
    test_case.assertTrue(MANIFEST_PATH.is_file(), "Ubuntu workstation manifest is missing")
    test_case.assertTrue(VALIDATOR_PATH.is_file(), "Ubuntu workstation manifest validator is missing")

    with MANIFEST_PATH.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    spec = importlib.util.spec_from_file_location("ubuntu_usb_manifest_validator", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return manifest, module.validate_manifest


class UbuntuUsbManifestTests(unittest.TestCase):
    def test_base_iso_sha_is_pinned(self):
        manifest, _ = load_project_files(self)

        self.assertEqual(manifest["base_iso"]["sha256"], EXPECTED_ISO_SHA256)

    def test_required_apps_are_listed(self):
        manifest, _ = load_project_files(self)

        app_ids = {app["id"] for app in manifest["apps"]}
        self.assertTrue({"antigravity", "chatgpt", "brave", "keepassxc"}.issubset(app_ids))
        package_names = set(manifest["packages"])
        self.assertTrue(
            {"git", "python3", "adb", "fastboot", "7zip", "e2fsprogs", "openjdk-21-jdk"}.issubset(package_names)
        )

    def test_application_asset_urls_use_vendor_delivery_hosts(self):
        manifest, validate_manifest = load_project_files(self)
        invalid = copy.deepcopy(manifest)
        invalid["assets"][0]["source_url"] = "https://example.com/Antigravity.tar.gz"

        errors = validate_manifest(invalid)

        self.assertTrue(any("vendor delivery host" in error for error in errors))

    def test_duplicate_app_ids_are_rejected(self):
        manifest, validate_manifest = load_project_files(self)
        invalid = copy.deepcopy(manifest)
        invalid["apps"].append(copy.deepcopy(invalid["apps"][0]))

        errors = validate_manifest(invalid)

        self.assertTrue(any("duplicate app id" in error for error in errors))

    def test_downloaded_app_version_and_hash_match_asset_record(self):
        manifest, validate_manifest = load_project_files(self)
        invalid = copy.deepcopy(manifest)
        invalid["apps"][0]["sha256"] = "0" * 64

        errors = validate_manifest(invalid)

        self.assertTrue(any("does not match its asset record" in error for error in errors))

    def test_pending_asset_hash_state_is_consistent(self):
        manifest, validate_manifest = load_project_files(self)

        self.assertEqual(validate_manifest(manifest), [])
        invalid = copy.deepcopy(manifest)
        invalid["assets"][0]["status"] = "pending_download"
        invalid["assets"][0]["version"] = None
        invalid["assets"][0]["sha256"] = "a" * 64
        self.assertTrue(any("pending_download" in error for error in validate_manifest(invalid)))

    def test_downloaded_asset_hash_is_valid(self):
        manifest, validate_manifest = load_project_files(self)
        downloaded = copy.deepcopy(manifest)
        downloaded["assets"][0]["status"] = "downloaded"
        downloaded["assets"][0]["version"] = "1.2.3"
        downloaded["assets"][0]["sha256"] = "a" * 64
        downloaded["apps"][0]["version"] = "1.2.3"
        downloaded["apps"][0]["sha256"] = "a" * 64
        self.assertEqual(validate_manifest(downloaded), [])

        downloaded["assets"][0]["sha256"] = "A" * 64
        self.assertTrue(any("lowercase SHA-256" in error for error in validate_manifest(downloaded)))

    def test_assets_use_local_relative_paths(self):
        manifest, _ = load_project_files(self)

        for asset in manifest["assets"]:
            path = asset["local_path"]
            self.assertFalse(Path(path).is_absolute(), path)
            self.assertFalse(path.startswith("/"), path)
            self.assertNotIn("..", Path(path).parts)

    def test_no_secret_fields_are_in_manifest(self):
        manifest, validate_manifest = load_project_files(self)
        invalid = copy.deepcopy(manifest)
        invalid["account_token"] = "should never be stored"
        self.assertTrue(any("secret field" in error for error in validate_manifest(invalid)))


if __name__ == "__main__":
    unittest.main()

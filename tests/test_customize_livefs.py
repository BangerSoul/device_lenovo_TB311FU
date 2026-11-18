import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "ubuntu-usb" / "customize-livefs.sh"
REQUIRED_ASSETS = {
    "antigravity_linux_x64": "Antigravity.tar.gz",
    "chatgpt_linux_amd64": "chatgpt_amd64.deb",
    "ivo0536_icc_profile": "Dell_IVO0536_HDR_D65.icm",
}


def bash_path(path):
    windows_path = Path(path).resolve().as_posix()
    if not (len(windows_path) > 1 and windows_path[1] == ":"):
        return windows_path
    return f"/{windows_path[0].lower()}{windows_path[2:]}"


@unittest.skipUnless(shutil.which("bash"), "Bash is required for the Cubic customizer")
class CustomizeLivefsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.assets_dir = Path(self.temporary_directory.name) / "assets"
        self.assets_dir.mkdir()
        self.manifest_path = Path(self.temporary_directory.name) / "asset-manifest.local.json"
        assets = []
        for asset_id, filename in REQUIRED_ASSETS.items():
            contents = f"fixture:{asset_id}".encode()
            asset_path = self.assets_dir / filename
            if asset_id == "antigravity_linux_x64":
                member = tarfile.TarInfo("Antigravity-x64/antigravity")
                member.mode = 0o755
                member.size = len(contents)
                with tarfile.open(asset_path, mode="w:gz") as archive:
                    archive.addfile(member, io.BytesIO(contents))
            else:
                asset_path.write_bytes(contents)
            assets.append(
                {
                    "id": asset_id,
                    "path": filename,
                    "version": "1.2.3",
                    "sha256": hashlib.sha256(asset_path.read_bytes()).hexdigest(),
                }
            )
        self.manifest_path.write_text(json.dumps({"assets": assets}), encoding="utf-8")

    def run_check(self):
        environment = os.environ.copy()
        environment["PYTHON"] = bash_path(Path(sys.executable))
        return subprocess.run(
            [
                "bash",
                bash_path(SCRIPT),
                "--check",
                "--assets-dir",
                bash_path(self.assets_dir),
                "--manifest",
                bash_path(self.manifest_path),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_package_list_includes_brave_browser(self):
        packages_path = SCRIPT.with_name("packages.txt")
        package_names = {
            line.split("#", 1)[0].strip()
            for line in packages_path.read_text(encoding="utf-8").splitlines()
            if line.split("#", 1)[0].strip()
        }

        self.assertIn("brave-browser", package_names)

    def test_installs_curl_before_fetching_brave_repository(self):
        script = SCRIPT.read_text(encoding="utf-8")
        bootstrap_command = "apt-get install -y --no-install-recommends curl ca-certificates gnupg"
        repository_command = "curl -fsSLo"

        self.assertIn(bootstrap_command, script)
        self.assertIn(repository_command, script)
        bootstrap = script.index(bootstrap_command)
        repository_fetch = script.index(repository_command)

        self.assertLess(bootstrap, repository_fetch)

    def test_disables_and_restores_cdrom_source_around_apt_install(self):
        script = SCRIPT.read_text(encoding="utf-8")
        disable_source = 'mv "$cdrom_source" "$cdrom_source_disabled"'
        restore_trap = "trap restore_cdrom_source EXIT"

        self.assertIn(disable_source, script)
        self.assertIn(restore_trap, script)
        self.assertLess(script.index(disable_source), script.index("apt-get update"))

    def test_check_passes_with_valid_assets(self):
        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("assets and package list verified", result.stdout.lower())

    def test_check_rejects_missing_asset(self):
        (self.assets_dir / REQUIRED_ASSETS["chatgpt_linux_amd64"]).unlink()

        result = self.run_check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("chatgpt", (result.stdout + result.stderr).lower())

    def test_check_rejects_hash_mismatch(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["assets"][0]["sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.run_check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sha-256", (result.stdout + result.stderr).lower())

    def test_check_rejects_antigravity_archive_without_launcher(self):
        antigravity_path = self.assets_dir / REQUIRED_ASSETS["antigravity_linux_x64"]
        antigravity_path.write_bytes(b"not an Antigravity tarball")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["assets"][0]["sha256"] = hashlib.sha256(antigravity_path.read_bytes()).hexdigest()
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.run_check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("antigravity", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()

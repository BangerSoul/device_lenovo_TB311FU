#!/usr/bin/env python3
"""Validate the public Ubuntu USB manifest without reading local assets."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse


EXPECTED_ISO_SHA256 = "601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f"
REQUIRED_APPS = {"antigravity", "chatgpt", "brave", "keepassxc"}
REQUIRED_PACKAGES = {
    "git",
    "python3",
    "adb",
    "fastboot",
    "7zip",
    "e2fsprogs",
    "openjdk-21-jdk",
}
SECRET_FIELD_MARKERS = {"password", "passwd", "token", "cookie", "session", "credential", "private_key", "secret"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OFFICIAL_HOSTS = {
    "antigravity": {"antigravity.google"},
    "chatgpt": {"persistent.oaistatic.com", "learn.chatgpt.com"},
    "brave": {"brave.com"},
    "keepassxc": {"packages.ubuntu.com"},
}
OFFICIAL_ASSET_LOCATIONS = {
    "antigravity_linux_x64": ("storage.googleapis.com", "/antigravity-public/antigravity-hub/"),
    "chatgpt_linux_amd64": ("persistent.oaistatic.com", "/codex-app-prod/linux/deb/"),
}


def _contains_secret_field(value: object, path: str = "manifest") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if any(marker in normalized for marker in SECRET_FIELD_MARKERS):
                errors.append(f"{path}.{key}: secret field is not allowed")
            errors.extend(_contains_secret_field(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_contains_secret_field(child, f"{path}[{index}]"))
    return errors


def _valid_local_path(path: object) -> bool:
    if not isinstance(path, str) or not path:
        return False
    parsed = PurePosixPath(path)
    return not parsed.is_absolute() and ".." not in parsed.parts and path.startswith("local-assets/")


def _https_host(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return parsed.hostname.lower()


def validate_manifest(data: dict) -> list[str]:
    """Return schema and policy errors for an Ubuntu USB build manifest."""
    errors = _contains_secret_field(data)

    if not isinstance(data, dict):
        return ["manifest: expected an object"]

    if data.get("schema_version") != 1:
        errors.append("schema_version: expected 1")

    base_iso = data.get("base_iso")
    if not isinstance(base_iso, dict):
        errors.append("base_iso: expected an object")
    else:
        if base_iso.get("filename") != "ubuntu-26.04.1-desktop-amd64.iso":
            errors.append("base_iso.filename: unexpected ISO filename")
        if base_iso.get("sha256") != EXPECTED_ISO_SHA256:
            errors.append("base_iso.sha256: does not match the pinned Canonical checksum")
        if _https_host(base_iso.get("checksum_url")) != "releases.ubuntu.com":
            errors.append("base_iso.checksum_url: expected the official Canonical release checksum URL")

    packages = data.get("packages")
    if not isinstance(packages, list) or any(not isinstance(name, str) for name in packages):
        errors.append("packages: expected a list of package names")
    else:
        missing = REQUIRED_PACKAGES - set(packages)
        if missing:
            errors.append(f"packages: missing required tools {', '.join(sorted(missing))}")
        if len(packages) != len(set(packages)):
            errors.append("packages: duplicate package names are not allowed")

    app_by_id: dict[str, dict] = {}
    apps = data.get("apps")
    if not isinstance(apps, list) or any(not isinstance(app, dict) for app in apps):
        errors.append("apps: expected a list of app objects")
    else:
        for app in apps:
            app_id = app.get("id")
            if not isinstance(app_id, str) or not app_id:
                errors.append("apps: each app requires a string id")
            elif app_id in app_by_id:
                errors.append(f"apps: duplicate app id {app_id!r}")
            else:
                app_by_id[app_id] = app
        missing_apps = REQUIRED_APPS - set(app_by_id)
        if missing_apps:
            errors.append(f"apps: missing required apps {', '.join(sorted(missing_apps))}")
        for app in apps:
            app_id = app.get("id")
            if not isinstance(app_id, str) or app_id not in OFFICIAL_HOSTS:
                errors.append(f"apps: unexpected app id {app_id!r}")
                continue
            if _https_host(app.get("source_url")) not in OFFICIAL_HOSTS[app_id]:
                errors.append(f"apps.{app_id}.source_url: not an official HTTPS source")
            if app_id in {"antigravity", "chatgpt"} and not _valid_local_path(app.get("local_asset")):
                errors.append(f"apps.{app_id}.local_asset: expected a safe local-assets path")

    assets = data.get("assets")
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        errors.append("assets: expected a list of asset objects")
        return errors

    asset_ids: set[str] = set()
    asset_by_id: dict[str, dict] = {}
    local_paths: set[str] = set()
    for index, asset in enumerate(assets):
        prefix = f"assets[{index}]"
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id:
            errors.append(f"{prefix}.id: required")
        elif asset_id in asset_ids:
            errors.append(f"{prefix}.id: duplicate asset id")
        else:
            asset_ids.add(asset_id)
            asset_by_id[asset_id] = asset

        local_path = asset.get("local_path")
        if not _valid_local_path(local_path):
            errors.append(f"{prefix}.local_path: expected a safe local-assets path")
        elif local_path in local_paths:
            errors.append(f"{prefix}.local_path: duplicate local path")
        else:
            local_paths.add(local_path)

        status = asset.get("status")
        version = asset.get("version")
        sha256 = asset.get("sha256")
        if status in {"pending_download", "pending_local_copy"}:
            if version is not None or sha256 is not None:
                errors.append(f"{prefix}: {status} requires null version and SHA-256")
        elif status == "present_locally" and asset.get("kind") == "icc_profile":
            if version is not None or sha256 is not None:
                errors.append(f"{prefix}: local-only ICC metadata must omit version and SHA-256")
        elif status == "downloaded":
            if not isinstance(version, str) or not version.strip():
                errors.append(f"{prefix}: downloaded asset requires an exact version")
            if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
                errors.append(f"{prefix}: downloaded asset requires a lowercase SHA-256")
        else:
            errors.append(f"{prefix}.status: unsupported asset state")

        source_url = asset.get("source_url")
        if asset.get("kind") != "icc_profile":
            expected_location = OFFICIAL_ASSET_LOCATIONS.get(asset_id)
            parsed_source = urlparse(source_url) if isinstance(source_url, str) else None
            if (
                expected_location is None
                or parsed_source is None
                or parsed_source.scheme != "https"
                or parsed_source.hostname != expected_location[0]
                or not parsed_source.path.startswith(expected_location[1])
            ):
                errors.append(f"{prefix}.source_url: not an approved vendor delivery host and path")

    required_assets = {"antigravity_linux_x64", "chatgpt_linux_amd64", "ivo0536_icc_profile"}
    missing_assets = required_assets - asset_ids
    if missing_assets:
        errors.append(f"assets: missing required local assets {', '.join(sorted(missing_assets))}")

    for app_id, asset_id in {
        "antigravity": "antigravity_linux_x64",
        "chatgpt": "chatgpt_linux_amd64",
    }.items():
        app = app_by_id.get(app_id)
        asset = asset_by_id.get(asset_id)
        if app is None or asset is None:
            continue
        if app.get("status") != asset.get("status"):
            errors.append(f"apps.{app_id}: status does not match its asset record")
        if app.get("local_asset") != asset.get("local_path"):
            errors.append(f"apps.{app_id}: local asset path does not match its asset record")
        if asset.get("status") == "downloaded":
            recorded_version = asset.get("version")
            app_version = app.get("version")
            if not isinstance(app_version, str) or not isinstance(recorded_version, str) or not recorded_version.startswith(app_version):
                errors.append(f"apps.{app_id}: version does not match its asset record")
            if app.get("sha256") != asset.get("sha256"):
                errors.append(f"apps.{app_id}: SHA-256 does not match its asset record")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    manifest_path = Path(args[0]) if args else Path(__file__).with_name("manifest.json")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Manifest error: {exc}", file=sys.stderr)
        return 1

    errors = validate_manifest(data)
    if errors:
        print("Manifest validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Ubuntu USB manifest validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

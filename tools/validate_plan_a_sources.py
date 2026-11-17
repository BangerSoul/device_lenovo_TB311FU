#!/usr/bin/env python3
"""Validate the public source and redistribution metadata for Plan A."""

from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from typing import Any

REPOSITORIES = {
    "device_lenovo_TB311FU": "https://github.com/BangerSoul/device_lenovo_TB311FU",
    "vendor_lenovo_TB311FU": "https://github.com/BangerSoul/vendor_lenovo_TB311FU",
    "kernel_lenovo_TB311FU": "https://github.com/BangerSoul/kernel_lenovo_TB311FU",
    "recovery_lenovo_TB311FU": "https://github.com/BangerSoul/recovery_lenovo_TB311FU",
    "linux-lenovo-tb311fu": "https://github.com/BangerSoul/linux-lenovo-tb311fu",
    "local_manifests": "https://github.com/BangerSoul/local_manifests",
    "crave_aosp_builder": "https://github.com/BangerSoul/crave_aosp_builder",
}
SOURCE = {
    "project": "MisterZtr/LineageOS_gsi",
    "tag": "v2026.05.24-lineage23.2",
    "commit": "7bf212f",
    "release_url": "https://github.com/MisterZtr/LineageOS_gsi/releases/tag/v2026.05.24-lineage23.2",
    "archive_url": (
        "https://sourceforge.net/projects/misterztr-gsi/files/LineageOS/"
        "Android%2016/LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z/download"
    ),
    "archive_filename": "LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z",
    "variant": "Android 16 QPR2; A/B; GAPPS; EXT4",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _object_at(data: Any, key: str, errors: list[str], label: str) -> dict[str, Any]:
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def validate_manifest(data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest must be an object"]

    device = _object_at(data, "device", errors, "device")
    for field, expected in (("manufacturer", "Lenovo"), ("model", "TB311FU"), ("codename", "poplar")):
        if device.get(field) != expected:
            errors.append(f"device.{field} must be {expected!r}")

    source = _object_at(data, "source", errors, "source")
    for field, expected in SOURCE.items():
        if source.get(field) != expected:
            errors.append(f"source.{field} does not match the pinned release")

    status = source.get("status")
    archive_hash = source.get("archive_sha256")
    if status == "pending_first_download":
        if archive_hash is not None:
            errors.append("source.archive_sha256 must be null while the first download is pending")
    elif status == "pinned":
        if not isinstance(archive_hash, str) or not SHA256_RE.fullmatch(archive_hash):
            errors.append("source.archive_sha256 must be 64 lowercase hexadecimal characters when pinned")
    else:
        errors.append("source.status must be 'pending_first_download' or 'pinned'")

    artifacts = _object_at(data, "artifacts", errors, "artifacts")
    for artifact_name in ("gsi", "google_apps"):
        artifact = _object_at(artifacts, artifact_name, errors, f"artifacts.{artifact_name}")
        if artifact.get("redistribute") is not False:
            errors.append(f"artifacts.{artifact_name}.redistribute must be false")

    repositories = data.get("repositories")
    if not isinstance(repositories, list):
        errors.append("repositories must be a list")
    else:
        actual_names: list[str] = []
        for index, repository in enumerate(repositories):
            if not isinstance(repository, dict):
                errors.append(f"repositories[{index}] must be an object")
                continue
            name = repository.get("name")
            if not isinstance(name, str):
                errors.append(f"repositories[{index}].name must be a string")
                continue
            actual_names.append(name)
            if name not in REPOSITORIES:
                errors.append(f"unexpected repository: {name}")
                continue
            if repository.get("url") != REPOSITORIES[name]:
                errors.append(f"repositories[{index}].url does not match {name}")
            if not isinstance(repository.get("role"), str) or not repository["role"].strip():
                errors.append(f"repositories[{index}].role must be non-empty")
        if len(actual_names) != len(set(actual_names)):
            errors.append("repositories must not contain duplicate names")
        if set(actual_names) != set(REPOSITORIES):
            errors.append("repositories must list exactly the seven Plan A repositories")

    local_artifacts = data.get("local_artifacts")
    if not isinstance(local_artifacts, list) or not any(
        isinstance(item, dict)
        and item.get("name") == "vibrant-hertz workspace"
        and item.get("classification") == "local-only / inventory required"
        for item in local_artifacts
    ):
        errors.append("local_artifacts must mark the vibrant-hertz workspace for local inventory")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "plan_a_sources.json",
        help="manifest path (defaults to docs/plan_a_sources.json)",
    )
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read manifest {args.manifest}: {exc}")
        return 1
    errors = validate_manifest(data)
    if errors:
        print("Plan A source manifest: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Plan A source manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""Create a local metadata-only inventory of a workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

CLASSIFICATIONS = {
    "source",
    "test",
    "documentation",
    "configuration",
    "generated_binary",
    "third_party",
    "sensitive_or_license_review",
    "cache",
    "unclassified",
}
CHUNK_SIZE = 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _classification(relative_path: str, existing: dict[str, str]) -> str:
    parts = Path(relative_path).parts
    if "__pycache__" in parts or relative_path.endswith(".pyc"):
        return "cache"
    value = existing.get(relative_path, "unclassified")
    return value if value in CLASSIFICATIONS else "unclassified"


def _record(path: Path, root: Path, existing: dict[str, str]) -> dict[str, Any]:
    relative_path = path.relative_to(root).as_posix()
    row: dict[str, Any] = {
        "path": relative_path,
        "classification": _classification(relative_path, existing),
    }
    if path.is_symlink():
        target_bytes = os.fsencode(os.readlink(path))
        row.update(
            kind="symlink",
            size_bytes=len(target_bytes),
            sha256=hashlib.sha256(target_bytes).hexdigest(),
        )
    else:
        row.update(
            kind="file",
            size_bytes=path.stat().st_size,
            sha256=_sha256_file(path),
        )
    return row


def inventory_workspace(
    root: Path,
    existing_classifications: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"workspace root is not a directory: {root}")

    existing = existing_classifications or {}
    rows: list[dict[str, Any]] = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        symlink_directories = [
            name for name in directories if (current_path / name).is_symlink()
        ]
        directories[:] = sorted(
            name
            for name in directories
            if name != ".git" and name not in symlink_directories
        )

        for name in sorted(symlink_directories + filenames):
            path = current_path / name
            if name == ".git":
                continue
            if not path.is_file() and not path.is_symlink():
                continue
            rows.append(_record(path, root, existing))

    return sorted(rows, key=lambda row: row["path"])


def _load_existing_classifications(output: Path) -> dict[str, str]:
    if not output.exists():
        return {}
    rows = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("existing inventory must be a JSON list")
    return {
        row["path"]: row["classification"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("path"), str)
        and isinstance(row.get("classification"), str)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="workspace to inventory")
    parser.add_argument("--output", required=True, type=Path, help="local JSON output path")
    parser.add_argument(
        "--check",
        action="store_true",
        help="return 1 if any inventory row still needs classification",
    )
    args = parser.parse_args()

    try:
        root = args.root.resolve(strict=True)
        output = args.output.resolve()
        if output == root or root in output.parents:
            raise ValueError("inventory output must be outside the workspace root")
        existing = _load_existing_classifications(output)
        rows = inventory_workspace(root, existing)
        output.write_text(json.dumps(rows, indent=2) + "\r\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Workspace inventory: FAIL: {exc}")
        return 1

    unclassified = sum(row["classification"] == "unclassified" for row in rows)
    if args.check and unclassified:
        print(f"Workspace inventory: REVIEW REQUIRED ({unclassified} unclassified entries)")
        return 1

    print(f"Workspace inventory: PASS ({len(rows)} entries; {unclassified} unclassified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

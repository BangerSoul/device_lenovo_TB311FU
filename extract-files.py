#!/usr/bin/env python3
"""Extract and verify TB311FU proprietary files from a supplied firmware dump."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

DEVICE = "TB311FU"
VENDOR = "lenovo"
SHA256_LENGTH = 64
EXPECTED_BLOB_COUNT = 111


def sha256sum(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(value: str, field: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"Unsafe {field} path in proprietary-files.txt: {value!r}")
    return path.as_posix()


class BlobExtractor:
    def __init__(self, dump_dir: str, vendor_out: Optional[str] = None):
        self.device_dir = Path(__file__).resolve().parent
        self.repo_root = self.device_dir.parent.parent.parent
        self.dump_dir = Path(dump_dir).resolve()
        self.vendor_out = (
            Path(vendor_out).resolve()
            if vendor_out
            else self.repo_root / "vendor" / VENDOR / DEVICE
        )
        self.prop_files_txt = self.device_dir / "proprietary-files.txt"

    def parse_blob_list(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        seen_destinations = set()
        if not self.prop_files_txt.is_file():
            raise FileNotFoundError(f"Missing proprietary-files.txt at {self.prop_files_txt}")

        with self.prop_files_txt.open("r", encoding="utf-8") as stream:
            for line_number, raw_line in enumerate(stream, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                is_module = line.startswith("-")
                if is_module:
                    line = line[1:].strip()

                expected_sha256 = None
                if "|" in line:
                    line, expected_sha256 = line.rsplit("|", 1)
                    expected_sha256 = expected_sha256.strip().lower()
                    if len(expected_sha256) != SHA256_LENGTH or any(
                        char not in "0123456789abcdef" for char in expected_sha256
                    ):
                        raise ValueError(
                            f"Line {line_number}: expected a 64-character SHA-256 digest"
                        )
                else:
                    raise ValueError(
                        f"Line {line_number}: missing the required SHA-256 digest"
                    )

                if ":" in line:
                    src_path, dest_path = line.split(":", 1)
                else:
                    src_path = dest_path = line

                src_path = safe_relative_path(src_path.strip(), "source")
                dest_path = safe_relative_path(dest_path.strip(), "destination")
                if dest_path in seen_destinations:
                    raise ValueError(
                        f"Line {line_number}: duplicate destination path {dest_path!r}"
                    )
                seen_destinations.add(dest_path)
                entries.append(
                    {
                        "src": src_path,
                        "dest": dest_path,
                        "is_module": is_module,
                        "sha256": expected_sha256,
                    }
                )

        if not entries:
            raise ValueError("proprietary-files.txt contains no blob entries")
        if len(entries) != EXPECTED_BLOB_COUNT:
            raise ValueError(
                f"Expected {EXPECTED_BLOB_COUNT} TB311FU blobs, found {len(entries)}"
            )
        return entries

    def locate_dump_file(self, relative_path: str) -> Optional[Path]:
        candidates = (
            self.dump_dir / relative_path,
            self.dump_dir / "partitions" / relative_path,
        )
        for candidate in candidates:
            if candidate.is_file():
                resolved = candidate.resolve()
                try:
                    resolved.relative_to(self.dump_dir)
                except ValueError:
                    continue
                return resolved
        return None

    def extract_from_dump(self, entries: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        sources: List[Tuple[Dict[str, Any], Path]] = []
        failures: List[str] = []

        for entry in entries:
            source = self.locate_dump_file(entry["src"])
            if source is None:
                failures.append(f"missing: {entry['src']}")
                continue
            actual = sha256sum(source)
            if actual != entry["sha256"]:
                failures.append(
                    f"SHA-256 mismatch: {entry['src']} "
                    f"(expected {entry['sha256']}, got {actual})"
                )
                continue
            sources.append((entry, source))

        if failures:
            return 0, failures

        self.vendor_out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".TB311FU-proprietary-", dir=self.vendor_out.parent
        ) as temporary_directory:
            temporary_root = Path(temporary_directory)
            staged_proprietary = temporary_root / "proprietary"
            staged_proprietary.mkdir()

            for entry, source in sources:
                destination = staged_proprietary / entry["dest"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

            target_proprietary = self.vendor_out / "proprietary"
            backup = temporary_root / "previous-proprietary"
            had_previous = target_proprietary.exists()
            try:
                if had_previous:
                    os.replace(target_proprietary, backup)
                os.replace(staged_proprietary, target_proprietary)
            except Exception:
                if had_previous and backup.exists() and not target_proprietary.exists():
                    os.replace(backup, target_proprietary)
                raise

        return len(sources), []

    def run(self) -> None:
        print(f"[*] Extracting proprietary blobs for {VENDOR}/{DEVICE}...")
        entries = self.parse_blob_list()
        print(f"[*] Indexed proprietary blobs: {len(entries)}")

        extracted, failures = self.extract_from_dump(entries)
        if failures:
            print(f"[ERROR] Refusing partial extraction ({len(failures)} input errors):")
            for failure in failures:
                print(f"  - {failure}")
            raise SystemExit(1)

        print(f"[*] Verified and extracted {extracted} blobs.")
        setup_script = self.device_dir / "setup-makefiles.py"
        if setup_script.is_file():
            subprocess.run([sys.executable, str(setup_script)], check=True)
        print("[OK] Extraction completed with every source hash verified.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract verified TB311FU proprietary files from a firmware dump"
    )
    parser.add_argument(
        "--dump-dir",
        "-d",
        required=True,
        help="Root of an extracted firmware dump, including vendor/system_ext/product/odm",
    )
    parser.add_argument(
        "--vendor-out",
        help="Output vendor/lenovo/TB311FU directory (defaults to the Android checkout)",
    )
    args = parser.parse_args()
    BlobExtractor(dump_dir=args.dump_dir, vendor_out=args.vendor_out).run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
patch_ramdisk_verity.py - Patches fstab in boot/vendor_boot ramdisk.

Removes:
  - avb (e.g. avb, avb=vbmeta, avb=vbmeta_system, avb=vbmeta_vendor)
  - avb_keys (e.g. avb_keys=/avb/q-gsi.avbpubkey:...)
  - verify (e.g. verify, verify=/path, verify_at_boot)

Converts:
  - forceencrypt=... -> encryptable=...
  - forceencrypt     -> encryptable
  - forcefde=...     -> encryptable=...

Preserves:
  - All mount flags and options
  - Comments (# ...)
  - Blank lines and whitespace column formatting
"""

import argparse
import difflib
import os
from pathlib import Path
import re
import shutil
import sys
from typing import List, Optional, Tuple


def is_avb_flag(flag: str) -> bool:
    """Return True if flag matches avb, avb=..., avb_keys, avb_keys=..."""
    return bool(
        re.match(r"^(avb|avb=.*|avb_keys|avb_keys=.*)$", flag, re.IGNORECASE)
    )


def is_verify_flag(flag: str) -> bool:
    """Return True if flag matches verify, verify=..., verify_at_boot"""
    return bool(
        re.match(r"^(verify|verify=.*|verify_at_boot)$", flag, re.IGNORECASE)
    )


def convert_flag(flag: str) -> Tuple[str, bool]:
    """Convert forceencrypt / forcefde to encryptable."""
    m_enc = re.match(r"^forceencrypt=(.*)$", flag, re.IGNORECASE)
    if m_enc:
        return f"encryptable={m_enc.group(1)}", True
    if flag.lower() == "forceencrypt":
        return "encryptable", True
    m_fde = re.match(r"^forcefde=(.*)$", flag, re.IGNORECASE)
    if m_fde:
        return f"encryptable={m_fde.group(1)}", True
    return flag, False


def filter_flags(flags_str: str) -> Tuple[str, int]:
    """
    Process comma-separated flags string.
    Removes avb, avb_keys, verify.
    Converts forceencrypt -> encryptable.
    Returns (new_flags_str, change_count).
    """
    if not flags_str or flags_str == "defaults":
        return flags_str, 0

    tokens = [t.strip() for t in flags_str.split(",") if t.strip()]
    new_tokens: List[str] = []
    changes = 0

    for token in tokens:
        if is_avb_flag(token):
            changes += 1
            continue
        if is_verify_flag(token):
            changes += 1
            continue
        converted, was_converted = convert_flag(token)
        if was_converted:
            changes += 1
            new_tokens.append(converted)
        else:
            new_tokens.append(token)

    if not new_tokens:
        return "defaults", changes
    return ",".join(new_tokens), changes


def patch_fstab_line(line: str) -> Tuple[str, int]:
    """
    Patch a single line of an fstab file.
    Preserves comments and whitespace.
    Returns (patched_line, number_of_changes).
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return line, 0

    # Split keeping whitespace delimiters
    parts = re.split(r"(\s+)", line)
    # Even indices (0, 2, 4, 6, 8, ...) are non-whitespace column values.
    non_ws_indices = [
        i for i in range(len(parts)) if i % 2 == 0 and parts[i]
    ]
    if len(non_ws_indices) < 4:
        return line, 0

    total_changes = 0

    # Check 5th column (fs_mgr_flags) if present
    if len(non_ws_indices) >= 5:
        idx5 = non_ws_indices[4]
        new_val, changes = filter_flags(parts[idx5])
        if changes > 0:
            parts[idx5] = new_val
            total_changes += changes

    # Check 4th column (mount_flags) in case verify / forceencrypt is placed there
    idx4 = non_ws_indices[3]
    new_val, changes = filter_flags(parts[idx4])
    if changes > 0:
        parts[idx4] = new_val
        total_changes += changes

    return "".join(parts), total_changes


def patch_fstab_content(content: str) -> Tuple[str, int]:
    """
    Patch entire fstab file content string.
    Returns (patched_content, total_changes).
    """
    lines = content.splitlines(keepends=True)
    patched_lines = []
    total_changes = 0

    for line in lines:
        patched, changes = patch_fstab_line(line)
        patched_lines.append(patched)
        total_changes += changes

    return "".join(patched_lines), total_changes


def patch_fstab_file(
    file_path: str,
    backup: bool = False,
    output_path: Optional[str] = None,
    show_diff: bool = False,
) -> int:
    """
    Patch an fstab file.
    Returns number of changes made.
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        original = f.read()

    patched, changes = patch_fstab_content(original)

    if show_diff and changes > 0:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{p.name}",
            tofile=f"b/{p.name}",
        )
        print("".join(diff), end="")

    if backup and changes > 0:
        shutil.copy2(file_path, f"{file_path}.bak")

    dest = output_path if output_path else file_path
    if changes > 0 or output_path:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(patched)

    return changes


def is_fstab_filename(name: str) -> bool:
    """Check if filename matches typical fstab naming conventions."""
    name_lower = name.lower()
    return (
        name_lower == "fstab"
        or name_lower.startswith("fstab.")
        or name_lower.endswith(".fstab")
    )


def find_fstab_files(directory: str) -> List[Path]:
    """Recursively discover fstab files in a directory tree."""
    results = []
    for root, _, files in os.walk(directory):
        for f in files:
            if is_fstab_filename(f):
                results.append(Path(root) / f)
    return results


def patch_ramdisk_directory(
    dir_path: str,
    backup: bool = False,
    show_diff: bool = False,
) -> List[Tuple[str, int]]:
    """
    Recursively find and patch all fstab files in a ramdisk directory.
    Returns list of (filepath, changes_count).
    """
    p = Path(dir_path)
    if not p.is_dir():
        raise NotADirectoryError(f"Directory not found: {dir_path}")

    fstab_files = find_fstab_files(dir_path)
    summary = []
    for f in fstab_files:
        changes = patch_fstab_file(
            str(f), backup=backup, show_diff=show_diff
        )
        summary.append((str(f), changes))
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Patch fstab in ramdisk to remove AVB/verity and convert forceencrypt to encryptable."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Path(s) to fstab file(s) or ramdisk director(ies)",
    )
    parser.add_argument(
        "-b",
        "--backup",
        action="store_true",
        help="Create .bak backup copies of modified files",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output file path (only valid with single target file)",
    )
    parser.add_argument(
        "-d",
        "--diff",
        action="store_true",
        help="Show unified diff of changes made",
    )

    args = parser.parse_args(argv)

    if not args.targets:
        parser.print_help()
        print("\nError: No fstab files or ramdisk directories specified.", file=sys.stderr)
        return 1

    if args.output and len(args.targets) > 1:
        print("Error: --output can only be used with a single file target.", file=sys.stderr)
        return 1

    total_files_patched = 0
    total_modifications = 0

    for target in args.targets:
        p = Path(target)
        if p.is_file():
            try:
                changes = patch_fstab_file(
                    target,
                    backup=args.backup,
                    output_path=args.output,
                    show_diff=args.diff,
                )
                dest = args.output if args.output else target
                print(f"[patch_ramdisk_verity] {dest}: {changes} modification(s) applied.")
                if changes > 0:
                    total_files_patched += 1
                    total_modifications += changes
            except Exception as e:
                print(f"[patch_ramdisk_verity] Error processing file {target}: {e}", file=sys.stderr)
                return 1
        elif p.is_dir():
            if args.output:
                print("Error: --output cannot be used with directory targets.", file=sys.stderr)
                return 1
            print(f"[patch_ramdisk_verity] Scanning directory: {target}")
            results = patch_ramdisk_directory(
                target, backup=args.backup, show_diff=args.diff
            )
            if not results:
                print(f"[patch_ramdisk_verity] No fstab files found under {target}")
            for fpath, changes in results:
                print(f"[patch_ramdisk_verity] {fpath}: {changes} modification(s) applied.")
                if changes > 0:
                    total_files_patched += 1
                    total_modifications += changes
        else:
            print(f"Error: Target path does not exist: {target}", file=sys.stderr)
            return 1

    print(
        f"[patch_ramdisk_verity] Complete: {total_files_patched} file(s) patched with {total_modifications} change(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

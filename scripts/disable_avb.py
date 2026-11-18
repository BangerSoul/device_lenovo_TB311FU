#!/usr/bin/env python3
"""
disable_avb.py - AVB 2.0 / dm-verity disabler utility for Android vbmeta images.

Patches vbmeta images (vbmeta.img, vbmeta_system.img, vbmeta_vendor.img)
to disable AVB verification and hashtree verification by setting flags |= 3
at offset 120 in the AVB descriptor header.

AVB Header Reference (AOSP external/avb/libavb/avb_vbmeta_image.h):
  - Offset 0   (4 bytes): Magic "AVB0"
  - Offset 120 (4 bytes): uint32 flags in network byte order (Big-Endian)
    - Bit 0 (0x01): AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED
    - Bit 1 (0x02): AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED
    - Combined flag: 0x03
"""

import argparse
import os
from pathlib import Path
import struct
import sys
from typing import List, Optional, Tuple

AVB_MAGIC = b"AVB0"
AVB_MAGIC_LEN = 4
AVB_HEADER_SIZE = 256
AVB_FLAGS_OFFSET = 120

AVB_FOOTER_MAGIC = b"AVBf"
AVB_FOOTER_SIZE = 64

# AVB 2.0 flags
AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED = 1 << 0  # 0x01
AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED = 1 << 1  # 0x02
DEFAULT_DISABLE_FLAGS = (
    AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED
    | AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED
)  # 0x03


def describe_flags(flags: int) -> str:
    """Return human-readable representation of AVB vbmeta flags."""
    parts = []
    if flags & AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED:
        parts.append("HASHTREE_DISABLED(0x1)")
    if flags & AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED:
        parts.append("VERIFICATION_DISABLED(0x2)")
    if not parts:
        parts.append("NONE(0x0)")
    other = flags & ~(
        AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED
        | AVB_VBMETA_IMAGE_FLAGS_VERIFICATION_DISABLED
    )
    if other:
        parts.append(f"RESERVED(0x{other:x})")
    return " | ".join(parts)


def find_vbmeta_header_offset(data: bytes) -> Optional[int]:
    """
    Locate the AVB0 header offset in image data.
    Checks offset 0 first, then checks for AVB footer in the trailing 64 bytes.
    """
    if len(data) >= AVB_MAGIC_LEN and data[:AVB_MAGIC_LEN] == AVB_MAGIC:
        return 0

    if len(data) >= AVB_FOOTER_SIZE:
        footer = data[-AVB_FOOTER_SIZE:]
        if footer[:4] == AVB_FOOTER_MAGIC:
            # vbmeta_offset is uint64 big-endian at offset 24 in the footer
            vbmeta_offset = struct.unpack(">Q", footer[24:32])[0]
            if (
                len(data) >= vbmeta_offset + AVB_MAGIC_LEN
                and data[vbmeta_offset : vbmeta_offset + AVB_MAGIC_LEN]
                == AVB_MAGIC
            ):
                return vbmeta_offset

    return None


def read_vbmeta_header(image_path: str) -> Tuple[int, int, bytes]:
    """
    Read (flags, header_offset, full_header_bytes) from vbmeta image.
    Raises ValueError or FileNotFoundError if invalid.
    """
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {image_path}")

    size = p.stat().st_size
    if size < AVB_FLAGS_OFFSET + 4:
        raise ValueError(
            f"File {image_path} too small ({size} bytes) for AVB header"
        )

    with open(image_path, "rb") as f:
        data = f.read()

    offset = find_vbmeta_header_offset(data)
    if offset is None:
        raise ValueError(
            f"File {image_path} does not contain valid AVB0 header or AVB footer"
        )

    flags_pos = offset + AVB_FLAGS_OFFSET
    if len(data) < flags_pos + 4:
        raise ValueError(
            f"File {image_path} truncated before flags offset {flags_pos}"
        )

    flags = struct.unpack(">I", data[flags_pos : flags_pos + 4])[0]
    header = data[offset : offset + AVB_HEADER_SIZE]
    return flags, offset, header


def patch_vbmeta_data(
    data: bytearray, flags_to_set: int = DEFAULT_DISABLE_FLAGS
) -> Tuple[int, int, int]:
    """
    Patch AVB header in bytearray buffer in-memory.
    Returns (old_flags, new_flags, header_offset).
    """
    if len(data) < AVB_FLAGS_OFFSET + 4:
        raise ValueError("Buffer too small for AVB header")

    offset = find_vbmeta_header_offset(bytes(data))
    if offset is None:
        raise ValueError("No valid AVB0 header or footer found")

    flags_pos = offset + AVB_FLAGS_OFFSET
    if len(data) < flags_pos + 4:
        raise ValueError(f"Buffer truncated before flags offset {flags_pos}")

    old_flags = struct.unpack(">I", data[flags_pos : flags_pos + 4])[0]
    new_flags = old_flags | flags_to_set

    struct.pack_into(">I", data, flags_pos, new_flags)
    return old_flags, new_flags, offset


def patch_vbmeta_file(
    image_path: str,
    flags_to_set: int = DEFAULT_DISABLE_FLAGS,
    output_path: Optional[str] = None,
) -> Tuple[int, int, int]:
    """
    Patch vbmeta file by setting flags |= flags_to_set at offset 120.
    Returns (old_flags, new_flags, header_offset).
    """
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with open(image_path, "rb") as f:
        data = bytearray(f.read())

    old_flags, new_flags, offset = patch_vbmeta_data(data, flags_to_set)

    target_path = output_path if output_path else image_path
    with open(target_path, "wb") as f:
        f.write(data)

    return old_flags, new_flags, offset


def create_empty_vbmeta(
    output_path: str,
    size: int = 4096,
    flags: int = DEFAULT_DISABLE_FLAGS,
) -> None:
    """
    Create a minimal valid AVB 2.0 vbmeta image with specified flags.
    Default size is 4096 bytes (standard vbmeta partition sector block).
    """
    buf = bytearray(size)
    # Magic "AVB0"
    buf[0:4] = AVB_MAGIC
    # Major version: 1
    struct.pack_into(">I", buf, 4, 1)
    # Minor version: 0
    struct.pack_into(">I", buf, 8, 0)
    # Auth block size: 0
    struct.pack_into(">Q", buf, 12, 0)
    # Aux block size: 0
    struct.pack_into(">Q", buf, 20, 0)
    # Algorithm type: AVB_ALGORITHM_TYPE_NONE (0)
    struct.pack_into(">I", buf, 28, 0)
    # Flags at offset 120
    struct.pack_into(">I", buf, AVB_FLAGS_OFFSET, flags)
    # Release string at offset 128 (48 bytes max)
    release_str = b"avbtool 1.2.0 (TB311FU disable_avb)\x00"
    buf[128 : 128 + len(release_str)] = release_str

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(buf)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Disable AVB / dm-verity in vbmeta images by setting flags |= 3 at offset 120."
    )
    parser.add_argument(
        "images",
        nargs="*",
        help="Path(s) to vbmeta image(s) to patch (e.g. vbmeta.img vbmeta_system.img vbmeta_vendor.img)",
    )
    parser.add_argument(
        "--flags",
        type=lambda x: int(x, 0),
        default=DEFAULT_DISABLE_FLAGS,
        help="Flags to bitwise-OR into header offset 120 (default: 0x03 = HASHTREE_DISABLED | VERIFICATION_DISABLED)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check and display current AVB flags without modifying files",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Optional output path (only valid when patching a single image)",
    )
    parser.add_argument(
        "--create",
        type=str,
        default=None,
        metavar="PATH",
        help="Create a minimal valid AVB0 disabled vbmeta.img at the specified path",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=4096,
        help="Size in bytes for --create (default: 4096)",
    )

    args = parser.parse_args(argv)

    if args.create:
        print(f"[disable_avb] Creating empty disabled vbmeta: {args.create} (size={args.size}, flags=0x{args.flags:08x})")
        create_empty_vbmeta(args.create, size=args.size, flags=args.flags)
        print(f"[disable_avb] Successfully created: {args.create} [{describe_flags(args.flags)}]")
        return 0

    target_images = list(args.images)

    # If no images provided, check standard filenames in current working directory
    if not target_images:
        defaults = ["vbmeta.img", "vbmeta_system.img", "vbmeta_vendor.img"]
        found = [f for f in defaults if os.path.isfile(f)]
        if found:
            print(f"[disable_avb] No images specified, discovered in current directory: {', '.join(found)}")
            target_images = found
        else:
            parser.print_help()
            print("\nError: No vbmeta images specified and default files not found in working directory.", file=sys.stderr)
            return 1

    if args.output and len(target_images) > 1:
        print("Error: --output can only be used with a single target image.", file=sys.stderr)
        return 1

    has_errors = False
    for img in target_images:
        try:
            if args.check:
                flags, offset, _ = read_vbmeta_header(img)
                print(f"[disable_avb] Check {img} (header at offset {offset}): flags=0x{flags:08x} [{describe_flags(flags)}]")
            else:
                out = args.output if (args.output and len(target_images) == 1) else None
                old_flags, new_flags, offset = patch_vbmeta_file(
                    img, flags_to_set=args.flags, output_path=out
                )
                dest = out if out else img
                print(
                    f"[disable_avb] Patched {dest} (header offset {offset}): "
                    f"0x{old_flags:08x} [{describe_flags(old_flags)}] -> "
                    f"0x{new_flags:08x} [{describe_flags(new_flags)}] [SUCCESS]"
                )
        except Exception as e:
            print(f"[disable_avb] Error processing {img}: {e}", file=sys.stderr)
            has_errors = True

    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())

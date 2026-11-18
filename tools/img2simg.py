#!/usr/bin/env python3
"""
tools/img2simg.py - Standalone Android Sparse Image Converter
Converts raw filesystem images (EXT4, EROFS, etc.) into Android sparse format.
Spec: Android sparse image format v1.0
Magic: 0xED26FF3A
"""

import os
import struct
import sys

SPARSE_HEADER_MAGIC = 0xED26FF3A
MAJOR_VERSION = 1
MINOR_VERSION = 0
FILE_HDR_SIZE = 28
CHUNK_HDR_SIZE = 12
BLOCK_SIZE = 4096

CHUNK_TYPE_RAW = 0xCAC1
CHUNK_TYPE_FILL = 0xCAC2
CHUNK_TYPE_DONT_CARE = 0xCAC3
CHUNK_TYPE_CRC32 = 0xCAC4


def is_all_zero(buf: bytes) -> bool:
    return not any(buf)


def convert_raw_to_sparse(in_path: str, out_path: str, block_size: int = BLOCK_SIZE) -> None:
    file_size = os.path.getsize(in_path)
    if file_size % block_size != 0:
        total_blocks = (file_size + block_size - 1) // block_size
    else:
        total_blocks = file_size // block_size

    # Check if already sparse
    with open(in_path, "rb") as f:
        magic = f.read(4)
        if len(magic) == 4 and struct.unpack("<I", magic)[0] == SPARSE_HEADER_MAGIC:
            print(f"[*] Input '{in_path}' is already an Android sparse image.")
            if in_path != out_path:
                with open(out_path, "wb") as out_f:
                    f.seek(0)
                    while chunk := f.read(1024 * 1024):
                        out_f.write(chunk)
            return

    # First pass: collect chunks
    chunks = []
    current_type = None
    current_blocks = 0
    raw_start_offset = 0

    with open(in_path, "rb") as f:
        for blk_idx in range(total_blocks):
            buf = f.read(block_size)
            if not buf:
                break
            if len(buf) < block_size:
                buf = buf + b"\x00" * (block_size - len(buf))

            if is_all_zero(buf):
                blk_type = CHUNK_TYPE_DONT_CARE
            else:
                blk_type = CHUNK_TYPE_RAW

            if current_type is None:
                current_type = blk_type
                current_blocks = 1
                raw_start_offset = blk_idx * block_size
            elif current_type == blk_type:
                current_blocks += 1
            else:
                chunks.append((current_type, current_blocks, raw_start_offset))
                current_type = blk_type
                current_blocks = 1
                raw_start_offset = blk_idx * block_size

        if current_type is not None:
            chunks.append((current_type, current_blocks, raw_start_offset))

    total_chunks = len(chunks)
    image_checksum = 0

    header = struct.pack(
        "<IHHHHIIII",
        SPARSE_HEADER_MAGIC,
        MAJOR_VERSION,
        MINOR_VERSION,
        FILE_HDR_SIZE,
        CHUNK_HDR_SIZE,
        block_size,
        total_blocks,
        total_chunks,
        image_checksum,
    )

    with open(in_path, "rb") as in_f, open(out_path, "wb") as out_f:
        out_f.write(header)

        for chunk_type, num_blocks, file_offset in chunks:
            if chunk_type == CHUNK_TYPE_DONT_CARE:
                total_sz = CHUNK_HDR_SIZE
                chunk_header = struct.pack("<HHII", chunk_type, 0, num_blocks, total_sz)
                out_f.write(chunk_header)
            elif chunk_type == CHUNK_TYPE_RAW:
                data_size = num_blocks * block_size
                total_sz = CHUNK_HDR_SIZE + data_size
                chunk_header = struct.pack("<HHII", chunk_type, 0, num_blocks, total_sz)
                out_f.write(chunk_header)
                in_f.seek(file_offset)
                remaining = data_size
                while remaining > 0:
                    read_len = min(remaining, 1024 * 1024)
                    data = in_f.read(read_len)
                    out_f.write(data)
                    remaining -= len(data)

    in_sz = os.path.getsize(in_path)
    out_sz = os.path.getsize(out_path)
    ratio = (1.0 - (out_sz / in_sz)) * 100 if in_sz > 0 else 0
    print(f"[+] Sparse conversion complete: {in_sz:,} B -> {out_sz:,} B ({ratio:.1f}% space saved)")


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input_raw.img> <output_sparse.img>")
        sys.exit(1)
    convert_raw_to_sparse(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()

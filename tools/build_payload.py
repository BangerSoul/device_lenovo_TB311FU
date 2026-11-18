#!/usr/bin/env bash
#!/usr/bin/env python3
"""
tools/build_payload.py - Android A/B OTA Payload (payload.bin) Builder & Signer
Builds a standard Android v2 A/B update payload (CrAU) and payload_properties.txt.
Compatible with Google update_engine, LineageOS OTA, and recovery clients.
"""

import argparse
import base64
import hashlib
import os
import struct
import subprocess
import sys
from typing import Dict, List, Tuple

# Import protobuf update_metadata
try:
    from tools import update_metadata_pb2
except ImportError:
    import update_metadata_pb2

PAYLOAD_MAGIC = b"CrAU"
PAYLOAD_VERSION = 2
BLOCK_SIZE = 4096


def sign_data_with_openssl(key_path: str, data: bytes) -> bytes:
    """Signs data using OpenSSL RSA-SHA256."""
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", key_path],
        input=data,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def ensure_private_key(key_path: str) -> str:
    """Ensures an RSA private key exists, generating a test key if absent."""
    if not os.path.exists(key_path):
        os.makedirs(os.path.dirname(os.path.abspath(key_path)), exist_ok=True)
        print(f"[*] Generating 2048-bit RSA test key at '{key_path}'...")
        subprocess.run(
            ["openssl", "genrsa", "-out", key_path, "2048"],
            check=True,
            capture_output=True,
        )
    return key_path


def build_payload(
    partitions: Dict[str, str],
    key_path: str,
    output_payload_path: str,
    output_properties_path: str,
) -> None:
    ensure_private_key(key_path)

    manifest = update_metadata_pb2.DeltaArchiveManifest()
    manifest.block_size = BLOCK_SIZE

    # We will buffer partition blob metadata and offsets
    data_blob_offset = 0
    partition_blobs: List[Tuple[str, str, int, bytes]] = []

    for part_name, img_path in partitions.items():
        if not os.path.exists(img_path):
            raise FileNotFoundError(f"Partition image for '{part_name}' not found: {img_path}")

        file_size = os.path.getsize(img_path)
        with open(img_path, "rb") as f:
            h = hashlib.sha256()
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
            img_hash = h.digest()

        num_blocks = (file_size + BLOCK_SIZE - 1) // BLOCK_SIZE

        part_update = manifest.partitions.add()
        part_update.partition_name = part_name
        part_update.new_partition_info.size = file_size
        part_update.new_partition_info.hash = img_hash

        op = part_update.operations.add()
        op.type = update_metadata_pb2.InstallOperation.REPLACE
        op.data_offset = data_blob_offset
        op.data_length = file_size
        op.data_sha256_hash = img_hash

        extent = op.dst_extents.add()
        extent.start_block = 0
        extent.num_blocks = num_blocks

        partition_blobs.append((part_name, img_path, file_size, img_hash))
        data_blob_offset += file_size

    # Prepare signature placeholder to determine signatures_offset & signatures_size
    dummy_signatures = update_metadata_pb2.Signatures()
    sig_entry = dummy_signatures.signatures.add()
    sig_entry.version = 1
    sig_entry.data = b"\x00" * 256  # 2048-bit RSA signature is 256 bytes
    expected_sig_size = dummy_signatures.ByteSize()

    manifest.signatures_offset = data_blob_offset
    manifest.signatures_size = expected_sig_size

    # Serialize manifest
    manifest_bytes = manifest.SerializeToString()
    manifest_size = len(manifest_bytes)

    # Temporary header without metadata_signature_size
    header_prefix = (
        PAYLOAD_MAGIC
        + struct.pack(">Q", PAYLOAD_VERSION)
        + struct.pack(">Q", manifest_size)
    )

    # Determine metadata signature
    # Compute signature over header_prefix (20 bytes) + placeholder 4-byte uint32 + manifest_bytes
    # In Android v2: metadata signature signs header (24 bytes) + manifest_bytes
    header_dummy = header_prefix + struct.pack(">I", expected_sig_size)
    meta_sig_data = sign_data_with_openssl(key_path, header_dummy + manifest_bytes)

    meta_signatures = update_metadata_pb2.Signatures()
    m_sig = meta_signatures.signatures.add()
    m_sig.version = 1
    m_sig.data = meta_sig_data
    meta_sig_bytes = meta_signatures.SerializeToString()
    meta_sig_size = len(meta_sig_bytes)

    # Re-sign with exact meta_sig_size in header
    final_header = header_prefix + struct.pack(">I", meta_sig_size)
    meta_sig_data = sign_data_with_openssl(key_path, final_header + manifest_bytes)
    meta_signatures.signatures[0].data = meta_sig_data
    meta_sig_bytes = meta_signatures.SerializeToString()

    metadata_total_size = len(final_header) + len(manifest_bytes) + len(meta_sig_bytes)
    metadata_bytes = final_header + manifest_bytes + meta_sig_bytes
    metadata_hash = hashlib.sha256(metadata_bytes).digest()

    print(f"[*] Metadata size: {metadata_total_size} bytes (Header: 24, Manifest: {manifest_size}, MetaSig: {len(meta_sig_bytes)})")
    print(f"[*] Writing payload to '{output_payload_path}'...")

    os.makedirs(os.path.dirname(os.path.abspath(output_payload_path)), exist_ok=True)
    payload_hash = hashlib.sha256()

    with open(output_payload_path, "wb") as out_f:
        # Write metadata
        out_f.write(metadata_bytes)
        payload_hash.update(metadata_bytes)

        # Write partition data blobs
        for part_name, img_path, file_size, _ in partition_blobs:
            print(f"    Writing partition '{part_name}' ({file_size:,} bytes)...")
            with open(img_path, "rb") as in_f:
                while chunk := in_f.read(1024 * 1024):
                    out_f.write(chunk)
                    payload_hash.update(chunk)

        # Compute payload signature over all bytes up to signatures
        payload_digest = payload_hash.digest()
        payload_sig_data = sign_data_with_openssl(key_path, payload_digest)

        payload_signatures = update_metadata_pb2.Signatures()
        p_sig = payload_signatures.signatures.add()
        p_sig.version = 1
        p_sig.data = payload_sig_data
        payload_sig_bytes = payload_signatures.SerializeToString()

        out_f.write(payload_sig_bytes)

    # Compute final full file hash
    total_file_size = os.path.getsize(output_payload_path)
    full_file_hash = hashlib.sha256()
    with open(output_payload_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            full_file_hash.update(chunk)
    final_file_hash = full_file_hash.digest()

    file_hash_b64 = base64.b64encode(final_file_hash).decode("ascii")
    meta_hash_b64 = base64.b64encode(metadata_hash).decode("ascii")

    # Write payload_properties.txt
    print(f"[*] Writing properties to '{output_properties_path}'...")
    os.makedirs(os.path.dirname(os.path.abspath(output_properties_path)), exist_ok=True)
    with open(output_properties_path, "w", encoding="utf-8") as pf:
        pf.write(f"FILE_HASH={file_hash_b64}\n")
        pf.write(f"FILE_SIZE={total_file_size}\n")
        pf.write(f"METADATA_HASH={meta_hash_b64}\n")
        pf.write(f"METADATA_SIZE={metadata_total_size}\n")

    print("[+] Android A/B OTA Payload and Properties built successfully!")
    print(f"    FILE_HASH:     {file_hash_b64}")
    print(f"    FILE_SIZE:     {total_file_size:,} bytes")
    print(f"    METADATA_HASH: {meta_hash_b64}")
    print(f"    METADATA_SIZE: {metadata_total_size} bytes")


def main():
    parser = argparse.ArgumentParser(description="Build Android A/B payload.bin and payload_properties.txt")
    parser.add_argument("--partitions", nargs="+", required=True, help="name=path pairs (e.g. boot=boot.img)")
    parser.add_argument("--key", required=True, help="Path to RSA private key (.pem or .key)")
    parser.add_argument("--out-payload", default="payload.bin", help="Output payload.bin path")
    parser.add_argument("--out-properties", default="payload_properties.txt", help="Output payload_properties.txt path")

    args = parser.parse_args()

    parts = {}
    for item in args.partitions:
        if "=" not in item:
            raise ValueError(f"Invalid partition argument '{item}', expected name=path")
        k, v = item.split("=", 1)
        parts[k.strip()] = v.strip()

    build_payload(parts, args.key, args.out_payload, args.out_properties)


if __name__ == "__main__":
    main()

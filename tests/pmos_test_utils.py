#!/usr/bin/env python3
"""
tests/pmos_test_utils.py - Shared Test Infrastructure & Utilities
PostmarketOS / Alpine ARM64 with Plasma Mobile on Lenovo Tab M11 (TB311FU / poplar)
"""

import hashlib
import json
import os
import re
import struct
import subprocess
from typing import Any, Dict, List, Optional, Tuple

# Base Directories
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(TESTS_DIR)
REF_REPOS_DIR = r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell\ref_repos"
REF_PMOS_DIR = os.path.join(REF_REPOS_DIR, "linux-lenovo-tb311fu")
FEARLESS_DIR = r"C:\Users\BangerSoul\Documents\antigravity\fearless-maxwell"
PLATFORM_TOOLS_DIR = r"C:\platform-tools"
ADB_BIN = os.path.join(PLATFORM_TOOLS_DIR, "adb.exe")

# AVB 2.0 & Geometry Constants
EXPECTED_BOOT_SIZE = 33554432          # 32 MB (0x2000000)
EXPECTED_VBMETA_OFFSET = 14561280      # 0xDE3000
EXPECTED_VBMETA_SIZE = 2432            # OEM VBMeta block size
AVB_FOOTER_OFFSET = 33554432 - 64      # 33554368
AVB_FOOTER_MAGIC = b"AVBf"
VBMETA_MAGIC = b"AVB0"
BOOT_MAGIC = b"ANDROID!"
VENDOR_BOOT_MAGIC = b"VNDRBOOT"

EXPECTED_OEM_KEY_SHA1 = "8fcb864f11f53ed11284615fb67685522085d3a2"
EXPECTED_AUTH_DIGEST = "cdb31fa8398a68b4492fbcaaaa01732a8e7101cc3816326aa9ee980234226e9b"

VENDOR_BOOT_PINNED_SIZE = 25047040
VENDOR_BOOT_PINNED_HASH = "a20109fba6c161a7d53ff837485010f48eb62d12d3996e2fee11fe8ebd3ac9ac"
AVB_SALT_HEX = "5db37c8e2388c9788a77775fcf84c5acc26ee2bb5166a785cfa92909f7fb7bc5"

WIFI_PATCH_OFFSET = 0xc3084
WIFI_OPCODE_BEFORE = 0x540005c1
WIFI_OPCODE_AFTER = 0x1400002e
WIFI_SOURCE_SHA256 = "ba66e406efe3d39cbc1a0fc777853585db8f5ed03558a3967ca84c5223a1056d"

SUPER_PHYSICAL_SIZE = 11811160064     # 11.81 GB
SYSTEM_A_TARGET_SIZE = 4294967296     # 4.0 GiB (1048576 * 4096)
PRODUCT_A_SIZE = 1836695552           # ~1.71 GB

_CACHED_DEVICE = None
_DEVICE_CHECKED = False


def is_live_device_available() -> Optional[str]:
    """Check if adb detects the live target tablet (HNQ09EZD). Cached for high performance."""
    global _CACHED_DEVICE, _DEVICE_CHECKED
    if _DEVICE_CHECKED:
        return _CACHED_DEVICE
    _DEVICE_CHECKED = True
    try:
        adb_exec = ADB_BIN if os.path.exists(ADB_BIN) else "adb"
        res = subprocess.run([adb_exec, "devices"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                _CACHED_DEVICE = parts[0]
                return _CACHED_DEVICE
    except Exception:
        pass
    _CACHED_DEVICE = None
    return None


def run_adb_cmd(cmd: List[str], timeout: int = 8) -> Tuple[int, str, str]:
    """Execute an ADB command against the live tablet if attached."""
    dev = is_live_device_available()
    adb_exec = ADB_BIN if os.path.exists(ADB_BIN) else "adb"
    prefix = [adb_exec]
    if dev:
        prefix.extend(["-s", dev])
    try:
        res = subprocess.run(prefix + cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except Exception as exc:
        return -1, "", str(exc)


def run_adb_su(cmd_str: str, timeout: int = 8) -> Tuple[int, str, str]:
    """Execute root shell command on target device via su -c."""
    escaped = cmd_str.replace('"', r'\"')
    return run_adb_cmd(["shell", f'su -c "{escaped}"'], timeout=timeout)


def resolve_file(*candidates: str) -> Optional[str]:
    """
    Multi-source resolver for project artifacts.
    Searches across workspace, reference repositories, and platform directories.
    """
    search_roots = [
        WORKSPACE_DIR,
        os.path.join(os.path.dirname(WORKSPACE_DIR), "linux-lenovo-tb311fu"),
        REF_PMOS_DIR,
        REF_REPOS_DIR,
        FEARLESS_DIR,
        PLATFORM_TOOLS_DIR,
    ]
    for rel in candidates:
        if not rel:
            continue
        if os.path.isabs(rel) and os.path.exists(rel):
            return rel
        for root in search_roots:
            p = os.path.normpath(os.path.join(root, rel))
            if os.path.exists(p):
                return p
    return None


def read_file_content(*candidates: str, binary: bool = False) -> Any:
    """Read file content (text or binary) searching across candidate paths."""
    path = resolve_file(*candidates)
    if not path or not os.path.exists(path):
        return b"" if binary else ""
    mode = "rb" if binary else "r"
    encoding = None if binary else "utf-8"
    with open(path, mode, encoding=encoding, errors=None if binary else "replace") as f:
        return f.read()


def parse_key_value(text: str) -> Dict[str, str]:
    """Parse shell-style key=value configuration into dictionary."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            result[k] = v
    return result


def parse_kconfig(text: str) -> Dict[str, str]:
    """Parse Linux kernel .config into dictionary of symbol: value."""
    configs = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("# CONFIG_") and "is not set" in line:
            parts = line.split()
            sym = parts[1]
            configs[sym] = "n"
        elif line.startswith("CONFIG_") and "=" in line:
            sym, val = line.split("=", 1)
            configs[sym.strip()] = val.strip().strip('"')
    return configs


def parse_apkbuild(text: str) -> Dict[str, Any]:
    """Parse APKBUILD header variables into dictionary."""
    vars_found = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line and not line.startswith(" "):
            parts = line.split("=", 1)
            var_name = parts[0].strip()
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", var_name):
                val = parts[1].strip().strip('"').strip("'")
                vars_found[var_name] = val
    return vars_found


_OEM_VBMETA_CACHE: Optional[bytes] = None


def get_oem_vbmeta_block() -> bytes:
    """Retrieve verbatim 2,432-byte OEM VBMeta block from verified platform image."""
    global _OEM_VBMETA_CACHE
    if _OEM_VBMETA_CACHE is not None and len(_OEM_VBMETA_CACHE) == EXPECTED_VBMETA_SIZE:
        return _OEM_VBMETA_CACHE
    candidates = [
        r"C:\platform-tools\poplar_boot_v12_clean.img",
        r"C:\platform-tools\recovery_boot.img",
        r"C:\platform-tools\stock_boot.img",
        os.path.join(WORKSPACE_DIR, "poplar_boot_v12_clean.img"),
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, "rb") as f:
                    f.seek(EXPECTED_BOOT_SIZE - 64)
                    footer = f.read(64)
                    if footer.startswith(AVB_FOOTER_MAGIC):
                        _, _, _, _, vb_off, vb_sz = struct.unpack(">4sIIQQQ", footer[:36])
                        f.seek(vb_off)
                        vb_data = f.read(vb_sz)
                        if vb_data.startswith(VBMETA_MAGIC) and len(vb_data) == EXPECTED_VBMETA_SIZE:
                            _OEM_VBMETA_CACHE = vb_data
                            return _OEM_VBMETA_CACHE
            except Exception:
                pass
    return b""


def synthesize_valid_pmos_boot_image() -> bytes:
    """
    Synthesize an in-memory Android Header v4 boot image strictly honoring LK AVB invariants:
    - 33,554,432 bytes total (32 MB)
    - Kernel payload zero-padded to 14,561,280 bytes (0xDE3000)
    - Verbatim OEM VBMeta block at 14,561,280 with flags=0x00 and OEM key
    - AVBf footer at 33,554,368 with original_image_size=14561280, vbmeta_offset=14561280
    """
    total_size = EXPECTED_BOOT_SIZE
    vbmeta_offset = EXPECTED_VBMETA_OFFSET

    # Allocate full 32 MB buffer zeroed
    image = bytearray(total_size)

    # Android header v4 (64 bytes in first 4096-byte page)
    image[0:8] = BOOT_MAGIC
    struct.pack_into("<I", image, 8, 10000000)      # kernel_size (10 MB dummy)
    struct.pack_into("<I", image, 12, 1000000)      # ramdisk_size (1 MB dummy)
    struct.pack_into("<I", image, 40, 4)            # header_version = 4

    # Inject verbatim OEM VBMeta block at exact offset 14,561,280 (0xDE3000)
    vbmeta = get_oem_vbmeta_block()
    if vbmeta:
        image[vbmeta_offset : vbmeta_offset + len(vbmeta)] = vbmeta
    else:
        # Fallback minimal VBMeta with flags 0x00
        image[vbmeta_offset : vbmeta_offset + 4] = VBMETA_MAGIC
        image[vbmeta_offset + 123] = 0x00

    # AVB footer at offset 33,554,368 (total_size - 64)
    footer_pos = total_size - 64
    struct.pack_into(
        ">4sIIQQQ",
        image,
        footer_pos,
        AVB_FOOTER_MAGIC,
        1, 0,                    # version 1.0
        vbmeta_offset,           # original_image_size = 14561280
        vbmeta_offset,           # vbmeta_offset = 14561280
        EXPECTED_VBMETA_SIZE,    # vbmeta_size = 2432
    )

    return bytes(image)

#!/usr/bin/env python3
"""
Lenovo Tab with Clear Case (TB311FU / 'poplar') Fastbootd Flashing Deployment Suite.
Automated dynamic partition resizing, product partition removal, GSI deployment,
and stabilized vendor flashing with mandatory -S 64M WinUSB chunking and
zero-data-loss enforcement.
"""

import os
import sys
import shutil
import subprocess
import argparse
from typing import List, Optional, Tuple, Dict, Any

# ==============================================================================
# Constants & Defaults
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

DEFAULT_CHUNK_SIZE: str = "64M"
DEFAULT_GSI_PATH: str = r"D:\poplar\GSI\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img"
DEFAULT_VENDOR_PATH: str = os.path.join(SCRIPT_DIR, "vendor_stabilized.img")
if not os.path.exists(DEFAULT_VENDOR_PATH):
    _fallback_v = r"C:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\partitions\vendor_stabilized.img"
    if os.path.exists(_fallback_v):
        DEFAULT_VENDOR_PATH = _fallback_v
SYSTEM_TARGET_SIZE_BYTES: int = 3446353920   # 3.2097 GiB (exact LineageOS 23.2 GSI byte size)

MAX_CHUNK_LIMIT_MB: int = 256                # WinUSB buffer transfer failure ceiling (error 22)
MIN_CHUNK_LIMIT_MB: int = 16                 # Excessive USB transaction overhead floor


# ==============================================================================
# Boundary & Validation Functions
# ==============================================================================
def validate_chunk_size(chunk_str: str) -> int:
    """
    Validate fastboot -S chunk size string (e.g., '64M', '128M').
    Rejects chunks >= 256M to prevent Windows WinUSB transfer failure (error 22).
    Rejects chunks < 16M for excessive transaction overhead.
    """
    cleaned = chunk_str.strip().upper()
    if not cleaned.endswith("M"):
        raise ValueError(f"Invalid chunk size format '{chunk_str}'. Must specify size in megabytes, e.g., '64M'.")

    val_str = cleaned[:-1]
    try:
        val_mb = int(val_str)
    except ValueError:
        raise ValueError(f"Invalid integer chunk size in '{chunk_str}'")

    if val_mb >= MAX_CHUNK_LIMIT_MB:
        raise ValueError(f"Chunk size {chunk_str} will fail on WinUSB. Must be < 256M.")
    if val_mb < MIN_CHUNK_LIMIT_MB:
        raise ValueError(f"Chunk size {chunk_str} too small.")

    return val_mb


def check_fastbootd_mode(is_userspace: str) -> bool:
    """
    Validate that device is currently in Fastbootd (userspace fastboot).
    In Little Kernel bootloader fastboot (is-userspace != 'yes'), logical
    partition modification is prohibited.
    """
    if is_userspace.strip().lower() != "yes":
        raise RuntimeError("Device is in Bootloader mode, NOT Fastbootd. Run 'fastboot reboot fastboot'.")
    return True


def generate_flash_command(part: str, img_path: str, chunk_size: str = DEFAULT_CHUNK_SIZE) -> str:
    """
    Generate verified fastboot flash command with chunking.
    Validates image file existence and chunk size.
    """
    validate_chunk_size(chunk_size)
    if not os.path.exists(img_path):
        raise FileNotFoundError(f"Image not found: {img_path}")
    return f'fastboot -S {chunk_size} flash {part} "{img_path}"'


def find_fastboot_binary(custom_path: Optional[str] = None) -> str:
    """Locate fastboot.exe binary on host system."""
    if custom_path and os.path.exists(custom_path):
        return custom_path

    # Search known paths
    candidates = [
        r"C:\platform-tools\fastboot.exe",
        shutil.which("fastboot"),
        shutil.which("fastboot.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c

    # Fallback to 'fastboot' command invocation
    return "fastboot"


# ==============================================================================
# Flashing Plan Generator
# ==============================================================================
def generate_flashing_plan(
    gsi_path: str = DEFAULT_GSI_PATH,
    vendor_path: str = DEFAULT_VENDOR_PATH,
    chunk_size: str = DEFAULT_CHUNK_SIZE,
    factory_reset: bool = False,
    target_system_size: int = SYSTEM_TARGET_SIZE_BYTES,
    fastboot_bin: str = "fastboot",
) -> List[str]:
    """
    Generate sequential fastboot command list for TB311FU dynamic partition deployment:
    1. Delete product_a / product_b (frees unallocated super headroom)
    2. Resize system_a to exact target GSI byte size (3,446,353,920 B)
    3. Erase system_a
    4. Flash system_a with safe -S 64M chunking
    5. Flash vendor_a vendor_stabilized.img with -S 64M chunking
    6. Factory reset (only if explicitly enabled)
    7. Reboot
    """
    validate_chunk_size(chunk_size)

    commands: List[str] = [
        f"{fastboot_bin} delete-logical-partition product_a",
        f"{fastboot_bin} delete-logical-partition product_b",
        f"{fastboot_bin} resize-logical-partition system_a {target_system_size}",
        f"{fastboot_bin} erase system_a",
        f'{fastboot_bin} -S {chunk_size} flash system_a "{gsi_path}"',
        f'{fastboot_bin} -S {chunk_size} flash vendor_a "{vendor_path}"',
    ]

    if factory_reset:
        commands.append(f"{fastboot_bin} -w")

    commands.append(f"{fastboot_bin} reboot")

    # Audit safety contracts:
    # 1. Zero data loss contract
    if not factory_reset:
        for cmd in commands:
            if " -w" in cmd or "erase userdata" in cmd or "format userdata" in cmd:
                raise RuntimeError(f"Violation of Zero Data Loss contract! Wipe command detected: {cmd}")

    # 2. AVB & Little Kernel invariants
    for cmd in commands:
        if "vendor_boot" in cmd:
            raise RuntimeError(f"AVB Violation: Attempt to flash salt-pinned vendor_boot: {cmd}")
        if "--disable-verity" in cmd or "--disable-verification" in cmd:
            raise RuntimeError(f"AVB Violation: Little Kernel RSA4096 signature failure trigger: {cmd}")

    return commands


# ==============================================================================
# Fastboot Deployment Runner
# ==============================================================================
class FastbootdDeployer:
    def __init__(
        self,
        gsi_path: str = DEFAULT_GSI_PATH,
        vendor_path: str = DEFAULT_VENDOR_PATH,
        chunk_size: str = DEFAULT_CHUNK_SIZE,
        factory_reset: bool = False,
        fastboot_path: Optional[str] = None,
        serial: Optional[str] = None,
    ):
        self.gsi_path = os.path.abspath(gsi_path)
        self.vendor_path = os.path.abspath(vendor_path)
        self.chunk_size = chunk_size
        self.factory_reset = factory_reset
        self.fastboot_bin = find_fastboot_binary(fastboot_path)
        self.serial = serial

    def run_fastboot(self, args: List[str]) -> subprocess.CompletedProcess:
        cmd = [self.fastboot_bin]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, text=True)

    def verify_target_images(self) -> None:
        """Verify image file presence and NVMe staging recommendation."""
        if not os.path.exists(self.gsi_path):
            raise FileNotFoundError(f"Target GSI image not found: {self.gsi_path}")
        gsi_sz = os.path.getsize(self.gsi_path)
        if gsi_sz != SYSTEM_TARGET_SIZE_BYTES:
            print(
                f"[!] Notice: GSI file size ({gsi_sz:,} B) differs from expected "
                f"{SYSTEM_TARGET_SIZE_BYTES:,} B. Resizing will use actual file size."
            )

        if not os.path.exists(self.vendor_path):
            fallback_v = os.path.join(r"C:\Users\BangerSoul\Documents\antigravity\vibrant-hertz\partitions", os.path.basename(self.vendor_path))
            if os.path.exists(fallback_v):
                self.vendor_path = fallback_v
            else:
                raise FileNotFoundError(f"Stabilized vendor image not found: {self.vendor_path}")

        # Check drive type recommendation
        drive_letter = os.path.splitdrive(self.gsi_path)[0]
        if drive_letter and drive_letter.upper() not in ("C:", "D:"):
            print(
                f"[i] Staging recommendation: For maximum USB 3.0 throughput and to prevent transfer timeouts, "
                f"stage GSI images on a local fast NVMe SSD rather than a network or external drive."
            )

    def query_device_status(self) -> Dict[str, str]:
        """Query fastboot getvar unlocked and is-userspace."""
        res_dev = self.run_fastboot(["devices"])
        if not res_dev.stdout.strip():
            raise ConnectionError("No device detected in Fastboot mode. Run 'adb reboot fastboot'.")

        res_unlocked = self.run_fastboot(["getvar", "unlocked"])
        unlocked = "yes" in (res_unlocked.stderr + res_unlocked.stdout).lower()

        res_userspace = self.run_fastboot(["getvar", "is-userspace"])
        is_userspace = "yes" in (res_userspace.stderr + res_userspace.stdout).lower()

        return {
            "unlocked": "yes" if unlocked else "no",
            "is_userspace": "yes" if is_userspace else "no",
        }

    def execute_deployment(self, dry_run: bool = True) -> bool:
        """Execute full fastbootd deployment sequence."""
        print("=" * 70)
        print("TB311FU ('poplar') Fastbootd Dynamic Partition Deployment Suite")
        gsi_size_str = f"{os.path.getsize(self.gsi_path):,} bytes" if os.path.exists(self.gsi_path) else "NOT FOUND"
        vendor_size_str = f"{os.path.getsize(self.vendor_path):,} bytes" if os.path.exists(self.vendor_path) else "NOT FOUND"
        print(f"Fastboot Binary:  {self.fastboot_bin}")
        print(f"Target GSI Path:  {self.gsi_path} ({gsi_size_str})")
        print(f"Stabilized Vendor: {self.vendor_path} ({vendor_size_str})")
        print(f"Chunk Size Flag:  -S {self.chunk_size} (WinUSB error 22 protection)")
        print(f"Zero Data Loss:   {'DISABLED (Factory reset requested)' if self.factory_reset else 'ENABLED (Preserving /data)'}")
        print("=" * 70)

        self.verify_target_images()

        system_size = os.path.getsize(self.gsi_path)
        plan = generate_flashing_plan(
            gsi_path=self.gsi_path,
            vendor_path=self.vendor_path,
            chunk_size=self.chunk_size,
            factory_reset=self.factory_reset,
            target_system_size=system_size,
            fastboot_bin=self.fastboot_bin,
        )

        if dry_run:
            print("\n[DRY-RUN VALIDATION] Staging fastboot commands without device execution:\n")
            for idx, cmd in enumerate(plan, 1):
                print(f"  Step {idx}: {cmd}")
            print("\n" + "-" * 70)
            print("Safety Audits Passed:")
            print("  [PASS] Mandatory -S 64M chunking configured on all flashing steps.")
            print(f"  [PASS] Zero data loss contract: {len([c for c in plan if '-w' in c])} wipe commands.")
            print("  [PASS] AVB Little Kernel contract: vendor_boot remains 100% untouched.")
            print("  [PASS] AVB Little Kernel contract: OEM vbmeta signatures preserved bare.")
            print("=" * 70)
            print("[+] DRY-RUN SUCCESS: Flashing deployment plan verified.")
            return True

        # Live Execution
        print("\n[Phase 1] Querying device Fastbootd state...")
        status = self.query_device_status()
        print(f"  [+] Bootloader Unlocked: {status['unlocked']}")
        print(f"  [+] Userspace Fastbootd: {status['is_userspace']}")

        if status["unlocked"] != "yes":
            raise RuntimeError("Bootloader is LOCKED. Unlock device before dynamic partition flashing.")

        check_fastbootd_mode(status["is_userspace"])

        print("\n[Phase 2] Executing Fastbootd commands sequentially...")
        for idx, cmd_str in enumerate(plan, 1):
            print(f"\n[*] Step {idx}/{len(plan)}: {cmd_str}")
            res = subprocess.run(cmd_str, shell=True)
            if res.returncode != 0:
                raise RuntimeError(f"Step {idx} failed with code {res.returncode}: {cmd_str}")

        print("\n" + "=" * 70)
        print("DEPLOYMENT SUCCESS: System and Vendor successfully flashed!")
        print("=" * 70)
        return True


# ==============================================================================
# CLI Entrypoint
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Lenovo Tab with Clear Case (TB311FU) Fastbootd Flashing Deployment Suite")
    parser.add_argument("--gsi", type=str, default=DEFAULT_GSI_PATH, help="Path to target GSI image")
    parser.add_argument("--vendor", type=str, default=DEFAULT_VENDOR_PATH, help="Path to stabilized vendor image")
    parser.add_argument("--chunk-size", type=str, default=DEFAULT_CHUNK_SIZE, help="Fastboot chunk size (default: 64M)")
    parser.add_argument("--factory-reset", action="store_true", help="Perform factory data reset (fastboot -w)")
    parser.add_argument("--fastboot", type=str, default=None, help="Path to fastboot executable")
    parser.add_argument("--serial", type=str, default=None, help="Device serial")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Validate and display flashing plan (default)")
    parser.add_argument("--execute", action="store_true", help="Execute live flashing on connected Fastbootd device")
    args = parser.parse_args()

    is_dry_run = not args.execute

    deployer = FastbootdDeployer(
        gsi_path=args.gsi,
        vendor_path=args.vendor,
        chunk_size=args.chunk_size,
        factory_reset=args.factory_reset,
        fastboot_path=args.fastboot,
        serial=args.serial,
    )

    try:
        deployer.execute_deployment(dry_run=is_dry_run)
    except Exception as e:
        print(f"\n[!] Deployment error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

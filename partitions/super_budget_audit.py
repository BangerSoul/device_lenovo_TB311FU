#!/usr/bin/env python3
"""
Lenovo Tab with Clear Case (TB311FU / 'poplar') Dynamic Partition Super Budget Audit Tool.
Forensic geometry analysis, live lpdump inspection, and headroom verification
tailored for LineageOS-23.2-20260524-GAPPS-EXT4-GSI.img.
"""

import os
import sys
import re
import json
import subprocess
import argparse
from typing import Dict, List, Optional, Tuple, Any

# ==============================================================================
# Hardware Constants: Lenovo Tab with Clear Case (TB311FU / poplar, MT8786 / MT6768)
# ==============================================================================
SECTOR_SIZE: int = 512
PAGE_SIZE: int = 4096

# Physical 'super' partition on eMMC 5.1 (starts at physical sector 2048)
SUPER_PHYSICAL_BYTES: int = 11811160064       # 11.00 GiB / 11.81 GB
SUPER_PHYSICAL_SECTORS: int = 23068672        # 23,068,672 sectors * 512

# Dynamic Super Group 'main_a' / 'main_b' limits (Virtual A/B metadata v10.2)
GROUP_MAIN_A_MAX_BYTES: int = 11809062912    # 11.00 GiB
GROUP_MAIN_A_MAX_SECTORS: int = 23064576     # 23,064,576 sectors * 512
GROUP_MAIN_B_MAX_BYTES: int = 11809062912    # 11.00 GiB
GROUP_MAIN_B_MAX_SECTORS: int = 23064576

# Target GSI: LineageOS 23.2 (Android 16 QPR2 / Baklava, API 36)
TARGET_GSI_SIZE_BYTES: int = 3446353920       # 3.2097 GiB / 3.4464 GB (841,395 * 4096)
TARGET_GSI_SECTORS: int = 6731160             # 6,731,160 sectors * 512

# Calibrated Baseline Logical Partitions (Slot _a) on TB311FU
STOCK_PARTITIONS_MAIN_A: Dict[str, Dict[str, Any]] = {
    "odm_dlkm_a":    {"sectors": 680,     "bytes": 348160,     "fs": "EROFS", "mount": "/odm_dlkm"},
    "system_a":      {"sectors": 6420408, "bytes": 3287248896, "fs": "EXT4",  "mount": "/"},
    "system_b":      {"sectors": 933624,  "bytes": 478015488,  "fs": "EXT4",  "mount": "inactive"},
    "system_dlkm_a": {"sectors": 14272,   "bytes": 7307264,    "fs": "EROFS", "mount": "/system_dlkm"},
    "system_ext_a":  {"sectors": 1308952, "bytes": 670183424,  "fs": "EROFS", "mount": "/system_ext"},
    "vendor_a":      {"sectors": 592472,  "bytes": 303345664,  "fs": "EROFS", "mount": "/vendor"},
    "vendor_dlkm_a": {"sectors": 24376,   "bytes": 12480512,   "fs": "EROFS", "mount": "/vendor_dlkm"},
    "product_a":     {"sectors": 0,       "bytes": 0,          "fs": "NONE",  "mount": "deleted"},
    "product_b":     {"sectors": 0,       "bytes": 0,          "fs": "NONE",  "mount": "deleted"},
}

MIN_RESERVE_HEADROOM_BYTES: int = 500 * 1024 * 1024  # 500 MB minimum dynamic reserve


# ==============================================================================
# Helper & Boundary Validation Functions
# ==============================================================================
def round_to_sectors(byte_size: int) -> int:
    """Round up byte size to next 512-byte sector boundary."""
    if byte_size <= 0:
        return 0
    return ((byte_size + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE


def round_to_blocks(byte_size: int) -> int:
    """Round up byte size to next 4096-byte page/block boundary."""
    if byte_size <= 0:
        return 0
    return ((byte_size + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE


def validate_partition_size(sz: int, max_bytes: int = SUPER_PHYSICAL_BYTES) -> bool:
    """Validate that requested partition size does not exceed physical capacity."""
    if sz < 0:
        raise ValueError(f"Partition size cannot be negative: {sz}")
    if sz > max_bytes:
        raise ValueError(f"Partition size {sz} exceeds super capacity {max_bytes}")
    return True


def check_headroom(available_bytes: int, min_reserve: int = MIN_RESERVE_HEADROOM_BYTES) -> bool:
    """Verify that available unallocated space exceeds minimum reserve threshold."""
    if available_bytes < min_reserve:
        raise ValueError(
            f"Insufficient super headroom reserve: {available_bytes} bytes "
            f"(required minimum: {min_reserve} bytes)"
        )
    return True


# ==============================================================================
# Data Structures
# ==============================================================================
class LogicalPartition:
    def __init__(
        self,
        name: str,
        group: str,
        sectors: int = 0,
        size_bytes: int = 0,
        extents: Optional[List[Tuple[int, int]]] = None,
        readonly: bool = True,
        fs_type: str = "UNKNOWN",
        mount_point: str = "UNKNOWN",
    ):
        self.name = name
        self.group = group
        self.sectors = sectors
        self.size_bytes = size_bytes if size_bytes > 0 else (sectors * SECTOR_SIZE)
        self.extents = extents or []
        self.readonly = readonly
        self.fs_type = fs_type
        self.mount_point = mount_point

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group,
            "sectors": self.sectors,
            "size_bytes": self.size_bytes,
            "size_mb": round(self.size_bytes / (1024 * 1024), 2),
            "size_gib": round(self.size_bytes / (1024 * 1024 * 1024), 3),
            "readonly": self.readonly,
            "extents": self.extents,
            "fs_type": self.fs_type,
            "mount_point": self.mount_point,
        }


class SuperGeometry:
    def __init__(
        self,
        physical_size: int = SUPER_PHYSICAL_BYTES,
        metadata_version: str = "10.2",
        groups: Optional[Dict[str, int]] = None,
        partitions: Optional[Dict[str, LogicalPartition]] = None,
    ):
        self.physical_size = physical_size
        self.metadata_version = metadata_version
        self.groups = groups or {
            "default": 0,
            "main_a": GROUP_MAIN_A_MAX_BYTES,
            "main_b": GROUP_MAIN_B_MAX_BYTES,
        }
        self.partitions = partitions or {}

    def get_group_allocated_sectors(self, group_name: str) -> int:
        total = 0
        for p in self.partitions.values():
            if p.group == group_name:
                total += p.sectors
        return total

    def get_group_allocated_bytes(self, group_name: str) -> int:
        return self.get_group_allocated_sectors(group_name) * SECTOR_SIZE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "physical_size_bytes": self.physical_size,
            "metadata_version": self.metadata_version,
            "groups": self.groups,
            "partitions": {name: p.to_dict() for name, p in self.partitions.items()},
        }


# ==============================================================================
# LPDump Parser & Hardware Prober
# ==============================================================================
def parse_lpdump_output(text: str) -> SuperGeometry:
    """Parse output from `lpdump` command into SuperGeometry model."""
    geometry = SuperGeometry()
    partitions: Dict[str, LogicalPartition] = {}
    groups: Dict[str, int] = {"default": 0, "main_a": GROUP_MAIN_A_MAX_BYTES, "main_b": GROUP_MAIN_B_MAX_BYTES}

    # Extract metadata version
    ver_match = re.search(r"Metadata version:\s*([0-9.]+)", text)
    if ver_match:
        geometry.metadata_version = ver_match.group(1).strip()

    # Extract block device size
    size_match = re.search(r"Partition name:\s*super\s+First sector:\s*\d+\s+Size:\s*(\d+)\s*bytes", text, re.DOTALL)
    if not size_match:
        size_match = re.search(r"Size:\s*(\d+)\s*bytes", text)
    if size_match:
        geometry.physical_size = int(size_match.group(1))

    # Extract group table
    group_blocks = re.findall(r"Name:\s*([a-zA-Z0-9_]+)\s+Maximum size:\s*(\d+)\s*bytes", text)
    for gname, gmax in group_blocks:
        groups[gname] = int(gmax)
    geometry.groups = groups

    # Extract Super partition layout summary if present (e.g., super: 3657728 .. 10078136: system_a (6420408 sectors))
    layout_matches = re.findall(r"super:\s*(\d+)\s*\.\.\s*(\d+):\s*([a-zA-Z0-9_]+)\s*\((\d+)\s*sectors\)", text)
    layout_dict: Dict[str, Dict[str, Any]] = {}
    for start, end, name, sectors in layout_matches:
        layout_dict[name] = {
            "start": int(start),
            "end": int(end),
            "sectors": int(sectors),
        }

    # Extract Partition table blocks
    # e.g.:
    # ------------------------
    #   Name: system_a
    #   Group: main_a
    #   Attributes: readonly
    #   Extents:
    #     0 .. 6420407 linear super 3657728
    part_blocks = re.split(r"-{10,}", text)
    for block in part_blocks:
        name_match = re.search(r"Name:\s*([a-zA-Z0-9_]+)", block)
        if not name_match:
            continue
        pname = name_match.group(1).strip()
        group_match = re.search(r"Group:\s*([a-zA-Z0-9_]+)", block)
        pgroup = group_match.group(1).strip() if group_match else "main_a"

        # Determine sectors
        p_sectors = 0
        extents: List[Tuple[int, int]] = []
        if pname in layout_dict:
            p_sectors = layout_dict[pname]["sectors"]
            extents.append((layout_dict[pname]["start"], layout_dict[pname]["end"]))
        else:
            # Parse from Extents lines
            ext_matches = re.findall(r"(\d+)\s*\.\.\s*(\d+)\s+linear\s+super\s+(\d+)", block)
            for e_start, e_end, phys_start in ext_matches:
                count = int(e_end) - int(e_start) + 1
                p_sectors += count
                extents.append((int(phys_start), int(phys_start) + count))

        # Check attributes
        readonly = "readonly" in block

        # Known metadata lookup
        known = STOCK_PARTITIONS_MAIN_A.get(pname, {})
        fs_type = known.get("fs", "EROFS" if "dlkm" in pname or "vendor" in pname else "EXT4")
        mount_point = known.get("mount", f"/{pname}")

        partitions[pname] = LogicalPartition(
            name=pname,
            group=pgroup,
            sectors=p_sectors,
            size_bytes=p_sectors * SECTOR_SIZE,
            extents=extents,
            readonly=readonly,
            fs_type=fs_type,
            mount_point=mount_point,
        )

    geometry.partitions = partitions
    return geometry


def get_default_tb311fu_geometry() -> SuperGeometry:
    """Construct calibrated forensic SuperGeometry for Lenovo Tab with Clear Case (TB311FU)."""
    geom = SuperGeometry(
        physical_size=SUPER_PHYSICAL_BYTES,
        metadata_version="10.2",
        groups={
            "default": 0,
            "main_a": GROUP_MAIN_A_MAX_BYTES,
            "main_b": GROUP_MAIN_B_MAX_BYTES,
        },
    )
    partitions: Dict[str, LogicalPartition] = {}
    for name, info in STOCK_PARTITIONS_MAIN_A.items():
        group = "main_b" if name.endswith("_b") else "main_a"
        partitions[name] = LogicalPartition(
            name=name,
            group=group,
            sectors=info["sectors"],
            size_bytes=info["bytes"],
            readonly=True,
            fs_type=info["fs"],
            mount_point=info["mount"],
        )
    geom.partitions = partitions
    return geom


def query_live_lpdump(device_serial: Optional[str] = None) -> SuperGeometry:
    """Query live tablet via adb shell 'su -c lpdump'."""
    cmd = ["adb"]
    if device_serial:
        cmd.extend(["-s", device_serial])
    cmd.extend(["shell", "su -c lpdump"])

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode != 0:
        raise RuntimeError(f"lpdump query failed (code {res.returncode}): {res.stderr or res.stdout}")
    return parse_lpdump_output(res.stdout)


# ==============================================================================
# Comprehensive Budget Auditor
# ==============================================================================
class BudgetAuditReport:
    def __init__(self):
        self.physical_super_bytes: int = SUPER_PHYSICAL_BYTES
        self.main_a_max_bytes: int = GROUP_MAIN_A_MAX_BYTES
        self.total_allocated_sectors: int = 0
        self.total_allocated_bytes: int = 0
        self.unallocated_headroom_bytes: int = 0
        self.target_gsi_bytes: int = TARGET_GSI_SIZE_BYTES
        self.existing_system_bytes: int = 0
        self.system_expansion_bytes: int = 0
        self.post_flash_allocated_bytes: int = 0
        self.post_flash_headroom_bytes: int = 0
        self.is_valid: bool = False
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.partition_summary: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "physical_super_bytes": self.physical_super_bytes,
            "physical_super_gib": round(self.physical_super_bytes / (1024 ** 3), 3),
            "main_a_max_bytes": self.main_a_max_bytes,
            "main_a_max_gib": round(self.main_a_max_bytes / (1024 ** 3), 3),
            "total_allocated_bytes": self.total_allocated_bytes,
            "total_allocated_gib": round(self.total_allocated_bytes / (1024 ** 3), 3),
            "unallocated_headroom_bytes": self.unallocated_headroom_bytes,
            "unallocated_headroom_gib": round(self.unallocated_headroom_bytes / (1024 ** 3), 3),
            "target_gsi_bytes": self.target_gsi_bytes,
            "target_gsi_gib": round(self.target_gsi_bytes / (1024 ** 3), 3),
            "existing_system_bytes": self.existing_system_bytes,
            "system_expansion_bytes": self.system_expansion_bytes,
            "system_expansion_mb": round(self.system_expansion_bytes / (1024 ** 2), 2),
            "post_flash_allocated_bytes": self.post_flash_allocated_bytes,
            "post_flash_allocated_gib": round(self.post_flash_allocated_bytes / (1024 ** 3), 3),
            "post_flash_headroom_bytes": self.post_flash_headroom_bytes,
            "post_flash_headroom_gib": round(self.post_flash_headroom_bytes / (1024 ** 3), 3),
            "is_valid": self.is_valid,
            "warnings": self.warnings,
            "errors": self.errors,
            "partitions": self.partition_summary,
        }

    def generate_markdown(self) -> str:
        lines = [
            "# Lenovo Tab with Clear Case (TB311FU / poplar) Super Budget Audit Report",
            "",
            "## 1. Physical & Group Super Geometry",
            f"- **Physical Super Size**: {self.physical_super_bytes:,} bytes ({round(self.physical_super_bytes / (1024**3), 3)} GiB, {self.physical_super_bytes // SECTOR_SIZE:,} sectors)",
            f"- **Group 'main_a' Maximum**: {self.main_a_max_bytes:,} bytes ({round(self.main_a_max_bytes / (1024**3), 3)} GiB)",
            f"- **Currently Allocated**: {self.total_allocated_bytes:,} bytes ({round(self.total_allocated_bytes / (1024**3), 3)} GiB, {self.total_allocated_sectors:,} sectors)",
            f"- **Current Headroom in main_a**: {self.unallocated_headroom_bytes:,} bytes ({round(self.unallocated_headroom_bytes / (1024**3), 3)} GiB)",
            "",
            "## 2. Target GSI Expansion Analysis",
            f"- **Target GSI Size**: {self.target_gsi_bytes:,} bytes ({round(self.target_gsi_bytes / (1024**3), 3)} GiB)",
            f"- **Existing system_a**: {self.existing_system_bytes:,} bytes ({round(self.existing_system_bytes / (1024**3), 3)} GiB)",
            f"- **Required Expansion (Delta)**: +{self.system_expansion_bytes:,} bytes (+{round(self.system_expansion_bytes / (1024**2), 2)} MB)",
            f"- **Post-Flash Allocated Storage**: {self.post_flash_allocated_bytes:,} bytes ({round(self.post_flash_allocated_bytes / (1024**3), 3)} GiB)",
            f"- **Post-Flash Remaining Headroom**: {self.post_flash_headroom_bytes:,} bytes ({round(self.post_flash_headroom_bytes / (1024**3), 3)} GiB)",
            "",
            "## 3. Logical Partition Map",
            "| Partition | Group | Sectors | Size (Bytes) | Size (MB) | Filesystem | Mount Point |",
            "|---|---|---|---|---|---|---|",
        ]
        for p in self.partition_summary:
            lines.append(
                f"| `{p['name']}` | `{p['group']}` | {p['sectors']:,} | {p['size_bytes']:,} B | {p['size_mb']} MB | {p['fs_type']} | `{p['mount_point']}` |"
            )
        lines.append("")
        lines.append("## 4. Audit Verdict")
        if self.is_valid:
            lines.append(f"✅ **PASS**: Expansion to {self.target_gsi_bytes:,} B safely leaves ~{round(self.post_flash_headroom_bytes / (1024**3), 2)} GiB reserve headroom.")
        else:
            lines.append("❌ **FAIL**: Budget validation encountered errors.")
            for err in self.errors:
                lines.append(f"  - Error: {err}")
        if self.warnings:
            lines.append("\n**Warnings:**")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


def audit_super_budget(
    geometry: SuperGeometry,
    target_gsi_size: int = TARGET_GSI_SIZE_BYTES,
) -> BudgetAuditReport:
    """
    Perform deep audit of dynamic super partition geometry against target GSI size.
    Validates headroom, sector alignment, 4k boundary alignment, and partition limits.
    """
    report = BudgetAuditReport()
    report.physical_super_bytes = geometry.physical_size
    report.main_a_max_bytes = geometry.groups.get("main_a", GROUP_MAIN_A_MAX_BYTES)
    report.target_gsi_bytes = target_gsi_size

    # Validate physical bounds
    validate_partition_size(target_gsi_size, report.physical_super_bytes)

    # 4K alignment verification
    if target_gsi_size % PAGE_SIZE != 0:
        report.errors.append(f"Target GSI size {target_gsi_size} is not 4096-byte page aligned")

    # Sector alignment verification
    if target_gsi_size % SECTOR_SIZE != 0:
        report.errors.append(f"Target GSI size {target_gsi_size} is not 512-byte sector aligned")

    # Sum all allocated sectors in super (across all groups or main_a)
    total_sectors = 0
    main_a_sectors = 0
    partition_list: List[Dict[str, Any]] = []

    for name, p in sorted(geometry.partitions.items()):
        total_sectors += p.sectors
        if p.group == "main_a":
            main_a_sectors += p.sectors
        partition_list.append(p.to_dict())

        # Check individual partition size bounds
        if p.size_bytes > report.physical_super_bytes:
            report.errors.append(f"Partition {name} ({p.size_bytes} B) exceeds super capacity ({report.physical_super_bytes} B)")

    report.partition_summary = partition_list
    report.total_allocated_sectors = total_sectors
    report.total_allocated_bytes = total_sectors * SECTOR_SIZE

    # Available unallocated dynamic storage in main_a
    report.unallocated_headroom_bytes = report.main_a_max_bytes - report.total_allocated_bytes

    # Existing system_a lookup
    sys_part = geometry.partitions.get("system_a")
    if sys_part:
        report.existing_system_bytes = sys_part.size_bytes
    else:
        report.existing_system_bytes = STOCK_PARTITIONS_MAIN_A["system_a"]["bytes"]

    # Calculate expansion requirements
    expansion = target_gsi_size - report.existing_system_bytes
    report.system_expansion_bytes = expansion
    report.post_flash_allocated_bytes = report.total_allocated_bytes + expansion
    report.post_flash_headroom_bytes = report.main_a_max_bytes - report.post_flash_allocated_bytes

    # Headroom check (> 500 MB minimum reserve)
    try:
        check_headroom(report.post_flash_headroom_bytes, MIN_RESERVE_HEADROOM_BYTES)
    except ValueError as e:
        report.errors.append(str(e))

    # Negative headroom check
    if report.post_flash_headroom_bytes < 0:
        report.errors.append(
            f"Super group main_a overflow! Post-flash allocation ({report.post_flash_allocated_bytes} B) "
            f"exceeds limit ({report.main_a_max_bytes} B) by {-report.post_flash_headroom_bytes} B"
        )

    # Check product partition removal
    prod_a = geometry.partitions.get("product_a")
    if prod_a and prod_a.size_bytes > 0:
        report.warnings.append(
            f"product_a is currently allocated ({prod_a.size_bytes} B). "
            f"Deletion in Fastbootd is required to free space."
        )

    # Set overall status
    report.is_valid = len(report.errors) == 0
    return report


# ==============================================================================
# CLI Entrypoint
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Lenovo Tab with Clear Case (TB311FU) Super Budget Audit Tool")
    parser.add_argument("--live", action="store_true", help="Query live connected device via ADB root lpdump")
    parser.add_argument("--serial", type=str, default=None, help="Specific ADB device serial (e.g., HNQ09EZD)")
    parser.add_argument("--file", type=str, default=None, help="Path to saved lpdump output file")
    parser.add_argument("--gsi", type=str, default=None, help="Path to custom GSI image file to measure")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--report", action="store_true", help="Output full Markdown audit report")
    args = parser.parse_args()

    # Determine GSI size
    gsi_size = TARGET_GSI_SIZE_BYTES
    if args.gsi:
        if not os.path.exists(args.gsi):
            print(f"[!] Error: Specified GSI image not found: {args.gsi}", file=sys.stderr)
            sys.exit(1)
        gsi_size = os.path.getsize(args.gsi)
        print(f"[*] Loaded GSI: {args.gsi} ({gsi_size:,} bytes)")

    # Obtain geometry
    geom = None
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            geom = parse_lpdump_output(f.read())
    elif args.live:
        try:
            print("[*] Querying live device lpdump via ADB...", file=sys.stderr)
            geom = query_live_lpdump(args.serial)
        except Exception as e:
            print(f"[!] Live query failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Default: Try live query first; if offline, fall back cleanly to forensic TB311FU baseline
        try:
            geom = query_live_lpdump(args.serial)
            print("[+] Successfully queried live device lpdump via ADB.", file=sys.stderr)
        except Exception:
            print("[i] Live device query not available. Using calibrated TB311FU forensic geometry.", file=sys.stderr)
            geom = get_default_tb311fu_geometry()

    # Run audit
    report = audit_super_budget(geom, target_gsi_size=gsi_size)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    elif args.report:
        print(report.generate_markdown())
    else:
        print("\n" + "=" * 70)
        print("TB311FU ('poplar') Dynamic Partition Super Budget Audit")
        print("=" * 70)
        print(f"Physical Super Limit:  {report.physical_super_bytes:>15,} bytes ({round(report.physical_super_bytes / (1024**3), 3)} GiB)")
        print(f"main_a Max Capacity:   {report.main_a_max_bytes:>15,} bytes ({round(report.main_a_max_bytes / (1024**3), 3)} GiB)")
        print(f"Currently Allocated:   {report.total_allocated_bytes:>15,} bytes ({round(report.total_allocated_bytes / (1024**3), 3)} GiB)")
        print(f"Available Headroom:    {report.unallocated_headroom_bytes:>15,} bytes ({round(report.unallocated_headroom_bytes / (1024**3), 3)} GiB)")
        print("-" * 70)
        print(f"Target GSI Size:       {report.target_gsi_bytes:>15,} bytes ({round(report.target_gsi_bytes / (1024**3), 3)} GiB)")
        print(f"Expansion Required:    {report.system_expansion_bytes:>15,} bytes ({round(report.system_expansion_bytes / (1024**2), 2)} MB)")
        print(f"Post-Flash Allocated:  {report.post_flash_allocated_bytes:>15,} bytes ({round(report.post_flash_allocated_bytes / (1024**3), 3)} GiB)")
        print(f"Post-Flash Headroom:   {report.post_flash_headroom_bytes:>15,} bytes ({round(report.post_flash_headroom_bytes / (1024**3), 3)} GiB)")
        print("=" * 70)
        if report.is_valid:
            print(f"[+] AUDIT PASSED: Target GSI fits comfortably with {round(report.post_flash_headroom_bytes / (1024**3), 3)} GiB reserve!")
        else:
            print("[!] AUDIT FAILED:")
            for err in report.errors:
                print(f"    - {err}")
            sys.exit(1)


if __name__ == "__main__":
    main()

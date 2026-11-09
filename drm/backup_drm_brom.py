#!/usr/bin/env python3
"""
Pre-Unlock BootROM (BROM) Disaster Recovery Backup Tool for Lenovo Tab M11 (TB311FU)
Safely reads byte-for-byte images of DRM and calibration partitions (nvram, nvdata,
protect1, protect2, proinfo, persist) prior to bootloader unlock or custom ROM flashing.
"""

import sys
import os
import shutil
import argparse
import subprocess
from pathlib import Path


CRITICAL_PARTITIONS = [
    "nvram",
    "nvdata",
    "protect1",
    "protect2",
    "proinfo",
    "persist",
    "seccfg",
]


def backup_drm(out_dir: str, port: str = None) -> bool:
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    print("================================================================================")
    print(" Lenovo Tab M11 (TB311FU) DRM & Calibration BROM Backup")
    print(" Target Partitions:", ", ".join(CRITICAL_PARTITIONS))
    print(f" Backup Destination: {out_path}")
    print("================================================================================")

    mtk_client = shutil.which("mtk") or shutil.which("mtkclient")
    if mtk_client:
        print(f"[*] Found mtkclient binary at: {mtk_client}")
        parts_arg = ",".join(CRITICAL_PARTITIONS)
        cmd = [mtk_client, "r", parts_arg, str(out_path)]
        if port:
            cmd.extend(["--port", port])
        print(f"[*] Executing: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True)
            print("[OK] BROM partition backup completed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[X] mtkclient execution failed: {e}")
            return False
    else:
        print("[!] mtkclient not detected on host PATH.")
        print("[*] To backup via mtkclient in BootROM mode:")
        print("    1. Power off tablet completely.")
        print("    2. Hold Volume Down (or Volume Up + Down) and connect USB cable.")
        print(f"    3. Run: python -m mtkclient r {','.join(CRITICAL_PARTITIONS)} {out_path}")
        print("\n[*] Writing disaster recovery instruction manifest...")
        manifest_path = out_path / "BROM_BACKUP_INSTRUCTIONS.txt"
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(f"""MediaTek BootROM (BROM) Backup Instructions for TB311FU
Critical Partitions Required for Widevine L1 & Attestation:
{chr(10).join(f"- {p}" for p in CRITICAL_PARTITIONS)}

Command:
python -m mtkclient r {','.join(CRITICAL_PARTITIONS)} {out_path}
""")
        print(f"[OK] Instructions written to: {manifest_path}")
        return True


def main():
    parser = argparse.ArgumentParser(description="MediaTek BROM DRM Backup Tool for TB311FU")
    parser.add_argument("--output", "-o", default="backup_drm", help="Destination backup directory")
    parser.add_argument("--port", "-p", help="Specific serial COM port for BROM connection")
    args = parser.parse_args()

    success = backup_drm(args.output, args.port)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

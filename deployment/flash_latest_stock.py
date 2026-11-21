#!/usr/bin/env python3
# ==============================================================================
# Complete Official Latest Stock Firmware Flasher for Lenovo Tab M11 (TB311FU)
# Target Device Serial: HNQ09EZD (POPLAR_ROW_WIFI)
# Package: TB311FU_ROW_OPEN_USER_M1457.5_W_ZUI_17.5.36.508_ST_261024
# SoC: MediaTek Helio G88 (MT6768 / MT8786)
# ==============================================================================

import os
import sys
import time
import subprocess
import usb.core
import usb.util

STOCK_DIR = "/home/bangersoul/GSI-Development/TB311FU_Stock_Firmware/image"
PRELOADER_RAW = "/home/bangersoul/GSI-Development/native_preloader.bin"
PRELOADER_PADDED = "/home/bangersoul/GSI-Development/native_preloader_padded.img"
MTK_BIN = "/home/bangersoul/.local/bin/mtk"

# Fallback preloader paths if needed
if not os.path.exists(PRELOADER_RAW):
    PRELOADER_RAW = os.path.join(STOCK_DIR, "preloader_tb8786p1_64_k66.bin")
if not os.path.exists(PRELOADER_PADDED):
    PRELOADER_PADDED = os.path.join(STOCK_DIR, "preloader_emmc.img")

def is_mtk_connected():
    try:
        dev = usb.core.find(idVendor=0x0E8D)
        if dev is not None:
            usb.util.dispose_resources(dev)
            return True
        return False
    except Exception:
        return False

def is_fastboot_connected():
    try:
        res = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=2)
        return bool(res.stdout.strip())
    except Exception:
        return False

def get_fastboot_serial():
    try:
        res = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=2)
        lines = res.stdout.strip().splitlines()
        if lines:
            return lines[0].split()[0]
    except Exception:
        pass
    return None

print("=" * 76, flush=True)
print(" Lenovo Tab M11 (TB311FU) - Complete Latest Official Stock Flasher", flush=True)
print(" Package: ZUI 17.5.36.508 (TB311FU_ROW_OPEN_USER_M1457.5_W_ZUI_17.5.36.508)", flush=True)
print(" Hardware: MediaTek Helio G88 (MT6768 / MT8786) | Target: HNQ09EZD", flush=True)
print("=" * 76, flush=True)

# 1. Check if tablet is already in Fastboot
if is_fastboot_connected():
    serial = get_fastboot_serial()
    print(f"\n[+] Detected tablet ALREADY in Fastboot mode! (Serial: {serial})", flush=True)
    ans = input("Do you want to skip BROM and proceed straight to flashing super.img? [Y/n]: ").strip().lower()
    if ans not in ("n", "no"):
        skip_brom = True
    else:
        skip_brom = False
else:
    skip_brom = False

if not skip_brom:
    # 2. Force unplug if currently plugged in with a stale USB session
    if is_mtk_connected():
        print("\n[!] Tablet is currently connected with an existing/stale USB session.", flush=True)
        print("[!] Please UNPLUG the USB-C cable from the tablet now...", flush=True)
        while is_mtk_connected():
            time.sleep(0.3)
        print("\n[+] Tablet UNPLUGGED detected!", flush=True)

    print("\n" + "=" * 76, flush=True)
    print(" HARDWARE BROM HANDSHAKE INSTRUCTIONS:", flush=True)
    print("  1. Ensure tablet is completely POWERED OFF (hold POWER 15s if unsure).", flush=True)
    print("  2. Press and hold BOTH [VOLUME UP] and [VOLUME DOWN] simultaneously.", flush=True)
    print("  3. While holding BOTH buttons, PLUG the USB-C cable into the computer.", flush=True)
    print("  4. Keep holding the buttons until mtkclient captures the BROM handshake!", flush=True)
    print("=" * 76, flush=True)
    print("\n[*] Waiting for tablet connection in BROM mode (0e8d:0003)...", flush=True)

    while not is_mtk_connected():
        time.sleep(0.1)

    print("\n[+] Device connected on USB! Initializing mtkclient...", flush=True)
    time.sleep(0.2)

    # Build mtk multi command string for dual-slot firmware partitions
    cmds = [
        f"w lk_a {STOCK_DIR}/lk.img",
        f"w lk_b {STOCK_DIR}/lk.img",
        f"w boot_a {STOCK_DIR}/boot.img",
        f"w boot_b {STOCK_DIR}/boot.img",
        f"w vendor_boot_a {STOCK_DIR}/vendor_boot.img",
        f"w vendor_boot_b {STOCK_DIR}/vendor_boot.img",
        f"w init_boot_a {STOCK_DIR}/init_boot.img",
        f"w init_boot_b {STOCK_DIR}/init_boot.img",
        f"w dtbo_a {STOCK_DIR}/dtbo.img",
        f"w dtbo_b {STOCK_DIR}/dtbo.img",
        f"w vbmeta_a {STOCK_DIR}/vbmeta.img",
        f"w vbmeta_b {STOCK_DIR}/vbmeta.img",
        f"w vbmeta_system_a {STOCK_DIR}/vbmeta_system.img",
        f"w vbmeta_system_b {STOCK_DIR}/vbmeta_system.img",
        f"w vbmeta_vendor_a {STOCK_DIR}/vbmeta_vendor.img",
        f"w vbmeta_vendor_b {STOCK_DIR}/vbmeta_vendor.img",
        f"w tee_a {STOCK_DIR}/tee.img",
        f"w tee_b {STOCK_DIR}/tee.img",
        f"w scp_a {STOCK_DIR}/scp.img",
        f"w scp_b {STOCK_DIR}/scp.img",
        f"w sspm_a {STOCK_DIR}/sspm.img",
        f"w sspm_b {STOCK_DIR}/sspm.img",
        f"w spmfw_a {STOCK_DIR}/spmfw.img",
        f"w spmfw_b {STOCK_DIR}/spmfw.img",
        f"w gz_a {STOCK_DIR}/gz.img",
        f"w gz_b {STOCK_DIR}/gz.img",
        f"w md1img_a {STOCK_DIR}/md1img.img",
        f"w md1img_b {STOCK_DIR}/md1img.img",
        f"w logo {STOCK_DIR}/logo.bin",
        f"w lenovocust {STOCK_DIR}/lenovocust.img",
        f"w lenovoraw {STOCK_DIR}/lenovoraw.img",
        f"wf --parttype boot1 {PRELOADER_PADDED}",
        f"wf --parttype boot2 {PRELOADER_PADDED}",
        "reset"
    ]
    multi_cmd_str = ";".join(cmds)

    print(f"\n[*] Flashing 31 dual-slot stock partitions & hardware preloader via mtkclient...", flush=True)
    full_cmd = [MTK_BIN, "--preloader", PRELOADER_RAW, "multi", multi_cmd_str]
    ret = subprocess.run(full_cmd)

    if ret.returncode != 0:
        print(f"\n[-] mtkclient returned error code {ret.returncode}", flush=True)
        print("[!] If the handshake timed out, please run this script again with fresh power-off.", flush=True)
        sys.exit(ret.returncode)

    print("\n" + "=" * 76, flush=True)
    print("[+] STAGE 1 COMPLETE: All dual-slot firmware partitions & preloader flashed!", flush=True)
    print("=" * 76, flush=True)

# 3. Stage 2: Super partition flashing via Fastboot
print("\n" + "=" * 76, flush=True)
print(" STAGE 2: Flashing Official Stock 'super' Partition (7.1 GB)", flush=True)
print("=" * 76, flush=True)
print("[*] Waiting for device to enumerate in Fastboot mode...", flush=True)

timeout = 60
start = time.time()
while time.time() - start < timeout:
    if is_fastboot_connected():
        break
    time.sleep(1)

if not is_fastboot_connected():
    print("[-] Device did not automatically enter Fastboot within 60s.", flush=True)
    print("[!] Please hold [VOLUME DOWN] + [POWER] to boot into Fastboot mode.", flush=True)
    while not is_fastboot_connected():
        time.sleep(1)

serial = get_fastboot_serial()
print(f"[+] Device detected in Fastboot! Serial: {serial}", flush=True)

print("[*] Setting active slot to 'a'...", flush=True)
subprocess.run(["fastboot", "set_active", "a"], check=True)

super_img = os.path.join(STOCK_DIR, "super.img")
print(f"[*] Flashing official stock super image: {super_img} (~7.1 GB)...", flush=True)
subprocess.run(["fastboot", "-S", "64M", "flash", "super", super_img], check=True)

print("[*] Performing factory wipe (userdata & metadata)...", flush=True)
subprocess.run(["fastboot", "erase", "userdata"], check=False)
subprocess.run(["fastboot", "erase", "metadata"], check=False)

print("\n" + "=" * 76, flush=True)
print("[+] FULL STOCK RESTORATION COMPLETED SUCCESSFULLY!", flush=True)
print("[*] Rebooting tablet into Official Lenovo Stock OS (ZUI 17.5)...", flush=True)
print("=" * 76, flush=True)
subprocess.run(["fastboot", "reboot"], check=False)

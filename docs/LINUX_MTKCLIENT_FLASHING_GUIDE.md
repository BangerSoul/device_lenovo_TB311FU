# Linux BROM Unbrick & Flashing Guide: Lenovo Tab M11 (TB311FU)

Comprehensive technical documentation and operational guide for unbricking, recovering, and flashing the **Lenovo Tab M11** (`TB311FU`, codename `poplar`) on **Linux** using **mtkclient** directly against the MediaTek BootROM (BROM).

---

## 1. Overview & Architecture

| Hardware Property | Specification |
| :--- | :--- |
| **Device Model** | Lenovo Tab M11 (`TB311FU` / Wi-Fi / India SKU: `ZAEH0019IN`) |
| **SoC** | MediaTek Helio G88 (`MT6768` / `MT8786`, platform `k68v1`) |
| **Target Serial Number** | `HNQ09EZD` |
| **Boot Architecture** | Android Boot Header v4, Chained AVB 2.0, A/B Slots |
| **Security Configuration** | `SBC enabled: True`, HW Code: `0x707`, Target Config: `0xe5` |
| **Watchdog Timer (WDT)** | `0x10007000` |
| **BROM Payload Address** | `0x100a00` |
| **DA Payload Address** | `0x201000` |
| **BROM USB Identity** | VID `0E8D`, PID `0003` (`MT6227 phone` / BootROM) |
| **Preloader USB Identity**| VID `0E8D`, PID `2000` |
| **Fastboot USB Identity** | VID `22B8`, PID `2E80` |

---

## 2. Why Linux `mtkclient` over Lenovo Windows "Software Fix"

Lenovo distributes a proprietary Windows tool named **Software Fix** (`software_fix_v7.6.2.10_setup.exe`, part of Rescue and Smart Assistant / LMSA). Reverse-engineering of its core assemblies (`lenovo.mbg.service.lmsa.flash.dll`, `lenovo.mbg.service.common.webservices.dll`) revealed significant operational limitations:

1. **Mandatory Cloud Session / SSO Wall**:
   - The OEM application queries `POST https://lsa.lenovo.com/lmsa-web/rescueDevice/getNewResourceBySN.jhtml` with device serial number (`{"sn":"HNQ09EZD"}`).
   - This endpoint returns HTTP 302 redirecting to `https://lsa.lenovo.com/lmsa-web/login` unless valid Lenovo Single-Sign-On authentication cookies (`JSESSIONID`) are present.
   - It cannot recover devices anonymously or offline.
2. **Proprietary SP Flash Tool Wrappers**:
   - The tool relies on internal sub-processes (`ShellResponseSpflashtool.cs`, `ShellResponseCfcflash.cs`) wrapping legacy MediaTek SP Flash Tool binaries requiring OEM signed Download Agents (DA).
3. **Windows Driver Hostility**:
   - Requires custom Windows `libusb-win32` / MTK VCOM drivers which frequently fail USB enumeration handshake loops during BROM reboot cycles.

### The Open-Source Solution: `mtkclient`
By using **mtkclient** on Linux:
- The BootROM exploit injects a custom payload into SRAM (`0x100a00`), disabling the Watchdog (`0x10007000`) and bypassing Secure Boot (SBC) authentication without requiring Lenovo server credentials or proprietary signed DAs.
- Operates reliably in standard Linux environments (Ubuntu 24.04/26.04 Live USB, Debian, Arch).
- Directly writes raw partition blocks using standard USB bulk transfers at **~7.2 MB/s**.

---

## 3. Environment Setup & Prerequisites

### 3.1 System Dependencies
Ensure `python3`, `pip`, and `git` are available:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git libusb-1.0-0 udev
```

### 3.2 Installing `mtkclient`
Because Ubuntu 24.04+ enforces **PEP 668** (externally managed environment), install mtkclient from source:

```bash
# Clone the repository
git clone --depth=1 https://github.com/bkerler/mtkclient.git /tmp/mtkclient
cd /tmp/mtkclient

# Install requirements
pip3 install -r requirements.txt --break-system-packages

# Build and install wheel
pip3 install . --break-system-packages
```

Verify binary and module resolution:
```bash
export PYTHONPATH="/tmp/mtkclient:$PYTHONPATH"
python3 /tmp/mtkclient/mtk.py --help
```

### 3.3 Configure `udev` Rules (Non-Root USB Access)
To communicate with BROM without requiring `sudo` for every command, install the MediaTek USB rules:

```bash
sudo tee /etc/udev/rules.d/52-mtk.rules > /dev/null << 'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="1004", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="22d9", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0fce", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="22b8", MODE="0666", TAG+="uaccess"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

## 4. Hardware BROM Entry Timing & Handshake

MediaTek Helio G88 enters BootROM mode for only **~1.5 seconds** on power-up before falling back to Preloader or initiating Watchdog reset. Capturing this window requires exact physical timing:

```
+-----------------------------------------------------------------------+
|                       HARDWARE BROM HANDSHAKE                         |
+-----------------------------------------------------------------------+
|  1. Unplug USB-C cable from tablet.                                   |
|  2. Power off tablet completely:                                      |
|     Hold [POWER] button for 15-20 seconds until screen is DEAD BLACK. |
|  3. Press and hold [VOLUME UP] + [VOLUME DOWN] simultaneously.        |
|  4. While holding BOTH buttons, plug in the USB-C cable.              |
|  5. Keep holding buttons for 2-3 seconds until mtkclient captures:    |
|     "Preloader - Disabling Watchdog..."                               |
|  6. Release buttons once handshake completes.                        |
+-----------------------------------------------------------------------+
```

Verify device appearance via terminal:
```bash
lsusb | grep 0e8d
# Output: Bus 003 Device 088: ID 0e8d:0003 MediaTek Inc. MT6227 phone
```

---

## 5. Verified Partition Table & Flashing Execution

During live recovery, `mtkclient` successfully queried the GPT and wrote all five critical boot vector partitions.

### 5.1 TB311FU Partition Offsets Discovered
```
Partition Table (Sample from printgpt):
misc:                Offset 0x0000000000008000, Length 0x0000000000080000
para:                Offset 0x0000000000088000, Length 0x0000000000080000
lenovocust:          Offset 0x0000000000108000, Length 0x0000000012c00000
lenovoraw:           Offset 0x0000000012d08000, Length 0x0000000001000000
vbmeta_a:            Sector 695360,             Count 16384 (8 MiB)
vbmeta_system_a:     Sector 711744,             Count 16384 (8 MiB)
vbmeta_vendor_a:     Sector 728128,             Count 16384 (8 MiB)
boot_a:              Sector 1576960,            Count 65536 (32 MiB)
vendor_boot_a:       Sector 1642496,            Count 131072 (64 MiB)
super:               Offset ~0x00000000ec000000 (9.0 GiB Dynamic Partitions)
```

### 5.2 Step-by-Step Flashing Commands
To restore an unbootable tablet to working OrangeFox recovery and permissive AVB:

```bash
export PYTHONPATH="/tmp/mtkclient:$PYTHONPATH"
MTK="python3 /tmp/mtkclient/mtk.py"
FLASH_DIR="/home/bangersoul/GSI-Development/flash_work"

# 1. Flash clean kernel boot vector (Linux 6.6 / Android 16 Boot v4)
$MTK w boot_a "$FLASH_DIR/poplar_boot_v12_clean.img"

# 2. Flash OrangeFox custom recovery ramdisk into vendor_boot
$MTK w vendor_boot_a "$FLASH_DIR/vendor_boot_fixed_orangefox.img"

# 3. Flash AVB disabled vbmeta flags (bypass dm-verity / hash tree verification)
$MTK w vbmeta_a "$FLASH_DIR/vbmeta_a_disabled.img"
$MTK w vbmeta_system_a "$FLASH_DIR/vbmeta_system_a_disabled.img"
$MTK w vbmeta_vendor_a "$FLASH_DIR/vbmeta_vendor_a_disabled.img"
```

### 5.3 Actual Execution Telemetry
```
[1/5] boot_a -> poplar_boot_v12_clean.img
Progress: |██████████| 100.0% Write: (0x2000000/0x2000000), 7.17 MB/s
Wrote poplar_boot_v12_clean.img to sector 1576960 with sector count 65536.

[2/5] vendor_boot_a -> vendor_boot_fixed_orangefox.img
Progress: |██████████| 100.0% Write: (0x2485000/0x2485000), 1.82 MB/s
Wrote vendor_boot_fixed_orangefox.img to sector 1642496 with sector count 131072.

[3/5] vbmeta_a -> disabled
Progress: |██████████| 100.0% Write: (0x800000/0x800000), 7.08 MB/s
Wrote vbmeta_a_disabled.img to sector 695360 with sector count 16384.

[4/5] vbmeta_system_a -> disabled
Progress: |██████████| 100.0% Write: (0x800000/0x800000), 7.26 MB/s
Wrote vbmeta_system_a_disabled.img to sector 711744 with sector count 16384.

[5/5] vbmeta_vendor_a -> disabled
Progress: |██████████| 100.0% Write: (0x800000/0x800000), 7.08 MB/s
Wrote vbmeta_vendor_a_disabled.img to sector 728128 with sector count 16384.
```

---

## 6. Using the Automated Deployment Script

A production script is provided in the repository under `deployment/flash_mtkclient_linux.sh`:

```bash
# 1. Set permissions
chmod +x deployment/flash_mtkclient_linux.sh

# 2. Automatically wait for BROM and print GPT info
./deployment/flash_mtkclient_linux.sh detect

# 3. Flash the complete boot recovery suite
./deployment/flash_mtkclient_linux.sh flash_boot a

# 4. Or flash to slot B if required
./deployment/flash_mtkclient_linux.sh flash_boot b

# 5. Open interactive debugging shell
./deployment/flash_mtkclient_linux.sh shell
```

---

## 7. Post-Flash Boot & System Installation

Once all five partitions are flashed:
1. **Unplug USB-C cable**.
2. **Boot into OrangeFox Recovery**:
   - Press and hold **Power + Volume Down** simultaneously for ~10 seconds.
   - Release buttons when the OrangeFox splash screen appears.
3. **From OrangeFox Recovery UI**:
   - Wipe `Data`, `Cache`, and `Dalvik`.
   - Connect USB cable to PC.
   - Run ADB sideload or reboot into `Fastbootd` userspace:
     ```bash
     adb reboot fastboot
     ```
4. **Deploy LineageOS 23.2 GSI System Image**:
   Follow Plan A deployment (`deployment/flash_lineage23_fastbootd.ps1` or `fastboot flash system <gsi_image.img>`).

---

## 8. Troubleshooting & Diagnostics

| Symptom | Root Cause | Solution |
| :--- | :--- | :--- |
| `Status: Waiting for PreLoader VCOM` loop | Watchdog reset device before handshake was established | Unplug USB, hold Power 15s to reset, hold Vol Up + Vol Down, re-insert USB firmly. |
| `ModuleNotFoundError: No module named 'mtkclient'` | `PYTHONPATH` not pointing to cloned source directory | Run `export PYTHONPATH="/tmp/mtkclient:$PYTHONPATH"` before calling `mtk.py`. |
| `Permission denied` opening USB device | Missing udev rules for vendor `0e8d` | Run `./deployment/flash_mtkclient_linux.sh install_udev` and trigger rules. |
| `Target config is still unset` | Device rebooted into charging/battery animation | Ensure tablet is 100% powered OFF before plugging USB with buttons pressed. |
| Fastboot command not responding | Device is in bootloader fastboot instead of fastbootd | Execute `fastboot reboot fastboot` to enter userspace fastbootd for dynamic partition writes. |

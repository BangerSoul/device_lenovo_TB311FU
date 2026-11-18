# device_lenovo_TB311FU

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Target: Lenovo Tab with Clear Case (TB311FU)](https://img.shields.io/badge/Device-Lenovo%20Tab%20with%20Clear%20Case%20(TB311FU)-orange.svg)](https://www.lenovo.com)
[![Branch: main](https://img.shields.io/badge/Branch-main%20%2F%20lineage--23.2-success.svg)](https://github.com/BangerSoul/device_lenovo_TB311FU)

LineageOS 23.2 / 22.1 device tree for the **Lenovo Tab with Clear Case** (`TB311FU`, codename `poplar`, MediaTek Helio G88 / MT8786 / MT6768).

---

## 🌐 Lenovo Tab with Clear Case (TB311FU / poplar) Open-Source Bringup Ecosystem

The complete open-source software stack for the **Lenovo Tab with Clear Case** (`TB311FU`, codename `poplar`, MediaTek Helio G88 / MT8786 / MT6768) is organized into five specialized, interconnected repositories under [@BangerSoul](https://github.com/BangerSoul):

| Repository | Role & Subsystem Scope | Target Stack | Key Deliverables & Artifacts | Badges & Links |
| :--- | :--- | :--- | :--- | :---: |
| [**`device_lenovo_TB311FU`**](https://github.com/BangerSoul/device_lenovo_TB311FU) | **Device Tree & RRO Overlays**<br>LineageOS device configuration, 90Hz display profiles, SystemUI/Framework RRO overlays, super partition budget management, and 5-tier diagnostic test suite. | Android 16 QPR2<br>LineageOS 23.2 / 22.1 | `TrebleOverlayLenovoTB311FU.apk`<br>`TrebleOverlayLenovoTB311FUSystemUI.apk`<br>`flash_lineage23_fastbootd.ps1`<br>E2E Diagnostic Test Suite | [![Device Tree](https://img.shields.io/badge/Repo-device__lenovo__TB311FU-blue.svg?logo=android)](https://github.com/BangerSoul/device_lenovo_TB311FU)<br>[![Releases](https://img.shields.io/badge/Releases-v1.0--lineage23-blue.svg)](https://github.com/BangerSoul/device_lenovo_TB311FU/releases) |
| [**`vendor_lenovo_TB311FU`**](https://github.com/BangerSoul/vendor_lenovo_TB311FU) | **Vendor Blobs & Hardware Policies**<br>Proprietary blobs, 4-speaker surround audio routing (`AUDIO_CHANNEL_OUT_QUAD`), Dolby Atmos DAP/DRC trees, AP500U active stylus IDC configs, and EROFS vendor repacking tools. | Android 16 QPR2<br>LineageOS 23.2 HALs | `vendor_stabilized.img` (EROFS LZ4)<br>`audio_policy_configuration.xml`<br>`audio_effects.xml`<br>`himax-touchscreen.idc` / `NVT-ts.idc` | [![Vendor Blobs](https://img.shields.io/badge/Repo-vendor__lenovo__TB311FU-orange.svg?logo=android)](https://github.com/BangerSoul/vendor_lenovo_TB311FU)<br>[![Releases](https://img.shields.io/badge/Releases-Assets-orange.svg)](https://github.com/BangerSoul/vendor_lenovo_TB311FU/releases) |
| [**`kernel_lenovo_TB311FU`**](https://github.com/BangerSoul/kernel_lenovo_TB311FU) | **PoplarKernel GKI 2.0 & AVB Vector**<br>Downstream Linux 6.6 LTS kernel, KernelSU-Next native integration, module signature bypass (`CONFIG_RFKILL=m`), permissive dm-verity, PWM >= 48 floor clamp, and 32MB LK AVB boot vector builder. | Linux 6.6 LTS GKI 2.0<br>Android 15 / 16 & Halium | PoplarKernel v1.2 AnyKernel3 Zip<br>32MB AVB Chained `boot.img`<br>Halium `Image.gz` / `dtbo.img`<br>CI/CD Automated Build Actions | [![Kernel](https://img.shields.io/badge/Repo-kernel__lenovo__TB311FU-teal.svg?logo=linux)](https://github.com/BangerSoul/kernel_lenovo_TB311FU)<br>[![Releases](https://img.shields.io/badge/Releases-v1.2-teal.svg)](https://github.com/BangerSoul/kernel_lenovo_TB311FU/releases) |
| [**`recovery_lenovo_TB311FU`**](https://github.com/BangerSoul/recovery_lenovo_TB311FU) | **TWRP 3.7+ Recovery & Slot B Vector**<br>Non-destructive custom recovery deployment to secondary slot `boot_b`, pristine factory `vendor_boot` & `vbmeta` preservation, BCB staging, and zero-risk slot switching. | Android Header v4<br>TWRP 3.7+ / OrangeFox | Slot B Chained `recovery_boot.img`<br>Turnkey Hybrid `vendor_boot.img`<br>Bootloader Control Block Tools<br>CI/CD Automated Build Actions | [![Recovery](https://img.shields.io/badge/Repo-recovery__lenovo__TB311FU-blueviolet.svg?logo=twrp)](https://github.com/BangerSoul/recovery_lenovo_TB311FU)<br>[![Releases](https://img.shields.io/badge/Releases-v1.0--twrp-blueviolet.svg)](https://github.com/BangerSoul/recovery_lenovo_TB311FU/releases) |
| [**`linux-lenovo-tb311fu`**](https://github.com/BangerSoul/linux-lenovo-tb311fu) | **Native Linux / PostmarketOS Port**<br>Alpine ARM64 + KDE Plasma Mobile 6 port, KWin Wayland 24-bit True Color fallback & rotation fix (`libkwin.so.6.7.5`), WMT Wi-Fi/BT daemons, quad ALSA UCM scenarios, and Fastbootd direct `system_a` flasher. | PostmarketOS<br>Alpine ARM64 / Plasma Mobile 6 | `device-lenovo-tb311fu` package<br>`linux-lenovo-tb311fu` package<br>`libkwin.so.6.7.5.patched`<br>Fastbootd `-S 64M` Rootfs Flasher | [![Linux Port](https://img.shields.io/badge/Repo-linux--lenovo--tb311fu-success.svg?logo=postmarketos)](https://github.com/BangerSoul/linux-lenovo-tb311fu)<br>[![Releases](https://img.shields.io/badge/Releases-v1.0--alpha-success.svg)](https://github.com/BangerSoul/linux-lenovo-tb311fu/releases) |

---

## Branches

- **`arrow-14.0`**: ArrowOS 14.0 (Android 14) official ROM tree with `arrow_TB311FU.mk`, `arrow.dependencies`, and custom lunch combos.
- **`main`**: Master branch with LineageOS 23.2 (Android 16 QPR2) device configurations, RRO overlays, 90Hz display profiles, and dynamic partition tools.
- **`lineage-23.2`**: Dedicated Android 16 QPR2 GSI / ROM tree branch.
- **`lineage-22.1`**: LineageOS 22.1 (Android 15) baseline snapshot.

---

## Device Architecture & Specifications

| Feature | Value |
| :--- | :--- |
| **Device Model** | Lenovo Tab with Clear Case (TB311FU) |
| **SoC** | MediaTek Helio G88 (`MT8786` / `MT6768`) |
| **Display** | 1200 x 1920 IPS LCD @ 90Hz |
| **Digitizer** | Dual-source Himax HX83102E & Novatek NVT (Lenovo AP500U active pen) |
| **Audio** | Quad stereo speakers + dual smart amplifiers (Awinic AW883xx) |
| **Dynamic Partitions** | Android Dynamic Partitions (`super` partition 9.0 GiB / 9,663,676,416 B) |
| **Boot Architecture** | Android Boot Header v4 with AVB 2.0 chained verification |

---

## Features & Deliverables Included

### 1. Runtime Resource Overlays (RRO)
- **`overlay/TrebleOverlayLenovoTB311FU/`**:
  - Full source overlay targeting `framework-res` (android).
  - Enforces 90Hz peak refresh rate with dynamic switching (`config_defaultRefreshRate=90`, `config_peakRefreshRate=90`).
  - Sets minimum brightness clamp to PWM 48 (`config_screenBrightnessSettingMinimum=48`) to eliminate 0-nit panel blackouts.
  - Symmetrical 11" tablet padding and status bar geometries.
- **`overlay/TrebleOverlayLenovoTB311FUSystemUI/`**:
  - Overlay targeting SystemUI.
  - Suppresses invalid flashlight QuickSettings tile (Lenovo Tab with Clear Case (TB311FU) has no physical rear flash diode).
  - Masks mobile network/carrier UI elements for clean Wi-Fi-only tablet presentation.

### 2. 90Hz Display Profiles & Calibration
- **`configs/display/display_90hz_calibration.xml`**:
  - Declares panel timings for BOE 1200x1920 90Hz panel.
  - Color mode definitions (`NATIVE`, `BOOSTED`, `SATURATED`).
  - SurfaceFlinger unsignaled latching and 3 acquired framebuffers.

### 3. Dynamic Super Partition Budgeting
- **`partitions/super_budget_audit.py`**:
  - Audits physical partition extents within `super` partition budget (9,663,676,416 B).
  - Verifies headroom for LineageOS 23.2 GSI + stabilized EROFS vendor image.
- **`partitions/strip_system_cellular.py`**:
  - Prunes non-functional cellular daemons and telephony APKs from GSI images.

### 4. Fastbootd Deployment Suite (`-S 64M`)
- **`deployment/flash_lineage23_fastbootd.ps1`**:
  - Production PowerShell flashing suite implementing the mandatory Windows `-S 64M` WinUSB standard.
  - Automatically manages logical partition resizing in userspace Fastbootd.
  - Enforces safety invariant prohibiting modification of stock `vendor_boot` and `vbmeta` partitions.

### 5. Linux BROM Recovery & mtkclient Flashing Suite
- **`deployment/flash_mtkclient_linux.sh`**:
  - Linux-native MediaTek BootROM (`0E8D:0003`) payload exploitation and recovery tool.
  - Flashes `boot`, `vendor_boot` (OrangeFox), and `vbmeta` chain directly, bypassing SBC authentication without proprietary Lenovo SSO requirements.
- **`docs/LINUX_MTKCLIENT_FLASHING_GUIDE.md`**:
  - Definitive technical guide covering environment setup, udev configuration, BROM hardware button timing, partition offsets, telemetry, and unbrick procedures.

### 6. Hardware Subsystems Diagnostic Audit
- **`diagnostics/audit_subsystems.py`**:
  - Forensic audit harness testing all 8 subsystems (Torch, Wi-Fi, Bluetooth, Backlight, Stylus, Display, Audio, Power).
- **`diagnostics/apply_live_remediation.py`**:
  - Live sysfs and runtime prop remediation manager.
- **`diagnostics/report_hardware_matrix.md`**:
  - Comprehensive forensic hardware matrix and audit report.

### 7. Master Dual-Track E2E Test Harness
- **`tests/e2e_test_runner.py` & `tests/pmos_e2e_runner.py`**:
  - Tier 1: Feature Coverage (F1-F24).
  - Tier 2: Boundary & Corner Cases.
  - Tier 3: Pairwise Combinations.
  - Tier 4: Real-world Workload Scenarios.
  - Tier 5: Adversarial and hostile security suites.

### 8. ArrowOS Build Support
- **Branch**: `arrow-14.0` (Android 14)
- **Product Definition**: `arrow_TB311FU.mk`
- **Lunch Target**: `arrow_TB311FU-userdebug`
- **Dependencies Manifest**: `arrow.dependencies` & `manifests/arrow_TB311FU.xml`
- **Compilation Quickstart**:
  ```bash
  # In your ArrowOS 14.0 workspace:
  mkdir -p .repo/local_manifests
  cp device/lenovo/TB311FU/manifests/arrow_TB311FU.xml .repo/local_manifests/
  repo sync -c -j$(nproc) --no-clone-bundle --no-tags
  source build/envsetup.sh
  lunch arrow_TB311FU-userdebug
  m bacon
  # or directly:
  bash device/lenovo/TB311FU/scripts/build_arrow.sh userdebug
  ```

---

## Maintainer

- **Maintainer:** Azmathulla Shaik ([@BangerSoul](https://github.com/BangerSoul))
- **Email:** `iamshaikhazmathulla@outlook.com`

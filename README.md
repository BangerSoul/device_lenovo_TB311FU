# device_lenovo_TB311FU

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Target: Lenovo Tab M11](https://img.shields.io/badge/Device-Lenovo%20Tab%20M11%20(TB311FU)-orange.svg)](https://www.lenovo.com)
[![Branch: main](https://img.shields.io/badge/Branch-main%20%2F%20lineage--23.2-success.svg)](https://github.com/BangerSoul/device_lenovo_TB311FU)

LineageOS 23.2 / 22.1 device tree for the **Lenovo Tab M11** (`TB311FU`, codename `poplar`, MediaTek Helio G88 / MT8786 / MT6768).

---

## Branches

- **`main`**: Master branch with LineageOS 23.2 (Android 16 QPR2) device configurations, RRO overlays, 90Hz display profiles, and dynamic partition tools.
- **`lineage-23.2`**: Dedicated Android 16 QPR2 GSI / ROM tree branch.
- **`lineage-22.1`**: LineageOS 22.1 (Android 15) baseline snapshot.

---

## Device Architecture & Specifications

| Feature | Value |
| :--- | :--- |
| **Device Model** | Lenovo Tab M11 (`TB311FU`) |
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
  - Suppresses invalid flashlight QuickSettings tile (Lenovo Tab M11 has no physical rear flash diode).
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

### 5. Hardware Subsystems Diagnostic Audit
- **`diagnostics/audit_subsystems.py`**:
  - Forensic audit harness testing all 8 subsystems (Torch, Wi-Fi, Bluetooth, Backlight, Stylus, Display, Audio, Power).
- **`diagnostics/apply_live_remediation.py`**:
  - Live sysfs and runtime prop remediation manager.
- **`diagnostics/report_hardware_matrix.md`**:
  - Comprehensive forensic hardware matrix and audit report.

### 6. Master Dual-Track E2E Test Harness
- **`tests/e2e_test_runner.py` & `tests/pmos_e2e_runner.py`**:
  - Tier 1: Feature Coverage (F1-F24).
  - Tier 2: Boundary & Corner Cases.
  - Tier 3: Pairwise Combinations.
  - Tier 4: Real-world Workload Scenarios.
  - Tier 5: Adversarial and hostile security suites.

---

## Maintainer

- **Maintainer:** Azmathulla Shaik ([@BangerSoul](https://github.com/BangerSoul))
- **Email:** `iamshaikhazmathulla@outlook.com`

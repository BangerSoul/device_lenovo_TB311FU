# Ubuntu Custom ISO and Bootable USB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate a locally remastered Ubuntu 26.04.1 Desktop ISO for the HP ProBook 440 G8, then install Ventoy on the already-authorized SanDisk USB and verify it boots.

**Architecture:** Verify the official base ISO and host first. Enable Intel virtualization, test Cubic in the local Ubuntu 26.04 WSL2 environment, and use an Ubuntu VM only if WSL cannot safely support Cubic's mount/build needs. Add official apps, developer tools, and the local ICC profile; validate the output before the USB is erased.

**Tech Stack:** Windows 11 Pro 26H2, Ubuntu 26.04 WSL2 or a local Ubuntu 26.04 VM, Cubic, Ubuntu apt, PowerShell, Ventoy, Python 3 standard-library `unittest`, and local ISO/USB verification.

**Spec:** `docs/superpowers/specs/2026-11-18-ubuntu-gsi-dev-usb-design.md`

## Global Constraints

- Base ISO: `ubuntu-26.04.1-desktop-amd64.iso`; expected SHA-256 `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f`.
- Host hardware: HP ProBook 440 G8, Intel i5-1135G7, 8 GB RAM, about 81 GB free SSD space; firmware virtualization is currently disabled.
- Install only Ubuntu's standard in-kernel Intel graphics/Wi-Fi and Realtek audio support; do not add Windows drivers or unofficial kernel replacements.
- Bundle only official Antigravity, OpenAI ChatGPT Linux, and Brave packages; record exact versions and hashes. Keep those binaries out of GitHub.
- Use the active `Dell_IVO0536_HDR_D65.icm` profile for the IVO0536 panel locally; do not publish the profile to GitHub.
- Use PipeWire/ALSA defaults for speakers, microphone, and Bluetooth; Windows Sound Research/Sonitude effects are not portable.
- KeePassXC may be installed. Copy an existing encrypted `.kdbx` vault to the USB or create and populate one locally before the first Linux boot; never store its master password, browser sessions, cookies, or plaintext private keys on the USB.
- The current SanDisk `D:` is explicitly authorized for erase; re-identify it by model and capacity immediately before formatting.
- Keep the custom ISO and app binaries out of GitHub; publish only the build recipe, package/version manifest, and hashes.

## Review Focus

- Wrong or altered Ubuntu ISO: preflight must stop on a digest mismatch before Cubic starts.
- Missing app package or ICC asset: manifest/customizer tests must fail before image generation.
- Unsupported WSL loop/mount behavior or memory exhaustion: the Cubic proof build must fail without formatting USB, then use the documented local VM fallback.
- Wrong USB target: the final preflight must abort unless exactly one removable SanDisk Dual Drive of the expected capacity is identified.
- Driver, audio, or color-profile mismatch: live-session checks must report the device/profile that was actually detected and the Windows-only effects that remain unavailable.

---

### Task 1: Prepare and verify the local Linux build host

**Files:**
- Create: `tools/ubuntu-usb/host-preflight.ps1`
- Create: `docs/UBUNTU_DEV_USB.md`

**Interfaces:**
- `host-preflight.ps1` is read-only. It reports Windows version, CPU virtualization, WSL distribution/version, C: free bytes, and the base ISO SHA-256.
- Exit 0 means all pre-build host and ISO checks pass; exit 2 means one or more prerequisites are missing; exit 1 means the ISO hash is wrong or a check failed unexpectedly.

- [ ] **Step 1: Implement** the report and exit-code behavior above. Do not enable firmware settings, install software, or partition disks from the script.
- [ ] **Step 2: Run** `pwsh -NoProfile -File tools/ubuntu-usb/host-preflight.ps1`; confirm it reports the correct ISO digest, VT-x disabled, and no installed WSL distro, with exit code 2 for missing prerequisites.
- [ ] **Step 3: Have the user enable Intel Virtualization Technology (VT-x) in firmware.** After Windows restarts, rerun the script and require VT-x to report enabled.
- [ ] **Step 4: Install the official Ubuntu 26.04 WSL2 distribution and confirm `wsl.exe --list --verbose` shows version 2. Keep the Cubic project and ISO under WSL's Linux filesystem, not `/mnt/c` or another NTFS path.**
- [ ] **Step 5: Verify** WSLg launches Cubic and the exact ISO can be extracted, loop-mounted, customized, and regenerated in a small proof project. If any of those checks fail, stop WSL work and use an Ubuntu 26.04 VM on the local Hyper-V host; rerun the same proof there before the full build.
- [ ] **Step 6: Record** the selected host method, Cubic version, and proof result in `docs/UBUNTU_DEV_USB.md`; commit as `docs: document Ubuntu ISO build host`.

### Task 2: Create and validate the workstation asset manifest

**Files:**
- Create: `tools/ubuntu-usb/manifest.json`
- Create: `tools/ubuntu-usb/validate_manifest.py`
- Create: `tests/test_ubuntu_usb_manifest.py`
- Modify: `.gitignore` to exclude `tools/ubuntu-usb/local-assets/`, local asset manifests, and generated custom ISOs

**Interfaces:**
- `validate_manifest(data: dict) -> list[str]` checks the base ISO digest, package names, official app URLs, local asset paths, status/hash consistency, and prohibited secret fields.
- The CLI `python3 tools/ubuntu-usb/validate_manifest.py` exits 0 for valid input and 1 for errors.
- A pending local asset has `status: pending_download` and `sha256: null`; a downloaded asset must have an exact version and 64-character lowercase SHA-256.

- [ ] **Step 1: Write failing tests** named `test_base_iso_sha_is_pinned`, `test_required_apps_are_listed`, `test_pending_asset_hash_state_is_consistent`, `test_downloaded_asset_hash_is_valid`, `test_assets_use_local_relative_paths`, and `test_no_secret_fields_are_in_manifest`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_ubuntu_usb_manifest.py' -v`; confirm failure before implementation.
- [ ] **Step 3: Implement** the manifest and validator with the standard library. Pin the verified Canonical base hash and list Antigravity, ChatGPT, Brave, KeePassXC, and Android/GSI tools.
- [ ] **Step 4: Add ignore rules** before downloading app packages or copying the ICC profile.
- [ ] **Step 5: Run** the focused tests and validator; commit as `feat: add Ubuntu workstation asset manifest`.

### Task 3: Prepare and test the Cubic customization recipe

**Files:**
- Create: `tools/ubuntu-usb/customize-livefs.sh`
- Create: `tools/ubuntu-usb/packages.txt`
- Create: `tests/test_customize_livefs.py`
- Local only: `tools/ubuntu-usb/local-assets/` and `asset-manifest.local.json`

**Interfaces:**
- `customize-livefs.sh --check --assets-dir <dir> --manifest <file>` checks the package list, required local assets, and SHA-256 values without changing files; exit 0 means complete and valid, exit 1 means any input is missing or mismatched.
- The normal mode runs inside Cubic's root filesystem terminal, installs packages from `packages.txt`, installs the official app packages, and copies the ICC profile to the system color-profile directory. Copy local files into Cubic's terminal environment using Cubic's local file-copy control; the ignored local manifest and binaries never enter Git.

- [ ] **Step 1: Write failing subprocess tests** named `test_check_passes_with_valid_assets`, `test_check_rejects_missing_asset`, and `test_check_rejects_hash_mismatch`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_customize_livefs.py' -v`; confirm failure before the script exists.
- [ ] **Step 3: Implement** the shell checker and customizer; validate asset SHA-256 values before any package installation.
- [ ] **Step 4: Run** the focused tests and `bash -n tools/ubuntu-usb/customize-livefs.sh`; require all to pass.
- [ ] **Step 5: Download** Antigravity, ChatGPT Linux, and Brave packages from their official sources; record exact version and SHA-256 in the ignored local manifest; copy the active ICC profile into the ignored local-assets directory.
- [ ] **Step 6: Run** `--check`, then create a disposable Cubic project and install one harmless package as a proof. Confirm the ISO regenerates and boots before adding the full package/app set.
- [ ] **Step 7: Commit** only the script, package list, tests, and non-sensitive manifest schema as `feat: add Ubuntu remaster recipe`.

### Task 4: Build and validate the custom ISO

**Files:**
- Modify: `tools/ubuntu-usb/manifest.json` with final package/app versions and hashes
- Modify: `docs/UBUNTU_DEV_USB.md` with build and validation results
- Local only: Cubic project directory and custom `.iso`

**Interfaces:**
- Output: `ubuntu-26.04.1-probook440g8-dev-amd64.iso`; store a separate SHA-256 for this output.

- [ ] **Step 1: Re-check** the base ISO SHA-256 and every app/profile input hash before building.
- [ ] **Step 2: Build** with Cubic on the proven local Linux host; keep the project on a Linux filesystem and all output in ignored local directories.
- [ ] **Step 3: Verify** ISO structure, boot catalog, output hash, and build manifest. Boot the result in Cubic's QEMU test or a local VM before touching the USB.
- [ ] **Step 4: Confirm** installed package versions and launch Antigravity, ChatGPT, Brave, and KeePassXC in the installed test system.
- [ ] **Step 5: Import** the IVO0536 ICC profile and confirm the profile is associated with the internal display; record its filename and hash locally.
- [ ] **Step 6: Verify** Wi-Fi, speakers, microphone, Bluetooth, and JBL headphones in the live or installed session. Record detected devices and state plainly that Windows Sound Research/Sonitude effects are not reproduced.
- [ ] **Step 7: Commit** only the package/version manifest and build instructions; never commit the ISO, ICC profile, or app binaries.

### Task 5: Format the SanDisk and create the Ventoy USB

**Files:**
- Local only: official Ventoy release archive, custom ISO, ICC sidecar, recovery notes, and any user-created encrypted KeePassXC vault

**Interfaces:**
- The Ventoy exFAT data partition contains the custom ISO, ICC profile, setup notes, and (if the user has one) an encrypted KeePassXC `.kdbx` vault. Never store the vault master password or browser session data on the USB.

- [ ] **Step 1: Re-identify** the USB immediately before writing using `Get-Disk` and `Get-Volume`: require exactly one removable SanDisk Dual Drive matching the recorded capacity near 30.76 GB; confirm its current drive letter and physical disk number, and abort on ambiguity.
- [ ] **Step 2: Install Ventoy** from its official Windows release onto that confirmed SanDisk. The user has authorized erasing this USB; do not select any internal disk.
- [ ] **Step 3: Copy** the custom ISO, ICC sidecar, Plan A download document, Ubuntu setup notes, and any existing encrypted `.kdbx` vault to Ventoy's exFAT partition. If no vault exists, create and populate one locally before the first Ubuntu boot; keep its master password off the USB.
- [ ] **Step 4: Re-read** the copied ISO SHA-256 and require it to match the validated local custom ISO.
- [ ] **Step 5: Boot** from the HP boot menu and confirm Ventoy launches the custom Ubuntu ISO.
- [ ] **Step 6: Leave** the laptop's internal storage unchanged; installing Ubuntu over Windows is a separate action.

## Handoff

Run this plan after Plan A source mapping and transformer hardening. Do not format the SanDisk until Task 4's ISO validation has passed.

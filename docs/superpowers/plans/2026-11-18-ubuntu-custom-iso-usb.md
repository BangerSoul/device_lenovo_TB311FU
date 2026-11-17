# Ubuntu Custom ISO and Bootable USB Implementation Plan

> **For agentic workers:** Implement task by task. Do not format `D:` until the custom ISO has been rebuilt and validated.

**Goal:** Create and verify a locally remastered Ubuntu 26.04.1 Desktop ISO for the HP ProBook 440 G8, then place it on a bootable Ventoy USB.

**Architecture:** Enable Intel virtualization, build in an Ubuntu 26.04 WSL2 workspace, use Cubic to add the selected applications, developer tools, and local ICC profile, verify the output, then install Ventoy on the user-selected USB and copy the ISO plus small recovery files.

**Tech Stack:** Windows 11 Pro 26H2, WSL2 Ubuntu 26.04, Cubic, Ubuntu apt, PowerShell, Ventoy, Python 3 standard-library `unittest`, and local ISO/USB verification.

**Spec:** `docs/superpowers/specs/2026-11-18-ubuntu-gsi-dev-usb-design.md`

## Global Constraints

- Base ISO: `ubuntu-26.04.1-desktop-amd64.iso`; expected SHA-256 `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f`.
- Host hardware: HP ProBook 440 G8, Intel i5-1135G7, 8 GB RAM, about 81 GB free SSD space; firmware virtualization is currently disabled.
- Install only the standard in-kernel Intel graphics/Wi-Fi and Realtek audio support; do not add unofficial kernel drivers.
- Bundle only official Antigravity, OpenAI ChatGPT Linux, and Brave downloads; record exact versions and hashes. Keep those binaries out of GitHub.
- Use the active `Dell_IVO0536_HDR_D65.icm` profile for the IVO0536 panel locally; do not publish the profile to GitHub.
- Use PipeWire/ALSA defaults for speakers, microphone, and Bluetooth. Windows Sound Research/Sonitude effects are not portable.
- KeePassXC may be installed, but the user must create and fill the encrypted vault. Do not copy browser sessions, cookies, passwords, or plaintext private keys.
- The current SanDisk `D:` is explicitly authorized for erase; re-identify it by model and capacity immediately before formatting.
- Keep the custom ISO and app binaries out of GitHub; publish only the build recipe, package/version manifest, and hashes.

## Review Focus

- Wrong input drive: preflight must confirm the target is the removable SanDisk Dual Drive around 30.76 GB and abort for any other device.
- Wrong base ISO: build must stop if the local Ubuntu ISO hash differs from Canonical's published hash.
- Missing bundled app or ICC asset: the build script must fail before remastering rather than silently producing an incomplete ISO.
- WSL/Cubic incompatibility or memory exhaustion: test loop mounting and a small proof build before the full package set; do not format USB on failure.
- Driver/audio/profile expectations: verify available Linux devices and profile association; explicitly report any Windows-only effect that cannot be imported.

---

### Task 1: Prepare the local Linux build host

**Files:**
- Create: `tools/ubuntu-usb/host-preflight.ps1`
- Create: `docs/UBUNTU_DEV_USB.md`

**Interfaces:**
- `host-preflight.ps1` reports Windows version, WSL state, firmware virtualization state, C: free space, and the verified base ISO hash; it never changes BIOS settings or partitions.

- [ ] **Step 1: Add a PowerShell self-check** that compares the ISO digest with the exact expected SHA-256 and reports missing WSL/virtualization prerequisites.
- [ ] **Step 2: Run** `pwsh -File tools/ubuntu-usb/host-preflight.ps1`; confirm it reports VT-x disabled and no WSL distribution, then exits with a prerequisite status.
- [ ] **Step 3: Have the user enable Intel Virtualization Technology (VT-x) in firmware.** After Windows restarts, rerun the preflight and require virtualization to report enabled.
- [ ] **Step 4: Install Ubuntu 26.04 as WSL2 and confirm `wsl.exe --list --verbose` shows version 2.
- [ ] **Step 5: Verify** WSLg launches and Cubic can access loop devices and write to the Linux filesystem. If this fails, stop and switch to a local Ubuntu VM before continuing.
- [ ] **Step 6: Commit** the preflight and host guide as `docs: document Ubuntu ISO build host`.

### Task 2: Create an app and workstation asset manifest

**Files:**
- Create: `tools/ubuntu-usb/manifest.json`
- Create: `tools/ubuntu-usb/validate_manifest.py`
- Create: `tests/test_ubuntu_usb_manifest.py`
- Modify: `.gitignore` to exclude `tools/ubuntu-usb/local-assets/` and generated custom ISOs

**Interfaces:**
- `validate_manifest(data: dict) -> list[str]` checks the base ISO pin, package names, official app source URLs, and 64-character hashes for downloaded app/profile assets.
- CLI: `python3 tools/ubuntu-usb/validate_manifest.py`; exit 0 means valid, exit 1 means invalid.

- [ ] **Step 1: Write failing tests** named `test_base_iso_sha_is_pinned`, `test_required_apps_are_listed`, `test_external_asset_hashes_are_valid`, `test_local_assets_are_not_repo_paths`, and `test_no_secrets_are_in_manifest`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_ubuntu_usb_manifest.py' -v`; confirm failure before implementation.
- [ ] **Step 3: Implement** the manifest and validator with only the Python standard library.
- [ ] **Step 4: Add ignore rules** before downloading Antigravity, ChatGPT, Brave packages, or the ICC profile.
- [ ] **Step 5: Run** the focused tests and validator; commit as `feat: add Ubuntu workstation asset manifest`.

### Task 3: Prepare and verify the remaster recipe

**Files:**
- Create: `tools/ubuntu-usb/customize-livefs.sh`
- Create: `tools/ubuntu-usb/packages.txt`
- Local only: `tools/ubuntu-usb/local-assets/`

**Interfaces:**
- `customize-livefs.sh` runs inside Cubic's root filesystem environment; it installs the manifest's system packages, official apps, and KeePassXC, copies the local ICC profile into the system color-profile directory, and fails if a required local asset is absent.

- [ ] **Step 1: Add a shell self-check** for required inputs, asset hashes, and package manifest; test missing files with temporary fixtures.
- [ ] **Step 2: Run** `bash -n tools/ubuntu-usb/customize-livefs.sh` and the manifest tests; require both to pass before installing anything in Cubic.
- [ ] **Step 3: Download** each app from its official source, record exact version and SHA-256 in the ignored local asset manifest, and copy the active ICC profile into the ignored local-assets directory.
- [ ] **Step 4: Run** the customizer in a disposable Cubic project on the exact ISO with one harmless package first; verify the image remains bootable.
- [ ] **Step 5: Add** the full package set and apps. Do not add proprietary Windows drivers or try to copy Windows audio effects.
- [ ] **Step 6: Commit** only the recipe, package list, and non-sensitive manifest as `feat: add Ubuntu remaster recipe`.

### Task 4: Build and validate the custom ISO

**Files:**
- Modify: `tools/ubuntu-usb/manifest.json` with final package/app versions and hashes
- Local only: custom `.iso` output and Cubic build directory

**Interfaces:**
- Output: `ubuntu-26.04.1-probook440g8-dev-amd64.iso`; record its SHA-256 separately from the Canonical base ISO.

- [ ] **Step 1: Re-check** the base ISO SHA-256 before opening the Cubic project.
- [ ] **Step 2: Build** the custom ISO on the local Linux workspace; keep all output under a local build directory ignored by Git.
- [ ] **Step 3: Verify** ISO structure and hash; boot it in a VM or on the laptop before using Ventoy.
- [ ] **Step 4: Confirm** installed-system package versions, Antigravity launch, ChatGPT launch, Brave launch, and KeePassXC presence.
- [ ] **Step 5: Import** the IVO0536 ICC profile and confirm it is associated with the internal display. Record the profile filename and hash.
- [ ] **Step 6: Verify** Wi-Fi, speakers, microphone, Bluetooth, and JBL headphones in the live/installed Ubuntu session; document that Windows-specific audio effects are not reproduced.
- [ ] **Step 7: Commit** only the package/version manifest and build instructions; never commit the ISO or app binaries.

### Task 5: Format the SanDisk and create the Ventoy USB

**Files:**
- Local only: Ventoy release archive, custom ISO, ICC sidecar, and USB recovery notes

**Interfaces:**
- USB data partition contains the custom ISO, ICC profile, and documentation. The user may create a KeePassXC `.kdbx` file there later; no vault contents are created by this plan.

- [ ] **Step 1: Re-identify** `D:` as the removable SanDisk Dual Drive around 30.76 GB, and verify C: remains the internal SSD.
- [ ] **Step 2: Install Ventoy** from its official Windows release to the confirmed SanDisk; this formats the USB as already authorized.
- [ ] **Step 3: Copy** the custom ISO, profile sidecar, Plan A download document, and setup notes to the Ventoy exFAT partition.
- [ ] **Step 4: Re-read** the copied ISO hash and require it to match the locally built ISO.
- [ ] **Step 5: Boot** the USB through the HP boot menu and confirm Ventoy launches the custom Ubuntu ISO.
- [ ] **Step 6: Leave** the laptop's internal storage untouched; installing Ubuntu over Windows is a separate step.

## Handoff

Run this plan after the Plan A source and artifact map plan. Do not format the SanDisk until Task 4's validation passes.
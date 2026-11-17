# Ubuntu Workstation USB

This guide tracks the locally built Ubuntu 26.04.1 workstation ISO for the HP ProBook 440 G8 and the bootable SanDisk USB. The Ubuntu ISO, bundled application binaries, ICC profile, private asset manifest, KeePassXC vault, and generated custom ISO stay local; GitHub receives only recipes, public package metadata, and verification instructions.

## Base image

- Base: Ubuntu 26.04.1 Desktop AMD64.
- Canonical checksum list: [SHA256SUMS](https://releases.ubuntu.com/26.04.1/SHA256SUMS).
- Expected SHA-256: `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f`.
- The local image matched this digest during host preflight on 2026-11-18.

## Workstation contents

The recipe includes Git, Python 3, Android `adb` and `fastboot`, EXT4 and archive tools, `repo`, and OpenJDK 21. This 8 GB laptop is a workstation and verification host, not a full local Android source-build host; use the linked GitHub repositories and remote build orchestration for resource-heavy builds.

The planned apps use their official Linux delivery channels:

- [Google Antigravity](https://antigravity.google/download?os=linux) is distributed as an official Linux `tar.gz` archive. The staged release is 2.32.1, build `6001966350991360`; the archive's internal payload reports 44.9.1. Its SHA-256 is recorded in `tools/ubuntu-usb/manifest.json`.
- [ChatGPT for Linux](https://learn.chatgpt.com/docs/linux/linux-app) is distributed as an official Ubuntu/Debian `amd64` `.deb`; the staged version is `26.1111.21308`. The Linux desktop app is in preview, and its Linux feature set differs from Windows/macOS. Its SHA-256 is recorded in `tools/ubuntu-usb/manifest.json`.
- [Brave for Linux](https://brave.com/linux/) is installed from Brave's signed Ubuntu repository.
- KeePassXC is installed from the Ubuntu package archive.

The active `Dell_IVO0536_HDR_D65.icm` profile is included as a local-only file for the `IVO0536` panel. It must be associated with that display and visually checked in the live or installed system. Ubuntu's standard kernel firmware and PipeWire/ALSA profiles are used for Intel graphics/Wi-Fi, Realtek audio, microphone, and Bluetooth. Windows Sound Research/Sonitude effects are not portable and are not represented as reproduced.

## Build host status

The native Windows 11 Pro host has an Intel i5-1135G7 and an active Hyper-V hypervisor. Windows reports `VirtualizationFirmwareEnabled: false` and `HypervisorPresent: true`; the preflight records both values and treats virtualization as available to Windows while Hyper-V is running. The WSL optional feature has been enabled without forcing an immediate restart. Windows reports that a restart is required, and no Ubuntu WSL distribution is installed yet.

The selected build path is Ubuntu 26.04 under WSL 2 with the project and Cubic workspace inside the Linux filesystem. If Cubic cannot extract, mount, customize, and rebuild the exact base ISO there, use the planned local Hyper-V Ubuntu VM fallback. Record the actual Cubic version and proof result below before the full image build.

| Build check | Result |
| --- | --- |
| Host preflight | Implemented and tested; current status 2 because the WSL 2 Ubuntu distribution is not installed |
| Base ISO hash | Matches Canonical's pinned SHA-256 |
| WSL Ubuntu 26.04 | WSL feature enabled; pending Windows restart and distro installation |
| Cubic proof build | Pending |
| Custom ISO validation and VM boot | Pending |
| Profile, Wi-Fi, audio, microphone, Bluetooth checks | Pending |
| SanDisk Ventoy write | Pending; do this only after custom ISO validation |

## Credential handling

The USB may hold an encrypted KeePassXC `.kdbx` vault only if the user provides an existing vault or creates one locally. Never place its master password, browser cookies, account sessions, or plaintext private keys on the USB. A new Ubuntu installation requires signing into Google, OpenAI, GitHub, and other services again; authentication sessions will not be transplanted.

## USB write gate

The user authorized erasing the SanDisk Dual Drive without backup. Re-identify it by model, capacity, bus type, and current drive letter immediately before installing Ventoy. Do not write the USB until the custom ISO hash, structure, boot catalog, VM boot, app launch, and hardware checks have been recorded. The laptop's internal storage is outside this USB task.

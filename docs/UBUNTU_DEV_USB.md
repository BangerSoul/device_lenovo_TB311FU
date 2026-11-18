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

The native Windows 11 Pro host has an Intel i5-1135G7 and an active Hyper-V hypervisor. Windows reports `VirtualizationFirmwareEnabled: false` and `HypervisorPresent: true`; the preflight records both values. Ubuntu 26.04 is installed as a WSL 2 distribution. The ISO and Cubic project remain in WSL's Linux filesystem.

The selected build path is Ubuntu 26.04 under WSL 2 with Cubic 2026.09.110. Cubic extracted and loop-mounted the verified base ISO, opened its custom root filesystem, accepted a harmless `hello` package proof, and regenerated a disposable image. Cubic's first QEMU attempt could not access `/dev/kvm`; the WSL build user was added to the existing `kvm` group, and the retry reached Ubuntu's live “Choose your language” welcome screen. The WSLg terminal did not accept keyboard input, so the package proof was run through `nsenter` in Cubic's active root and mount namespaces.

Disposable proof ISO: `ubuntu-26.04.1-2026.11.18-desktop-amd64.iso`, 6,596,521,984 bytes, SHA-256 `1380cc9a62804dcb2c7cb2c493770fd5e0341306a2a7c60ea8f878378f7fc0fa`. After its VM boot check, the disposable Cubic project and proof ISO were removed to recover build space; this is not the final workstation ISO.

| Build check | Result |
| --- | --- |
| Host preflight | Passed before the full build with 39.63 GB free and the pinned base ISO hash matching; after the full build C: has 8.88 GB free, so avoid making another local ISO copy |
| Base ISO hash | Matches Canonical's pinned SHA-256 |
| WSL Ubuntu 26.04 | Installed and running as WSL 2 |
| Cubic proof build | Passed with Cubic 2026.09.110; extraction, loop mount, custom-root package change, and ISO regeneration succeeded |
| Proof ISO VM boot | Passed after KVM device permissions were corrected; reached Ubuntu live language selection |
| Custom ISO | Built at `~/iso-build/cubic-full/ubuntu-26.04.1-probook440g8-dev-amd64.iso`; 7,864,367,104 bytes; SHA-256 `dd1ea66c312f09ca2a41944c1ba50760bd00fddbec905811e444a423dee52d61` |
| ISO structure | Passed xorriso inspection: ISO 9660/Rock Ridge/Joliet, `/boot.catalog`, BIOS El Torito boot image and UEFI El Torito boot image are present |
| QEMU boot | Reached GRUB and the Ubuntu GDM live-session greeter. Desktop entry and app launches were not verified in QEMU |
| Installed package state | `dpkg-query` confirmed Brave 1.99.57, ChatGPT 26.1111.21308, KeePassXC 2.7.10+dfsg1-2ubuntu1, Git 1:2.53.0-1ubuntu1.1, adb/fastboot 1:34.0.5-12build1, OpenJDK 21.0.13.0.3+1-1~26.04.1, and Python 3.14.3-0ubuntu2 in Cubic's custom root. Antigravity's executable exists and `ldd` reported no missing libraries. These checks establish installation, not successful GUI launch |
| ICC profile | Included at `/usr/share/color/icc/Dell_IVO0536_HDR_D65.icm`; its hash remains in the ignored local asset manifest; display association and visual match await hardware boot |
| Package state audit | `dpkg --audit` produced no findings; the Cubic CD-ROM apt source was restored |
| Physical Wi-Fi, audio, microphone, Bluetooth, JBL, display profile, and app launches | Pending live USB boot on the HP ProBook 440 G8 |
| SanDisk Ventoy write | Next: ISO checksum, boot structure, and QEMU-to-greeter validation passed; re-identify SanDisk immediately before authorized erase |

## Credential handling

The USB may hold an encrypted KeePassXC `.kdbx` vault only if the user provides an existing vault or creates one locally. Never place its master password, browser cookies, account sessions, or plaintext private keys on the USB. A new Ubuntu installation requires signing into Google, OpenAI, GitHub, and other services again; authentication sessions will not be transplanted.

## USB write gate

The user authorized erasing the SanDisk Dual Drive without backup. Re-identify it by model, capacity, bus type, and current drive letter immediately before installing Ventoy. The custom ISO hash, ISO/BIOS/UEFI structure, and QEMU boot to the live greeter are verified; app launch and physical hardware checks require the actual USB on the HP, so perform those immediately after USB creation. Do not select the laptop's internal storage or start the Ubuntu installer.

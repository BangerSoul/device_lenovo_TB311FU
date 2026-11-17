# Design: Plan A GSI and Ubuntu Developer USB

Status: Approved for implementation
Date: 2026-11-18

## Intent

Prepare a reproducible Ubuntu 26.04.1 Desktop AMD64 installer for the HP ProBook 440 G8, and place the exact upstream Lenovo Tab M11 TB311FU GSI source and transformation provenance in the GitHub Plan A documentation before ROM development continues.

## Goals

- Build a locally reproducible Ubuntu ISO with current development tools, Antigravity, the ChatGPT Linux app, Brave, KeePassXC, and the Windows-active display ICC profile.
- Create bootable media on the existing SanDisk USB after the user-authorized erase.
- Make the upstream GSI release downloadable from a Plan A document in `BangerSoul/device_lenovo_TB311FU`.
- Map the related source repositories, build scripts, and generated artifacts to GitHub without uploading credentials, Google Apps binaries, or proprietary firmware blobs.
- Use GitHub Actions for lightweight source and packaging checks, not as an undersized full ISO or AOSP build host.

## Non-goals

- No change to the laptop's internal partitions or Windows installation is part of creating the installer media.
- No passwords, browser cookies, session tokens, or unencrypted private keys will be embedded in the ISO, repository, or USB.
- No claim that Windows-only HP/Sound Research audio effects can be reproduced exactly on Linux.
- No guarantee of zero defects; final claims depend on boot and hardware validation.

## Verified starting state

- The downloaded Canonical file is `ubuntu-26.04.1-desktop-amd64.iso` (6,482,409,472 bytes). Its SHA-256 `601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f` matches Canonical's [26.04.1 SHA256SUMS](https://releases.ubuntu.com/26.04.1/SHA256SUMS).
- Host: HP ProBook 440 G8, Intel Core i5-1135G7, 8 GB RAM, Intel Iris Xe, Intel Wireless-AC 9560, Realtek audio, and about 81 GB free on the internal SSD.
- Intel firmware virtualization is currently off; Windows has no installed WSL distribution. Local Linux build setup therefore requires enabling VT-x in firmware and installing Ubuntu under WSL2 first.
- The active Windows display association maps `Dell_IVO0536_HDR_D65.icm` to the internal `IVO0536` panel. The profile is a local user asset; it can be included in this machine's ISO but will not be published to GitHub.
- The plugged-in 32 GB SanDisk is `D:`. The user authorized formatting it without backup; the GSI image and other current USB contents will be erased.
- The local `vibrant-hertz` workspace is about 12.4 GB, untracked, and has no GitHub remote. Its generated/proprietary artifacts must be inventoried and classified before any source is published.
- Existing Lenovo repositories already provide separate locations for device, vendor, kernel, recovery, Linux port, manifests, and AOSP build scripts. The local copies of the device, vendor, kernel, recovery, and Linux-port repositories are clean.

## Approaches considered

1. **Official ISO plus post-install setup script.** Simplest and easiest to refresh, but the user asked for apps and the profile to be present in the image.
2. **Remastered Ubuntu ISO (selected).** Packages and the local ICC profile are included in the installer image. This requires a Linux build host and each output must be tested; bundled app versions are a dated snapshot.
3. **Persistent live USB.** Runs from the USB without installing Ubuntu, but is slower and is not the selected full developer workstation path.

## Selected design

### Ubuntu image

- Use the verified official Ubuntu 26.04.1 Desktop ISO as the base. Keep its original checksum and record a separate SHA-256 for the custom output.
- After VT-x is enabled, use a local Ubuntu 26.04 WSL2 build workspace and the Cubic Ubuntu ISO customizer. Cubic publishes a 26.04.1 package; first validate it against this exact desktop ISO before adding the full package set.
- Include the ordinary in-kernel Intel graphics/Wi-Fi and Realtek audio support already supplied by Ubuntu. Do not add Windows drivers or unofficial kernel replacements.
- Include a small Android/GSI toolchain suited to this 8 GB laptop (Git, Python, platform-tools, archive/filesystem utilities, and required Java tooling), plus the official Antigravity Linux distribution, official ChatGPT Linux package, and Brave's signed Ubuntu package source.
- Include KeePassXC. The user will create a new encrypted vault on the USB and set its master password themselves; a new OS still needs account reauthentication because browser sessions cannot be safely transplanted.
- Include and import the active `IVO0536` ICC profile. Keep the source file local to the user and omit it from public Git history.
- Use Ubuntu's PipeWire/ALSA device profiles for Realtek speakers, microphone, and Bluetooth headphones. Windows Sound Research/Sonitude audio processing has no matching Linux profile established yet.
- Store a build manifest in the image with base ISO hash, build date, package/app versions, and hashes of locally bundled files. Update applications after installing Ubuntu.

### USB layout

- Install Ventoy to the user-selected SanDisk, which erases its current contents, then place the custom ISO and a small recovery folder on Ventoy's exFAT data partition.
- Ventoy is selected over direct Rufus imaging because its exFAT data partition remains usable for the ISO, ICC profile, and encrypted vault file; Rufus would produce a simpler single-purpose installer. Secure Boot is already off on this laptop.
- Store the ICC profile and instructions on that data partition. Store only a KeePassXC `.kdbx` vault there after the user creates it; never place plaintext credentials or active browser tokens there.
- Secure Boot is currently disabled on this laptop, so Ventoy's Secure Boot enrollment path is not expected to be needed.

### Plan A GSI and GitHub mapping

- Add `docs/PLAN_A_GSI.md` on branch `codex/plan-a-gsi`, based on `lineage-23.2`, with the upstream release, direct download link, exact version, device fit checks, transformation steps, and verification gates.
- Upstream baseline: the unofficial [MisterZtr/LineageOS_gsi release](https://github.com/MisterZtr/LineageOS_gsi/releases/tag/v2026.05.24-lineage23.2), tag `v2026.05.24-lineage23.2`, commit `7bf212f`; its [GAPPS/EXT4 archive](https://sourceforge.net/projects/misterztr-gsi/files/LineageOS/Android%2016/LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z/download) extracts to the 3.2 GB image used locally. The release describes an unofficial Android 16 QPR2 GSI for A/B devices. The release page does not list an archive SHA-256, so the first re-download must be hashed and recorded before transformation.
- The USB's local `.img` is not the pristine upstream image: its `.undo.json` records seven EXT4 directory-entry changes. Recreate that derivative from a clean download with `partitions/strip_system_cellular.py`; verify the output before flashing. The GSI contains Google Apps, so keep the binary upstream and do not commit it or publish a derivative.
- Map code to existing repositories: device tree and GSI transform to `device_lenovo_TB311FU`; proprietary HAL source references to `vendor_lenovo_TB311FU`; kernel work to `kernel_lenovo_TB311FU`; OrangeFox/recovery work to `recovery_lenovo_TB311FU`; mainline Linux work to `linux-lenovo-tb311fu`; source pins to `local_manifests`; and remote AOSP orchestration to `crave_aosp_builder`.
- For the untracked local workspace and large outputs, publish source only after license/secret review. Store local-only artifact paths, upstream URLs, provenance, and SHA-256 values in a manifest; keep OEM firmware, extracted proprietary blobs, app binaries, and GSI images outside public Git.

### GitHub Actions

- Use public-repository standard runners for workflow linting, source checks, GSI transformation validation, and small test outputs. Current standard Linux runners provide 4 CPUs, 16 GB RAM, and 14 GB SSD.
- Do not use a standard runner for a full Android source build or the Ubuntu ISO remaster. GitHub's 150 GB larger runners require a GitHub Team/Enterprise organization and are billable; the current repositories belong to the user's personal account and the chosen route is local.
- Do not upload the 3.45 GB GSI image as a GitHub Release asset (each release asset must be under 2 GiB). Keep public GitHub focused on recipes, source, manifests, and small verification outputs.

## Validation before the USB write

- Validate the Cubic project can rebuild the exact Ubuntu desktop ISO; verify the output file and package manifest.
- Boot the custom ISO in a VM or on this laptop before writing it to USB, then confirm the included applications appear in the installed system.
- Verify that the ICC profile imports for the `IVO0536` panel and that speakers, microphone, Wi-Fi, Bluetooth, and JBL headphones work on Linux. Record the limitation that the Windows audio effects are not replicated.
- Re-check the removable disk model, capacity, and drive letter immediately before Ventoy formats it; do not target the internal SSD.

## Sources checked

- [Ubuntu 26.04.1 ISO and checksums](https://releases.ubuntu.com/26.04.1/)
- [Cubic ISO customizer](https://github.com/PJ-Singh-001/Cubic) and [Ubuntu 26.04.1 Cubic package listing](https://ppa.launchpadcontent.net/cubic-wizard/release/ubuntu/pool/main/c/cubic/)
- [Antigravity Linux requirements](https://antigravity.google/docs/getting-started)
- [OpenAI ChatGPT Linux app support](https://help.openai.com/en/articles/6825453-chatgpt-release-notes)
- [Brave Linux installation](https://brave.com/linux/)
- [Ventoy Secure Boot](https://www.ventoy.net/en/doc_secure.html) and [disk layout](https://www.ventoy.net/en/doc_disk_layout.html)
- [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), [larger runner requirements](https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/manage-larger-runners), and [release asset size limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
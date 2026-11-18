# OrangeFox Recovery for TB311FU — Design

## Intent

Build and validate an OrangeFox recovery for the Lenovo Tab with Clear Case (TB311FU) (`poplar`) as the first stage of the user's custom ROM project. The recovery must support ADB sideload, slot reporting/switching, backup and restore, and USB OTG. It will become the installer and maintenance environment for a later GSI-based clean-install package.

## Current state and evidence

- The device is A/B with dynamic partitions and Virtual A/B metadata, currently boots slot A, and has successfully booted the Plan A LineageOS 23.2 GSI from `system_a`.
- The active `system_a` logical partition is 3,446,353,920 bytes. The current `system_b` logical entry is 478,015,488 bytes; do not assume the two slots are symmetric or attempt slot switching until both slot boot paths are understood.
- The recovery repository currently builds TWRP 12.1. OrangeFox is a selectable CI flavor, but no published OrangeFox image or on-device validation of sideload, slot control, backup/restore, or OTG was found.
- The latest recovery release is a hybrid `vendor_boot` image; repository README claims about `boot_b` do not match that artifact/workflow. The exact install target and recovery boot method are unresolved.
- Device-tree build configuration declares a 9 GiB `super`, while the connected device reports 11,811,160,064 bytes. Resolve this mismatch before using recovery code that inspects or changes dynamic partition metadata.
- No verified stock firmware/recovery package is present in the GSI workspace. This blocks destructive recovery/slot experiments until a tested restore path is available.

## Goals

- Produce an OrangeFox recovery image for the correct TB311FU recovery boot path, based on the existing recovery repository where its device configuration is sound.
- Demonstrate on-device ADB sideload using a harmless test package before the ROM installer is introduced.
- Display the active slot correctly and provide a slot-switch operation whose behavior is verified against TB311FU bootloader and Virtual A/B behavior.
- Back up and restore the explicitly supported partitions and user data, with an integrity check on backup files and a demonstrated restore round-trip.
- Detect, mount, read, and write a USB OTG storage device using a documented filesystem format.
- Preserve logs and build provenance, and keep proprietary firmware and generated recovery binaries out of the public device-tree repository unless their licenses permit distribution.

## Non-goals for this stage

- Building or flashing the ROM installer ZIP.
- Replacing boot, vendor, vbmeta, dtbo, or firmware as part of recovery validation.
- Treating a bootable recovery image as proof that backups, restores, sideload, OTG, or slot control work.
- Testing slot switching or restore on the tablet before a verified restore package and recovery path exist.
- Kernel performance tuning; that is a later, separately gated project.

## Approaches considered

1. **Adapt the existing recovery tree and OrangeFox build flavor (selected).** This reuses the TB311FU TWRP device configuration and CI setup, while auditing the artifact target and correcting the boot/recovery path claims. It is the smallest route to an OrangeFox build and preserves the existing project structure.
2. **Start a fresh OrangeFox device tree.** This could simplify upstream integration but duplicates the existing MediaTek/boot configuration and makes it harder to distinguish recovery fixes from device-tree drift.
3. **Keep TWRP.** The existing project already produces TWRP artifacts, but this does not meet the requested OrangeFox deliverable.

## Design decisions

- Build from the existing recovery repository's OrangeFox flavor, but do not assume that selecting the flavor alone creates a valid OrangeFox image.
- Treat the existing CI `vendor_boot` artifact as the build output to inspect, not as a confirmed install target. The recovery image must match the actual partition and boot method discovered from the device; the README's `boot_b` claim is not accepted as evidence.
- After a verified restore package/path is available, prefer a temporary recovery boot for first device validation if the bootloader supports it. If not, writing the confirmed recovery-bearing partition requires separate explicit owner authorization.
- Establish non-destructive host/build checks first. No recovery image is flashed or booted on-device until a verified stock restore package is available and the owner explicitly authorizes that device operation.
- Slot-switch support is not considered complete until the active slot and bootloader result are observed after a controlled test with recoverable boot images available in both slots. Merely exposing a menu item or running `set_active` is insufficient.
- Backup/restore support is limited to a documented partition set derived from a live partition inventory: present boot-chain partitions (`boot`, `init_boot`, `vendor_boot`, `dtbo`, and vbmeta variants), dynamic-partition metadata and each present logical partition (`system`, `system_ext`, `vendor`, `product`, `odm`), plus userdata when supported. Any omitted partition must be named in the recovery UI/docs; do not claim a full-device restore. A backup must be copied to OTG and hashed; a restore round-trip must be tested only after the restore path gate passes.
- Use exFAT as the primary OTG test filesystem so large backup/image files are not limited by FAT32's per-file size cap. If the recovery build lacks working exFAT support, record that as a failed acceptance item rather than silently switching formats.
- A verified restore package means a Lenovo TB311FU firmware/rescue package matching the tablet SKU/region, with archive integrity and image provenance recorded, all required restore images extractable, and the restore commands reviewed against the live partition map. Device-side restore validation is a later authorized test; until then no recovery/slot write test proceeds.
- The future ROM ZIP is expected to factory-reset userdata. The installer and recovery must clearly warn before formatting user data; no preservation/migration promise is part of a clean install.

## GitHub Actions build preference

- Use GitHub Actions for reproducible recovery builds and validation where runner capacity allows; prefer a manual `workflow_dispatch` for resource-intensive builds until the process is stable.
- Start with read-only token permissions, pin every third-party action to a reviewed full commit SHA, and do not expose PATs, signing keys, firmware archives, GSI images, or private vendor files to the workflow.
- Measure the source sync/build disk, memory, and runtime needs. Standard GitHub-hosted Linux runners currently provide 14 GB storage and 16 GB RAM for public repositories, which may not be enough for a full Android recovery build. If capacity is insufficient, keep build CI opt-in on a configured larger or isolated self-hosted runner and use hosted Actions for source validation and metadata checks.
- Do not upload a recovery image as an Actions artifact until the image contents and redistribution status are reviewed. Repository readers can download workflow artifacts, so a short retention period is not a license or confidentiality boundary.

## Acceptance criteria

1. Build output is identified by hash, image header/ramdisk contents, build manifest revision, and the correct TB311FU target partition.
2. On-device OrangeFox boots without changing active slot or writing unrelated partitions.
3. `adb sideload` transfers and installs a harmless validation ZIP; recovery reports its result and logs show no sideload transport error.
4. Recovery reports the booted slot accurately. A slot-switch test passes only after both target boot paths and restore readiness are independently verified.
5. Backup files are created on OTG storage and their hashes verify. A documented restore round-trip restores the supported backup set and returns the tablet to a bootable state.
6. USB OTG storage is detected, mounted, read, written, safely unmounted, and re-read on the host.
7. Logs, exact commands, image hashes, tested file systems, supported partitions, and known limitations are recorded in the recovery repository documentation.

## Risks and gates

- **No verified stock restore package:** blocks on-device recovery boot, partition restore, slot experiments, and any write to recovery/vendor_boot.
- **Boot target ambiguity:** blocks image packaging until `vendor_boot` versus another target is established from the actual partition map and boot chain.
- **Virtual A/B slot asymmetry:** blocks slot-switch claims until slot B's current partition metadata and bootability are understood.
- **Super geometry mismatch:** blocks dynamic-partition operations until the 9 GiB build constant is reconciled with the observed 11 GiB device size.
- **Backup/restore scope:** restoring the wrong partition or an incompatible image can make the tablet unbootable; restrict restore to the tested, hashed set.

## Follow-on project order

After OrangeFox passes its acceptance gates, create a separate design and plan for the GSI clean-install ZIP using the current transformed GSI plus only provenance-verified device firmware images. Design custom kernel integration as a third project after its Android 16 compatibility, module matching, security patches, and performance criteria have been reviewed.

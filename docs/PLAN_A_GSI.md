# Plan A: reproducible GSI source and transformation

This guide pins the input and the checks needed before a transformed system image is considered a candidate for the Lenovo Tab M11 TB311FU (`poplar`). It does not claim that this GSI is already compatible with the tablet or that a transformed image is safe to flash.

## Pinned upstream input

The selected release is [MisterZtr LineageOS 23.2, tag `v2026.05.24-lineage23.2`](https://github.com/MisterZtr/LineageOS_gsi/releases/tag/v2026.05.24-lineage23.2), at release commit `7bf212f`. The chosen file is [LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z](https://sourceforge.net/projects/misterztr-gsi/files/LineageOS/Android%2016/LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z/download). Its pinned variant is **Android 16 QPR2; A/B; GAPPS; EXT4**.

The release describes this as an unofficial build supplied as-is, says it is for A/B devices, and notes that the experience depends on the device vendor's Treble implementation. It lists separate EXT4 and EROFS downloads; this plan selects EXT4. The release notes say all EXT4 builds are read/write. This is upstream release information, not proof that TB311FU's vendor image, boot chain, partition layout, or firmware is compatible.

The source manifest at `docs/plan_a_sources.json` pins the release tag, commit, archive URL, filename, and variant. It deliberately has `archive_sha256: null` and `status: pending_first_download`: the release does not provide an upstream archive digest in the pinned metadata.

## First clean download and hash record

Download the exact archive from the pinned source URL into a private local build directory. Keep the downloaded archive unchanged. Compute its SHA-256 locally:

```powershell
Get-FileHash .\gsi-build\LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z -Algorithm SHA256
```

```sh
sha256sum ./gsi-build/LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z
```

Record the 64-character lowercase digest, exact filename, source URL, download date, and tool used in the private build record. This is a **locally observed** digest for the bytes downloaded from that source URL; it is **not an upstream signature**, checksum, or proof that the publisher signed those bytes. Only after confirming the filename and URL should the observed digest be copied into `docs/plan_a_sources.json` and the status changed to `pinned`.

Do not use the existing workspace image as the input. Workspace review found that image has already been modified. Re-download the archive, list its contents, extract a fresh image into a separate clean-input directory, and preserve the archive and pristine extracted image unchanged. Keep the clean input and transformed output in the private build directory excluded from Git.

## Device-fit gates

The release being A/B-only is a hard compatibility gate. Before any flash attempt, verify all of the following against the actual TB311FU firmware and bootloader state; do not infer a pass from the product name alone:

1. Confirm the connected tablet identifies as TB311FU / `poplar`, and record the installed vendor and firmware build.
2. Confirm the device uses the A/B slot arrangement required by this release. Check the bootloader-reported slot state and the device's partition metadata; stop if the slot layout is ambiguous or differs.
3. Confirm whether the system uses dynamic partitions or a physical system partition, then verify the target has enough usable capacity for this EXT4 image. Check the real partition map and image size before writing anything.
4. Confirm the device's Treble, vendor interface, system ABI, and Android framework/vendor level are compatible with this Android 16 GSI. Review the exact vendor build and its VNDK/VINTF details; do not assume an Android-version match is sufficient.
5. Record the AVB/vbmeta and boot-chain state, boot image/kernel requirements, and recovery access needed to restore stock firmware. Keep known-good stock firmware and a tested recovery path available before any write.

If any gate is unknown or fails, stop at offline analysis. This plan does not authorize a blind flash, partition resize, AVB change, or bootloader change. Passing these checks makes an image a test candidate; it does not guarantee that all hardware works.

## Clean transform and verification

Use the explicit source and a new output path. First scan only the pristine extracted image, then transform it to a path that does not exist:

```sh
python3 partitions/strip_system_cellular.py --image <pristine-ext4-image> --dry-run
python3 partitions/strip_system_cellular.py --image <pristine-ext4-image> --output <new-transformed-image>
python3 partitions/strip_system_cellular.py --image <new-transformed-image> --verify
```

The first command must not modify its source. Never use `--in-place` for this reproducible build. Keep the pristine input and output separate, and record both SHA-256 digests, the manifest revision, and the transform command in the private build record.

**Verifier gate:** the current verifier is being hardened in Plan A Task 5. Before that change is present, a missing EXT4 or 7-Zip dependency can be reported as a skipped check, so a successful-looking result is not sufficient. After Task 5, require both EXT4 and 7-Zip verification to run and pass; missing tools, parse errors, or a nonzero 7-Zip result must fail the command. Do not flash or distribute an output when any check is skipped, fails, or cannot be reproduced.

After transformation, confirm the expected cellular targets are absent, the filesystem still parses, and the image remains within the verified partition capacity. A passing script check is only one gate; validate boot, display, touch, audio, Wi-Fi, sensors, suspend/resume, charging, encryption, and recovery on the device before calling the ROM stable.

## Artifact and publication policy

The GSI image, Google Apps, firmware, extracted vendor files, APKs, shared libraries, credentials, and generated images must not commit to Git. Do not attach them to GitHub Actions artifacts or releases. Keep downloads, clean inputs, transformed outputs, and detailed build records local; publish only reviewed source, non-secret metadata, and reproducible instructions. See `docs/ARTIFACT_MAP.md` for the sanitized workspace routing map.

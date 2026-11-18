# OrangeFox Recovery for TB311FU Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate an OrangeFox recovery for Lenovo TB311FU with ADB sideload, accurate slot handling, backup/restore, and USB OTG, using GitHub Actions for reproducible builds where runner capacity and artifact licensing allow.

**Architecture:** Keep the device-tree planning and validation on `codex/plan-a-gsi`; make recovery-source/workflow changes in a companion branch of `BangerSoul/recovery_lenovo_TB311FU`. First pin the live partition/boot map and reconcile source claims, then harden a manual OrangeFox workflow, inspect its output before delivery, and finally run gated on-device acceptance checks. The later GSI installer ZIP and custom kernel remain separate follow-on plans.

**Tech Stack:** Android recovery build system (`repo`, `lunch`, `mka`), OrangeFox manifest, GitHub Actions, Python 3 standard-library validation, `unpack_bootimg`/`mkbootimg` tooling, ADB and fastbootd.

**Spec:** `docs/superpowers/specs/2026-11-18-orangefox-tb311fu-design.md`

## Global Constraints

- Device target is Lenovo Tab M11 TB311FU, codename `poplar`.
- Device observations currently show A/B, dynamic partitions, Virtual A/B, active slot A, physical `super` size 11,811,160,064 bytes, `system_a` size 3,446,353,920 bytes, and `system_b` size 478,015,488 bytes.
- Do not infer the recovery-bearing partition from repository names or release filenames; verify it against the live partition map and boot-chain metadata.
- No recovery, slot, vendor, vbmeta, dtbo, or super write is permitted until the restore package/path gate is met and the owner separately authorizes the device operation.
- Keep Lenovo firmware, proprietary vendor files, GSI images, signing keys, credentials, and generated binaries out of Git.
- GitHub Actions workflows use least-privilege token permissions, reviewed action commit SHAs, trusted-source triggers only, and no PATs or signing secrets.
- Standard public GitHub-hosted Linux runners currently have 14 GB SSD and 16 GB RAM; measure required source/build resources and use an isolated configured runner if standard capacity is insufficient.
- Workflow artifacts are downloadable by repository readers. Do not upload/release recovery images containing proprietary content until both the image contents and redistribution rights are reviewed. No automatic GitHub Release is created by a build.
- GitHub Actions should build/validate source where practical; CI success alone is not evidence that OrangeFox features work on the tablet.
- Reference: [GitHub-hosted runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), [artifact access and retention](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts), [secure use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

## Review Focus

- Wrong boot target (`vendor_boot` versus `boot_b` or `recovery`): pin with live partition metadata and inspect the image header before any device test.
- Virtual A/B slot asymmetry: prohibit a slot-switch acceptance claim until both slot boot paths are bootable and the bootloader's behavior is recorded.
- `super` size mismatch (9 GiB in build configuration versus 11 GiB measured): test physical size and metadata group limits independently before updating constants.
- Proprietary image content in CI output: scan/classify build inputs and output before artifact upload or release; test that upload/release remains disabled by default.
- Runner disk/runtime shortage or untrusted workflow input: add capacity preflight and safe input validation, and test the workflow policy before dispatch.

---

### Task 1: Record and validate the TB311FU recovery layout

**Files:**
- Create: `docs/recovery/tb311fu-layout.json`
- Create: `tools/validate_recovery_layout.py`
- Create: `tests/test_recovery_layout.py`
- Modify only after measured values are reconciled: `BoardConfig.mk`, `partitions/super_budget_audit.py`

**Interfaces:**
- `validate_layout(data: dict) -> list[str]` returns validation errors; an empty list means the sanitized layout record is internally consistent.
- The JSON records source/date and verified facts: device identity without serial number, slot scheme, Virtual A/B and dynamic-partition flags, physical super bytes, metadata group limits, and every relevant physical/logical partition name, slot suffix, size, and source of evidence. Unknown values are explicit `null`, never guessed.

- [ ] **Step 1: Write failing tests** named `test_device_identity_is_tb311fu_poplar`, `test_unknown_partition_sizes_are_not_guessed`, `test_super_groups_fit_measured_physical_super`, and `test_serial_or_absolute_host_path_is_rejected`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_recovery_layout.py' -v`; confirm failures before implementing the validator.
- [ ] **Step 3: Capture read-only layout evidence** from ADB/fastbootd and the existing recovery image workflow. Do not change slots or flash anything. Record the command source for each map entry.
- [ ] **Step 4: Implement** `validate_layout(data: dict) -> list[str]` and CLI `python3 tools/validate_recovery_layout.py [layout-path]`, returning 0 only when all required measured fields agree and no sensitive host/device identifiers appear.
- [ ] **Step 5: Reconcile** `BoardConfig.mk` and `partitions/super_budget_audit.py` with the validated physical geometry and metadata group maximum. Add/update tests for the exact constants; do not merely replace 9 GiB with 11 GiB without accounting for metadata and group limits.
- [ ] **Step 6: Run** `python3 -m unittest discover -s tests -p 'test_recovery_layout.py' -v`, `python3 partitions/super_budget_audit.py`, and `git diff --check`; all must pass before selecting an image target.
- [ ] **Step 7: Commit** only the sanitized layout record, validator, tests, and reviewed geometry update as `docs: record verified TB311FU recovery layout`.

### Task 2: Reconcile the recovery tree and boot-target documentation

**Files (companion repository `BangerSoul/recovery_lenovo_TB311FU`, on a dedicated `codex/orangefox-tb311fu` branch):**
- Modify: `README.md`
- Modify: `BoardConfig.mk`
- Modify: `.github/workflows/build-recovery.yml`
- Create: `docs/tb311fu-layout.json` (byte-identical copy of the validated device-tree layout)
- Test: `tests/test_recovery_workflow.py`

**Interfaces:**
- The recovery repository receives a byte-identical copy of `docs/recovery/tb311fu-layout.json` as `docs/tb311fu-layout.json`, pinned to the device-tree commit that produced it.
- The recovery build remains based on the existing TB311FU tree and OrangeFox manifest; build flavor, manifest revision, target, and image identity are emitted as build metadata.

- [ ] **Step 1: Write failing workflow/documentation tests** named `test_orangefox_target_and_artifact_names_are_consistent`, `test_build_does_not_claim_boot_b_without_layout_evidence`, and `test_super_size_matches_validated_layout`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_recovery_workflow.py' -v`; confirm the current README/workflow inconsistency is detected.
- [ ] **Step 3: Correct** recovery documentation and configuration from the measured layout. Preserve explicit `null`/unsupported features rather than claiming `boot_b`, sideload, slot-switch, backup/restore, or OTG support without evidence.
- [ ] **Step 4: Make image assembly fail closed:** missing DTB, recovery ramdisk, platform ramdisk, repacker failure, empty output, wrong image header, or target-name mismatch must stop the build. Remove `|| true` from required inputs and do not silently fall back to stale files.
- [ ] **Step 5: Run** `python3 -m unittest discover -s tests -p 'test_recovery_workflow.py' -v` and the layout validator against the copied, pinned manifest; require all to pass.
- [ ] **Step 6: Commit** the companion-repository changes as `fix: align TB311FU recovery target with measured layout`.

### Task 3: Make the OrangeFox build reproducible in GitHub Actions

**Files (companion repository):**
- Modify: `.github/workflows/build-recovery.yml`
- Create: `build/orangefox-build.json`
- Create: `tests/test_orangefox_ci_policy.py`
- Optional create after runner capacity is known: `.github/workflows/orangefox-build-self-hosted.yml`

**Interfaces:**
- Manual build inputs: `target` and `build_type`, both choices from a fixed allowlist and passed through environment variables, never interpolated directly into shell source. Manifest and source commits are pinned in `build/orangefox-build.json`, not supplied as free-form dispatch input.
- Build metadata JSON records recovery flavor, manifest commit, device-tree commit, target, toolchain/build host, image SHA-256, and build timestamp.
- Workflow outputs a build summary by default. Binary upload is disabled unless an explicit repository-level `ORANGEFOX_ARTIFACT_REVIEWED=true` gate is set after license/content review.

- [ ] **Step 1: Write failing tests** named `test_build_is_manual_and_uses_allowlisted_inputs`, `test_actions_are_pinned_to_full_commit_sha`, `test_token_permissions_are_read_only`, `test_workflow_has_no_secret_or_firmware_inputs`, `test_release_and_artifact_upload_are_disabled_by_default`, and `test_capacity_preflight_fails_clearly`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_orangefox_ci_policy.py' -v`; verify the current broad `contents: write`, movable action tags, manual release publishing, and artifact upload fail policy checks.
- [ ] **Step 3: Add a capacity preflight** that records free disk, memory, and source-sync size estimate. Use a standard hosted runner only if measurements fit; otherwise fail with an actionable message and route the manual build to an explicitly configured isolated runner label.
- [ ] **Step 4: Harden the build workflow:** retain `workflow_dispatch`; use `contents: read`; pin all actions to reviewed full SHAs; validate inputs against fixed choices; build only the selected OrangeFox target; remove automatic Release creation; never download firmware/GSI/proprietary blobs using credentials.
- [ ] **Step 5: Produce build metadata and checksums** for local/private-runner output. Keep the artifact on the runner by default. Enable Actions upload only after the exact image's content/license review, with minimum retention; do not treat short retention as access control.
- [ ] **Step 6: Validate** with `python3 -m unittest discover -s tests -p 'test_orangefox_ci_policy.py' -v`, `actionlint .github/workflows/build-recovery.yml`, and a manual trusted-branch dry-run/capacity preflight. The dry-run must not publish a release or upload a binary.
- [ ] **Step 7: Commit** the workflow hardening and metadata changes as `ci: build OrangeFox with pinned and gated workflow`.

### Task 4: Inspect recovery images and prepare non-destructive acceptance tools

**Files (companion repository):**
- Create: `tools/inspect_recovery_image.py`
- Create: `tests/test_inspect_recovery_image.py`
- Create: `tests/fixtures/recovery_headers/` with synthetic header fixtures only
- Modify: `README.md`

**Interfaces:**
- `inspect_image(image_path: Path, expected_target: str, layout: dict) -> dict` returns parsed header version, page/ramdisk/DTB sizes, target compatibility, SHA-256, and validation status; malformed images or unknown target mappings raise a validation error.
- CLI: `python3 tools/inspect_recovery_image.py --image <path> --target <target> --layout <layout.json>`; exit 0 only if header, target, size, required ramdisks, and image hash all pass.

- [ ] **Step 1: Write failing tests** named `test_valid_image_passes_for_verified_target`, `test_wrong_partition_target_fails`, `test_truncated_or_malformed_header_fails`, `test_missing_required_ramdisk_fails`, and `test_output_hash_is_recorded`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_inspect_recovery_image.py' -v`; confirm failures before implementation.
- [ ] **Step 3: Implement** image inspection using the Android boot image tools emitted by the pinned build, not heuristic filenames. Reject images that cannot be unpacked or do not match the validated device layout.
- [ ] **Step 4: Add a harmless sideload smoke package** with no partition-write commands. Validate its ZIP structure and SHA-256 on the host; document how to use it only after recovery boot is authorized.
- [ ] **Step 5: Run** `python3 -m unittest discover -s tests -p 'test_inspect_recovery_image.py' -v`, inspect the generated image locally, and confirm the output manifest contains no host paths, serials, credentials, or unrelated firmware.
- [ ] **Step 6: Commit** the inspector, synthetic fixtures, smoke package source, and instructions as `test: inspect OrangeFox image and sideload transport`.

### Task 5: Validate OrangeFox on TB311FU behind the restore gate

**Files:**
- Modify: `docs/PLAN_A_GSI.md`
- Modify: `docs/recovery/tb311fu-layout.json`
- Create: `docs/recovery/orangefox_acceptance.md`
- Local only: signed/official stock restore archive, image backups, OrangeFox test image, and detailed test logs

**Interfaces:**
- Acceptance record fields: firmware SKU/build, recovery image SHA-256, tested boot method and exact target, active slot before/after, tested OTG filesystem, backup partition set, backup hashes, restore result, sideload smoke result, and limitations.
- No serial number, proprietary image bytes, or absolute host path is committed.

- [ ] **Step 1: Verify restore readiness** by checking an exact TB311FU firmware/rescue package, archive integrity, image extraction, and documented restore commands against the validated layout. Stop if package provenance/model/region or required image coverage is uncertain.
- [ ] **Step 2: Obtain separate explicit owner authorization** before any recovery boot/write, slot change, or restore test; plan approval alone does not authorize device writes.
- [ ] **Step 3: Boot OrangeFox** using the supported temporary method if available; otherwise write only the confirmed recovery-bearing partition after recording its original backup hash. Verify active slot is unchanged and no unrelated partition was written.
- [ ] **Step 4: Test ADB sideload** with the harmless validation ZIP and record recovery logs, host exit status, and package hash.
- [ ] **Step 5: Test OTG exFAT** by mounting a test drive, writing a non-sensitive file, safely unmounting, and verifying its hash from the host.
- [ ] **Step 6: Test backup/restore** only for the partition set declared supported by the recovery. Hash backup files, restore from OTG, verify hashes/bootability, and record every omitted partition. Do not switch slots unless both slot boot paths are known-good and restore readiness is rechecked.
- [ ] **Step 7: Update** acceptance status with measured results; mark any failed/unavailable feature as unsupported rather than passing based on menu presence.
- [ ] **Step 8: Review** the artifact's license/content classification before enabling any GitHub Actions binary artifact or public release.

## Handoff

This plan covers OrangeFox only. After its acceptance gates pass, write separate plans for (1) the GSI-based full clean-install ZIP and (2) custom kernel security/Android 16 compatibility/performance integration. The ZIP must not include unverified partitions; kernel integration remains blocked until the existing integrity-bypass patches have been reviewed and the required vendor modules are proven compatible.

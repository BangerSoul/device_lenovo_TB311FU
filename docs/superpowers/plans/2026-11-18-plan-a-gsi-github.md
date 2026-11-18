# Plan A GSI Sources and Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin the upstream GSI provenance, safely map the current workspace and its artifacts to the Lenovo GitHub repositories, and make the transformation checks fail closed before further ROM work.

**Architecture:** Store exact upstream details and repository roles in a small JSON manifest; inventory local files by relative path, size, and hash, then classify them before publishing a sanitized map. Add lightweight standard-library tests and GitHub Actions checks. Keep all GSI images, Google Apps, firmware, generated outputs, credentials, and app binaries local.

**Tech Stack:** Markdown, JSON, Python 3 standard-library `unittest`, GitHub Actions on `ubuntu-24.04`, and the existing `partitions/strip_system_cellular.py` transformer.

**Spec:** `docs/superpowers/specs/2026-11-18-ubuntu-gsi-dev-usb-design.md`

## Global Constraints

- Target device is Lenovo Tab with Clear Case (TB311FU), codename `poplar`.
- Upstream GSI is unofficial LineageOS 23.2 Android 16 QPR2, A/B, GAPPS/EXT4, release tag `v2026.05.24-lineage23.2`, commit `7bf212f`.
- Exact archive URL: `https://sourceforge.net/projects/misterztr-gsi/files/LineageOS/Android%2016/LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z/download`.
- The release page publishes no archive SHA-256. Record the observed digest and source URL on the first clean download; do not describe that locally calculated digest as an upstream signature.
- Do not commit or publish the GSI image, Google Apps, extracted vendor firmware, credentials, cookies, private keys, or generated binary outputs.
- Do not upload the untracked workspace wholesale. Map its files and repository destinations only after classification and license/secret review.
- Keep public docs free of absolute local Windows paths and private asset contents.

## Review Focus

- Archive hash and state disagree: tests require a null hash only with `pending_first_download`, and a pinned status only with a valid 64-character lowercase SHA-256.
- Release metadata drifts: tests pin the exact tag, commit, archive URL, and variant.
- A GSI or Google Apps artifact is marked public: tests require both to remain non-redistributable.
- A local workspace file is unmapped or unclassified: inventory tests require complete file coverage; the public artifact map must show no unreviewed entries.
- Transformation tools are absent, fail, or cannot parse the image: regression tests require these conditions to fail instead of being reported as successful verification.
- Binary or secret content enters Git: final review checks the staged file list and diff before each commit.

---

### Task 1: Add the machine-readable Plan A source manifest

**Files:**
- Create: `docs/plan_a_sources.json`
- Create: `tools/validate_plan_a_sources.py`
- Test: `tests/test_plan_a_sources.py`

**Interfaces:**
- `validate_manifest(data: dict) -> list[str]` returns validation errors; an empty list means valid.
- Manifest fields: `device`, `source.tag`, `source.commit`, `source.archive_url`, `source.variant`, `source.archive_sha256`, `source.status`, `artifacts.gsi.redistribute`, `artifacts.google_apps.redistribute`, `repositories[]` with `name/url/role`, and `local_artifacts[]`.
- CLI: `python3 tools/validate_plan_a_sources.py [manifest-path]`; default is `docs/plan_a_sources.json`; exit 0 on valid input and 1 on errors.

- [ ] **Step 1: Write failing tests** named `test_source_pin_matches_release`, `test_archive_hash_state_is_consistent`, `test_pinned_hash_is_64_lowercase_hex`, `test_gsi_and_google_apps_are_not_publishable`, and `test_required_repositories_have_url_and_role`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_plan_a_sources.py' -v`; confirm the tests fail before the manifest and validator exist.
- [ ] **Step 3: Implement** the manifest and standard-library validator. Permit `archive_sha256: null` only with `status: pending_first_download`; require a 64-character lowercase hex digest with `status: pinned`. Include exactly these repositories and URLs: `BangerSoul/device_lenovo_TB311FU` (device tree and GSI transform), `BangerSoul/vendor_lenovo_TB311FU` (vendor source references), `BangerSoul/kernel_lenovo_TB311FU` (kernel), `BangerSoul/recovery_lenovo_TB311FU` (recovery), `BangerSoul/linux-lenovo-tb311fu` (mainline Linux), `BangerSoul/local_manifests` (source pins), and `BangerSoul/crave_aosp_builder` (remote AOSP orchestration).
- [ ] **Step 4: Run** the focused tests and `python3 tools/validate_plan_a_sources.py`; require both to pass.
- [ ] **Step 5: Commit** as `docs: pin Plan A GSI source metadata`.

### Task 2: Inventory and classify the existing local workspace

**Files:**
- Create: `tools/inventory_workspace.py`
- Create: `tests/test_workspace_inventory.py`
- Create: `docs/ARTIFACT_MAP.md`
- Modify: `.gitignore` to exclude `.local-artifact-inventory.json`

**Interfaces:**
- `inventory_workspace(root: Path, existing_classifications: dict[str, str] | None = None) -> list[dict]` records each file's relative POSIX path, byte size, SHA-256, and classification without storing file contents or absolute root paths.
- CLI: `python3 tools/inventory_workspace.py --root <workspace-root> --output .local-artifact-inventory.json [--check]`; it preserves prior classifications by relative path, defaults new rows to `unclassified`, and `--check` exits 1 while any row is unclassified. The output stays ignored and local.
- Classification values: `source`, `test`, `documentation`, `configuration`, `generated_binary`, `third_party`, `sensitive_or_license_review`, `cache`, or `unclassified`. No row may remain `unclassified` at handoff.

- [ ] **Step 1: Write failing tests** named `test_inventory_covers_each_file`, `test_paths_are_relative_and_content_is_not_copied`, `test_git_metadata_is_excluded`, `test_existing_classification_is_preserved_on_rescan`, and `test_check_rejects_unclassified_rows`, using temporary fixture directories.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_workspace_inventory.py' -v`; confirm failure before implementation.
- [ ] **Step 3: Implement** the inventory function and CLI using only the Python standard library. Hash files in chunks; exclude only Git metadata, and classify Python cache files as `cache`.
- [ ] **Step 4: Run** the inventory against the current workspace. Manually classify every entry, then rerun it so classifications are preserved; require `--check` to pass before documenting the inventory. Map every top-level directory and root-level asset group to a GitHub repository or a named local-only reason.
- [ ] **Step 5: Write** `docs/ARTIFACT_MAP.md` as a sanitized directory/file-group map with counts, destination repository, and publication status. Include `boot_vector`, `deployment`, `diagnostics`, `kernel_recovery`, `linux_bringup_backup`, `overlay_build`, `partitions`, `pmos_download`, `pmos_packaging`, `pmos_postmarketos_backup`, `rootfs_staging`, `telephony`, `tests`, `ui_sanitization`, `.agents`, `__pycache__`, and root-level files. Mark images, APKs, shared libraries, screenshots, account configs, and third-party firmware as local-only unless individually cleared.
- [ ] **Step 6: Verify** the inventory has no unclassified rows and the public map contains no absolute paths, file contents, secrets, or unapproved binary destinations; run the focused tests and `git diff --check`.
- [ ] **Step 7: Commit** only the inventory code, tests, ignore rule, and sanitized map as `docs: map local artifacts and repository destinations`.

### Task 3: Publish the Plan A download and transformation guide

**Files:**
- Create: `docs/PLAN_A_GSI.md`
- Modify: `tests/test_plan_a_sources.py`

**Interfaces:**
- `docs/PLAN_A_GSI.md` is the user-facing source and reproducibility entry point.
- Tests named `test_plan_guide_pins_variant_and_links`, `test_plan_guide_explains_hash_provenance`, and `test_plan_guide_forbids_binary_publication` pin its required statements.

- [ ] **Step 1: Add the failing documentation assertions** and run `python3 -m unittest discover -s tests -p 'test_plan_a_sources.py' -v`.
- [ ] **Step 2: Write** the guide with links to the exact GitHub release and SourceForge archive, A/B and EXT4/GAPPS variant, first-download hash procedure, device-fit gates, and no-binary-publication policy.
- [ ] **Step 3: Explain** that the existing local image was modified; recreate it from a clean archive using `partitions/strip_system_cellular.py` with an explicit source and new output path, then require the hardened verifier to pass.
- [ ] **Step 4: Run** the focused tests and manifest validator; inspect `git diff --check` and `git status --short` to confirm only allowed text/source files are staged.
- [ ] **Step 5: Commit** as `docs: add Plan A GSI download and artifact map`.

### Task 4: Add lightweight GitHub Actions validation

**Files:**
- Create: `.github/workflows/plan-a-source-validation.yml`

**Interfaces:**
- Run on pull requests and pushes to `codex/plan-a-gsi` with path filters for `.github/workflows/plan-a-source-validation.yml`, `docs/plan_a_sources.json`, `docs/PLAN_A_GSI.md`, `docs/ARTIFACT_MAP.md`, `tools/validate_plan_a_sources.py`, `tools/inventory_workspace.py`, `partitions/strip_system_cellular.py`, `tests/test_plan_a_sources.py`, `tests/test_workspace_inventory.py`, and `tests/test_strip_system_cellular.py`.
- Use `ubuntu-24.04`, `actions/checkout@v4`, `permissions: contents: read`, and `timeout-minutes: 10`.
- Run exactly: `python3 -m unittest discover -s tests -p 'test_plan_a_sources.py' -v`, `python3 -m unittest discover -s tests -p 'test_workspace_inventory.py' -v`, `python3 -m unittest discover -s tests -p 'test_strip_system_cellular.py' -v`, and `python3 tools/validate_plan_a_sources.py`; upload no artifacts.

- [ ] **Step 1: Add the workflow** with the exact triggers, path filters, read-only permission, runner, timeout, and commands above.
- [ ] **Step 2: Validate** workflow YAML with an available parser or `actionlint`; if neither is installed, rely on the first GitHub Actions run for syntax validation.
- [ ] **Step 3: Run** every workflow command locally and require success.
- [ ] **Step 4: Commit** as `ci: validate Plan A sources and transformation checks`, then inspect the Actions run.

### Task 5: Harden GSI transformation and verification behavior

**Files:**
- Modify: `partitions/strip_system_cellular.py`
- Create: `tests/test_strip_system_cellular.py`

**Interfaces:**
- `verify_image_with_ext4(path: str) -> tuple[bool, list[str]]` returns false when the EXT4 library is missing or the image cannot be parsed/scanned.
- `verify_image_with_7z(path: str) -> tuple[bool, list[str]]` returns false when 7-Zip is missing, exits nonzero, or cannot list the image.
- The CLI exits 0 only after every required verifier completes and passes; incomplete checks return exit 1.
- `--dry-run` scans the source image without changing any file and rejects the ambiguous `--dry-run --output` combination.
- `--output` must differ from the source and must not overwrite an existing file.

- [ ] **Step 1: Write failing unit tests** named `test_missing_ext4_is_failure`, `test_ext4_parse_error_is_failure`, `test_missing_7z_is_failure`, `test_7z_nonzero_exit_is_failure`, `test_dry_run_does_not_create_or_modify_output`, `test_existing_output_is_not_overwritten`, and `test_failed_post_transform_verification_returns_nonzero`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_strip_system_cellular.py' -v`; confirm failures expose the current silent-skip and dry-run/output behavior.
- [ ] **Step 3: Implement** fail-closed verifier results, explicit CLI status propagation, dry-run argument validation, and output collision checks. Do not change the target purge list in this task.
- [ ] **Step 4: Run** the focused tests; require missing tools, parse errors, and nonzero 7-Zip results to fail rather than pass.
- [ ] **Step 5: Commit** as `fix: fail closed on incomplete GSI verification`.

### Task 6: Re-download, pin, transform, and verify the pristine GSI

**Files:**
- Modify: `docs/plan_a_sources.json`
- Modify: `docs/PLAN_A_GSI.md`
- Modify: `docs/ARTIFACT_MAP.md`
- Local only: upstream `.7z`, extracted `.img`, transformed `.img`, and local inventory/build record

**Interfaces:**
- No GSI binary is added to GitHub.
- Set `source.archive_sha256` to the locally observed digest and `source.status` to `pinned` only after calculating it from the exact downloaded archive.

- [ ] **Step 1: Download** the exact SourceForge archive into a local build directory; confirm the archive filename and release contents.
- [ ] **Step 2: Calculate** SHA-256 and pin it as observed provenance, not as an upstream signature; run the manifest tests and validator.
- [ ] **Step 3: Extract** the clean image, run `--dry-run` on the source only, then transform to a new non-existing output path.
- [ ] **Step 4: Run** both required verifiers on the output; stop if either verifier is missing, errors, or finds a target. Record source and output hashes in the local build record and non-secret GitHub artifact map.
- [ ] **Step 5: Commit** metadata and documentation only as `docs: pin observed GSI archive hash`; inspect the staged file list to ensure no image, Google Apps, firmware, key, or local inventory dump is included.

## Handoff

Finish Plan A source mapping and transformer hardening before continuing with ROM development. Keep all GSI image files local.

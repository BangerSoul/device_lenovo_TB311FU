# Plan A GSI GitHub Sources Implementation Plan

> **For agentic workers:** Implement this plan task by task. Each step has a checkable result; do not upload the GSI binary or application credentials.

**Goal:** Make Plan A's exact upstream GSI source, transformation, repository map, and safe artifact policy available on GitHub before further ROM development.

**Architecture:** Keep source metadata in a small JSON manifest, explain it in Markdown, validate it with Python's standard library, and run that validation in a small GitHub Actions job. Download and transform the large GSI locally; do not publish it as a repository or release asset.

**Tech Stack:** Markdown, JSON, Python 3 standard library `unittest`, GitHub Actions on `ubuntu-26.04`, and the existing `partitions/strip_system_cellular.py` script.

**Spec:** `docs/superpowers/specs/2026-11-18-ubuntu-gsi-dev-usb-design.md`

## Global Constraints

- Target device is Lenovo Tab M11 TB311FU, codename `poplar`.
- Upstream GSI is unofficial LineageOS 23.2 Android 16 QPR2, A/B, GAPPS/EXT4, release tag `v2026.05.24-lineage23.2`, commit `7bf212f`.
- Exact archive URL: `https://sourceforge.net/projects/misterztr-gsi/files/LineageOS/Android%2016/LineageOS-23.2-20260524-GAPPS-EXT4-GSI.7z/download`.
- No upstream SHA-256 is listed on the checked release page; calculate and record it on the first download before use.
- Do not commit or publish the GSI image, Google Apps, extracted vendor firmware, credentials, cookies, or private keys.
- Preserve generated GSI images locally; GitHub Actions must not upload large images or binaries.
- Keep public docs free of absolute local Windows paths and private asset content.

## Review Focus

- Missing or malformed GSI archive SHA-256: validator must reject any non-null value that is not exactly 64 lowercase hexadecimal characters.
- GSI source link or tag drift: tests must pin the exact tag, commit, and archive filename in the manifest.
- Redistribution mistakes: tests must fail if the GSI or Google Apps is marked for public upload.
- Incomplete repository mapping: tests must require a repository URL and role for every listed TB311FU source repository.
- Accidental sensitive or binary files: review the final Git diff and tracked file list; only documentation, source metadata, tests, and workflow files may be committed in this plan.

---

### Task 1: Add and validate the machine-readable Plan A source manifest

**Files:**
- Create: `docs/plan_a_sources.json`
- Create: `tools/validate_plan_a_sources.py`
- Test: `tests/test_plan_a_sources.py`

**Interfaces:**
- `validate_manifest(data: dict) -> list[str]` returns validation errors; an empty list means the manifest is valid.
- CLI: `python3 tools/validate_plan_a_sources.py [manifest-path]`; default path is `docs/plan_a_sources.json`, exit 0 on valid input and 1 on errors.

- [ ] **Step 1: Write failing `unittest` cases** named `test_exact_gsi_source_pin`, `test_archive_sha_is_null_or_64_hex`, `test_google_apps_are_not_public_artifacts`, and `test_repo_entries_have_url_and_role`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s tests -p 'test_plan_a_sources.py' -v`; confirm the tests fail because the manifest and validator do not exist.
- [ ] **Step 3: Implement** the JSON manifest and standard-library validator. Pin the tag, short commit, exact SourceForge archive URL, expected variant, and `redistribute: false`; leave the archive hash null with status `pending_first_download` until a fresh archive is downloaded and hashed.
- [ ] **Step 4: Run** `python3 -m unittest discover -s tests -p 'test_plan_a_sources.py' -v` and `python3 tools/validate_plan_a_sources.py`; both must pass.
- [ ] **Step 5: Commit** as `docs: pin Plan A GSI source metadata`.

### Task 2: Publish Plan A download and artifact mapping docs

**Files:**
- Create: `docs/PLAN_A_GSI.md`
- Create: `docs/ARTIFACT_MAP.md`
- Modify: `docs/plan_a_sources.json` only if a validation issue requires it

**Interfaces:**
- `docs/PLAN_A_GSI.md` is the user-facing download and transformation entry point.
- `docs/ARTIFACT_MAP.md` maps code repositories and classifies local/generated artifacts; no binary content is embedded.

- [ ] **Step 1: Write failing documentation assertions** in `tests/test_plan_a_sources.py` for the release tag, direct archive URL, A/B and EXT4 constraints, and the no-binary-publication notice.
- [ ] **Step 2: Run** the same focused `unittest` command and confirm the new assertions fail.
- [ ] **Step 3: Write** the docs. `PLAN_A_GSI.md` must link to both the GitHub release and SourceForge archive; explain first-download hashing; state that the local `.img` was modified and must be recreated from a clean source with `partitions/strip_system_cellular.py --output <new-image>` and verified with `--verify`.
- [ ] **Step 4: Map** `device_lenovo_TB311FU`, `vendor_lenovo_TB311FU`, `kernel_lenovo_TB311FU`, `recovery_lenovo_TB311FU`, `linux-lenovo-tb311fu`, `local_manifests`, and `crave_aosp_builder` to their roles. Add a row for the untracked local workspace as `local-only / inventory required`; do not publish its contents in bulk.
- [ ] **Step 5: Run** the focused test and validator; review `git diff --check` and `git status --short` to confirm there are no binary or secret files.
- [ ] **Step 6: Commit** as `docs: add Plan A GSI and artifact map`.

### Task 3: Add lightweight GitHub Actions validation

**Files:**
- Create: `.github/workflows/plan-a-source-validation.yml`

**Interfaces:**
- The workflow runs for pull requests and pushes to `codex/plan-a-gsi` when source metadata, docs, validator, tests, or the workflow changes.
- The job uses `ubuntu-26.04`, checks out the repository, runs the focused `unittest` command and the validator, and uploads no artifacts.

- [ ] **Step 1: Add the workflow** with read-only repository permissions and a bounded timeout.
- [ ] **Step 2: Validate YAML** with an available YAML parser or `actionlint`; if neither is installed, use the workflow's first GitHub Actions run as the syntax check.
- [ ] **Step 3: Run** the same test and validator commands locally.
- [ ] **Step 4: Commit** as `ci: validate Plan A source metadata` and inspect the resulting Actions run.

### Task 4: Re-download and pin the pristine GSI archive before ROM work

**Files:**
- Modify: `docs/plan_a_sources.json`
- Modify: `docs/PLAN_A_GSI.md`
- Local only: downloaded `.7z`, extracted `.img`, and stripped output `.img`

**Interfaces:**
- No GSI binary is added to Git.
- The manifest's `archive_sha256` becomes the calculated 64-character digest; the source status changes to `pinned`.

- [ ] **Step 1: Download** the exact SourceForge archive to a local build directory and confirm the archive filename and release contents.
- [ ] **Step 2: Calculate** SHA-256 and store it in the manifest; re-run the validator and focused tests.
- [ ] **Step 3: Extract** the archive, run a dry scan, create a separate stripped output with `--output`, and run `--verify` on that output.
- [ ] **Step 4: Record** source and output hashes locally and in the non-secret artifact map; do not upload either image.
- [ ] **Step 5: Commit** only the new metadata/documentation changes as `docs: pin downloaded GSI archive hash`.

## Handoff

Finish this plan before starting the Ubuntu ISO plan. The Plan A document and exact source link must be present on GitHub first; the large GSI files remain local.
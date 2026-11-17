# Local workspace artifact map

Inventory snapshot: 2026-11-18. The private inventory covers 1,031 entries from the existing `vibrant-hertz` workspace. It stores relative paths, sizes, SHA-256 digests, and classifications in an ignored local report; that report is not committed. This document exposes group counts and routing only. It contains no file contents, absolute paths, or per-file digests.

## Publication rules

- The GSI and Google Apps artifacts are not redistributed. The source manifest pins the upstream release and records the archive digest as pending until the first download.
- Images, APKs, shared libraries, screenshots, root filesystem exports, account or security configuration, and third-party firmware remain local unless each item is reviewed and explicitly cleared.
- Source candidates are not published automatically. They need individual provenance, license, secret, and relevance review before being copied into a destination repository.
- Repository names below refer to the seven repositories listed in `plan_a_sources.json`. A suggested destination does not mean an upload has occurred.

## Directory and file-group routing

| Local group | Entries | Bytes | Inventory classifications | Destination | Publication status |
|---|---:|---:|---|---|---|
| `.agents` | 528 | 3,222,502 | 526 configuration; 2 cache | Local-only | Agent instructions and workspace metadata; do not publish. |
| `__pycache__` | 1 | 9,252 | 1 cache | Local-only | Disposable cache. |
| Root-level files | 26 | 48,530,016 | 4 source; 2 test; 2 configuration; 7 generated binary; 11 sensitive/license review | Mixed: source/tests may map to `device_lenovo_TB311FU`; other items stay local | Per-file review required. Binaries and sensitive/license-review entries stay local. |
| `boot_vector` | 9 | 33,751,475 | 4 source; 1 generated binary; 4 cache | `kernel_lenovo_TB311FU` or `device_lenovo_TB311FU` for reviewed source | Source is a candidate; generated image and caches stay local. |
| `deployment` | 28 | 362,807,783 | 22 source; 3 generated binary; 2 sensitive/license review; 1 cache | `device_lenovo_TB311FU` for reviewed source | Source candidate pending review; binaries and sensitive entries stay local. |
| `diagnostics` | 5 | 119,184 | 2 source; 1 documentation; 2 cache | `device_lenovo_TB311FU` | Source and docs are candidates; caches stay local. |
| `kernel_recovery` | 8 | 202,963 | 2 source; 1 test; 2 documentation; 3 cache | `kernel_lenovo_TB311FU` and `recovery_lenovo_TB311FU` | Source/docs/tests are candidates pending review; caches stay local. |
| `linux_bringup_backup` | 52 | 24,766,175 | 13 source; 2 test; 24 configuration; 7 generated binary; 6 sensitive/license review | Local-only backup; reviewed source may later map to `linux-lenovo-tb311fu` or `device_lenovo_TB311FU` | No bulk upload; contains build and configuration backups. |
| `overlay_build` | 7 | 30,813 | 2 configuration; 1 generated binary; 4 sensitive/license review | Local-only | Review and rebuild from approved sources before considering publication. |
| `partitions` | 12 | 295,718,844 | 5 source; 1 test; 1 generated binary; 5 cache | `device_lenovo_TB311FU` for reviewed source/tests | Image and caches stay local; source is a candidate. |
| `pmos_download` | 8 | 5,271,628,638 | 6 source; 2 third-party | Local-only | Download/build material includes third-party data and unrelated device material; no bulk upload. |
| `pmos_packaging` | 96 | 16,166,795 | 55 source; 30 configuration; 1 sensitive/license review; 10 cache | `linux-lenovo-tb311fu` and `device_lenovo_TB311FU` for reviewed components | Candidate source/configuration pending provenance and license review; caches stay local. |
| `pmos_postmarketos_backup` | 100 | 14,494,570 | 31 source; 34 configuration; 7 generated binary; 28 sensitive/license review | Local-only backup; reviewed source may map to `linux-lenovo-tb311fu` or `device_lenovo_TB311FU` | No bulk upload; configuration, binaries, and sensitive entries stay local. |
| `rootfs_staging` | 82 | 4,327,633,928 | 4 source; 27 configuration; 1 generated binary; 46 sensitive/license review; 4 cache | Local-only | Root filesystem staging and account/security configuration; do not publish. |
| `telephony` | 4 | 29,289 | 1 source; 2 configuration; 1 cache | `device_lenovo_TB311FU` for reviewed source/configuration | Candidate pending review; cache stays local. |
| `tests` | 57 | 1,859,114 | 29 test; 28 cache | `device_lenovo_TB311FU` | Tests are candidates; caches stay local. |
| `ui_sanitization` | 8 | 60,443 | 3 source; 3 configuration; 1 sensitive/license review; 1 cache | `device_lenovo_TB311FU` for reviewed source | Configuration/sensitive entries need review; cache stays local. |

## Inventory status

The completed private inventory has zero `unclassified` entries. Its classification totals are 152 source, 35 test, 3 documentation, 650 configuration, 28 generated binary, 2 third-party, 99 sensitive/license review, and 62 cache entries. These labels describe the local scan; they do not grant redistribution rights or certify that source candidates are free of credentials.

The workspace scan is an inventory aid, not a release manifest. Before any artifact is copied, confirm its source, license, device relevance, and contents. Keep GSI/GApps and other restricted downloads out of GitHub and CI artifacts.

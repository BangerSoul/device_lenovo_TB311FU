#!/usr/bin/env python3
"""
Master E2E Test Suite Runner for Lenovo Tab with Clear Case (poplar / TB311FU)
Engineering Verification: Dynamic Partitions, Hardware Remediations, AVB 2.0 & GKI
Discovers, executes, and aggregates results across Tiers 1-4 and Features F1-F21.
"""

import unittest
import os
import sys
import time
import argparse
import json
import re
import subprocess

# Ensure tests/ directory is in sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import tier1_feature_tests as t1
import tier2_boundary_tests as t2
import tier3_combination_tests as t3
import tier4_workload_scenarios as t4

# Feature Inventory definitions
FEATURES = {
    "F1": "Torch / Flashlight State Audit & QS Suppression",
    "F2": "Wi-Fi Subsystem CONFIG_RFKILL=m & WMT Diagnostics",
    "F3": "Bluetooth Stack /dev/stpbt & NVData MAC Persistence",
    "F4": "Backlight PWM Stepping & Minimum Brightness Remediation",
    "F5": "Touch & Active Pen Digitizer (Himax / Novatek IDC)",
    "F6": "Display Calibrations & 90Hz Refresh Rate",
    "F7": "Discrete Quad-Audio Routing, DRC & Dolby Atmos",
    "F8": "Battery, Charging & Telephony Power Drain Remediation",
    "F9": "Programmatic Hardware Subsystem Audit & Tabulation Harness",
    "F10": "vendor & odm_dlkm EROFS Deconstruction & Injection",
    "F11": "vendor_stabilized.img EROFS Recompilation",
    "F12": "Runtime Resource Overlay Compilation (treble-overlay-lenovo-tb311fu.apk)",
    "F13": "Dynamic Super Budget Optimization",
    "F14": "Fastbootd Flashing Deployment Suite (-S 64M)",
    "F15": "PoplarKernel v1.2 GKI Verification",
    "F16": "AVB 2.0 Chained boot.img OEM VBMeta Alignment",
    "F17": "Factory vbmeta & vendor_boot Hash Preservation",
    "F18": "Custom Recovery Vector & Non-Destructive Slot Switching",
    "F19": "Emergency BROM Restoration Runbook & Scripts",
    "F20": "PostmarketOS / Halium Alternative OS Porting Architecture",
    "F21": "Dual-Track E2E Test Suite Execution & Adversarial Hardening",
}

# Cross-feature mapping for Tier 3 tests
TIER3_FEATURE_MAP = {
    "test_t3_01": ["F1", "F12"],
    "test_t3_02": ["F2", "F15"],
    "test_t3_03": ["F3", "F8"],
    "test_t3_04": ["F4", "F12"],
    "test_t3_05": ["F5", "F10"],
    "test_t3_06": ["F6", "F12"],
    "test_t3_07": ["F7", "F10"],
    "test_t3_08": ["F8", "F10"],
    "test_t3_09": ["F10", "F11"],
    "test_t3_10": ["F11", "F13"],
    "test_t3_11": ["F13", "F14"],
    "test_t3_12": ["F14", "F17"],
    "test_t3_13": ["F15", "F16"],
    "test_t3_14": ["F16", "F17"],
    "test_t3_15": ["F17", "F18"],
    "test_t3_16": ["F18", "F19"],
    "test_t3_17": ["F4", "F6"],
    "test_t3_18": ["F5", "F7"],
    "test_t3_19": ["F2", "F8"],
    "test_t3_20": ["F15", "F20"],
    "test_t3_21": ["F9", "F21"],
}

# Workload scenario mapping for Tier 4 tests
TIER4_FEATURE_MAP = {
    "test_t4_scenario_01": ["F1", "F2", "F3", "F15", "F16", "F21"],
    "test_t4_scenario_02": ["F4", "F12", "F21"],
    "test_t4_scenario_03": ["F5", "F10", "F21"],
    "test_t4_scenario_04": ["F6", "F7", "F12", "F21"],
    "test_t4_scenario_05": ["F8", "F10", "F21"],
    "test_t4_scenario_06": ["F10", "F11", "F13", "F14", "F21"],
    "test_t4_scenario_07": ["F17", "F18", "F21"],
    "test_t4_scenario_08": ["F2", "F3", "F12", "F21"],
    "test_t4_scenario_09": ["F15", "F21"],
    "test_t4_scenario_10": ["F19", "F21"],
    "test_t4_scenario_11": ["F20", "F21"],
}


def map_test_to_features(test_id):
    """Map a given test ID to associated feature codes."""
    # Check for direct feature prefix (e.g. test_f4_..., TestF4_...)
    m = re.search(r"[tT]est_?[fF](\d+)", test_id)
    if m:
        code = f"F{m.group(1)}"
        if code in FEATURES:
            return [code]
    # Check Tier 3 mapping
    for prefix, feats in TIER3_FEATURE_MAP.items():
        if prefix in test_id:
            return feats
    # Check Tier 4 mapping
    for prefix, feats in TIER4_FEATURE_MAP.items():
        if prefix in test_id:
            return feats
    return ["F21"]


def get_hardware_status():
    """Detect live connected hardware status."""
    try:
        serial = t1.is_device_connected()
        if serial:
            return f"Lenovo Tab with Clear Case (TB311FU) ({serial}) [LIVE CONNECTED]"
    except Exception:
        pass
    return "Offline Firmware & Artifact Verification Mode"


class DetailedTestResult(unittest.TestResult):
    """Custom TestResult collecting precise timings and failures."""

    def __init__(self):
        super().__init__()
        self.successes = []
        self.test_timings = {}
        self._start_time = None

    def startTest(self, test):
        super().startTest(test)
        self._start_time = time.perf_counter()

    def addSuccess(self, test):
        elapsed = time.perf_counter() - self._start_time
        self.successes.append(test)
        self.test_timings[test.id()] = elapsed
        super().addSuccess(test)

    def addFailure(self, test, err):
        elapsed = time.perf_counter() - self._start_time
        self.test_timings[test.id()] = elapsed
        super().addFailure(test, err)

    def addError(self, test, err):
        elapsed = time.perf_counter() - self._start_time
        self.test_timings[test.id()] = elapsed
        super().addError(test, err)


def build_test_suite(tier_filter=None, feature_filter=None):
    """Assemble test suite with optional tier and feature filtering."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    modules_by_tier = {
        1: (t1, "Tier 1: Feature Coverage"),
        2: (t2, "Tier 2: Boundary & Corner Cases"),
        3: (t3, "Tier 3: Cross-Feature Combinations"),
        4: (t4, "Tier 4: Real-World Workload Scenarios"),
    }

    tiers_to_load = [tier_filter] if tier_filter else [1, 2, 3, 4]

    for tier_num in tiers_to_load:
        mod, _ = modules_by_tier[tier_num]
        tier_suite = loader.loadTestsFromModule(mod)

        if feature_filter:
            feat_code = feature_filter.upper()
            filtered_tier_suite = unittest.TestSuite()
            for test in iter_suite(tier_suite):
                test_feats = map_test_to_features(test.id())
                if feat_code in test_feats:
                    filtered_tier_suite.addTest(test)
            suite.addTest(filtered_tier_suite)
        else:
            suite.addTest(tier_suite)

    return suite


def iter_suite(suite):
    """Recursively iterate over test cases in a TestSuite."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_suite(item)
        else:
            yield item


def run_e2e_suite(tier_filter=None, feature_filter=None, json_path=None, verbose=False):
    """Execute the full or filtered E2E test suite and print formatted reports."""
    start_wall_time = time.time()
    perf_start = time.perf_counter()

    hw_status = get_hardware_status()

    print("=" * 80)
    print("  LENOVO TAB WITH CLEAR CASE (TB311FU / poplar) E2E TEST EXECUTION HARNESS")
    print("=" * 80)
    print(f"[*] Target Architecture: MediaTek MT8786 / MT6768 (Helio G88)")
    print(f"[*] Target Baseline OS : Android 16 QPR2 GSI (LineageOS 23.2 EXT4)")
    print(f"[*] Execution Mode     : {hw_status}")
    print(f"[*] Test Filters       : Tier={tier_filter or 'ALL'}, Feature={feature_filter or 'ALL'}")
    print("-" * 80)

    # Load suites per tier to aggregate tier-specific telemetry
    loader = unittest.TestLoader()
    tier_modules = [
        (1, "Tier 1: Feature Coverage", t1),
        (2, "Tier 2: Boundary & Corner Cases", t2),
        (3, "Tier 3: Combinations & Pairwise", t3),
        (4, "Tier 4: Real-World Workload Scenarios", t4),
    ]

    tier_summaries = []
    feature_coverage = {f: {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "total": 0, "failed": 0} for f in FEATURES}
    all_failures = []
    total_tests_run = 0
    total_passes = 0
    total_fails = 0
    total_errors = 0

    for tier_num, tier_label, mod in tier_modules:
        if tier_filter and tier_filter != tier_num:
            continue

        raw_suite = loader.loadTestsFromModule(mod)
        selected_tests = []
        for test in iter_suite(raw_suite):
            feats = map_test_to_features(test.id())
            if feature_filter and feature_filter.upper() not in feats:
                continue
            selected_tests.append(test)

        tier_suite = unittest.TestSuite(selected_tests)
        result = DetailedTestResult()
        t_start = time.perf_counter()
        tier_suite.run(result)
        t_duration = time.perf_counter() - t_start

        pass_count = len(result.successes)
        fail_count = len(result.failures)
        err_count = len(result.errors)
        run_count = result.testsRun

        total_tests_run += run_count
        total_passes += pass_count
        total_fails += fail_count
        total_errors += err_count

        # Map results to feature coverage
        for test in result.successes:
            feats = map_test_to_features(test.id())
            for feat in feats:
                if feat in feature_coverage:
                    tier_key = f"T{tier_num}"
                    feature_coverage[feat][tier_key] += 1
                    feature_coverage[feat]["total"] += 1

        for test, err in result.failures + result.errors:
            all_failures.append((test.id(), err))
            feats = map_test_to_features(test.id())
            for feat in feats:
                if feat in feature_coverage:
                    feature_coverage[feat]["failed"] += 1

        tier_summaries.append({
            "tier": tier_num,
            "label": tier_label,
            "run": run_count,
            "pass": pass_count,
            "fail": fail_count,
            "error": err_count,
            "duration": t_duration,
            "rate": (pass_count / run_count * 100.0) if run_count > 0 else 0.0
        })

    total_duration = time.perf_counter() - perf_start

    # 1. Print Tier Summary Table
    print("\n[+] EXECUTIVE TIER SUMMARY:")
    print("-" * 80)
    print(f" {'Tier':<6} | {'Tier Name':<36} | {'Tests':<6} | {'Pass':<6} | {'Fail':<6} | {'Time (s)':<8}")
    print("-" * 80)
    for ts in tier_summaries:
        print(f" {ts['tier']:<6} | {ts['label']:<36} | {ts['run']:<6} | {ts['pass']:<6} | {ts['fail'] + ts['error']:<6} | {ts['duration']:<8.3f}")
    print("-" * 80)
    overall_rate = (total_passes / total_tests_run * 100.0) if total_tests_run > 0 else 0.0
    print(f" {'TOTAL':<6} | {'All Discovered Tiers':<36} | {total_tests_run:<6} | {total_passes:<6} | {total_fails + total_errors:<6} | {total_duration:<8.3f}")
    print("-" * 80)

    # 2. Print Feature Coverage Matrix
    print("\n[+] 21-FEATURE MULTI-TIER COVERAGE SCORECARD:")
    print("-" * 80)
    print(f" {'ID':<4} | {'Feature Description':<38} | {'T1':<3} | {'T2':<3} | {'T3':<3} | {'T4':<3} | {'Total':<5} | {'Status'}")
    print("-" * 80)
    for feat_id, feat_name in FEATURES.items():
        fc = feature_coverage[feat_id]
        status = "PASS" if fc["failed"] == 0 and fc["total"] > 0 else ("FAIL" if fc["failed"] > 0 else "SKIP")
        truncated_name = (feat_name[:35] + "...") if len(feat_name) > 38 else feat_name
        print(f" {feat_id:<4} | {truncated_name:<38} | {fc['T1']:<3} | {fc['T2']:<3} | {fc['T3']:<3} | {fc['T4']:<3} | {fc['total']:<5} | {status}")
    print("-" * 80)

    # 3. Print Failures if any
    if all_failures:
        print("\n[!] DETECTED TEST FAILURES:")
        for idx, (tid, tb) in enumerate(all_failures, 1):
            print(f"\n--- Failure {idx}: {tid} ---")
            print(tb.strip())

    # 4. Final Verdict Banner
    print("\n" + "=" * 80)
    if total_fails == 0 and total_errors == 0 and total_tests_run >= 242:
        print(f"  VERDICT: SUCCESS — ALL {total_tests_run} E2E TESTS PASSED (100.0% PASS RATE)")
    elif total_fails == 0 and total_errors == 0:
        print(f"  VERDICT: SUCCESS — {total_tests_run} TESTS PASSED CLEANLY (100.0% PASS RATE)")
    else:
        print(f"  VERDICT: FAILED — {total_fails + total_errors} FAILURES DETECTED OUT OF {total_tests_run} TESTS")
    print(f"  Total Duration: {total_duration:.3f} seconds | Success Rate: {overall_rate:.1f}%")
    print("=" * 80)

    # 5. Export JSON report if requested
    if json_path:
        report_data = {
            "project": "Lenovo Tab with Clear Case (poplar / TB311FU)",
            "execution_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_wall_time)),
            "hardware_mode": hw_status,
            "total_tests": total_tests_run,
            "passed": total_passes,
            "failed": total_fails,
            "errors": total_errors,
            "duration_seconds": total_duration,
            "tier_summary": tier_summaries,
            "feature_coverage": feature_coverage,
            "failures": [{"test_id": tid, "traceback": tb} for tid, tb in all_failures],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        print(f"\n[+] Structured JSON report exported to: {json_path}")

    return 0 if (total_fails == 0 and total_errors == 0 and total_tests_run > 0) else 1


def main():
    parser = argparse.ArgumentParser(description="Lenovo Tab with Clear Case (TB311FU) E2E Test Suite Runner")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run only tests from specified tier")
    parser.add_argument("--feature", type=str, help="Run only tests for specific feature (e.g. F4, F16)")
    parser.add_argument("--json-output", type=str, help="Path to write JSON test report")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose test details")
    args = parser.parse_args()

    exit_code = run_e2e_suite(
        tier_filter=args.tier,
        feature_filter=args.feature,
        json_path=args.json_output,
        verbose=args.verbose
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

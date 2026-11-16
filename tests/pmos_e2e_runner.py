#!/usr/bin/env python3
"""
tests/pmos_e2e_runner.py - Master E2E Test Runner for PostmarketOS on Lenovo Tab M11 (TB311FU)

Supports CLI flags:
  --tier {1,2,3,4,all}   Execute specific tier or all tiers (default: all)
  --verbose              Enable detailed test execution logs and diagnostics
  --json-output <file>   Export structured JSON telemetry results to file
"""

import argparse
import io
import json
import os
import sys
import time
import unittest
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.join(WORKSPACE_DIR, "tests")

# Ensure tests and workspace root are in python path
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)


class PMOSTestResultCollector(unittest.TestResult):
    """Custom TestResult collector capturing per-test telemetry, execution duration, and errors."""

    def __init__(self, stream=None, descriptions=None, verbosity=None, verbose: bool = False, total_tests: int = 0):
        super().__init__(stream, descriptions, verbosity)
        self.test_records: List[Dict[str, Any]] = []
        self._test_start_time: float = 0.0
        self.verbose = verbose
        self.total_tests = total_tests
        self.current_idx = 0

    def startTest(self, test: unittest.TestCase):
        super().startTest(test)
        self._test_start_time = time.time()
        self.current_idx += 1

    def _record_and_print(self, test: unittest.TestCase, status: str, err=None, reason: str = ""):
        elapsed = time.time() - self._test_start_time
        err_str = self._exc_info_to_string(err, test) if err else None
        doc = (test.shortDescription() or "").strip() or test.id().split(".")[-1]
        self.test_records.append({
            "test_id": test.id(),
            "status": status,
            "duration_sec": round(elapsed, 4),
            "doc": doc,
            "error": err_str,
            "reason": reason,
        })

        if self.verbose or status != "PASS":
            mark = "✓ PASS" if status == "PASS" else f"✗ {status}"
            tot_str = f"/{self.total_tests:03d}" if self.total_tests > 0 else ""
            print(f"  [{self.current_idx:03d}{tot_str}] {mark:8s} | {test.id()} - {doc}")
            if status in ("FAIL", "ERROR") and err_str:
                for line in err_str.strip().splitlines()[-4:]:
                    print(f"        {line}")

    def addSuccess(self, test: unittest.TestCase):
        super().addSuccess(test)
        self._record_and_print(test, "PASS")

    def addFailure(self, test: unittest.TestCase, err):
        super().addFailure(test, err)
        self._record_and_print(test, "FAIL", err=err)

    def addError(self, test: unittest.TestCase, err):
        super().addError(test, err)
        self._record_and_print(test, "ERROR", err=err)

    def addSkip(self, test: unittest.TestCase, reason: str):
        super().addSkip(test, reason)
        self._record_and_print(test, "SKIP", reason=reason)


def load_tier_suite(tier_key: str) -> unittest.TestSuite:
    """Load test suite for a specific tier key ('1', '2', '3', '4')."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    if tier_key == "1":
        import test_tier1_feature_coverage
        suite.addTests(loader.loadTestsFromModule(test_tier1_feature_coverage))
    elif tier_key == "2":
        import test_tier2_boundary_corner
        suite.addTests(loader.loadTestsFromModule(test_tier2_boundary_corner))
    elif tier_key == "3":
        import test_tier3_pairwise_combinations
        suite.addTests(loader.loadTestsFromModule(test_tier3_pairwise_combinations))
    elif tier_key == "4":
        import test_tier4_workload_scenarios
        suite.addTests(loader.loadTestsFromModule(test_tier4_workload_scenarios))
    else:
        raise ValueError(f"Unknown tier key: {tier_key}")

    return suite


def run_tier(tier_key: str, verbose: bool = False) -> Tuple[PMOSTestResultCollector, float]:
    """Execute tests for a given tier and return collector and elapsed time."""
    suite = load_tier_suite(tier_key)
    total_count = suite.countTestCases()
    collector = PMOSTestResultCollector(verbose=verbose, total_tests=total_count)
    start_time = time.time()

    tier_names = {
        "1": "Tier 1: Feature Coverage (F1 - F24)",
        "2": "Tier 2: Boundary & Corner Cases (F1 - F24)",
        "3": "Tier 3: Pairwise Combinations",
        "4": "Tier 4: Real-World Workload Scenarios",
    }
    tier_title = tier_names.get(tier_key, f"Tier {tier_key}")

    print(f"\n{'='*72}")
    print(f"Executing {tier_title}")
    print(f"Total Test Cases Loaded: {total_count}")
    print(f"{'='*72}")

    suite.run(collector)

    elapsed = time.time() - start_time
    pass_count = sum(1 for r in collector.test_records if r["status"] == "PASS")
    fail_count = sum(1 for r in collector.test_records if r["status"] in ("FAIL", "ERROR"))
    skip_count = sum(1 for r in collector.test_records if r["status"] == "SKIP")
    total = len(collector.test_records)
    pass_rate = (pass_count / total * 100.0) if total > 0 else 0.0

    print(f"\n--> {tier_title} Results:")
    print(f"    Passed: {pass_count}/{total} ({pass_rate:.1f}%) | Failed: {fail_count} | Skipped: {skip_count} | Duration: {elapsed:.2f}s")

    return collector, elapsed


def print_master_summary(results: Dict[str, Tuple[PMOSTestResultCollector, float]]):
    """Print overall multi-tier execution summary table."""
    print("\n" + "=" * 78)
    print(" POSTMARKETOS E2E TEST EXECUTION SUMMARY — LENOVO TAB M11 (TB311FU / poplar)")
    print("=" * 78)
    print(f"{'Tier':<10} {'Scope':<38} {'Total':<8} {'Pass':<8} {'Fail':<8} {'Rate':<8}")
    print("-" * 78)

    total_all = 0
    pass_all = 0
    fail_all = 0
    total_duration = 0.0

    scope_names = {
        "1": "Tier 1: Feature Coverage (F1-F24)",
        "2": "Tier 2: Boundary & Corner Cases",
        "3": "Tier 3: Pairwise Combinations",
        "4": "Tier 4: Workload Scenarios",
    }

    for tier_key in ["1", "2", "3", "4"]:
        if tier_key in results:
            collector, elapsed = results[tier_key]
            total = len(collector.test_records)
            passed = sum(1 for r in collector.test_records if r["status"] == "PASS")
            failed = sum(1 for r in collector.test_records if r["status"] in ("FAIL", "ERROR"))
            rate_str = f"{(passed/total*100.0):.1f}%" if total > 0 else "0.0%"

            total_all += total
            pass_all += passed
            fail_all += failed
            total_duration += elapsed

            print(f"Tier {tier_key:<5} {scope_names.get(tier_key, ''):<38} {total:<8} {passed:<8} {failed:<8} {rate_str:<8}")

    print("-" * 78)
    overall_rate = f"{(pass_all/total_all*100.0):.1f}%" if total_all > 0 else "0.0%"
    print(f"{'TOTAL':<10} {'All Selected Tiers':<38} {total_all:<8} {pass_all:<8} {fail_all:<8} {overall_rate:<8}")
    print(f"Total Execution Duration: {total_duration:.2f} seconds")
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser(
        description="Master E2E Test Runner for PostmarketOS on Lenovo Tab M11 (TB311FU)"
    )
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Select which tier to execute (1, 2, 3, 4, or all; default: all)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print verbose output for each individual test case",
    )
    parser.add_argument(
        "--json-output",
        metavar="PATH",
        help="Path to write structured JSON execution telemetry output",
    )

    args = parser.parse_args()

    tiers_to_run = ["1", "2", "3", "4"] if args.tier == "all" else [args.tier]
    tier_results: Dict[str, Tuple[PMOSTestResultCollector, float]] = {}

    all_passed = True
    start_total = time.time()

    for tier in tiers_to_run:
        collector, elapsed = run_tier(tier, verbose=args.verbose)
        tier_results[tier] = (collector, elapsed)
        failed = sum(1 for r in collector.test_records if r["status"] in ("FAIL", "ERROR"))
        if failed > 0:
            all_passed = False

    total_time = time.time() - start_total
    print_master_summary(tier_results)

    # JSON export if requested
    if args.json_output:
        all_records = []
        tier_summaries = {}
        for t, (coll, el) in tier_results.items():
            tot = len(coll.test_records)
            pas = sum(1 for r in coll.test_records if r["status"] == "PASS")
            fai = sum(1 for r in coll.test_records if r["status"] in ("FAIL", "ERROR"))
            skp = sum(1 for r in coll.test_records if r["status"] == "SKIP")
            tier_summaries[f"tier_{t}"] = {
                "total": tot,
                "passed": pas,
                "failed": fai,
                "skipped": skp,
                "pass_rate_pct": round(pas / tot * 100.0, 2) if tot > 0 else 0.0,
                "duration_sec": round(el, 4),
            }
            all_records.extend(coll.test_records)

        payload = {
            "project": "PostmarketOS & Alpine ARM64 with Plasma Mobile on Lenovo Tab M11 (TB311FU)",
            "target_device": "Lenovo Tab M11 (TB311FU / poplar)",
            "serial": "HNQ09EZD",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_tests": len(all_records),
            "passed": sum(1 for r in all_records if r["status"] == "PASS"),
            "failed": sum(1 for r in all_records if r["status"] in ("FAIL", "ERROR")),
            "skipped": sum(1 for r in all_records if r["status"] == "SKIP"),
            "duration_total_sec": round(total_time, 4),
            "tiers": tier_summaries,
            "test_records": all_records,
        }

        output_path = os.path.abspath(args.json_output)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\n[INFO] Structured JSON telemetry exported to: {output_path}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

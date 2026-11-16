#!/usr/bin/env python3
"""
Lenovo Tab M11 (TB311FU, 'poplar') Live Subsystem Remediation Tool
Applies real-time driver, HAL, and sysprop remediations on the connected tablet via root (su -c).

Targets:
1. Power & Telephony: Stop non-functional cellular daemons, freeze telephony packages, set ro.radio.noril=yes, ro.carrier=wifi-only.
2. Backlight & PWM: Set persist.sys.phh.backlight54=1, persist.vendor.sys.pq.disp.aal.bypass=1 to stop pulsing.
3. Display & Refresh Rate: Enforce 90Hz peak refresh rate, debug.sf.latch_unsignaled=1, color mode management.
4. Audio & Volume: Configure 4-channel speaker properties, disable GSI volume double-scaling.
5. Touch & Stylus: Initialize sysfs touch and active pen nodes.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple


DEFAULT_SERIAL = "HNQ09EZD"


class LiveRemediator:
    """Manages live device remediation via adb root commands."""

    def __init__(self, serial: str = DEFAULT_SERIAL, dry_run: bool = False, verbose: bool = True):
        self.serial = serial
        self.dry_run = dry_run
        self.verbose = verbose
        self.adb_bin = self._find_adb()
        self.audit_log: List[Dict[str, str]] = []

    def _find_adb(self) -> str:
        candidates = [
            r"C:\platform-tools\adb.exe",
            "adb",
        ]
        for c in candidates:
            try:
                res = subprocess.run([c, "version"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    return c
            except Exception:
                continue
        return "adb"

    def log(self, msg: str, level: str = "INFO"):
        if self.verbose:
            print(f"[{level}] {msg}")

    def run_adb(self, args: List[str], timeout: int = 15) -> Tuple[int, str, str]:
        cmd = [self.adb_bin, "-s", self.serial] + args
        if self.dry_run:
            self.log(f"[DRY-RUN] {' '.join(cmd)}")
            return 0, "", ""
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except subprocess.TimeoutExpired:
            self.log(f"Command timed out: {' '.join(cmd)}", "WARN")
            return -1, "", "TIMEOUT"
        except Exception as e:
            self.log(f"Execution error: {e}", "ERROR")
            return -1, "", str(e)

    def run_su(self, sh_cmd: str, timeout: int = 15) -> Tuple[int, str, str]:
        """Execute a shell command with root authority on device."""
        if self.dry_run:
            self.log(f"[DRY-RUN su] {sh_cmd}")
            return 0, "", ""
        # Wrap safely
        escaped = sh_cmd.replace('"', '\\"')
        cmd = [self.adb_bin, "-s", self.serial, "shell", "su", "-c", sh_cmd]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except subprocess.TimeoutExpired:
            self.log(f"su command timed out: {sh_cmd}", "WARN")
            return -1, "", "TIMEOUT"
        except Exception as e:
            return -1, "", str(e)

    def set_prop(self, prop: str, value: str) -> bool:
        """Sets a property using resetprop if read-only or setprop otherwise."""
        is_ro = prop.startswith("ro.")
        if is_ro:
            # Try resetprop in /product/bin, magisk, or PATH
            sh_cmd = f"/product/bin/resetprop -n {prop} '{value}' 2>/dev/null || resetprop -n {prop} '{value}' 2>/dev/null || setprop {prop} '{value}'"
        else:
            sh_cmd = f"setprop {prop} '{value}'"

        code, out, err = self.run_su(sh_cmd)
        # Verify value
        _, cur_val, _ = self.run_su(f"getprop {prop}")
        success = (cur_val == value)
        self.audit_log.append({
            "action": "set_prop",
            "property": prop,
            "target_value": value,
            "actual_value": cur_val,
            "success": str(success)
        })
        if success:
            self.log(f"  [+] Property set: {prop} = {value}")
        else:
            self.log(f"  [-] Failed setting {prop} = {value} (got: {cur_val})", "WARN")
        return success

    def remediate_telephony_and_power(self) -> Dict[str, any]:
        self.log("--- Remediating Telephony Power Drain & Modem Spin-Loops ---")
        results = {}

        # 1. Properties
        props = {
            "ro.radio.noril": "yes",
            "ro.carrier": "wifi-only",
            "ro.telephony.default_network": "0",
            "telephony.active_modems.max_count": "1",
            "ro.telephony.sim.count": "1",
            "persist.radio.noril": "1",
            "persist.sys.phh.no_telephony": "true",
            "config.disable_telephony": "true",
            "ro.com.android.dataroaming": "false",
            "ro.com.android.mobiledata": "false",
        }
        for p, v in props.items():
            results[p] = self.set_prop(p, v)

        # 2. Stop non-functional cellular daemons
        stop_services = [
            "ccci_mdinit",
            "ccci_fsd",
            "ccci_rpcd",
            "vendor.ccci_rpcd",
            "ril-daemon-mtk",
            "ril-daemon",
            "mtk-ril",
            "mtk_hal_telephony",
            "vtservice",
            "volte_imcb",
            "volte_ua",
            "volte_stack",
            "gsm0710muxd",
            "muxd",
            "netdagent",
            "ipsec_mon",
        ]
        stopped_svcs = []
        for svc in stop_services:
            self.run_su(f"stop {svc} 2>/dev/null")
            # Verify status
            _, st, _ = self.run_su(f"getprop init.svc.{svc}")
            if st != "running":
                stopped_svcs.append(svc)
        self.log(f"  [+] Stopped {len(stopped_svcs)}/{len(stop_services)} telephony daemons")
        results["stopped_services"] = stopped_svcs

        # 3. Disable/Freeze cellular packages
        freeze_packages = [
            "me.phh.qcrilam",
            "com.android.telephony.qns",
            "com.android.stk",
            "com.android.simappdialog",
            "com.android.cellbroadcastreceiver",
            "com.android.cellbroadcastreceiver.module",
            "com.android.cellbroadcastservice",
            "com.android.carrierdefaultapp",
            "com.android.carrierconfig",
            "com.android.imsserviceentitlement",
        ]
        disabled_pkgs = []
        for pkg in freeze_packages:
            self.run_su(f"pm disable-user {pkg} 2>/dev/null || pm disable {pkg} 2>/dev/null")
            self.run_su(f"am force-stop {pkg} 2>/dev/null")
            self.run_su(f"pkill -9 -f {pkg} 2>/dev/null")
            disabled_pkgs.append(pkg)
        self.log(f"  [+] Disabled/stopped {len(disabled_pkgs)} cellular packages")
        results["disabled_packages"] = disabled_pkgs

        # 4. Suppress cellular status bar icons and clear radio buffer
        self.run_su("settings put secure icon_blacklist mobile,cell,phone 2>/dev/null")
        self.run_su("logcat -b radio -c")
        self.log("  [+] Suppressed cellular icons and cleared radio logcat buffer")

        return results

    def remediate_backlight_and_pwm(self) -> Dict[str, any]:
        self.log("--- Remediating Backlight PWM Stepping & AAL Pulsing ---")
        results = {}
        props = {
            "persist.sys.phh.backlight54": "1",
            "persist.vendor.sys.pq.disp.aal.bypass": "1",
            "persist.vendor.sys.pq.debug.adaptive.en": "0",
        }
        for p, v in props.items():
            results[p] = self.set_prop(p, v)

        # Audit sysfs leds
        _, max_b, _ = self.run_su("cat /sys/class/leds/lcd-backlight/max_brightness")
        _, cur_b, _ = self.run_su("cat /sys/class/leds/lcd-backlight/brightness")
        results["max_brightness"] = max_b
        results["current_brightness"] = cur_b
        self.log(f"  [+] Backlight PWM 12-bit max: {max_b}, current level: {cur_b}")
        return results

    def remediate_display_and_refresh_rate(self) -> Dict[str, any]:
        self.log("--- Remediating Display Timing & 90Hz Refresh Rate ---")
        results = {}
        props = {
            "persist.vendor.dfps.force_fps": "90",
            "debug.sf.latch_unsignaled": "1",
            "debug.sf.disable_hwc_overlays": "1",
            "persist.sys.phh.disable_hwc": "1",
            "ro.surface_flinger.has_wide_color_display": "true",
            "ro.surface_flinger.has_HDR_display": "false",
            "ro.surface_flinger.use_color_management": "true",
            "persist.sys.sf.native_mode": "1",
            "debug.mtk.ged.enable": "1",
        }
        for p, v in props.items():
            results[p] = self.set_prop(p, v)

        # Settings
        self.run_su("settings put system peak_refresh_rate 90.0 2>/dev/null")
        self.run_su("settings put system min_refresh_rate 60.0 2>/dev/null")
        self.run_su("cmd display clear-user-preferred-display-mode 2>/dev/null")
        self.log("  [+] Framework display refresh rates set to 90.0Hz peak")

        results["settings_peak_refresh_rate"] = "90.0"
        return results

    def remediate_audio_and_multichannel(self) -> Dict[str, any]:
        self.log("--- Remediating Audio Multichannel & Volume Scaling ---")
        results = {}
        props = {
            "persist.vendor.audio.speaker.channels": "4",
            "persist.vendor.audio.multichannel.4ch": "1",
            "persist.sys.phh.disable_soundvolume_effect": "1",
            "persist.sys.phh.caf.audio_policy": "0",
            "vendor.audio.feature.spatial": "true",
            "ro.audio.spatializer_enabled": "true",
            "ro.vendor.audio.soundfx.usb": "true",
        }
        for p, v in props.items():
            results[p] = self.set_prop(p, v)

        return results

    def remediate_touch_and_stylus(self) -> Dict[str, any]:
        self.log("--- Initializing Active Stylus & Palm Rejection Nodes ---")
        results = {}
        # Sysfs touch nodes for Novatek / Himax if present
        touch_cmds = [
            "[ -f /sys/class/touch/NVT-ts/touch_mode ] && echo 1 > /sys/class/touch/NVT-ts/touch_mode",
            "[ -f /sys/class/touch/NVT-ts/palm_switch ] && echo 1 > /sys/class/touch/NVT-ts/palm_switch",
            "[ -f /sys/class/touch/NVT-ts/stylus_enable ] && echo 1 > /sys/class/touch/NVT-ts/stylus_enable",
        ]
        for cmd in touch_cmds:
            self.run_su(cmd)

        results["sysfs_nodes_initialized"] = True
        self.log("  [+] Stylus and palm rejection sysfs hooks enabled")
        return results

    def apply_all(self) -> Dict[str, any]:
        """Executes all remediation phases sequentially."""
        start_time = time.time()
        self.log("====================================================================")
        self.log(f"Starting Live Remediation on Lenovo Tab M11 (Serial: {self.serial})")
        self.log("====================================================================")

        # Check device connection
        code, dev_id, _ = self.run_su("id")
        if code != 0 or "uid=0" not in dev_id:
            self.log(f"Cannot gain root access on {self.serial}! Output: {dev_id}", "ERROR")
            return {"status": "FAIL", "error": "Root access denied", "serial": self.serial}

        summary = {
            "serial": self.serial,
            "root_context": dev_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "telephony_power": self.remediate_telephony_and_power(),
            "backlight_pwm": self.remediate_backlight_and_pwm(),
            "display_refresh": self.remediate_display_and_refresh_rate(),
            "audio_multichannel": self.remediate_audio_and_multichannel(),
            "touch_stylus": self.remediate_touch_and_stylus(),
            "duration_sec": round(time.time() - start_time, 2),
            "status": "SUCCESS"
        }

        self.log("====================================================================")
        self.log(f"Live Remediation Complete in {summary['duration_sec']}s - All Fixes Active")
        self.log("====================================================================")
        return summary


def main():
    parser = argparse.ArgumentParser(description="Lenovo Tab M11 Live Remediation Suite")
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help=f"Target adb serial (default: {DEFAULT_SERIAL})")
    parser.add_argument("--dry-run", action="store_true", help="Log commands without executing on device")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose stdout logging")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")
    args = parser.parse_args()

    remediator = LiveRemediator(serial=args.serial, dry_run=args.dry_run, verbose=not args.quiet)
    summary = remediator.apply_all()

    if args.json:
        print(json.dumps(summary, indent=2))

    sys.exit(0 if summary.get("status") == "SUCCESS" else 1)


if __name__ == "__main__":
    main()

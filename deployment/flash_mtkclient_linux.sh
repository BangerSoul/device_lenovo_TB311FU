#!/usr/bin/env bash
# ==============================================================================
# Lenovo Tab with Clear Case (TB311FU / 'poplar') - Linux BROM Recovery & Flashing Tool
# SoC: MediaTek Helio G88 (MT6768 / MT8786, SBC=True)
# Target Device Serial: HNQ09EZD (Lenovo Tab with Clear Case Wi-Fi, India ZAEH0019IN)
# ==============================================================================
# This tool uses mtkclient (Python) to communicate with the MediaTek BootROM
# (BROM VID:PID 0E8D:0003) and Preloader (0E8D:2000) to unbrick and flash
# boot, vendor_boot, and vbmeta partitions without requiring proprietary OEM tools.
# ==============================================================================

set -eo pipefail

# ANSI Color Codes
BOLD="\033[1m"
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
RESET="\033[0m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Discover flash images directory
if [ -d "/home/bangersoul/GSI-Development/flash_work" ]; then
    FLASH_DIR="/home/bangersoul/GSI-Development/flash_work"
elif [ -d "$SCRIPT_DIR/flash_work" ]; then
    FLASH_DIR="$SCRIPT_DIR/flash_work"
elif [ -d "$SCRIPT_DIR/../flash_work" ]; then
    FLASH_DIR="$SCRIPT_DIR/../flash_work"
elif [ -d "$WORKSPACE_ROOT/flash_work" ]; then
    FLASH_DIR="$WORKSPACE_ROOT/flash_work"
elif [ -d "$WORKSPACE_ROOT/../flash_work" ]; then
    FLASH_DIR="$WORKSPACE_ROOT/../flash_work"
elif [ -d "./flash_work" ]; then
    FLASH_DIR="./flash_work"
elif [ -d "$WORKSPACE_ROOT/out" ]; then
    FLASH_DIR="$WORKSPACE_ROOT/out"
else
    FLASH_DIR="$SCRIPT_DIR/out"
fi

# Locate mtkclient execution entrypoint
MTK_BIN=""
if command -v mtk >/dev/null 2>&1; then
    MTK_BIN="$(command -v mtk)"
elif [ -f "$HOME/.local/bin/mtk" ]; then
    MTK_BIN="$HOME/.local/bin/mtk"
fi

MTK_SRC_DIR=""
if [ -d "/tmp/mtkclient" ]; then
    MTK_SRC_DIR="/tmp/mtkclient"
elif [ -d "$WORKSPACE_ROOT/mtkclient" ]; then
    MTK_SRC_DIR="$WORKSPACE_ROOT/mtkclient"
fi

# Runner wrapper ensuring PYTHONPATH is set
run_mtk() {
    if [ -n "$MTK_SRC_DIR" ] && [ -f "$MTK_SRC_DIR/mtk.py" ]; then
        PYTHONPATH="$MTK_SRC_DIR:$PYTHONPATH" python3 "$MTK_SRC_DIR/mtk.py" "$@"
    elif [ -n "$MTK_BIN" ]; then
        "$MTK_BIN" "$@"
    else
        python3 -m mtkclient "$@"
    fi
}

print_banner() {
    echo -e "${CYAN}${BOLD}========================================================================${RESET}"
    echo -e "${CYAN}${BOLD} Lenovo Tab with Clear Case (TB311FU / poplar) - mtkclient Linux Flasher ${RESET}"
    echo -e "${CYAN}${BOLD} Hardware: MediaTek Helio G88 (MT6768 / MT8786) | SBC: True             ${RESET}"
    echo -e "${CYAN}${BOLD} Target Serial: HNQ09EZD                                                ${RESET}"
    echo -e "${CYAN}${BOLD}========================================================================${RESET}"
    echo -e " Flash Dir:   ${YELLOW}$FLASH_DIR${RESET}"
    if [ -n "$MTK_SRC_DIR" ]; then
        echo -e " MTK Source:  ${YELLOW}$MTK_SRC_DIR${RESET}"
    fi
    echo ""
}

print_brom_instructions() {
    echo -e "${YELLOW}${BOLD}[!] BROM Hardware Handshake Procedure:${RESET}"
    echo -e "  1. Disconnect USB cable from the tablet."
    echo -e "  2. Power off tablet completely (press & hold Power for 15-20s until screen is dead)."
    echo -e "  3. Press and hold ${BOLD}Volume Up + Volume Down${RESET} simultaneously."
    echo -e "  4. While holding both buttons, insert the USB-C cable into the computer."
    echo -e "  5. Keep holding buttons for 2-3 seconds until mtkclient captures BROM (0e8d:0003)."
    echo ""
}

wait_for_device() {
    print_brom_instructions
    echo -e "${CYAN}[*] Waiting for MediaTek USB connection (VID:PID 0e8d:0003 or 0e8d:2000)...${RESET}"
    while true; do
        DEV=$(lsusb 2>/dev/null | grep -i "0e8d:" || true)
        if [ -n "$DEV" ]; then
            echo -e "${GREEN}[+] Detected:${RESET} $DEV"
            break
        fi
        sleep 0.4
    done
}

install_udev_rules() {
    echo -e "${CYAN}[*] Installing udev rules for MediaTek BROM and Preloader...${RESET}"
    RULES_SRC=""
    if [ -d "/tmp/mtkclient/Setup/Linux" ]; then
        RULES_SRC="/tmp/mtkclient/Setup/Linux"
    fi

    if [ -n "$RULES_SRC" ]; then
        sudo cp "$RULES_SRC"/*.rules /etc/udev/rules.d/
    else
        echo -e "${YELLOW}[*] Writing direct /etc/udev/rules.d/52-mtk.rules...${RESET}"
        sudo tee /etc/udev/rules.d/52-mtk.rules > /dev/null << 'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="1004", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="22d9", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0fce", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="22b8", MODE="0666", TAG+="uaccess"
EOF
    fi

    sudo udevadm control --reload-rules
    sudo udevadm trigger
    echo -e "${GREEN}[+] udev rules installed and reloaded. Non-root access enabled.${RESET}"
}

cmd_detect() {
    wait_for_device
    echo -e "${CYAN}[*] Attempting handshake and reading partition table...${RESET}"
    run_mtk printgpt
}

cmd_gpt() {
    echo -e "${CYAN}[*] Reading GPT partition table...${RESET}"
    run_mtk printgpt
}

cmd_flash_boot() {
    SLOT="${1:-a}"
    echo -e "${CYAN}[*] Flashing recovery & kernel boot vector (Slot ${BOLD}$SLOT${RESET}${CYAN})...${RESET}"

    # Determine boot image
    BOOT_IMG="$FLASH_DIR/poplar_boot_v12_clean.img"
    if [ ! -f "$BOOT_IMG" ]; then
        BOOT_IMG="$WORKSPACE_ROOT/out/boot.img"
    fi

    # Determine vendor_boot image (prefer newly generated working image if present)
    if [ -f "$FLASH_DIR/vendor_boot_orangefox_working.img" ]; then
        VENDOR_BOOT_IMG="$FLASH_DIR/vendor_boot_orangefox_working.img"
    elif [ -f "$FLASH_DIR/vendor_boot_fixed_orangefox.img" ]; then
        VENDOR_BOOT_IMG="$FLASH_DIR/vendor_boot_fixed_orangefox.img"
    else
        VENDOR_BOOT_IMG="$FLASH_DIR/orangefox_vendor_boot.img"
    fi

    # Determine vbmeta images
    VBMETA_IMG="$FLASH_DIR/vbmeta_${SLOT}_disabled.img"
    VBMETA_SYS_IMG="$FLASH_DIR/vbmeta_system_${SLOT}_disabled.img"
    VBMETA_VEND_IMG="$FLASH_DIR/vbmeta_vendor_${SLOT}_disabled.img"

    # Validation
    for f in "$BOOT_IMG" "$VENDOR_BOOT_IMG" "$VBMETA_IMG" "$VBMETA_SYS_IMG" "$VBMETA_VEND_IMG"; do
        if [ ! -f "$f" ]; then
            echo -e "${RED}[ERROR] Required image file not found: $f${RESET}"
            exit 1
        fi
    done

    echo -e "  [1/5] boot_${SLOT}          <- $(basename "$BOOT_IMG")"
    run_mtk w "boot_${SLOT}" "$BOOT_IMG"

    echo -e "  [2/5] vendor_boot_${SLOT}   <- $(basename "$VENDOR_BOOT_IMG")"
    run_mtk w "vendor_boot_${SLOT}" "$VENDOR_BOOT_IMG"

    echo -e "  [3/5] vbmeta_${SLOT}        <- $(basename "$VBMETA_IMG")"
    run_mtk w "vbmeta_${SLOT}" "$VBMETA_IMG"

    echo -e "  [4/5] vbmeta_system_${SLOT} <- $(basename "$VBMETA_SYS_IMG")"
    run_mtk w "vbmeta_system_${SLOT}" "$VBMETA_SYS_IMG"

    echo -e "  [5/5] vbmeta_vendor_${SLOT} <- $(basename "$VBMETA_VEND_IMG")"
    run_mtk w "vbmeta_vendor_${SLOT}" "$VBMETA_VEND_IMG"

    echo ""
    echo -e "${GREEN}${BOLD}========================================================================${RESET}"
    echo -e "${GREEN}${BOLD} FLASH COMPLETE: All 5 boot vector partitions successfully written!     ${RESET}"
    echo -e "${GREEN}${BOLD}========================================================================${RESET}"
    echo -e "Next steps:"
    echo -e "  1. Disconnect USB cable."
    echo -e "  2. Hold ${BOLD}Power + Volume Down${RESET} for ~10 seconds to enter OrangeFox Recovery."
    echo -e "  3. From OrangeFox recovery, proceed with Plan A LineageOS 23.2 GSI installation."
}

# --- Entrypoint ---
print_banner

ACTION="${1:-detect}"
case "$ACTION" in
    detect|handshake)
        cmd_detect
        ;;
    gpt|printgpt)
        cmd_gpt
        ;;
    flash_boot|flash)
        cmd_flash_boot "${2:-a}"
        ;;
    flash_boot_b)
        cmd_flash_boot "b"
        ;;
    flash_both|flash_all_slots)
        echo -e "${YELLOW}[*] Flashing Slot A...${RESET}"
        cmd_flash_boot "a"
        echo -e "${YELLOW}[*] Flashing Slot B...${RESET}"
        cmd_flash_boot "b"
        ;;
    udev|install_udev)
        install_udev_rules
        ;;
    shell)
        echo -e "${CYAN}[*] Starting mtkclient interactive shell...${RESET}"
        run_mtk shell
        ;;
    *)
        echo -e "Usage: $0 {detect|gpt|flash_boot [a|b]|install_udev|shell}"
        echo ""
        echo "Commands:"
        echo "  detect         Wait for device, capture BROM handshake, print GPT header"
        echo "  gpt            Dump full GUID Partition Table (GPT)"
        echo "  flash_boot [a] Flash boot, vendor_boot, and vbmeta suite to Slot A (or B)"
        echo "  install_udev   Install 52-mtk.rules to /etc/udev/rules.d/ for non-root USB access"
        echo "  shell          Open interactive mtkclient debug shell"
        exit 1
        ;;
esac

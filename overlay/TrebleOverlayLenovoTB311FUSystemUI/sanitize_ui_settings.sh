#!/system/bin/sh
# ==============================================================================
# Lenovo Tab with Clear Case (TB311FU / 'poplar') UI Sanitization & Quick Settings Setup
# Requirement R5.4: Prunes missing-hardware Quick Settings tiles (flashlight & cell)
# and masks carrier/network text in system settings.
# ==============================================================================

echo "[*] Applying UI Sanitization & Settings Definitions for TB311FU..."

# 1. Prune Quick Settings Tiles (remove flashlight, cell, internet)
# Configure pure tablet set: Wi-Fi, Bluetooth, Do Not Disturb, Auto-rotate, Battery, Screen Record, Cast, Alarm
QS_TILES="wifi,bt,dnd,rotation,battery,screenrecord,cast,alarm"
settings put secure sysui_qs_tiles "$QS_TILES"
echo "[+] Injected sysui_qs_tiles: $QS_TILES"

# 2. Suppress Cellular Airplane Mode dependency (Wi-Fi and Bluetooth only)
settings put global airplane_mode_radios "wifi,bluetooth"
echo "[+] Configured airplane_mode_radios to wifi,bluetooth"

# 3. Disable Cellular Data & Cellular Radios at the Settings Provider layer
settings put global mobile_data 0
settings put global mobile_data0 0
settings put global mobile_data1 0
settings put global cell_on 0
settings put global data_roaming 0
settings put global data_roaming0 0
settings put global data_roaming1 0
echo "[+] Disabled mobile data and cellular roaming"

# 4. Silence Carrier Network Name displays
settings put secure show_carrier_network_name 0
settings put global show_operator_name 0
echo "[+] Disabled operator name display"

# 5. Suppress Emergency Call UI buttons on Lockscreen
settings put secure emergency_affordance_needed 0
echo "[+] Disabled emergency affordance button"

echo "[✓] UI Sanitization complete."

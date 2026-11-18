<#
.SYNOPSIS
    Lenovo Tab with Clear Case (TB311FU / 'poplar') UI Sanitization Host Provisioner
    Requirement R5.4: Prunes missing-hardware Quick Settings tiles (flashlight & cell)
    and masks carrier text across Keyguard and SystemUI.
#>

[CmdletBinding()]
param(
    [string]$Serial = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$adbArgs = @()
if ($Serial -ne "") {
    $adbArgs += "-s", $Serial
}

function Run-Adb([string]$Command) {
    if ($DryRun) {
        Write-Host "[DRY-RUN] adb $adbArgs shell `"$Command`""
        return
    }
    Write-Host "[*] Executing: adb shell `"$Command`""
    & adb @adbArgs shell "$Command"
}

Write-Host "======================================================================"
Write-Host "Lenovo Tab with Clear Case (TB311FU) UI Sanitization & Quick Settings Setup"
Write-Host "======================================================================"

# 1. Prune Quick Settings Tiles (remove flashlight, cell, internet)
$qsTiles = "wifi,bt,dnd,rotation,battery,screenrecord,cast,alarm"
Run-Adb "settings put secure sysui_qs_tiles `"$qsTiles`""

# 2. Wi-Fi Only Airplane Mode Radios
Run-Adb "settings put global airplane_mode_radios `"wifi,bluetooth`""

# 3. Cellular Data & Roaming Termination
Run-Adb "settings put global mobile_data 0"
Run-Adb "settings put global cell_on 0"
Run-Adb "settings put global data_roaming 0"

# 4. Operator / Carrier Network Name Masking
Run-Adb "settings put secure show_carrier_network_name 0"
Run-Adb "settings put global show_operator_name 0"
Run-Adb "settings put secure emergency_affordance_needed 0"

Write-Host "[✓] UI Sanitization and Quick Settings provisioned successfully."

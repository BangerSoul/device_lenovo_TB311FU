#
# Lenovo Tab with Clear Case (TB311FU) Active Stylus Input Device Configuration
# Device Name: himax-touchscreen (Himax HX83102E Touch & Stylus Digitizer IC)
# Stylus: Lenovo Tab Pen / Tab Pen Plus (AP500U / AP501U)
# Protocol: Lenovo Pen Protocol 2.0 (LPP 2.0) / Wacom WGP
#

# Device Classification
device.internal = 1
touch.deviceType = touchScreen
touch.orientationAware = 1

# Coordinate & Spot Gesture Tracking
touch.gestureMode = spots

# Pressure Sensitivity Calibration
# Hardware digitizer reports 12-bit range (0 to 4095).
# Calibration scale factor: 1.0 / 4096.0 = 0.000244140625
touch.pressure.calibration = physical
touch.pressure.source = default
touch.pressure.scale = 0.000244140625

# Contact Area & Geometric Sizing Calibration
touch.size.calibration = area

# Tool Classification (Differentiates finger capacitance from active pen electrostatic pulse)
touch.toolType.calibration = linear

# Hover Distance Calibration (Active pen tip detection up to ~12mm above panel)
# Raw hardware distance reporting 0 (on screen) to 255 (maximum hover range)
# Scale factor: 1.0 / 256.0 = 0.00390625
touch.distance.calibration = scaled
touch.distance.scale = 0.00390625

# Palm Rejection Filter Level
# Level 2 enables advanced spatial and temporal palm filtering in TouchInputMapper
touch.filter.level = 2

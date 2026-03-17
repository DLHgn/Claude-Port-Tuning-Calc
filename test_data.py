"""
test_data.py — Default Test Values
====================================

Provides pre-configured driver and box parameters for quick testing.

The driver values come from the Tymphany XLS-12 datasheet, which was used
in Janne Ahonen's original LTSpice simulation example. The box parameters
are from the same example, configured as a vented (ported) enclosure.

Using a known reference driver makes it easy to validate the simulation
against LTSpice and WinISD results.

All values are stored in SI base units so they can be passed directly to
the physics engine without any conversion.
"""

# =============================================================================
# Tymphany XLS-12 Driver — Thiele-Small Parameters (SI units)
# =============================================================================
# Source: Tymphany XLS-12 datasheet, as used in Janne Ahonen's LTSpice example

DRIVER = {
    "re":  3.5,         # Voice coil DC resistance (Ohms)
    "le":  0.0042,      # Voice coil inductance (Henries)  — 4.2 mH
    "bl":  17.6,        # Force factor (Tesla·meters)
    "sd":  0.04662,     # Effective cone area (m²)         — 466.2 cm²
    "cms": 0.00046,     # Mechanical compliance (m/N)      — 0.46 mm/N
    "mms": 0.1663,      # Total moving mass (Kg)           — 166.3 g
    "rms": 5.12,        # Mechanical resistance (Kg/s)
}

# Display units — what unit label to show in the GUI for each parameter.
# These are purely for the UI; the DRIVER values above are already in SI.
DRIVER_DISPLAY_UNITS = {
    "re":  "ohm",
    "le":  "H",
    "bl":  "Tm",
    "sd":  "m^2",
    "cms": "m/N",
    "mms": "Kg",
    "rms": "Kg/s",
}

# =============================================================================
# Vented Box Parameters (SI units)
# =============================================================================
# Matched to the Janne Ahonen LTSpice simulation example

BOX = {
    "vb":             0.1,      # Net internal volume (m³)   — 100 liters
    "port_area":      0.0079,   # Single port cross-section area (m²) — ~79 cm²
    "port_length":    0.303,    # Physical port length (m)   — ~30.3 cm
    "num_ports":      1,        # Number of identical ports
    "end_correction": "One Flanged End",  # Human-readable label (mapped to 0.732)
}

BOX_DISPLAY_UNITS = {
    "vb":          "m^3",
    "port_area":   "m^2",
    "port_length": "m",
}

# =============================================================================
# Amplifier / Source
# =============================================================================

VG = 10  # Driving voltage (Volts RMS) — matches Janne's LTSpice Vg value

# =============================================================================
# Voice Coil Configuration
# =============================================================================

VC_TYPE   = "Single VC"   # "Single VC" or "Dual VC"
VC_WIRING = "Series"      # "Series" or "Parallel" (only relevant for Dual VC)

# =============================================================================
# Graph Defaults
# =============================================================================

GRAPH_START_FREQ = 10    # Hz
GRAPH_STOP_FREQ  = 120   # Hz
GRAPH_STEP       = 0.5   # Hz
"""
physics.py — Loudspeaker Equivalent Circuit Solver
===================================================

This module implements the electroacoustic equivalent circuit model for a
vented (ported) loudspeaker enclosure, as described by Janne Ahonen (WinISD).

The loudspeaker system is modeled as three coupled circuits:

  1. Electrical Circuit — The amplifier drives current (I) through the voice
     coil, which has resistance Re and inductance Le.

  2. Mechanical Circuit — The motor force (Bl·I) drives cone velocity (U)
     through the mechanical impedance: mass (Mms), compliance (Cms), and
     damping (Rms). In this analog, voltage = force, current = velocity.

  3. Acoustical Circuit — The cone's volume velocity (Sd·U) generates
     pressure (Pd) across the box impedance (Zb). In this analog,
     voltage = pressure, current = volume velocity.

The coupling between domains uses two transduction coefficients:
  - Bl (force factor in T·m): couples electrical ↔ mechanical
  - Sd (effective cone area in m²): couples mechanical ↔ acoustical

The three mesh equations (from Ahonen's derivation):
  EQ1 (Electrical):   Vg  = I·(Re + s·Le) + U·Bl
  EQ2 (Mechanical):   Bl·I = U·(Rms + 1/(s·Cms) + s·Mms) + Sd·Pd
  EQ3 (Acoustical):   Pd  = U · Sd · Zb

Solving algebraically yields:
  Zin = Ze + Bl² / Zt        (input impedance seen by the amplifier)
  I   = Vg / Zin             (voice coil current)
  U   = Bl·I / Zt            (cone velocity)
  Pd  = U · Sd · Zb          (pressure inside the box)

Where:
  Ze = Re + s·Le                              (voice coil electrical impedance)
  Zm = Rms + s·Mms + 1/(s·Cms)               (mechanical impedance)
  Zt = Zm + Sd²·Zb                            (total, including acoustic load)

References:
  - Janne Ahonen, WinISD electroacoustic model (private correspondence, 2021)
  - W. Marshall Leach, "Introduction to Electroacoustics and Audio Amplifier Design"
"""

import math
import cmath
import numpy as np
from dataclasses import dataclass, field


# =============================================================================
# Data Structures
# =============================================================================
# Using Python dataclasses for clean, self-documenting parameter containers.
# All values are expected in SI base units when passed to the analysis functions.

@dataclass
class DriverParams:
    """
    Thiele-Small parameters for a single loudspeaker driver.

    These are the fundamental electromechanical properties that fully describe
    how a driver converts electrical energy into acoustic output. They are
    typically measured by the driver manufacturer or with an impedance analyzer.

    All values must be in SI base units:
      re  — Voice coil DC resistance (Ohms)
      le  — Voice coil inductance (Henries)
      bl  — Motor force factor (Tesla·meters)
      sd  — Effective radiating area of the cone (m²)
      cms — Mechanical compliance of the suspension (m/N)
      mms — Total moving mass: cone + air load + coil (Kg)
      rms — Mechanical resistance (damping) of the suspension (Kg/s)
    """
    re: float
    le: float
    bl: float
    sd: float
    cms: float
    mms: float
    rms: float


@dataclass
class BoxParams:
    """
    Parameters describing a vented (ported) loudspeaker enclosure.

    All lengths, areas, and volumes must be in SI base units (m, m², m³).

    Fields:
      vb             — Net internal air volume of the box (m³)
      port_area      — Cross-sectional area of ONE port (m²)
      port_length    — Physical length of the port tube (m)
      num_ports      — Number of identical ports (default: 1)
      end_correction — Dimensionless factor accounting for the extra air mass
                       that "clings" to the ends of the port tube. Common values:
                         0.732 — One flanged end (most common for internal ports)
                         0.850 — Both ends flanged
                         0.614 — Both ends free (rare)
      ql             — Enclosure leakage Q-factor (default: 10). Models energy
                       lost through imperfect sealing. Higher = better sealed.
    """
    vb: float
    port_area: float
    port_length: float
    num_ports: int = 1
    end_correction: float = 0.732
    ql: float = 10.0


@dataclass
class EnvironmentParams:
    """
    Physical constants for the acoustic environment.

    Default values correspond to standard air at approximately 20°C / 68°F
    at sea level.

    Fields:
      rho — Air density (kg/m³)
      c   — Speed of sound in air (m/s)
    """
    rho: float = 1.18
    c: float = 343.68


@dataclass
class AnalysisResult:
    """
    Complete results of the equivalent circuit analysis at one frequency point.

    All values are in SI units unless otherwise noted in the field name.
    Complex quantities retain their full complex value for downstream use
    (e.g., computing group delay from the phase of Zin).
    """
    frequency: float            # Analysis frequency (Hz)
    fb: float                   # Port tuning frequency (Hz)
    zin: complex                # Total input impedance (Ohms, complex)
    zin_magnitude: float        # |Zin| in Ohms — what an impedance meter reads
    zin_phase_rad: float        # Phase angle of Zin (radians)
    current: complex            # Voice coil current I (Amps, complex)
    velocity: complex           # Cone velocity U (m/s, complex)
    pressure: complex           # Acoustic pressure inside box Pd (Pa, complex)
    port_velocity_peak_ms: float  # Peak air velocity in one port (m/s)
    cone_excursion_peak_mm: float # Peak cone displacement (mm)


# =============================================================================
# Port Tuning — Empirical Formulas
# =============================================================================
# The port tuning frequency (fb) is calculated using the average of two
# well-known empirical formulas rather than deriving it from the circuit model.
# This approach was chosen deliberately: the average of these two formulas
# produces results that closely match real-world measurements.

# Internal unit conversion constants for the empirical formulas,
# which were originally published in imperial / mixed units.
_M2_TO_IN2 = 1550.003
_M2_TO_CM2 = 10000.0
_M3_TO_IN3 = 61023.7
_M3_TO_L   = 1000.0
_M_TO_IN   = 39.3701
_M_TO_CM   = 100.0


def _port_diameter_cm(area_cm2: float) -> float:
    """Converts a circular port's cross-sectional area (cm²) to diameter (cm)."""
    if area_cm2 <= 0:
        return 0.0
    return 2.0 * math.sqrt(area_cm2 / math.pi)


def calculate_port_tuning(box: BoxParams) -> float:
    """
    Calculates the port tuning frequency (fb) by averaging two empirical formulas.

    Formula 1 — JL Audio:
        fb = 0.159 · √( A_total · 1.84e8 / (V · (L + k·√(A_single))) )
        (all inputs in inches / cubic inches)

    Formula 2 — DIY Audio:
        fb = 153.501 · D · √(N) / (√(V_L) · √(L_cm + k·D))
        (area as diameter in cm, volume in liters, length in cm)

    Where k is the end correction factor and N is the number of ports.

    Args:
        box: BoxParams with enclosure dimensions in SI units.

    Returns:
        Port tuning frequency in Hz, or 0 if any input is invalid.
    """
    if box.vb <= 0 or box.port_area <= 0 or box.num_ports <= 0:
        return 0.0

    # Convert from SI to the units each empirical formula expects
    total_area_in2     = box.port_area * box.num_ports * _M2_TO_IN2
    single_area_in2    = box.port_area * _M2_TO_IN2
    single_area_cm2    = box.port_area * _M2_TO_CM2
    volume_in3         = box.vb * _M3_TO_IN3
    volume_liters      = box.vb * _M3_TO_L
    length_in          = box.port_length * _M_TO_IN
    length_cm          = box.port_length * _M_TO_CM
    diameter_cm        = _port_diameter_cm(single_area_cm2)

    if diameter_cm <= 0:
        return 0.0

    k = box.end_correction  # Shorthand for readability

    # --- Formula 1: JL Audio ---
    jl_inner = volume_in3 * (length_in + k * math.sqrt(single_area_in2))
    fb1 = 0.159 * math.sqrt(total_area_in2 * 1.84e8 / jl_inner) if jl_inner > 0 else 0.0

    # --- Formula 2: DIY Audio ---
    diy_inner = math.sqrt(volume_liters) * math.sqrt(length_cm + k * diameter_cm)
    fb2 = (153.501 * diameter_cm * math.sqrt(box.num_ports)) / diy_inner if diy_inner > 0 else 0.0

    # Average the two results, ignoring any that failed (NaN or zero)
    valid_results = [f for f in (fb1, fb2) if f > 0 and math.isfinite(f)]
    return sum(valid_results) / len(valid_results) if valid_results else 0.0


# =============================================================================
# Acoustic Component Calculations
# =============================================================================
# These functions convert the physical properties of the box into their
# equivalent circuit elements in the acoustical domain.
#
# The vented box model consists of three parallel branches:
#
#     ────┬────────────┬────────────┬────
#         │            │            │
#        ═══ Ccab     ┤├ Ral      ╓╖ Lmap
#         │            │           ╙╜
#         │            │            │
#     ────┴────────────┴────────────┴────
#        (air spring) (leak)      (port mass)
#
# Ccab = acoustic compliance of the air volume (the "spring" of trapped air)
# Ral  = acoustic resistance of enclosure leaks
# Lmap = acoustic mass (inertance) of the air plug moving in the port

def _acoustic_compliance(vb: float, rho: float, c: float) -> float:
    """
    Acoustic compliance of the sealed air volume.
    Ccab = Vb / (ρ · c²)

    A larger box volume means higher compliance (softer air spring).
    """
    return vb / (rho * c ** 2)


def _acoustic_leak_resistance(ql: float, omega_b: float, ccab: float) -> float:
    """
    Acoustic resistance modeling air leakage through enclosure walls and seams.
    Ral = Ql / (ωb · Ccab)

    Higher Ql → higher resistance → less leakage → better-sealed box.
    """
    if omega_b == 0 or ccab == 0:
        return float('inf')
    return ql / (omega_b * ccab)


def _acoustic_port_mass(omega_b: float, ccab: float) -> float:
    """
    Acoustic mass (inertance) of the air column inside the port tube.
    Lmap = 1 / (ωb² · Ccab)

    Derived from the resonance condition at the tuning frequency fb:
    at resonance, ωb² = 1/(Lmap·Ccab), so Lmap = 1/(ωb²·Ccab).
    """
    if omega_b == 0 or ccab == 0:
        return float('inf')
    return 1.0 / (omega_b ** 2 * ccab)


def _box_impedance(s: complex, ccab: float, ral: float, lmap: float) -> complex:
    """
    Calculates the total acoustic impedance of the vented box (Zb).

    The three branches are in parallel, so we sum their admittances:
        1/Zb = (s · Ccab) + (1/Ral) + (1/(s · Lmap))

    Then Zb = 1 / (total admittance).
    """
    # Admittance of each branch
    y_spring = s * ccab                                           # Air compliance
    y_leak   = (1.0 / ral) if ral and ral != float('inf') else 0  # Air leakage
    y_port   = (1.0 / (s * lmap)) if s and lmap and lmap != float('inf') else 0  # Port mass

    total_admittance = y_spring + y_leak + y_port
    if total_admittance == 0:
        return float('inf')
    return 1.0 / total_admittance


# =============================================================================
# Core Equivalent Circuit Solver
# =============================================================================

def _solve_circuit(s: complex, driver: DriverParams, vg: float, zb: complex) -> dict:
    """
    Solves the coupled three-mesh loudspeaker equivalent circuit.

    The algebraic solution (derived by substituting EQ3 into EQ2, then into EQ1):

        Ze  = Re + s·Le                     (voice coil impedance)
        Zm  = Rms + s·Mms + 1/(s·Cms)       (cone/suspension mechanical impedance)
        Zt  = Zm + Sd²·Zb                    (total mech. impedance w/ acoustic load)
        Zin = Ze + Bl²/Zt                    (total input impedance)

        I  = Vg / Zin                        (voice coil current)
        U  = Bl·I / Zt                       (cone velocity)
        Pd = U · Sd · Zb                     (acoustic pressure in box)

    The Bl²/Zt term is called the "motional impedance" — it represents the
    back-EMF generated by the moving voice coil in the magnetic field. This is
    what causes the impedance peaks visible on an impedance plot: when Zt is
    small (near resonance), the motional impedance becomes very large.

    Args:
        s:      Complex frequency variable (j·ω)
        driver: DriverParams with Thiele-Small parameters
        vg:     Driving voltage (Volts RMS)
        zb:     Acoustic box impedance at this frequency

    Returns:
        dict with keys 'zin', 'i', 'u', 'pd' (all complex-valued)
    """
    # --- Electrical impedance ---
    z_elec = driver.re + s * driver.le

    # --- Mechanical impedance ---
    # The compliance term 1/(s·Cms) is the mechanical analog of a capacitor's
    # impedance 1/(sC) in electronics. At low frequencies it dominates (stiff),
    # at high frequencies the mass term s·Mms dominates (inertia).
    if s == 0:
        z_mech = float('inf')
    else:
        z_mech = driver.rms + s * driver.mms + 1.0 / (s * driver.cms)

    # --- Total mechanical impedance (including acoustic load from the box) ---
    # The Sd² factor transforms the acoustic impedance Zb into the mechanical
    # domain: F = Sd·Pd and Q = Sd·U, so Z_acoustic_in_mech = Sd²·Zb.
    z_total = z_mech + driver.sd ** 2 * zb

    # --- Input impedance as seen by the amplifier ---
    z_input = z_elec + (driver.bl ** 2 / z_total if z_total else 0)

    # --- Solve for the three unknowns ---
    current_i   = vg / z_input if z_input else 0     # Amps
    velocity_u  = driver.bl * current_i / z_total if z_total else 0  # m/s
    pressure_pd = velocity_u * driver.sd * zb         # Pascals

    return {
        'zin': z_input,
        'i':   current_i,
        'u':   velocity_u,
        'pd':  pressure_pd,
    }


# =============================================================================
# Derived Output Quantities
# =============================================================================

def _peak_port_velocity(pd: complex, s: complex, lmap: float,
                        single_port_area: float) -> float:
    """
    Calculates the peak air velocity through a single port.

    The volume velocity through the port equals the "current" through the
    Lmap branch of the acoustic circuit:
        Q_port = Pd / (s · Lmap)      [units: m³/s]

    Dividing by the port's cross-sectional area gives linear velocity,
    and multiplying by √2 converts RMS to peak:
        v_peak = √2 · |Q_port| / A_port    [units: m/s]

    This matches the LTSpice expression: sqrt(2)*I(Lmap)/(port_area)
    """
    if not s or lmap == 0 or lmap == float('inf') or single_port_area <= 0:
        return 0.0
    volume_velocity = pd / (s * lmap)
    return abs(volume_velocity) * math.sqrt(2) / single_port_area


def _peak_cone_excursion_m(u: complex, omega: float) -> float:
    """
    Calculates peak cone excursion (displacement) from cone velocity.

    In the frequency domain, displacement is the integral of velocity:
        X = U / (jω)

    So the peak displacement magnitude is:
        x_peak = √2 · |U| / ω    [units: meters]

    The √2 converts from RMS to peak value.

    This matches the LTSpice expression: sqrt(2)*I(Vu)/w
    """
    if omega == 0:
        return 0.0
    return abs(u) * math.sqrt(2) / omega


# =============================================================================
# Public Analysis API
# =============================================================================

def analyze_at_frequency(freq_hz: float, driver: DriverParams, box: BoxParams,
                         vg: float, env: EnvironmentParams = None) -> AnalysisResult:
    """
    Runs the complete equivalent circuit analysis at a single frequency.

    This is the main entry point for the physics engine. It:
      1. Calculates the port tuning frequency (fb) from box geometry
      2. Derives the acoustic circuit components (Ccab, Ral, Lmap) from fb
      3. Computes the box impedance (Zb) at the analysis frequency
      4. Solves the three-mesh circuit for current I, velocity U, pressure Pd
      5. Derives port velocity and cone excursion from the solution

    Args:
        freq_hz:  Frequency to analyze (Hz). Must be > 0.
        driver:   DriverParams with all Thiele-Small parameters in SI units.
        box:      BoxParams with enclosure dimensions in SI units.
        vg:       Driving voltage (Volts RMS).
        env:      EnvironmentParams (optional, defaults to standard air at 20°C).

    Returns:
        AnalysisResult dataclass with every computed quantity at this frequency.
    """
    if env is None:
        env = EnvironmentParams()

    # --- Frequency variables ---
    omega = 2.0 * math.pi * freq_hz   # Angular frequency for THIS analysis point
    s     = 1j * omega                  # Complex frequency variable (s = jω)

    # --- Port tuning ---
    fb      = calculate_port_tuning(box)
    omega_b = 2.0 * math.pi * fb       # Angular frequency at box tuning

    # --- Acoustic circuit components (derived from box geometry and fb) ---
    ccab = _acoustic_compliance(box.vb, env.rho, env.c)
    ral  = _acoustic_leak_resistance(box.ql, omega_b, ccab)
    lmap = _acoustic_port_mass(omega_b, ccab)

    # --- Box impedance at the analysis frequency ---
    zb = _box_impedance(s, ccab, ral, lmap)

    # --- Solve the equivalent circuit ---
    solution = _solve_circuit(s, driver, vg, zb)

    # --- Derive output quantities ---
    port_vel = _peak_port_velocity(solution['pd'], s, lmap, box.port_area)
    cone_exc = _peak_cone_excursion_m(solution['u'], omega)

    return AnalysisResult(
        frequency             = freq_hz,
        fb                    = fb,
        zin                   = solution['zin'],
        zin_magnitude         = abs(solution['zin']),
        zin_phase_rad         = cmath.phase(solution['zin']),
        current               = solution['i'],
        velocity              = solution['u'],
        pressure              = solution['pd'],
        port_velocity_peak_ms = port_vel,
        cone_excursion_peak_mm = cone_exc * 1000,  # meters → millimeters
    )


def analyze_frequency_range(frequencies: np.ndarray, driver: DriverParams,
                            box: BoxParams, vg: float,
                            env: EnvironmentParams = None) -> list[AnalysisResult]:
    """
    Runs the full analysis across an array of frequencies.

    This is a convenience wrapper that calls analyze_at_frequency() for each
    frequency in the array. Frequencies <= 0 are skipped.

    Args:
        frequencies: NumPy array of frequencies in Hz.
        driver:      DriverParams (SI units).
        box:         BoxParams (SI units).
        vg:          Driving voltage (Volts RMS).
        env:         EnvironmentParams (optional).

    Returns:
        List of AnalysisResult objects, one per valid frequency.
    """
    return [
        analyze_at_frequency(f, driver, box, vg, env)
        for f in frequencies
        if f > 0
    ]
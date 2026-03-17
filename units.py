"""
units.py — Unit Conversion Utility
====================================

Provides a single function, `convert()`, that converts a numeric value from
one unit to another within the same physical dimension (e.g., inches → meters).

The conversion works by defining every unit's factor relative to the SI base
unit for that dimension. To convert from unit A to unit B:

    result = value × (factor_A / factor_B)

For example, to convert 12 inches to centimeters:
    factor_in = 0.0254      (inches → meters)
    factor_cm = 0.01        (centimeters → meters)
    result    = 12 × (0.0254 / 0.01) = 30.48 cm

The module groups units by physical dimension so that nonsensical conversions
(e.g., meters → kilograms) are impossible — they'll raise a ValueError.

Usage:
    from units import convert

    length_m = convert(12.0, "in", "m")       # 0.3048
    area_m2  = convert(466.2, "cm^2", "m^2")  # 0.04662
    vol_m3   = convert(100.0, "L", "m^3")     # 0.1
"""


# =============================================================================
# Unit Definitions
# =============================================================================
# Each tuple: (unit_string, factor_to_si_base)
# All factors express: 1 <unit> = <factor> × <SI base unit>

_LENGTH_UNITS = {
    # SI base: meters (m)
    "m":   1.0,
    "cm":  0.01,
    "mm":  0.001,
    "in":  0.0254,
    "ft":  0.3048,
}

_AREA_UNITS = {
    # SI base: m²
    "m^2":  1.0,
    "cm^2": 1e-4,
    "mm^2": 1e-6,
    "in^2": 6.4516e-4,
    "ft^2": 0.092903,
}

_VOLUME_UNITS = {
    # SI base: m³
    "m^3":  1.0,
    "L":    0.001,
    "cm^3": 1e-6,
    "mm^3": 1e-9,
    "in^3": 1.63871e-5,
    "ft^3": 0.0283168,
}

_INDUCTANCE_UNITS = {
    # SI base: Henries (H)
    "H":  1.0,
    "mH": 0.001,
}

_MASS_UNITS = {
    # SI base: kilograms (Kg)
    "Kg": 1.0,
    "g":  0.001,
}

_COMPLIANCE_UNITS = {
    # SI base: m/N  (meters per Newton)
    "m/N":  1.0,
    "mm/N": 0.001,
    "um/N": 1e-6,
}

_MECHANICAL_RESISTANCE_UNITS = {
    # SI base: Kg/s  (also called N·s/m or mechanical ohms)
    "Kg/s": 1.0,
    "Ns/s": 1.0,   # Alternate notation sometimes seen in datasheets
}

# These dimensions have only one practical unit in this context,
# but we include them so the conversion function works uniformly.
_FORCE_FACTOR_UNITS = {
    # Bl: Tesla·meters
    "Tm":  1.0,
    "N/A": 1.0,    # Equivalent notation (Newtons per Ampere)
}

_RESISTANCE_UNITS = {
    # Electrical resistance: Ohms
    "ohm": 1.0,
}

_VOLTAGE_UNITS = {
    # Volts
    "V": 1.0,
    "W": 1.0,  # Placeholder — Vg is labeled "W" in the GUI but treated as volts
}


# =============================================================================
# Master Lookup — Maps every known unit string to (dimension_name, factor)
# =============================================================================
# Built automatically from the dimension dictionaries above.

_ALL_UNITS: dict[str, tuple[str, float]] = {}

_DIMENSION_TABLES = [
    ("length",                _LENGTH_UNITS),
    ("area",                  _AREA_UNITS),
    ("volume",                _VOLUME_UNITS),
    ("inductance",            _INDUCTANCE_UNITS),
    ("mass",                  _MASS_UNITS),
    ("compliance",            _COMPLIANCE_UNITS),
    ("mechanical_resistance", _MECHANICAL_RESISTANCE_UNITS),
    ("force_factor",          _FORCE_FACTOR_UNITS),
    ("resistance",            _RESISTANCE_UNITS),
    ("voltage",               _VOLTAGE_UNITS),
]

for _dim_name, _table in _DIMENSION_TABLES:
    for _unit_str, _factor in _table.items():
        if _unit_str in _ALL_UNITS:
            # Some unit strings appear in multiple dimensions (shouldn't happen,
            # but guard against copy-paste errors in the tables above).
            raise ValueError(f"Duplicate unit string '{_unit_str}' in dimension '{_dim_name}'")
        _ALL_UNITS[_unit_str] = (_dim_name, _factor)


# =============================================================================
# Public API
# =============================================================================

def convert(value: float, from_unit: str, to_unit: str) -> float:
    """
    Converts a numeric value between two units of the same physical dimension.

    Args:
        value:     The numeric value to convert.
        from_unit: The unit the value is currently in (e.g., "in", "cm^2", "L").
        to_unit:   The target unit to convert to (e.g., "m", "m^2", "m^3").

    Returns:
        The converted value as a float.

    Raises:
        ValueError: If either unit string is unknown, or if the two units
                    belong to different physical dimensions.

    Examples:
        >>> convert(12.0, "in", "m")
        0.3048
        >>> convert(466.2, "cm^2", "m^2")
        0.04662
        >>> convert(100.0, "L", "m^3")
        0.1
    """
    if from_unit == to_unit:
        return value  # No conversion needed — fast path

    # Look up both units
    from_entry = _ALL_UNITS.get(from_unit)
    to_entry   = _ALL_UNITS.get(to_unit)

    if from_entry is None:
        raise ValueError(f"Unknown unit: '{from_unit}'")
    if to_entry is None:
        raise ValueError(f"Unknown unit: '{to_unit}'")

    from_dim, from_factor = from_entry
    to_dim,   to_factor   = to_entry

    if from_dim != to_dim:
        raise ValueError(
            f"Cannot convert between different dimensions: "
            f"'{from_unit}' ({from_dim}) → '{to_unit}' ({to_dim})"
        )

    return value * (from_factor / to_factor)


def get_si_unit(unit_str: str) -> str:
    """
    Returns the SI base unit string for the same dimension as the given unit.

    This is useful when you have a display unit (e.g., "cm^2") and need to
    know what SI unit to convert to (e.g., "m^2").

    Args:
        unit_str: Any recognized unit string.

    Returns:
        The SI base unit string for that dimension.

    Raises:
        ValueError: If the unit string is not recognized.

    Examples:
        >>> get_si_unit("in")
        'm'
        >>> get_si_unit("L")
        'm^3'
        >>> get_si_unit("mH")
        'H'
    """
    entry = _ALL_UNITS.get(unit_str)
    if entry is None:
        raise ValueError(f"Unknown unit: '{unit_str}'")

    dim_name, _ = entry

    # Find the dimension table and return the unit whose factor is 1.0
    for name, table in _DIMENSION_TABLES:
        if name == dim_name:
            for unit, factor in table.items():
                if factor == 1.0:
                    return unit

    # Should never reach here if tables are set up correctly
    raise ValueError(f"No SI base unit found for dimension '{dim_name}'")


def get_units_for_dimension(unit_str: str) -> list[str]:
    """
    Returns all available unit strings for the same dimension as the given unit.

    Useful for populating GUI dropdowns — pass any unit from a dimension and
    get back all the options.

    Args:
        unit_str: Any recognized unit string.

    Returns:
        List of all unit strings in the same dimension.

    Examples:
        >>> get_units_for_dimension("in")
        ['m', 'cm', 'mm', 'in', 'ft']
        >>> get_units_for_dimension("L")
        ['m^3', 'L', 'cm^3', 'mm^3', 'in^3', 'ft^3']
    """
    entry = _ALL_UNITS.get(unit_str)
    if entry is None:
        raise ValueError(f"Unknown unit: '{unit_str}'")

    dim_name, _ = entry

    for name, table in _DIMENSION_TABLES:
        if name == dim_name:
            return list(table.keys())

    return []
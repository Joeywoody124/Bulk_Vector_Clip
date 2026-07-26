"""Paper sizes, scale parsing and sheet-size maths.

Pure Python - see the package docstring for why.
"""

import re

MM_PER_INCH = 25.4

#: Metres per linear unit, for the CRS units that matter here.
METRES_PER_UNIT = {
    "m": 1.0,
    "ft": 0.3048,  # international foot
    "ftUS": 1200.0 / 3937.0,  # US survey foot
}

#: Sheet sizes in millimetres, portrait (width, height).
#: The three in daily use come first so they are the short trip in the dropdown.
#: Note ANSI D is 22x34 and ARCH D is 24x36 - they are not the same sheet.
PAPER_SIZES = {
    "Letter (8.5x11)": (215.9, 279.4),
    "Tabloid (11x17)": (279.4, 431.8),
    "ARCH D (24x36)": (609.6, 914.4),
    "ANSI C (17x22)": (431.8, 558.8),
    "ANSI D (22x34)": (558.8, 863.6),
    "ANSI E (34x44)": (863.6, 1117.6),
    "ARCH C (18x24)": (457.2, 609.6),
    "ARCH E1 (30x42)": (762.0, 1066.8),
    "A4 (210x297)": (210.0, 297.0),
    "A3 (297x420)": (297.0, 420.0),
    "A2 (420x594)": (420.0, 594.0),
    "A1 (594x841)": (594.0, 841.0),
    "A0 (841x1189)": (841.0, 1189.0),
}

PAPER_NAMES = list(PAPER_SIZES)

DEFAULT_PAPER = "ARCH D (24x36)"
DEFAULT_SCALE = "1\"=60'"

#: The engineering ladder, for the estimator's default.
DEFAULT_SCALE_LADDER = "1\"=20',1\"=30',1\"=40',1\"=50',1\"=60',1\"=100',1\"=200'"

_UNIT_TO_M = {
    '"': 0.0254,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
    "'": 0.3048,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
    "m": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "km": 1000.0,
}

_INCH_UNITS = ('"', "in", "inch", "inches")

_NUM_UNIT = re.compile(r"^([0-9]*\.?[0-9]+)\s*(.*)$")


def _split_number_unit(token):
    """``50'`` -> (50.0, "'"), ``60`` -> (60.0, None)."""
    token = token.strip()
    match = _NUM_UNIT.match(token)
    if not match:
        raise ValueError("Cannot read a length from %r" % token)
    unit = match.group(2).strip().rstrip(".").lower()
    return float(match.group(1)), (unit or None)


def _to_metres(value, unit):
    if unit not in _UNIT_TO_M:
        raise ValueError("Unknown unit %r" % unit)
    return value * _UNIT_TO_M[unit]


def parse_scale(text):
    """Return the scale denominator for a scale written any of the usual ways.

    ``1:2000`` -> 2000, ``1"=50'`` -> 600, ``1 in = 100 ft`` -> 1200,
    ``600`` -> 600.

    An engineering scale with a bare right-hand side - ``1"=60`` - is read as
    feet, because that is what it means on every plan set that writes it that
    way.
    """
    raw = str(text).strip().lower()
    if not raw:
        raise ValueError("No scale given")

    if ":" in raw:
        left, right = raw.split(":", 1)
        denom = float(right.strip()) / float(left.strip())
    elif "=" in raw:
        left, right = raw.split("=", 1)
        left_value, left_unit = _split_number_unit(left)
        right_value, right_unit = _split_number_unit(right)
        if left_unit is None:
            raise ValueError(
                "Give the left-hand side a unit, for example 1\"=60' or 1cm=20m")
        if right_unit is None:
            if left_unit not in _INCH_UNITS:
                raise ValueError(
                    "Give the right-hand side a unit, for example 1cm=20m")
            right_unit = "ft"
        denom = (_to_metres(right_value, right_unit)
                 / _to_metres(left_value, left_unit))
    else:
        denom = float(raw)

    if denom <= 0:
        raise ValueError("Scale denominator must be positive, got %s" % denom)
    return round(denom, 6)


def format_scale(denominator, imperial=False):
    """Human-readable scale, for logs and report tables."""
    if imperial:
        feet = denominator / 12.0
        if abs(feet - round(feet)) < 1e-6:
            return '1" = %d\'' % round(feet)
        return '1" = %.2f\'' % feet
    return "1:%s" % ("%g" % denominator)


def sheet_size(paper_mm, margin_mm, scale_denominator, metres_per_unit,
               landscape=True):
    """Printable sheet size expressed in the layer's map units.

    ``paper_mm`` is a (width, height) portrait pair from :data:`PAPER_SIZES`.
    Returns (width, height) in map units.
    """
    width, height = paper_mm
    if landscape:
        width, height = height, width
    printable_w = width - 2.0 * margin_mm
    printable_h = height - 2.0 * margin_mm
    if printable_w <= 0 or printable_h <= 0:
        raise ValueError(
            "Margins of %s mm leave nothing to print on a %s x %s mm sheet"
            % (margin_mm, width, height)
        )
    if metres_per_unit <= 0:
        raise ValueError("metres_per_unit must be positive")
    factor = scale_denominator / 1000.0 / metres_per_unit
    return (printable_w * factor, printable_h * factor)


def parse_scale_list(text):
    """Parse a comma-separated ladder of scales into denominators."""
    out = []
    for chunk in str(text).split(","):
        chunk = chunk.strip()
        if chunk:
            out.append(parse_scale(chunk))
    if not out:
        raise ValueError("No scales given")
    return out

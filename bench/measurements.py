from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType


FLOW_UNIT_FACTORS = MappingProxyType({
    'mL/s': Fraction(1),
    'L/min': Fraction(50, 3),
})


@dataclass(frozen=True)
class NormalizedMeasurement:
    key: str
    response: Fraction
    design: tuple[Fraction, ...]


def _rational(value):
    if type(value) not in (int, str, Fraction):
        raise ValueError('expected an exact rational value')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'invalid rational value {value!r}') from error


def _name(value):
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError('expected a nonempty name without surrounding whitespace')
    return value


def _vector(values, width):
    if not isinstance(values, (list, tuple)) or len(values) != width:
        raise ValueError(f'expected a vector of length {width}')
    return tuple(_rational(value) for value in values)


def _unit_factor(unit):
    if not isinstance(unit, str) or unit not in FLOW_UNIT_FACTORS:
        raise ValueError(f'unsupported flow unit {unit!r}')
    return FLOW_UNIT_FACTORS[unit]


def _check_fields(record, fields):
    if not isinstance(record, dict) or record.keys() != fields:
        raise ValueError(f'expected fields {", ".join(sorted(fields))}')


def normalize_measurement(key, value, unit, design, width):
    return NormalizedMeasurement(
        _name(key), _rational(value) * _unit_factor(unit), _vector(design, width)
    )

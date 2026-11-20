from dataclasses import dataclass
from fractions import Fraction

from bench.measurements import _check_fields, _name, _rational, _unit_factor, _vector


class DuplicateChannelError(ValueError):
    pass


@dataclass(frozen=True)
class ChannelDefinition:
    name: str
    offset: Fraction
    coefficients: tuple[Fraction, ...]


def normalize_wiring(channels, width):
    if not isinstance(channels, (list, tuple)) or not channels:
        raise ValueError('at least one channel definition is required')
    names = set()
    definitions = []
    for channel in channels:
        _check_fields(channel, {'name', 'offset', 'unit', 'coefficients'})
        name = _name(channel['name'])
        if name in names:
            raise DuplicateChannelError(name)
        names.add(name)
        factor = _unit_factor(channel['unit'])
        definitions.append(ChannelDefinition(
            name,
            _rational(channel['offset']) * factor,
            tuple(value * factor for value in _vector(channel['coefficients'], width)),
        ))
    return tuple(sorted(definitions, key=lambda channel: channel.name))

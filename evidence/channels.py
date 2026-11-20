from dataclasses import dataclass
from fractions import Fraction


def _check_shape(matrix):
    if any(value != matrix[j][i] for i, row in enumerate(matrix) for j, value in enumerate(row)):
        raise ValueError('public shape must be symmetric')
    remaining = [list(row) for row in matrix]
    for pivot in range(len(remaining)):
        diagonal = remaining[pivot][pivot]
        tail = remaining[pivot][pivot + 1:]
        if diagonal < 0 or (diagonal == 0 and any(tail)):
            raise ValueError('public shape must be positive semidefinite')
        if diagonal == 0:
            continue
        for i, left in enumerate(tail, start=pivot + 1):
            for j, right in enumerate(tail, start=pivot + 1):
                remaining[i][j] -= left * right / diagonal


@dataclass(frozen=True)
class ChannelCatalog:
    names: tuple[str, ...]

    def __post_init__(self):
        names = tuple(self.names)
        if not names or any(type(name) is not str or not name or name.strip() != name for name in names):
            raise ValueError('channel catalog contains an invalid name')
        if len(set(names)) != len(names):
            raise ValueError('channel catalog contains duplicate names')
        object.__setattr__(self, 'names', names)

    def index_of(self, name):
        try:
            return self.names.index(name)
        except ValueError as error:
            raise KeyError(name) from error


@dataclass(frozen=True)
class ReadingPair:
    inlet_center: Fraction
    outlet_center: Fraction
    inlet_shape: Fraction
    cross_shape: Fraction
    outlet_shape: Fraction


@dataclass(frozen=True)
class PublicReadings:
    catalog: ChannelCatalog
    center: tuple[Fraction, ...]
    shape: tuple[tuple[Fraction, ...], ...]

    def __post_init__(self):
        center = tuple(self.center)
        shape = tuple(tuple(row) for row in self.shape)
        size = len(self.catalog.names)
        if len(center) != size or len(shape) != size or any(len(row) != size for row in shape):
            raise ValueError('public evidence dimensions do not match the channel catalog')
        if any(type(value) not in (int, Fraction) for row in (center, *shape) for value in row):
            raise ValueError('public evidence requires exact rational values')
        center = tuple(map(Fraction, center))
        shape = tuple(tuple(map(Fraction, row)) for row in shape)
        _check_shape(shape)
        object.__setattr__(self, 'center', center)
        object.__setattr__(self, 'shape', shape)

    def pair(self, inlet_index, outlet_index):
        return ReadingPair(
            self.center[inlet_index], self.center[outlet_index],
            self.shape[inlet_index][inlet_index], self.shape[inlet_index][outlet_index],
            self.shape[outlet_index][outlet_index],
        )

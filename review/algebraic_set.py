from dataclasses import dataclass
from functools import cmp_to_key

from review.quadratics import ExactNumber, compare_exact


@dataclass(frozen=True)
class ExactInterval:
    lower: ExactNumber | None
    upper: ExactNumber | None
    lower_closed: bool = False
    upper_closed: bool = False

    def __post_init__(self):
        if (self.lower is None and self.lower_closed) or (self.upper is None and self.upper_closed):
            raise ValueError('infinite endpoints must be open')
        if self.lower is not None and self.upper is not None:
            order = compare_exact(self.lower, self.upper)
            if order > 0 or (order == 0 and not (self.lower_closed and self.upper_closed)):
                raise ValueError('interval has no points')

    def contains(self, value):
        if self.lower is not None:
            order = compare_exact(value, self.lower)
            if order < 0 or (order == 0 and not self.lower_closed):
                return False
        if self.upper is not None:
            order = compare_exact(value, self.upper)
            if order > 0 or (order == 0 and not self.upper_closed):
                return False
        return True


@dataclass(frozen=True)
class RatioSet:
    components: tuple[ExactInterval, ...]

    def contains(self, value):
        return any(interval.contains(value) for interval in self.components)


def _lower_order(left, right):
    if left.lower is None or right.lower is None:
        order = (left.lower is not None) - (right.lower is not None)
    else:
        order = compare_exact(left.lower, right.lower)
    return order or (right.lower_closed - left.lower_closed)


def _join(left, right):
    if left.upper is None:
        return left
    if right.lower is not None:
        contact = compare_exact(left.upper, right.lower)
        if contact < 0 or (contact == 0 and not (left.upper_closed or right.lower_closed)):
            return None
    if right.upper is None:
        return ExactInterval(left.lower, None, left.lower_closed)
    order = compare_exact(left.upper, right.upper)
    if order > 0:
        return left
    closed = right.upper_closed or (order == 0 and left.upper_closed)
    return ExactInterval(left.lower, right.upper, left.lower_closed, closed)


def normalize_ratio_set(intervals):
    merged = []
    for interval in sorted(intervals, key=cmp_to_key(_lower_order)):
        combined = _join(merged[-1], interval) if merged else None
        if combined is None:
            merged.append(interval)
        else:
            merged[-1] = combined
    return RatioSet(tuple(merged))

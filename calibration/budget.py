from dataclasses import dataclass
from fractions import Fraction

from bench.measurements import _rational


class InfeasibleBudget(ValueError):
    pass


@dataclass(frozen=True)
class ResidualBudget:
    limit: Fraction
    minimum: Fraction
    slack: Fraction


def evaluate_budget(limit, minimum):
    limit, minimum = _rational(limit), _rational(minimum)
    if minimum < 0:
        raise ValueError('minimum residual sum must be nonnegative')
    slack = limit - minimum
    if slack < 0:
        raise InfeasibleBudget(f'minimum residual sum {minimum} exceeds budget {limit}')
    return ResidualBudget(limit, minimum, slack)

from dataclasses import dataclass

from bench.revisions import FrozenRevision
from calibration.budget import ResidualBudget, evaluate_budget
from calibration.design import build_design
from calibration.least_squares import LeastSquaresResult, fit_least_squares


@dataclass(frozen=True)
class FittedCalibration:
    revision: FrozenRevision
    least_squares: LeastSquaresResult
    budget: ResidualBudget


def fit_frozen_revision(revision, limit):
    solution = fit_least_squares(build_design(revision))
    budget = evaluate_budget(limit, solution.residual_sum)
    return FittedCalibration(revision, solution, budget)

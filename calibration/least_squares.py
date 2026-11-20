from dataclasses import dataclass
from fractions import Fraction

from calibration.design import CalibrationDesign
from calibration.rational_linalg import SingularMatrixError, gram_matrix, multiply_matrices, solve_linear_system


class RankDeficientCalibration(ValueError):
    pass


@dataclass(frozen=True)
class LeastSquaresResult:
    center: tuple[Fraction, ...]
    gram: tuple[tuple[Fraction, ...], ...]
    residual_sum: Fraction


def fit_least_squares(design: CalibrationDesign):
    matrix = design.matrix
    gram = gram_matrix(matrix)
    transpose = tuple(zip(*matrix, strict=True))
    column_response = tuple((value,) for value in design.response)
    right = tuple(row[0] for row in multiply_matrices(transpose, column_response))
    try:
        center = solve_linear_system(gram, right)
    except SingularMatrixError as error:
        raise RankDeficientCalibration(design.revision_id) from error

    predicted = multiply_matrices(matrix, tuple((value,) for value in center))
    residual_sum = sum((
        (observation - estimate[0]) ** 2
        for observation, estimate in zip(design.response, predicted, strict=True)
    ), Fraction(0))
    return LeastSquaresResult(center, gram, residual_sum)

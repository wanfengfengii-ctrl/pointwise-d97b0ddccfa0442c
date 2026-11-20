from fractions import Fraction

from calibration.rational_linalg import multiply_matrices, solve_linear_system
from evidence.channels import ChannelCatalog, PublicReadings


def _public_center(wiring, coefficients, least_squares):
    fitted_column = tuple((value,) for value in least_squares.center)
    linear_centers = multiply_matrices(coefficients, fitted_column)
    return tuple(
        linear[0] + channel.offset
        for linear, channel in zip(linear_centers, wiring, strict=True)
    )


def project_joint_domain(fitted, wiring):
    catalog = ChannelCatalog(tuple(channel.name for channel in wiring))
    least_squares = fitted.least_squares
    coefficients = tuple(channel.coefficients for channel in wiring)
    center = _public_center(wiring, coefficients, least_squares)
    slack = fitted.budget.slack
    if slack == 0:
        zero_row = (Fraction(0),) * len(center)
        return PublicReadings(catalog, center, (zero_row,) * len(center))

    inverse_actions = tuple(
        solve_linear_system(least_squares.gram, row) for row in coefficients
    )
    unscaled = multiply_matrices(coefficients, tuple(zip(*inverse_actions, strict=True)))
    shape = tuple(tuple(slack * value for value in row) for row in unscaled)
    return PublicReadings(catalog, center, shape)


def project_tolerance_domain(fitted, wiring):
    catalog = ChannelCatalog(tuple(channel.name for channel in wiring))
    least_squares = fitted.least_squares
    coefficients = tuple(channel.coefficients for channel in wiring)
    center = _public_center(wiring, coefficients, least_squares)
    # The unscaled Gram action W G^{-1} W^T describes every reachable public
    # reading together with the exact residual cost of reaching it, including
    # the zero-slack and rank-reduced cases.
    inverse_actions = tuple(
        solve_linear_system(least_squares.gram, row) for row in coefficients
    )
    unscaled = multiply_matrices(coefficients, tuple(zip(*inverse_actions, strict=True)))
    return PublicReadings(catalog, center, unscaled)

from fractions import Fraction
from functools import cmp_to_key

from review.algebraic_set import ExactInterval, RatioSet, normalize_ratio_set
from review.quadratics import compare_exact, polynomial_sign, rational_between, solve_real_quadratic
from review.request import BoundRatioRequest


def compute_ratio_set(bound: BoundRatioRequest):
    pair = bound.pair
    inlet = pair.inlet_center
    outlet = pair.outlet_center
    inlet_shape, cross, outlet_shape = pair.inlet_shape, pair.cross_shape, pair.outlet_shape
    if inlet == 0 and inlet_shape == 0:
        return RatioSet(())

    # The ratio line is the zero set of outlet - r*inlet. Its squared
    # projected radius and its squared mean determine whether it intersects.
    width = (inlet_shape, -2 * cross, outlet_shape)
    room = (inlet_shape - inlet**2, 2 * (inlet * outlet - cross), outlet_shape - outlet**2)
    determinant = inlet_shape * outlet_shape - cross**2
    # When width is positive, this polynomial is the slice center's inlet
    # multiplied by width. The inlet can vary inside a proper slice only
    # when the shape has rank two and the ratio line is not tangent.
    inlet_on_slice = (
        Fraction(0), outlet * inlet_shape - inlet * cross, inlet * outlet_shape - outlet * cross
    )

    def has_witness(value):
        clearance = polynomial_sign(room, value)
        if clearance < 0:
            return False
        if polynomial_sign(width, value) == 0:
            # A zero-width intersecting line contains the entire domain.
            return True
        if clearance > 0 and determinant > 0:
            return True
        return polynomial_sign(inlet_on_slice, value) != 0

    cuts = sorted({
        root for polynomial in (room, width, inlet_on_slice)
        for root in (solve_real_quadratic(*polynomial) or ())
    }, key=cmp_to_key(compare_exact))
    pieces = []
    left = None
    for right in [*cuts, None]:
        if has_witness(rational_between(left, right)):
            pieces.append(ExactInterval(left, right))
        if right is not None and has_witness(right):
            pieces.append(ExactInterval(right, right, True, True))
        left = right
    return normalize_ratio_set(pieces)

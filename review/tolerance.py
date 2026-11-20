"""Exact offline tolerance assessment.

The V2 calibration envelope exposes, for every public channel, the least
squares reading center ``r0`` and the unscaled Gram action ``B = W G^-1 W^T``.
A public reading ``z = r0 + B q`` is reachable precisely when
``(z - r0) = B q`` for some rational parameter ``q``, and reaching it costs

    residual_sum(z) = residual_floor + (z - r0)^T B^+ (z - r0).

Constrained channels give closed rational intervals, so the minimum cost is
the exact solution of a strictly convex quadratic program with linear box
constraints.  The KKT optimum is recovered by exhaustive active-set
enumeration over the small constraint list; every arithmetic operation stays
in :class:`fractions.Fraction`.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from calibration.rational_linalg import SingularMatrixError, solve_linear_system
from evidence.codec import ToleranceCalibrationArtifact
from review.quadratics import compare_exact


@dataclass(frozen=True)
class ToleranceInterval:
    name: str
    lower: Fraction
    upper: Fraction


def _rational_endpoint(value):
    if isinstance(value, bool) or type(value) not in (int, str, Fraction):
        raise ValueError('tolerance endpoints must be exact rational values')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f'invalid rational endpoint {value!r}') from error


def parse_intervals(artifact: ToleranceCalibrationArtifact, intervals):
    if not isinstance(intervals, (list, tuple)) or not intervals:
        raise ValueError('a nonempty interval group is required')
    catalog = artifact.readings.catalog
    seen = set()
    parsed = []
    for item in intervals:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError('each tolerance entry must be [name, lower, upper]')
        name, lower, upper = item
        if not isinstance(name, str) or not name or name.strip() != name:
            raise ValueError('tolerance channel names must be nonempty clean strings')
        if name in seen:
            raise ValueError(f'duplicate tolerance channel {name!r}')
        try:
            catalog.index_of(name)
        except KeyError as error:
            raise ValueError(f'unknown tolerance channel {error.args[0]!r}') from error
        seen.add(name)
        low = _rational_endpoint(lower)
        high = _rational_endpoint(upper)
        if compare_exact(low, high) > 0:
            raise ValueError(f'reversed tolerance interval for {name!r}')
        parsed.append(ToleranceInterval(name, low, high))
    return tuple(sorted(parsed, key=lambda interval: interval.name))


def _eliminate(matrix):
    """Gauss-Jordan elimination returning (pivot_columns, reduced rows)."""
    rows = [list(row) for row in matrix]
    pivots = []
    pivot_row = 0
    for column in range(len(rows[0]) if rows else 0):
        pivot = next((index for index in range(pivot_row, len(rows)) if rows[index][column]), None)
        if pivot is None:
            continue
        rows[pivot_row], rows[pivot] = rows[pivot], rows[pivot_row]
        divisor = rows[pivot_row][column]
        rows[pivot_row] = [value / divisor for value in rows[pivot_row]]
        for index in range(len(rows)):
            if index == pivot_row or not rows[index][column]:
                continue
            factor = rows[index][column]
            rows[index] = [
                value - factor * pivot_value
                for value, pivot_value in zip(rows[index], rows[pivot_row], strict=True)
            ]
        pivots.append(column)
        pivot_row += 1
    return tuple(pivots), rows


def factor_public_shape(shape):
    """Rank-revealing rational elimination of the symmetric PSD shape.

    Returns ``(basis, inverse, links)`` where ``basis`` lists the independent
    channel rows, ``inverse`` is the inverse of the principal basis block, and
    ``links`` maps every channel row to its coordinates on the basis rows.
    """
    size = len(shape)
    basis, _ = _eliminate(shape)
    if not basis:
        empty_links = tuple(tuple() for _ in range(size))
        return (), (), empty_links
    degree = len(basis)
    principal = tuple(tuple(shape[row][column] for column in basis) for row in basis)
    inverse = tuple(
        solve_linear_system(principal, tuple(1 if j == i else 0 for j in range(degree)))
        for i in range(degree)
    )
    links = tuple(tuple(shape[row][column] for column in basis) for row in range(size))
    return basis, inverse, links


def _build_constraints(artifact, intervals):
    readings = artifact.readings
    center, shape = readings.center, readings.shape
    basis, inverse, links = factor_public_shape(shape)
    degree = len(basis)
    index_of = readings.catalog.index_of
    # Every constraint is kept in the uniform form ``normal . u <= delta``,
    # where the normal lives in the basis-variable coordinates. An independent
    # channel contributes its own basis direction; a dependent channel
    # contributes the linear combination that reaches it through the wiring; a
    # constant channel only needs a feasibility check.
    constraints = []
    constants_feasible = True
    for interval in intervals:
        channel = index_of(interval.name)
        row = links[channel]
        low_delta = interval.lower - center[channel]
        high_delta = interval.upper - center[channel]
        if not any(row):
            # A constant channel is feasible only when its fixed reading lies
            # inside the requested closed interval.
            reading = center[channel]
            if reading < interval.lower or reading > interval.upper:
                constants_feasible = False
            continue
        # In basis coordinates every non-constant channel moves along the
        # normal B_SS^-1 B_{cS}; this holds for both basis rows (where B_{cS}
        # is a unit direction) and linearly dependent rows.
        normal = tuple(sum(inverse[i][j] * row[j] for j in range(degree))
                       for i in range(degree))
        # Uniform form ``normal . u <= delta`` for both interval endpoints:
        # the lower bound ``normal.u >= low`` becomes ``-normal.u <= -low``.
        pair = (
            (tuple(-value for value in normal), -low_delta),
            (normal, high_delta),
        )
        for normal, delta in pair:
            if (normal, delta) not in constraints:
                constraints.append((normal, delta))
    return basis, inverse, constraints, constants_feasible


def _linearly_independent(normals):
    pivots, _ = _eliminate(normals)
    return len(pivots) == len(normals)


def minimum_residual_sum(artifact, intervals):
    """Return the exact minimum residual sum, or ``None`` when infeasible."""
    basis, inverse, constraints, constants_feasible = _build_constraints(artifact, intervals)
    degree = len(basis)
    if not constants_feasible:
        return None
    if degree == 0:
        return artifact.residual_floor

    def cost(point):
        # q^T H^-1 q where H is the inverse of the principal basis block.
        total = Fraction(0)
        for i, value in enumerate(point):
            total += value * sum(inverse[i][j] * point[j] for j in range(degree))
        return artifact.residual_floor + total

    count = len(constraints)
    best = None
    for active_count in range(min(degree, count) + 1):
        for subset in combinations(range(count), active_count):
            normals = tuple(constraints[index][0] for index in subset)
            if active_count > 0 and not _linearly_independent(normals):
                continue
            if active_count == 0:
                point, multipliers = (Fraction(0),) * degree, ()
            else:
                kkt = [[Fraction(0) for _ in range(degree + active_count)]
                       for _ in range(degree + active_count)]
                for i in range(degree):
                    for j in range(degree):
                        # Stationarity of the quadratic cost uses 2 H^-1.
                        kkt[i][j] = 2 * inverse[i][j]
                for position, index in enumerate(subset):
                    normal = constraints[index][0]
                    for row in range(degree):
                        kkt[row][degree + position] = normal[row]
                        kkt[degree + position][row] = normal[row]
                rhs = [Fraction(0)] * degree + [
                    constraints[index][1] for index in subset
                ]
                try:
                    solution = solve_linear_system(
                        tuple(tuple(row) for row in kkt), tuple(rhs)
                    )
                except SingularMatrixError:
                    continue
                point = solution[:degree]
                multipliers = solution[degree:]
            if any(multiplier < 0 for multiplier in multipliers):
                continue
            feasible = True
            for normal, delta in constraints:
                value = sum(normal[j] * point[j] for j in range(degree))
                if value > delta:
                    feasible = False
                    break
            if not feasible:
                continue
            candidate = cost(point)
            if best is None or candidate < best:
                best = candidate
    return best

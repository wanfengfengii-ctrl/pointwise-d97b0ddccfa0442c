from dataclasses import dataclass
from fractions import Fraction
from math import gcd, isqrt, lcm


@dataclass(frozen=True)
class QuadraticNumber:
    a: int
    b: int
    c: int
    root_index: int

    def __post_init__(self):
        if any(type(value) is not int for value in (self.a, self.b, self.c, self.root_index)):
            raise ValueError('quadratic representation requires integers')
        if self.a <= 0 or gcd(self.a, self.b, self.c) != 1 or self.root_index not in (0, 1):
            raise ValueError('noncanonical quadratic representation')
        discriminant = self.discriminant
        if discriminant <= 0 or isqrt(discriminant) ** 2 == discriminant:
            raise ValueError('quadratic endpoint must have two distinct irrational roots')

    @property
    def discriminant(self):
        return self.b * self.b - 4 * self.a * self.c

    def bounds(self, bits):
        scale = 1 << bits
        numerator = isqrt(self.discriminant * scale * scale)
        low, high = Fraction(numerator, scale), Fraction(numerator + 1, scale)
        divisor = 2 * self.a
        if self.root_index == 0:
            return (-self.b - high) / divisor, (-self.b - low) / divisor
        return (-self.b + low) / divisor, (-self.b + high) / divisor


ExactNumber = Fraction | QuadraticNumber


def solve_real_quadratic(a, b, c):
    """Return ordered distinct real roots, or None for the zero polynomial."""
    a, b, c = map(Fraction, (a, b, c))
    if not a:
        if b:
            return (-c / b,)
        return () if c else None

    scale = lcm(a.denominator, b.denominator, c.denominator)
    a, b, c = (int(value * scale) for value in (a, b, c))
    divisor = gcd(a, b, c)
    if a < 0:
        divisor = -divisor
    a, b, c = (value // divisor for value in (a, b, c))
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return ()
    root = isqrt(discriminant)
    if root == 0:
        return (Fraction(-b, 2 * a),)
    if root * root == discriminant:
        return Fraction(-b - root, 2 * a), Fraction(-b + root, 2 * a)
    return QuadraticNumber(a, b, c, 0), QuadraticNumber(a, b, c, 1)


def _bounds(value, bits):
    if isinstance(value, QuadraticNumber):
        return value.bounds(bits)
    return Fraction(value), Fraction(value)


def _precisions():
    bits = 0
    while True:
        yield bits
        bits = max(8, bits * 2)


def compare_exact(left, right):
    if left == right:
        return 0
    # Distinct irrational roots have distinct canonical polynomial/root pairs.
    for bits in _precisions():
        left_low, left_high = _bounds(left, bits)
        right_low, right_high = _bounds(right, bits)
        if left_high <= right_low:
            return -1
        if right_high <= left_low:
            return 1


def rational_between(left, right):
    if left is None and right is None:
        return Fraction(0)
    if left is None:
        return _bounds(right, 0)[0] - 1
    if right is None:
        return _bounds(left, 0)[1] + 1
    if compare_exact(left, right) >= 0:
        raise ValueError('expected two ordered distinct endpoints')
    for bits in _precisions():
        low, high = _bounds(left, bits)[1], _bounds(right, bits)[0]
        if low < high:
            return (low + high) / 2


def polynomial_sign(coefficients, value):
    a, b, c = coefficients
    if isinstance(value, QuadraticNumber):
        # Reduce modulo the minimal polynomial so only one exact comparison is needed.
        factor = Fraction(a) / value.a
        b -= factor * value.b
        c -= factor * value.c
        if b:
            return (1 if b > 0 else -1) * compare_exact(value, -c / b)
        evaluated = c
    else:
        evaluated = (a * value + b) * value + c
    return (evaluated > 0) - (evaluated < 0)

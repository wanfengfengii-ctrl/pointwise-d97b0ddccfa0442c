import json
from dataclasses import dataclass
from fractions import Fraction

from review.algebraic_set import ExactInterval, RatioSet, normalize_ratio_set
from review.quadratics import QuadraticNumber


@dataclass(frozen=True)
class ReportRecord:
    report_id: int
    artifact_id: str
    revision_id: str
    revision_fingerprint: str
    inlet: str
    outlet: str
    ratios: RatioSet


def _encode_endpoint(value):
    if value is None:
        return None
    if isinstance(value, QuadraticNumber):
        return [value.a, value.b, value.c, value.root_index]
    return str(value)


def _decode_endpoint(value):
    if value is None:
        return None
    if type(value) is str:
        try:
            result = Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError('invalid rational endpoint') from error
        if str(result) != value:
            raise ValueError('noncanonical rational endpoint')
        return result
    if type(value) is list and len(value) == 4:
        return QuadraticNumber(*value)
    raise ValueError('invalid archived endpoint')


def encode_ratio_set(ratios):
    return json.dumps([
        [_encode_endpoint(part.lower), _encode_endpoint(part.upper), part.lower_closed, part.upper_closed]
        for part in ratios.components
    ], separators=(',', ':'))


def decode_ratio_set(text):
    payload = json.loads(text)
    if type(payload) is not list:
        raise ValueError('invalid archived ratio set')
    intervals = []
    for part in payload:
        if type(part) is not list or len(part) != 4:
            raise ValueError('invalid archived interval')
        low, high, lower_closed, upper_closed = part
        if type(lower_closed) is not bool or type(upper_closed) is not bool:
            raise ValueError('invalid archived endpoint closure')
        intervals.append(ExactInterval(_decode_endpoint(low), _decode_endpoint(high), lower_closed, upper_closed))
    result = normalize_ratio_set(intervals)
    if result.components != tuple(intervals):
        raise ValueError('archived ratio set is not canonical')
    return result

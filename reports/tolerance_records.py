import json
from dataclasses import dataclass
from fractions import Fraction

from review.tolerance import ToleranceInterval


@dataclass(frozen=True)
class ToleranceReport:
    report_id: int
    artifact_id: str
    revision_id: str
    revision_fingerprint: str
    limit: Fraction
    intervals: tuple[ToleranceInterval, ...]
    minimum_residual_sum: Fraction | None
    within_budget: bool


def _rational_text(value):
    if value is None:
        return None
    return str(value)


def encode_tolerance_report(report):
    return json.dumps({
        'limit': str(report.limit),
        'intervals': [
            [interval.name, str(interval.lower), str(interval.upper)]
            for interval in report.intervals
        ],
        'minimum_residual_sum': _rational_text(report.minimum_residual_sum),
        'within_budget': report.within_budget,
    }, sort_keys=True, separators=(',', ':'))


def _decode_rational(raw):
    if type(raw) is not str:
        raise ValueError('invalid archived tolerance value')
    try:
        value = Fraction(raw)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid archived rational value') from error
    if str(value) != raw:
        raise ValueError('noncanonical archived rational value')
    return value


def decode_tolerance_report(text):
    body = json.loads(text)
    if type(body) is not dict or body.keys() != {
        'limit', 'intervals', 'minimum_residual_sum', 'within_budget'
    }:
        raise ValueError('invalid archived tolerance report')
    if type(body['intervals']) is not list or not body['intervals']:
        raise ValueError('invalid archived tolerance intervals')
    intervals = []
    seen = set()
    for entry in body['intervals']:
        if type(entry) is not list or len(entry) != 3 or any(type(part) is not str for part in entry):
            raise ValueError('invalid archived tolerance interval')
        name, lower, upper = entry
        if name in seen:
            raise ValueError('duplicate archived tolerance interval')
        seen.add(name)
        intervals.append(ToleranceInterval(name, _decode_rational(lower), _decode_rational(upper)))
    ordered = tuple(sorted(intervals, key=lambda interval: interval.name))
    if ordered != tuple(intervals):
        raise ValueError('archived tolerance intervals are not canonical')
    minimum = None if body['minimum_residual_sum'] is None else _decode_rational(
        body['minimum_residual_sum']
    )
    if type(body['within_budget']) is not bool:
        raise ValueError('invalid archived budget verdict')
    return {
        'limit': _decode_rational(body['limit']),
        'intervals': ordered,
        'minimum_residual_sum': minimum,
        'within_budget': body['within_budget'],
    }

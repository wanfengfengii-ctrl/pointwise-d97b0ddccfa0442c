from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class CalibrationDesign:
    revision_id: str
    columns: tuple[str, ...]
    matrix: tuple[tuple[Fraction, ...], ...]
    response: tuple[Fraction, ...]


def build_design(revision):
    rows = revision.cohort.measurements
    return CalibrationDesign(
        revision.revision_id,
        revision.cohort.columns,
        tuple(row.design for row in rows),
        tuple(row.response for row in rows),
    )

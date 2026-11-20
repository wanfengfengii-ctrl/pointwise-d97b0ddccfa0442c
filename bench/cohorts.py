import json
from dataclasses import dataclass, replace

from bench.measurements import NormalizedMeasurement, _check_fields, _name, normalize_measurement
from bench.wiring import ChannelDefinition, normalize_wiring


@dataclass(frozen=True)
class WorkingCohort:
    columns: tuple[str, ...]
    measurements: tuple[NormalizedMeasurement, ...]
    wiring: tuple[ChannelDefinition, ...]


def prepare_cohort(columns, measurements, wiring):
    if not isinstance(columns, (list, tuple)) or not columns:
        raise ValueError('at least one private column is required')
    columns = tuple(_name(name) for name in columns)
    if len(set(columns)) != len(columns):
        raise ValueError('private column names must be unique')
    if not isinstance(measurements, (list, tuple)) or not measurements:
        raise ValueError('at least one reading is required')

    readings = {}
    for record in measurements:
        _check_fields(record, {'key', 'value', 'unit', 'design'})
        reading = normalize_measurement(**record, width=len(columns))
        if reading.key in readings:
            raise ValueError(f'duplicate reading {reading.key!r}')
        readings[reading.key] = reading
    return WorkingCohort(
        columns,
        tuple(readings[key] for key in sorted(readings)),
        normalize_wiring(wiring, len(columns)),
    )


def apply_reading_corrections(cohort, corrections):
    if not isinstance(corrections, (list, tuple)) or not corrections:
        raise ValueError('at least one correction is required')
    originals = {row.key: row for row in cohort.measurements}
    updates = {}
    for correction in corrections:
        _check_fields(correction, {'key', 'value', 'unit'})
        key = _name(correction['key'])
        if key in updates:
            raise ValueError(f'duplicate correction for {key!r}')
        if key not in originals:
            raise ValueError(f'unknown reading {key!r}')
        updates[key] = normalize_measurement(
            **correction, design=originals[key].design, width=len(cohort.columns)
        )
    return replace(cohort, measurements=tuple(
        updates.get(row.key, row) for row in cohort.measurements
    ))


def encode_cohort(cohort):
    body = {
        'columns': cohort.columns,
        'measurements': [
            {'key': row.key, 'value': str(row.response), 'unit': 'mL/s',
             'design': [str(value) for value in row.design]}
            for row in cohort.measurements
        ],
        'wiring': [
            {'name': channel.name, 'offset': str(channel.offset), 'unit': 'mL/s',
             'coefficients': [str(value) for value in channel.coefficients]}
            for channel in cohort.wiring
        ],
    }
    return json.dumps(body, sort_keys=True, separators=(',', ':'))


def decode_cohort(text):
    body = json.loads(text)
    _check_fields(body, {'columns', 'measurements', 'wiring'})
    return prepare_cohort(**body)

import json
from dataclasses import dataclass
from fractions import Fraction

from evidence.channels import ChannelCatalog, PublicReadings


@dataclass(frozen=True)
class CalibrationArtifact:
    artifact_id: str
    revision_id: str
    revision_fingerprint: str
    readings: PublicReadings


def encode_artifact(artifact):
    readings = artifact.readings
    return json.dumps({
        'version': 1,
        'artifact_id': artifact.artifact_id,
        'revision_id': artifact.revision_id,
        'revision_fingerprint': artifact.revision_fingerprint,
        'channels': readings.catalog.names,
        'center': [str(value) for value in readings.center],
        'shape': [[str(value) for value in row] for row in readings.shape],
    }, sort_keys=True, separators=(',', ':'))


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate calibration field {key!r}')
        result[key] = value
    return result


def _exact_row(raw):
    if type(raw) is not list or any(type(value) is not str for value in raw):
        raise ValueError('calibration values must be arrays of rational strings')
    try:
        result = tuple(Fraction(value) for value in raw)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid rational in calibration') from error
    if any(str(value) != text for value, text in zip(result, raw, strict=True)):
        raise ValueError('noncanonical rational in calibration')
    return result


def _decode_envelope(text, fields):
    if type(text) is not str:
        raise ValueError('calibration envelope must be text')
    body = json.loads(text, object_pairs_hook=_unique_fields)
    if type(body) is not dict or body.keys() != fields:
        raise ValueError('invalid calibration envelope fields')
    for key in ('artifact_id', 'revision_id'):
        if type(body[key]) is not str or not body[key].strip():
            raise ValueError(f'invalid {key}')
    fingerprint = body['revision_fingerprint']
    if type(fingerprint) is not str or len(fingerprint) != 64 or any(
        char not in '0123456789abcdef' for char in fingerprint
    ):
        raise ValueError('invalid revision fingerprint')
    return body, fingerprint


def _decode_readings(body):
    if type(body['channels']) is not list or type(body['shape']) is not list:
        raise ValueError('invalid calibration catalog or shape')
    return PublicReadings(
        ChannelCatalog(tuple(body['channels'])), _exact_row(body['center']),
        tuple(_exact_row(row) for row in body['shape']),
    )


def _exact_scalar(raw):
    if type(raw) is not str:
        raise ValueError('calibration values must be rational strings')
    try:
        value = Fraction(raw)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid rational in calibration') from error
    if str(value) != raw:
        raise ValueError('noncanonical rational in calibration')
    return value


def decode_artifact(text):
    fields = {'version', 'artifact_id', 'revision_id', 'revision_fingerprint', 'channels', 'center', 'shape'}
    body, fingerprint = _decode_envelope(text, fields)
    if type(body['version']) is not int or body['version'] != 1:
        raise ValueError('unsupported calibration envelope version')
    readings = _decode_readings(body)
    return CalibrationArtifact(body['artifact_id'], body['revision_id'], fingerprint, readings)


@dataclass(frozen=True)
class ToleranceCalibrationArtifact:
    artifact_id: str
    revision_id: str
    revision_fingerprint: str
    readings: PublicReadings
    residual_floor: Fraction
    limit: Fraction


def encode_tolerance_artifact(artifact):
    readings = artifact.readings
    return json.dumps({
        'version': 2,
        'artifact_id': artifact.artifact_id,
        'revision_id': artifact.revision_id,
        'revision_fingerprint': artifact.revision_fingerprint,
        'channels': readings.catalog.names,
        'center': [str(value) for value in readings.center],
        'shape': [[str(value) for value in row] for row in readings.shape],
        'residual_floor': str(artifact.residual_floor),
        'limit': str(artifact.limit),
    }, sort_keys=True, separators=(',', ':'))


def decode_tolerance_artifact(text):
    fields = {
        'version', 'artifact_id', 'revision_id', 'revision_fingerprint', 'channels',
        'center', 'shape', 'residual_floor', 'limit',
    }
    body, fingerprint = _decode_envelope(text, fields)
    if type(body['version']) is not int or body['version'] != 2:
        raise ValueError('unsupported tolerance calibration envelope version')
    readings = _decode_readings(body)
    residual_floor = _exact_scalar(body['residual_floor'])
    limit = _exact_scalar(body['limit'])
    if residual_floor < 0:
        raise ValueError('residual floor must be nonnegative')
    if limit < residual_floor:
        raise ValueError('tolerance limit must cover the residual floor')
    return ToleranceCalibrationArtifact(
        body['artifact_id'], body['revision_id'], fingerprint, readings, residual_floor, limit
    )

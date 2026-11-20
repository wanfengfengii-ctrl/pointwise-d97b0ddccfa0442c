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
        return tuple(Fraction(value) for value in raw)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid rational in calibration') from error


def decode_artifact(text):
    if type(text) is not str:
        raise ValueError('calibration envelope must be text')
    body = json.loads(text, object_pairs_hook=_unique_fields)
    fields = {'version', 'artifact_id', 'revision_id', 'revision_fingerprint', 'channels', 'center', 'shape'}
    if type(body) is not dict or body.keys() != fields:
        raise ValueError('invalid calibration envelope fields')
    if type(body['version']) is not int or body['version'] != 1:
        raise ValueError('unsupported calibration envelope version')
    for key in ('artifact_id', 'revision_id'):
        if type(body[key]) is not str or not body[key].strip():
            raise ValueError(f'invalid {key}')
    fingerprint = body['revision_fingerprint']
    if type(fingerprint) is not str or len(fingerprint) != 64 or any(
        char not in '0123456789abcdef' for char in fingerprint
    ):
        raise ValueError('invalid revision fingerprint')
    if type(body['channels']) is not list or type(body['shape']) is not list:
        raise ValueError('invalid calibration catalog or shape')
    readings = PublicReadings(
        ChannelCatalog(tuple(body['channels'])), _exact_row(body['center']),
        tuple(_exact_row(row) for row in body['shape']),
    )
    return CalibrationArtifact(body['artifact_id'], body['revision_id'], fingerprint, readings)

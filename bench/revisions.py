import hashlib
import json
from dataclasses import dataclass

from bench.cohorts import WorkingCohort, decode_cohort, encode_cohort


@dataclass(frozen=True)
class FrozenRevision:
    revision_id: str
    work_version: int
    fingerprint: str
    cohort: WorkingCohort


def cohort_fingerprint(cohort):
    return hashlib.sha256(encode_cohort(cohort).encode('utf-8')).hexdigest()


def freeze_cohort(cohort, revision_id, work_version):
    return FrozenRevision(revision_id, work_version, cohort_fingerprint(cohort), cohort)


def encode_revision(revision):
    return json.dumps({
        'revision_id': revision.revision_id,
        'work_version': revision.work_version,
        'fingerprint': revision.fingerprint,
        'cohort': encode_cohort(revision.cohort),
    }, sort_keys=True, separators=(',', ':'))


def decode_revision(text):
    body = json.loads(text)
    revision = freeze_cohort(
        decode_cohort(body['cohort']), body['revision_id'], body['work_version']
    )
    if revision.fingerprint != body['fingerprint']:
        raise ValueError('frozen revision fingerprint mismatch')
    return revision

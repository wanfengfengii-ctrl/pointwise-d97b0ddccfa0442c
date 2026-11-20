import json
import sqlite3
from contextlib import closing
from pathlib import Path

from bench.store import BenchLedger
from calibration.fit import fit_frozen_revision
from evidence.issue import issue_calibration
from evidence.register import IssueRegister


SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def sample_batch():
    return json.loads((SAMPLES / 'batch.json').read_text(encoding='utf-8'))


def sample_correction():
    return json.loads((SAMPLES / 'correction.json').read_text(encoding='utf-8'))


def channel(name, offset, coefficients, unit='mL/s'):
    return {'name': name, 'offset': offset, 'coefficients': coefficients, 'unit': unit}


def reading(key, value, design, unit='mL/s'):
    return {'key': key, 'value': value, 'design': design, 'unit': unit}


def initialize_bench(connection):
    ledger, register = BenchLedger(connection), IssueRegister(connection)
    ledger.initialize()
    register.initialize()
    return ledger, register


def issue_current(ledger, register, budget=1):
    revision = ledger.freeze_current()
    artifact = issue_calibration(fit_frozen_revision(revision, budget), register)
    return revision, artifact, register.get(artifact.artifact_id)


def disk_artifact(batch=None):
    with closing(sqlite3.connect(':memory:')) as connection:
        ledger, register = initialize_bench(connection)
        ledger.accept_batch(**(sample_batch() if batch is None else batch))
        return issue_current(ledger, register)


def archive_counts(connection):
    reports = connection.execute('SELECT COUNT(*) FROM ratio_reports').fetchone()[0]
    receipts = connection.execute('SELECT COUNT(*) FROM report_receipts').fetchone()[0]
    return reports, receipts

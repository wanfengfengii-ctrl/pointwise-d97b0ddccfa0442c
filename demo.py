import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from bench.store import BenchLedger
from calibration.fit import fit_frozen_revision
from evidence.issue import issue_calibration
from evidence.register import IssueRegister
from reports.publish import initialize_archive
from reports.records import encode_ratio_set
from reports.retrieve import retrieve_report
from review.assess import assess_and_publish
from review.request import RatioRequest


ROOT = Path(__file__).resolve().parent
A_EXPECTED = [[None, '0', False, True], ['2', None, True, False]]
B_EXPECTED = [[None, '0', False, False], ['0', None, False, False]]
CORRECTED_EXPECTED = [[None, [1, 0, -3, 0], False, True], [[1, 0, -3, 1], None, True, False]]


def _snapshot(report, receipt):
    return {
        'report_id': report.report_id,
        'artifact_id': report.artifact_id,
        'revision_id': report.revision_id,
        'revision_fingerprint': report.revision_fingerprint,
        'inlet': report.inlet,
        'outlet': report.outlet,
        'ratios': json.loads(encode_ratio_set(report.ratios)),
        'receipt': asdict(receipt),
    }


def offline_report(archive, artifact_text, inlet, outlet):
    completed = subprocess.run(
        [sys.executable, '-B', str(ROOT / 'demo.py'), 'offline', str(archive), inlet, outlet],
        input=artifact_text, text=True, capture_output=True, encoding='utf-8',
    )
    if completed.returncode:
        raise RuntimeError(f'offline review exited {completed.returncode}: {completed.stderr.strip()}')
    return json.loads(completed.stdout)


def _freeze_and_issue(ledger, register):
    revision = ledger.freeze_current()
    artifact = issue_calibration(fit_frozen_revision(revision, '1'), register)
    return artifact, register.get(artifact.artifact_id)


def run_workday(directory):
    source = directory / 'bench.sqlite3'
    archive = directory / 'archive.sqlite3'
    batch = json.loads((ROOT / 'samples' / 'batch.json').read_text(encoding='utf-8'))
    corrections = json.loads((ROOT / 'samples' / 'correction.json').read_text(encoding='utf-8'))
    with closing(sqlite3.connect(source)) as connection:
        ledger, register = BenchLedger(connection), IssueRegister(connection)
        ledger.initialize()
        register.initialize()
        ledger.accept_batch(**batch)
        original, original_text = _freeze_and_issue(ledger, register)

    first = offline_report(archive, original_text, 'in', 'out-a')
    second = offline_report(archive, original_text, 'in', 'out-b')
    observed = [first['ratios'], second['ratios']]
    if observed != [A_EXPECTED, B_EXPECTED]:
        raise AssertionError(f'RATIO_SET_MISMATCH expected {[A_EXPECTED, B_EXPECTED]!r}, got {observed!r}')

    with closing(sqlite3.connect(source)) as connection:
        ledger, register = BenchLedger(connection), IssueRegister(connection)
        ledger.initialize()
        register.initialize()
        ledger.correct_readings(corrections)
        corrected, corrected_text = _freeze_and_issue(ledger, register)
        if register.get(original.artifact_id) != original_text:
            raise AssertionError('source correction changed the original calibration envelope')
    revised = offline_report(archive, corrected_text, 'in', 'out-b')
    replay = offline_report(archive, original_text, 'in', 'out-b')

    with closing(sqlite3.connect(archive)) as connection:
        initialize_archive(connection)
        first_retrieved = _snapshot(*retrieve_report(connection, first['report_id']))
        second_retrieved = _snapshot(*retrieve_report(connection, second['report_id']))
    downstream_expected = {
        'first_pair_bound_to_original': True,
        'corrected_bound_to_new_revision': True,
        'corrected_ratios': CORRECTED_EXPECTED,
        'replay_bound_to_original': True,
        'replay_ratios': B_EXPECTED,
        'original_reports_and_receipts_retrieved': True,
        'replay_has_own_receipt': True,
    }
    downstream_actual = {
        'first_pair_bound_to_original': all(
            report['artifact_id'] == original.artifact_id and report['revision_id'] == original.revision_id
            and report['revision_fingerprint'] == original.revision_fingerprint
            for report in (first, second)
        ),
        'corrected_bound_to_new_revision': (
            corrected.revision_id != original.revision_id and revised['artifact_id'] == corrected.artifact_id
            and revised['revision_id'] == corrected.revision_id
            and revised['revision_fingerprint'] == corrected.revision_fingerprint
        ),
        'corrected_ratios': revised['ratios'],
        'replay_bound_to_original': (
            replay['artifact_id'] == original.artifact_id and replay['revision_id'] == original.revision_id
            and replay['revision_fingerprint'] == original.revision_fingerprint
        ),
        'replay_ratios': replay['ratios'],
        'original_reports_and_receipts_retrieved': (first_retrieved, second_retrieved) == (first, second),
        'replay_has_own_receipt': replay['receipt'] != second['receipt'],
    }
    if downstream_actual != downstream_expected:
        raise AssertionError(f'workday archive mismatch: {downstream_actual!r}')
    return {
        'case_id': 'N2',
        'input': {'budget': '1', 'batch': batch, 'requests': [['in', 'out-a'], ['in', 'out-b']],
                  'next_day_corrections': corrections},
        'expected': [A_EXPECTED, B_EXPECTED],
        'actual': observed,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': ['bench/store.py', 'calibration/fit.py', 'evidence/projection.py', 'evidence/issue.py',
                       'review/ratios.py', 'reports/publish.py', 'reports/retrieve.py'],
        'oracle': '甲为 1+1/x，分别取 x∈[-1,0) 和 x∈(0,1]。乙在单位盘中比值零只经过原点，其余斜率均有非零入口见证。更正后圆心为 (0,2)，过原点的切线斜率满足 r²=3，切点入口非零。重开按先前保存的报告核对回执。',
    }, first_retrieved


def main(argv=None):
    parser = argparse.ArgumentParser(description='澄浦双口流量变比复核')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('workday')
    offline = commands.add_parser('offline')
    offline.add_argument('archive', type=Path)
    offline.add_argument('inlet')
    offline.add_argument('outlet')
    args = parser.parse_args(argv)
    if args.command == 'offline':
        with closing(sqlite3.connect(args.archive)) as connection:
            initialize_archive(connection)
            report, receipt = assess_and_publish(connection, sys.stdin.read(), RatioRequest(args.inlet, args.outlet))
        print(json.dumps(_snapshot(report, receipt), ensure_ascii=True))
        return 0
    with tempfile.TemporaryDirectory(prefix='chengpu-') as directory:
        scenario, original_report = run_workday(Path(directory))
        print('POINTWISE_SCENARIO ' + json.dumps(scenario, ensure_ascii=False, sort_keys=True))
        print(json.dumps({'retrieved_original_report': original_report}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

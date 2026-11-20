import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path

from bench.store import BenchLedger
from calibration.fit import fit_frozen_revision
from evidence.codec import decode_artifact, decode_tolerance_artifact
from evidence.issue import issue_calibration, issue_tolerance_calibration
from evidence.register import IssueRegister
from reports.publish import initialize_archive
from reports.retrieve import ReportNotFound, retrieve_tolerance_report
from review.assess import assess_tolerance_and_publish


SAMPLES = Path(__file__).resolve().parents[1] / 'samples'
TOLERANCE_CASES = json.loads((SAMPLES / 'tolerance.json').read_text(encoding='utf-8'))


def tolerance_artifact(case, directory, corrections=None):
    path = Path(directory) / 'bench.sqlite3'
    with closing(sqlite3.connect(path)) as connection:
        ledger, register = BenchLedger(connection), IssueRegister(connection)
        ledger.initialize()
        register.initialize()
        ledger.accept_batch(**case['batch'])
        if corrections:
            ledger.correct_readings(corrections)
        revision = ledger.freeze_current()
        fitted = fit_frozen_revision(revision, case['limit'])
        artifact = issue_tolerance_calibration(fitted, register)
        return artifact, register.get(artifact.artifact_id), revision


class ToleranceSampleTests(unittest.TestCase):
    def test_every_sample_request_matches_fixed_minimum_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'archive.sqlite3'
            for case in TOLERANCE_CASES:
                artifact, text, revision = tolerance_artifact(case, directory)
                with self.subTest(case=case['name']):
                    self.assertEqual(
                        (artifact.revision_id, artifact.revision_fingerprint),
                        (revision.revision_id, revision.fingerprint),
                    )
                    decoded = decode_tolerance_artifact(text)
                    self.assertEqual(decoded, artifact)
                    self.assertEqual(set(json.loads(text)), {
                        'version', 'artifact_id', 'revision_id', 'revision_fingerprint',
                        'channels', 'center', 'shape', 'residual_floor', 'limit',
                    })
                    self.assertEqual(json.loads(text)['version'], 2)
                    for private in case['batch']['columns']:
                        self.assertNotIn(private, text)
                with closing(sqlite3.connect(archive)) as connection:
                    initialize_archive(connection)
                    for request in case['requests']:
                        report, receipt = assess_tolerance_and_publish(
                            connection, text, request['intervals']
                        )
                        with self.subTest(case=case['name'], intervals=request['intervals']):
                            expected = (
                                None if request['minimum_residual_sum'] is None
                                else Fraction(request['minimum_residual_sum'])
                            )
                            self.assertEqual(report.minimum_residual_sum, expected)
                            self.assertEqual(report.within_budget, request['within_budget'])
                            self.assertEqual(report.limit, Fraction(case['limit']))
                            self.assertEqual(receipt.report_id, report.report_id)
                            names = [iv.name for iv in report.intervals]
                            self.assertEqual(names, sorted(names))
                            stored, stored_receipt = retrieve_tolerance_report(
                                connection, report.report_id
                            )
                            self.assertEqual((stored, stored_receipt), (report, receipt))

    def test_envelope_self_consistency_and_exact_rationals(self):
        case = next(case for case in TOLERANCE_CASES if case['name'] == 'dependent')
        with tempfile.TemporaryDirectory() as directory:
            _, text, _ = tolerance_artifact(case, directory)
            body = json.loads(text)
            # All math payload values stay exact rational strings.
            for value in body['center']:
                self.assertEqual(type(value), str)
                Fraction(value)
            for row in body['shape']:
                for value in row:
                    self.assertEqual(type(value), str)
                    Fraction(value)
            Fraction(body['residual_floor'])
            Fraction(body['limit'])
            self.assertEqual(body['residual_floor'], '0')
            self.assertEqual(body['limit'], '2')

    def test_correction_reissues_same_budget_new_revision_and_reopen_keeps_report(self):
        case = next(case for case in TOLERANCE_CASES if case['name'] == 'residual-floor')
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'archive.sqlite3'
            original, original_text, first_revision = tolerance_artifact(case, directory)
            request = case['requests'][0]['intervals']
            with closing(sqlite3.connect(archive)) as connection:
                initialize_archive(connection)
                first, first_receipt = assess_tolerance_and_publish(connection, original_text, request)
            self.assertEqual(first.minimum_residual_sum, 4)
            self.assertTrue(first.within_budget)

            corrected, corrected_text, new_revision = tolerance_artifact(
                case, directory, corrections=case['correction']
            )
            self.assertNotEqual(first_revision.revision_id, new_revision.revision_id)
            self.assertEqual(corrected.limit, original.limit)
            with closing(sqlite3.connect(archive)) as connection:
                initialize_archive(connection)
                second, second_receipt = assess_tolerance_and_publish(connection, corrected_text, request)
                # Reopening the archive still returns the original report by its number.
                reopened, reopened_receipt = retrieve_tolerance_report(connection, first.report_id)
            self.assertEqual(second.minimum_residual_sum, 0)
            self.assertTrue(second.within_budget)
            self.assertEqual(second.revision_id, new_revision.revision_id)
            self.assertEqual((reopened, reopened_receipt), (first, first_receipt))
            self.assertNotEqual(first_receipt, second_receipt)


class ToleranceValidationTests(unittest.TestCase):
    def setUp(self):
        self.case = next(case for case in TOLERANCE_CASES if case['name'] == 'dependent')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        _, self.text, _ = tolerance_artifact(self.case, self.temp.name)
        self.archive = sqlite3.connect(':memory:')
        self.addCleanup(self.archive.close)
        initialize_archive(self.archive)

    def _rejected(self, intervals):
        with self.assertRaises(ValueError):
            assess_tolerance_and_publish(self.archive, self.text, intervals)
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM tolerance_reports').fetchone()[0], 0
        )

    def test_invalid_request_structures(self):
        self._rejected([])
        self._rejected(())
        self._rejected('nope')
        self._rejected([['A', 0]])
        self._rejected([['A', 0, 1, 2]])
        self._rejected([[0, 0, 1]])
        self._rejected([[' A', 0, 1]])
        self._rejected([['A', 0, 1], ['A', 0, 1]])
        self._rejected([{'name': 'A', 'lower': 0, 'upper': 1}])

    def test_unknown_and_reversed_and_non_exact_endpoints(self):
        self._rejected([['Z', 0, 1]])
        self._rejected([['A', 2, 1]])
        self._rejected([['A', 1.5, 2]])
        self._rejected([['A', True, 2]])
        self._rejected([['A', None, 2]])
        self._rejected([['A', '1/0', 2]])
        self._rejected([['A', 'x', 2]])

    def test_endpoint_input_kinds_accepted(self):
        report, _ = assess_tolerance_and_publish(
            self.archive, self.text, [['A', 1, 1], ('B', Fraction(1), '1')]
        )
        self.assertEqual(report.minimum_residual_sum, 2)
        report, _ = assess_tolerance_and_publish(
            self.archive, self.text, (('D', '5', '5'),)
        )
        self.assertEqual(report.minimum_residual_sum, 0)
        self.assertTrue(all(
            type(value) is Fraction
            for interval in report.intervals for value in (interval.lower, interval.upper)
        ))

    def test_bad_and_cross_version_envelopes_rejected_without_writes(self):
        decoded = json.loads(self.text)
        wrong_shape = dict(decoded, shape=decoded['shape'][:-1])
        negative = dict(decoded)
        negative['shape'] = [['-1'] + row[1:] for row in decoded['shape']]
        bad_limit = dict(decoded, limit='-1')
        below_floor = dict(decoded, limit='-9')
        duplicates = self.text.replace('"version":2', '"version":2,"version":2', 1)
        for bad in (
            '{}', json.dumps(wrong_shape), json.dumps(negative), json.dumps(bad_limit),
            json.dumps(below_floor), duplicates, self.text.replace('"version":2', '"version":3'),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    assess_tolerance_and_publish(self.archive, bad, [['A', 0, 0]])
        self.assertEqual(
            self.archive.execute('SELECT COUNT(*) FROM tolerance_reports').fetchone()[0], 0
        )

    def test_v1_envelope_rejected_by_tolerance_entry(self):
        # Build a genuine V1 artifact and confirm the V2 entry refuses it.
        batch = json.loads((SAMPLES / 'batch.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bench.sqlite3'
            with closing(sqlite3.connect(path)) as connection:
                ledger, register = BenchLedger(connection), IssueRegister(connection)
                ledger.initialize()
                register.initialize()
                ledger.accept_batch(**batch)
                revision = ledger.freeze_current()
                v1 = issue_calibration(fit_frozen_revision(revision, 1), register)
                v1_text = register.get(v1.artifact_id)
        v1_decoded = decode_artifact(v1_text)
        self.assertEqual(json.loads(v1_text)['version'], 1)
        self.assertEqual(v1_decoded.artifact_id, v1.artifact_id)
        with self.assertRaises(ValueError):
            assess_tolerance_and_publish(self.archive, v1_text, [['in', 0, 0]])
        # And the V2 envelope is rejected by the V1 decoder.
        with self.assertRaises(ValueError):
            decode_artifact(self.text)

    def test_unknown_report_id_raises_report_not_found(self):
        report, _ = assess_tolerance_and_publish(self.archive, self.text, [['D', 5, 5]])
        for bad in (report.report_id + 100, 0, -1, '1', 1.0):
            with self.assertRaises(ReportNotFound):
                retrieve_tolerance_report(self.archive, bad)


class ToleranceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.case = next(case for case in TOLERANCE_CASES if case['name'] == 'dependent')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        _, self.text, _ = tolerance_artifact(self.case, self.temp.name)
        self.request = [['C', 3, 3]]

    def _counts(self, connection):
        return (
            connection.execute('SELECT COUNT(*) FROM tolerance_reports').fetchone()[0],
            connection.execute('SELECT COUNT(*) FROM tolerance_receipts').fetchone()[0],
        )

    def test_receipt_write_failure_rolls_back_report(self):
        path = Path(self.temp.name) / 'archive.sqlite3'
        with closing(sqlite3.connect(path)) as writer, closing(sqlite3.connect(path)) as reader:
            initialize_archive(writer)
            writer.execute('''
                CREATE TEMP TRIGGER reject_tolerance_receipt
                BEFORE INSERT ON tolerance_receipts
                BEGIN SELECT RAISE(ABORT, 'tolerance receipt interrupted'); END
            ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'tolerance receipt interrupted'):
                assess_tolerance_and_publish(writer, self.text, self.request)
            self.assertFalse(writer.in_transaction)
            self.assertEqual(self._counts(writer), (0, 0))
            self.assertEqual(self._counts(reader), (0, 0))
            writer.execute('DROP TRIGGER reject_tolerance_receipt')
            report, receipt = assess_tolerance_and_publish(writer, self.text, self.request)
            self.assertEqual(self._counts(reader), (1, 1))
            self.assertEqual(retrieve_tolerance_report(reader, report.report_id), (report, receipt))

    def test_commit_stage_failure_is_retryable(self):
        path = Path(self.temp.name) / 'archive.sqlite3'
        with closing(sqlite3.connect(path)) as writer, closing(sqlite3.connect(path)) as reader:
            initialize_archive(writer)
            existing = assess_tolerance_and_publish(writer, self.text, self.request)
            writer.executescript('''
                CREATE TABLE probe_parent (id INTEGER PRIMARY KEY);
                CREATE TABLE probe_child (
                    id INTEGER REFERENCES probe_parent(id) DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TRIGGER interrupt_tolerance_commit AFTER INSERT ON tolerance_receipts
                BEGIN INSERT INTO probe_child VALUES (1); END;
            ''')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                assess_tolerance_and_publish(writer, self.text, self.request)
            self.assertFalse(writer.in_transaction)
            self.assertEqual(self._counts(reader), (1, 1))
            self.assertEqual(retrieve_tolerance_report(reader, existing[0].report_id), existing)
            writer.execute('DROP TRIGGER interrupt_tolerance_commit')
            retried = assess_tolerance_and_publish(writer, self.text, self.request)
            self.assertEqual(self._counts(reader), (2, 2))
            self.assertEqual(retrieve_tolerance_report(reader, retried[0].report_id), retried)

    def test_reinitialize_and_reopen_are_idempotent(self):
        path = Path(self.temp.name) / 'archive.sqlite3'
        with closing(sqlite3.connect(path)) as connection:
            initialize_archive(connection)
            report, receipt = assess_tolerance_and_publish(connection, self.text, self.request)
            initialize_archive(connection)
            initialize_archive(connection)
            self.assertEqual(self._counts(connection), (1, 1))
        with closing(sqlite3.connect(path)) as connection:
            initialize_archive(connection)
            self.assertEqual(retrieve_tolerance_report(connection, report.report_id), (report, receipt))


class ToleranceMathTests(unittest.TestCase):
    def _artifact(self, name):
        case = next(case for case in TOLERANCE_CASES if case['name'] == name)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        artifact, _, _ = tolerance_artifact(case, temp.name)
        return artifact

    def test_single_point_and_omitted_channels(self):
        artifact = self._artifact('dependent')
        from review.tolerance import minimum_residual_sum, parse_intervals
        # D is the constant 5 channel; only constraining it leaves A,B free.
        self.assertEqual(
            minimum_residual_sum(artifact, parse_intervals(artifact, [['D', 5, 5]])), 0
        )
        self.assertIsNone(
            minimum_residual_sum(artifact, parse_intervals(artifact, [['D', 4, 4]]))
        )

    def test_rank_reduced_dependent_relationship(self):
        artifact = self._artifact('dependent')
        from review.tolerance import minimum_residual_sum, parse_intervals
        # C = A + B: constraining only C reaches the documented 9/2 floor.
        self.assertEqual(
            minimum_residual_sum(artifact, parse_intervals(artifact, [['C', 3, 3]])),
            Fraction(9, 2),
        )
        # Contradictory single points across the linear dependency are infeasible.
        self.assertIsNone(minimum_residual_sum(
            artifact, parse_intervals(artifact, [['A', 1, 1], ['B', 1, 1], ['C', 3, 3]])
        ))

    def test_scaled_gram_keeps_dependent_normals_in_basis_metric(self):
        # G = diag(4, 1), public A = x, B = y, C = x + y. The residual is
        # 4x^2 + y^2; the dependent channel normal must use B_SS^-1 B_{cS}.
        from evidence.codec import ToleranceCalibrationArtifact
        from evidence.channels import ChannelCatalog, PublicReadings
        from review.tolerance import minimum_residual_sum, parse_intervals
        q = Fraction
        shape = (
            (q(1, 4), q(0), q(1, 4)),
            (q(0), q(1), q(1)),
            (q(1, 4), q(1), q(5, 4)),
        )
        readings = PublicReadings(
            ChannelCatalog(('A', 'B', 'C')), (q(0), q(0), q(0)), shape
        )
        artifact = ToleranceCalibrationArtifact('id', 'rev', 'e' * 64, readings, q(0), q(100))
        self.assertEqual(
            minimum_residual_sum(artifact, parse_intervals(artifact, [['A', 1, 1]])), 4
        )
        # min 4x^2 + y^2 s.t. x + y = 1 -> x = 1/5, y = 4/5 -> 4/5.
        self.assertEqual(
            minimum_residual_sum(artifact, parse_intervals(artifact, [['C', 1, 1]])),
            Fraction(4, 5),
        )
        # The box on A binds at x = 1 with y = 0 once C = 1 is imposed.
        self.assertEqual(
            minimum_residual_sum(
                artifact, parse_intervals(artifact, [['A', 1, 2], ['C', 1, 1]])
            ),
            4,
        )


if __name__ == '__main__':
    unittest.main()

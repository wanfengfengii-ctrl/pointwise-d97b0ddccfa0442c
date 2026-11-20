import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from fractions import Fraction

from bench.wiring import DuplicateChannelError
from calibration.budget import InfeasibleBudget
from calibration.fit import fit_frozen_revision
from calibration.least_squares import RankDeficientCalibration
from evidence.codec import decode_artifact
from evidence.issue import WiringMismatchError, issue_calibration
from reports.publish import initialize_archive
from review.assess import assess_and_publish
from review.request import RatioRequest
from tests.fixtures import channel, initialize_bench, reading, sample_batch


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.addCleanup(self.connection.close)
        self.ledger, self.register = initialize_bench(self.connection)

    def _count_issued(self):
        return self.connection.execute('SELECT COUNT(*) FROM issued_calibrations').fetchone()[0]

    def _constant_fit_batch(self):
        self.ledger.accept_batch(
            ['drift'], [reading('a', 0, [1]), reading('b', 2, [1])],
            [channel('in', 1, [0]), channel('out', 0, [1])],
        )
        return self.ledger.freeze_current()

    def test_exact_budget(self):
        revision = self._constant_fit_batch()
        fitted = fit_frozen_revision(revision, '2.0')
        self.assertEqual(fitted.least_squares.center, (Fraction(1),))
        self.assertEqual(fitted.budget.minimum, 2)
        self.assertEqual(fitted.budget.slack, 0)
        artifact = issue_calibration(fitted, self.register)
        text = self.register.get(artifact.artifact_id)
        self.assertEqual(decode_artifact(text), artifact)
        self.assertEqual((artifact.revision_id, artifact.revision_fingerprint),
                         (revision.revision_id, revision.fingerprint))
        self.assertEqual(artifact.readings.center, (Fraction(1), Fraction(1)))
        self.assertEqual(artifact.readings.shape, ((0, 0), (0, 0)))
        with closing(sqlite3.connect(':memory:')) as archive:
            initialize_archive(archive)
            report, receipt = assess_and_publish(archive, text, RatioRequest('in', 'out'))
        point, = report.ratios.components
        self.assertEqual((point.lower, point.upper, point.lower_closed, point.upper_closed), (1, 1, True, True))
        self.assertEqual((report.revision_id, receipt.report_id), (revision.revision_id, report.report_id))

    def test_mixed_units(self):
        self.ledger.accept_batch(
            ['drive'], [reading('a', '60', [1]), reading('b', '3.6', [1], 'L/min')],
            [channel('in', '3.6', [0], 'L/min'), channel('out', 0, [1])],
        )
        revision = self.ledger.freeze_current()
        self.assertEqual([row.response for row in revision.cohort.measurements], [60, 60])
        fitted = fit_frozen_revision(revision, 0)
        self.assertEqual((fitted.budget.minimum, fitted.budget.slack), (0, 0))
        artifact = issue_calibration(fitted, self.register)
        self.assertEqual(artifact.readings.center, (60, 60))
        self.assertEqual(artifact.revision_id, revision.revision_id)
        self.assertEqual(self._count_issued(), 1)

    def test_wiring_mismatch(self):
        revision = self._constant_fit_batch()
        fitted = fit_frozen_revision(revision, 2)
        inlet, outlet = revision.cohort.wiring
        changed = replace(outlet, coefficients=(Fraction(2),))
        with self.assertRaises(WiringMismatchError):
            issue_calibration(fitted, self.register, [inlet, changed])
        self.assertEqual(self._count_issued(), 0)
        artifact = issue_calibration(fitted, self.register, [outlet, inlet])
        self.assertEqual(artifact.readings.catalog.names, ('in', 'out'))
        self.assertEqual(self._count_issued(), 1)

    def test_duplicate_channel(self):
        batch = sample_batch()
        self.ledger.accept_batch(**batch)
        before = self.ledger.freeze_current()
        batch['wiring'].append(channel('in', 99, [0, 2]))
        with self.assertRaises(DuplicateChannelError):
            self.ledger.accept_batch(**batch)
        self.assertEqual(self.ledger.freeze_current(), before)

    def test_invalid_unit_and_missing_value_reject_entire_batch(self):
        batch = sample_batch()
        self.ledger.accept_batch(**batch)
        before = self.ledger.freeze_current()
        for invalid in (reading('c', 2, [0, 1], 'L/s'), {'key': 'c', 'unit': 'mL/s', 'design': [1, 0]},
                        reading('c', None, [0, 1]), reading('c', '1/0', [0, 1])):
            with self.subTest(invalid=invalid):
                attempted = dict(batch, measurements=[reading('a', 99, [1, 0]), invalid])
                with self.assertRaises(ValueError):
                    self.ledger.accept_batch(**attempted)
                self.assertEqual(self.ledger.freeze_current(), before)

    def test_infeasible_budget(self):
        revision = self._constant_fit_batch()
        with self.assertRaises(InfeasibleBudget):
            issue_calibration(fit_frozen_revision(revision, 1), self.register)
        self.assertEqual(self._count_issued(), 0)
        self.assertEqual(self.ledger.load_revision(revision.revision_id), revision)
        self.assertEqual([row.response for row in revision.cohort.measurements], [0, 2])

    def test_rank_deficient(self):
        self.ledger.accept_batch(
            ['x', 'y'], [reading('a', 1, [1, 1]), reading('b', 2, [2, 2])],
            [channel('out', 0, [1, 0])],
        )
        revision = self.ledger.freeze_current()
        with self.assertRaises(RankDeficientCalibration):
            issue_calibration(fit_frozen_revision(revision, 0), self.register)
        self.assertEqual(self._count_issued(), 0)
        self.assertEqual(self.ledger.load_revision(revision.revision_id), revision)

    def test_replay_and_reversion_have_distinct_version_semantics(self):
        batch = sample_batch()
        with self.assertRaises(LookupError):
            self.ledger.freeze_current()
        self.ledger.accept_batch(**batch)
        original = self.ledger.freeze_current()
        self.ledger.accept_batch(**dict(batch, measurements=list(reversed(batch['measurements']))))
        self.ledger.correct_readings([{'key': 'a', 'value': '0', 'unit': 'L/min'}])
        self.assertEqual(self.ledger.freeze_current(), original)
        with self.assertRaises(ValueError):
            self.ledger.correct_readings([
                {'key': 'a', 'value': 2, 'unit': 'mL/s'}, {'key': 'unknown', 'value': 0, 'unit': 'mL/s'},
            ])
        self.assertEqual(self.ledger.freeze_current(), original)
        self.ledger.correct_readings([{'key': 'a', 'value': 3, 'unit': 'mL/s'}])
        corrected = self.ledger.freeze_current()
        self.ledger.correct_readings([{'key': 'a', 'value': 0, 'unit': 'mL/s'}])
        reverted = self.ledger.freeze_current()
        self.assertEqual(reverted.fingerprint, original.fingerprint)
        self.assertEqual(len({original.revision_id, corrected.revision_id, reverted.revision_id}), 3)
        self.assertEqual(self.ledger.load_revision(corrected.revision_id).cohort.measurements[0].response, 3)

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path

from demo import offline_report
from evidence.codec import decode_artifact
from reports.publish import initialize_archive
from reports.retrieve import retrieve_report
from review.assess import assess_and_publish
from review.quadratics import QuadraticNumber, compare_exact, solve_real_quadratic
from review.request import RatioRequest, UnknownChannelError
from tests.fixtures import archive_counts, channel, disk_artifact, sample_batch


class RatioTests(unittest.TestCase):
    def test_disconnected_and_punctured(self):
        # The in-memory source is closed on return. Each worker receives only
        # the serialized calibration, the destination and its channel names.
        revision, artifact, text = disk_artifact()
        decoded = decode_artifact(text)
        self.assertEqual(decoded.revision_id, revision.revision_id)
        self.assertEqual(set(json.loads(text)), {
            'version', 'artifact_id', 'revision_id', 'revision_fingerprint', 'channels', 'center', 'shape',
        })
        for private_name in revision.cohort.columns:
            self.assertNotIn(private_name, text)
        readings = decoded.readings
        index = readings.catalog.index_of
        pair_a = readings.pair(index('in'), index('out-a'))
        pair_b = readings.pair(index('in'), index('out-b'))
        for pair in (pair_a, pair_b):
            self.assertEqual((pair.inlet_center, pair.inlet_shape, pair.outlet_center, pair.outlet_shape),
                             (0, 1, 1, 1))
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'review.sqlite3'
            a = offline_report(archive, text, 'in', 'out-a')
            b = offline_report(archive, text, 'in', 'out-b')
            expected = [
                [[None, '0', False, True], ['2', None, True, False]],
                [[None, '0', False, False], ['0', None, False, False]],
            ]
            self.assertEqual([a['ratios'], b['ratios']], expected, 'RATIO_SET_MISMATCH')
            self.assertEqual((pair_a.cross_shape, pair_b.cross_shape), (1, 0))
            for published, name in ((a, 'out-a'), (b, 'out-b')):
                self.assertEqual((published['inlet'], published['outlet']), ('in', name))
                self.assertEqual((published['artifact_id'], published['revision_id'], published['revision_fingerprint']),
                                 (artifact.artifact_id, revision.revision_id, revision.fingerprint))
            with closing(sqlite3.connect(archive)) as connection:
                old_a, receipt_a = retrieve_report(connection, a['report_id'])
                old_b, receipt_b = retrieve_report(connection, b['report_id'])
            self.assertEqual([old_a.ratios.contains(value) for value in (0, 1, 2)], [True, False, True])
            self.assertEqual([old_b.ratios.contains(value) for value in (0, 1, 2)], [False, True, True])
            self.assertEqual(receipt_a.receipt_id, a['receipt']['receipt_id'])
            self.assertEqual(receipt_b.receipt_id, b['receipt']['receipt_id'])

    def setUp(self):
        self.archive = sqlite3.connect(':memory:')
        self.addCleanup(self.archive.close)
        initialize_archive(self.archive)

    def test_degenerate_channels(self):
        _, artifact, text = disk_artifact()
        expected = [('in', 'twice', 2), ('zero', 'twice', None), ('in', 'in', 1), ('in', 'zero', 0)]
        for inlet, outlet, only in expected:
            with self.subTest(inlet=inlet, outlet=outlet):
                report, receipt = assess_and_publish(self.archive, text, RatioRequest(inlet, outlet))
                self.assertEqual(report.artifact_id, artifact.artifact_id)
                self.assertEqual(retrieve_report(self.archive, report.report_id), (report, receipt))
                if only is None:
                    self.assertEqual(report.ratios.components, ())
                else:
                    component, = report.ratios.components
                    self.assertEqual((component.lower, component.upper), (only, only))
                    self.assertTrue(component.lower_closed and component.upper_closed)
        self.assertEqual(archive_counts(self.archive), (4, 4))

    def test_algebraic_roundtrip(self):
        _, _, text = disk_artifact()
        report, receipt = assess_and_publish(self.archive, text, RatioRequest('one', 'sum'))
        stored, stored_receipt = retrieve_report(self.archive, report.report_id)
        self.assertEqual((report, receipt), (stored, stored_receipt))
        part, = stored.ratios.components
        self.assertEqual((part.lower, part.upper), (QuadraticNumber(1, 0, -2, 0), QuadraticNumber(1, 0, -2, 1)))
        self.assertTrue(part.lower_closed and part.upper_closed)
        self.assertTrue(stored.ratios.contains(part.lower))
        self.assertTrue(stored.ratios.contains(Fraction(7, 5)))
        self.assertFalse(stored.ratios.contains(Fraction(3, 2)))
        _, other_right = solve_real_quadratic(1, 0, -3)
        self.assertLess(compare_exact(part.upper, other_right), 0)
        self.assertEqual(solve_real_quadratic(-2, 0, 4), (part.lower, part.upper))

    def test_rank_one_offset_and_tangent_proportional_channels(self):
        batch = sample_batch()
        batch['wiring'].extend([
            channel('shifted', 1, [1, 0]), channel('proportional', 2, [2, 0]), channel('y', 0, [0, 1]),
        ])
        _, _, text = disk_artifact(batch)
        expectations = [
            ('in', 'one', [(None, -1, False, True), (1, None, True, False)]),
            ('shifted', 'proportional', [(2, 2, True, True)]),
            ('shifted', 'y', [(None, None, False, False)]),
            ('in', 'y', [(None, None, False, False)]),
        ]
        for inlet, outlet, expected in expectations:
            with self.subTest(inlet=inlet, outlet=outlet):
                report, _ = assess_and_publish(self.archive, text, RatioRequest(inlet, outlet))
                self.assertEqual([
                    (part.lower, part.upper, part.lower_closed, part.upper_closed)
                    for part in report.ratios.components
                ], expected)

    def test_unknown_channel(self):
        _, _, text = disk_artifact()
        with self.assertRaises(UnknownChannelError):
            assess_and_publish(self.archive, text, RatioRequest('in', 'unwired'))
        with self.assertRaises(UnknownChannelError):
            assess_and_publish(self.archive, text, RatioRequest('unwired', 'out-a'))
        self.assertEqual(archive_counts(self.archive), (0, 0))

    def test_invalid_envelope_never_publishes(self):
        _, _, text = disk_artifact()
        wrong_shape = json.loads(text)
        wrong_shape['shape'][0].pop()
        impossible_shape = json.loads(text)
        impossible_shape['shape'][0][0] = '-1'
        for bad in ('{}', json.dumps(wrong_shape), json.dumps(impossible_shape), text.replace('"version":1', '"version":1,"version":1')):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    assess_and_publish(self.archive, bad, RatioRequest('in', 'out-a'))
        self.assertEqual(archive_counts(self.archive), (0, 0))

import sqlite3
import tempfile
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path

from calibration.fit import fit_frozen_revision
from reports.publish import initialize_archive
from reports.retrieve import ReportNotFound, retrieve_report
from review.assess import assess_and_publish
from review.quadratics import QuadraticNumber
from review.request import RatioRequest
from tests.fixtures import archive_counts, disk_artifact, initialize_bench, issue_current, sample_batch, sample_correction


class ArchiveTests(unittest.TestCase):
    def test_revision_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            bench_path = Path(directory) / 'bench.sqlite3'
            archive_path = Path(directory) / 'archive.sqlite3'
            request = RatioRequest('in', 'out-b')
            with closing(sqlite3.connect(bench_path)) as bench:
                ledger, register = initialize_bench(bench)
                ledger.accept_batch(**sample_batch())
                old, old_artifact, old_text = issue_current(ledger, register)
            with closing(sqlite3.connect(archive_path)) as archive:
                initialize_archive(archive)
                original = assess_and_publish(archive, old_text, request)

            with closing(sqlite3.connect(bench_path)) as bench:
                ledger, register = initialize_bench(bench)
                ledger.correct_readings(sample_correction())
                new, new_artifact, new_text = issue_current(ledger, register)
                self.assertNotEqual(old.revision_id, new.revision_id)
                self.assertNotEqual(old.fingerprint, new.fingerprint)
                loaded_old = ledger.load_revision(old.revision_id)
                loaded_new = ledger.load_revision(new.revision_id)
                self.assertEqual(loaded_old, old)
                self.assertEqual(loaded_new, new)
                self.assertEqual(tuple(row.response for row in loaded_old.cohort.measurements), (0, 0))
                self.assertEqual(tuple(row.response for row in loaded_new.cohort.measurements), (0, 1))
                self.assertEqual(fit_frozen_revision(loaded_old, 1).least_squares.center, (0, 0))
                self.assertEqual(fit_frozen_revision(loaded_new, 1).least_squares.center, (0, 1))
                initialize_bench(bench)
                self.assertEqual(ledger.freeze_current(), new)
                self.assertEqual(register.get(old_artifact.artifact_id), old_text)
                self.assertEqual(register.get(new_artifact.artifact_id), new_text)

            with closing(sqlite3.connect(archive_path)) as archive:
                initialize_archive(archive)
                corrected = assess_and_publish(archive, new_text, request)
                repeated = assess_and_publish(archive, old_text, request)
            report, receipt = original
            self.assertEqual((report.artifact_id, report.revision_id, report.revision_fingerprint),
                             (old_artifact.artifact_id, old.revision_id, old.fingerprint))
            self.assertEqual((repeated[0].artifact_id, repeated[0].revision_id, repeated[0].ratios),
                             (report.artifact_id, report.revision_id, report.ratios))
            self.assertNotEqual(repeated[1], receipt)
            changed = corrected[0]
            self.assertEqual((changed.artifact_id, changed.revision_id, changed.revision_fingerprint),
                             (new_artifact.artifact_id, new.revision_id, new.fingerprint))
            self.assertTrue(report.ratios.contains(Fraction(1)))
            self.assertFalse(changed.ratios.contains(Fraction(1)))
            lower_ray, upper_ray = changed.ratios.components
            self.assertEqual((lower_ray.upper, upper_ray.lower),
                             (QuadraticNumber(1, 0, -3, 0), QuadraticNumber(1, 0, -3, 1)))
            self.assertTrue(lower_ray.upper_closed and upper_ray.lower_closed)

            with closing(sqlite3.connect(archive_path)) as archive:
                initialize_archive(archive)
                initialize_archive(archive)
                self.assertEqual(archive_counts(archive), (3, 3))
                self.assertEqual(retrieve_report(archive, report.report_id), original)
                self.assertEqual(retrieve_report(archive, changed.report_id), corrected)
                self.assertEqual(retrieve_report(archive, repeated[0].report_id), repeated)
                with self.assertRaises(ReportNotFound):
                    retrieve_report(archive, max(report.report_id, changed.report_id, repeated[0].report_id) + 1)
                self.assertEqual(archive_counts(archive), (3, 3))

    def test_publish_rollback(self):
        _, _, text = disk_artifact()
        request = RatioRequest('in', 'out-a')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'archive.sqlite3'
            with closing(sqlite3.connect(path)) as writer, closing(sqlite3.connect(path)) as reader:
                initialize_archive(writer)
                writer.execute('''
                    CREATE TEMP TRIGGER reject_receipt BEFORE INSERT ON report_receipts
                    BEGIN SELECT RAISE(ABORT, 'receipt write interrupted'); END
                ''')
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt write interrupted'):
                    assess_and_publish(writer, text, request)
                self.assertFalse(writer.in_transaction)
                self.assertEqual(archive_counts(writer), (0, 0))
                self.assertEqual(archive_counts(reader), (0, 0))
                writer.execute('DROP TRIGGER reject_receipt')
                report, receipt = assess_and_publish(writer, text, request)
                self.assertEqual(archive_counts(reader), (1, 1))
                self.assertEqual(retrieve_report(reader, report.report_id), (report, receipt))

    def test_commit_error_preserves_existing_snapshot(self):
        _, _, text = disk_artifact()
        request = RatioRequest('one', 'sum')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'archive.sqlite3'
            with closing(sqlite3.connect(path)) as writer, closing(sqlite3.connect(path)) as reader:
                initialize_archive(writer)
                existing = assess_and_publish(writer, text, request)
                writer.executescript('''
                    CREATE TABLE commit_probe_parent (id INTEGER PRIMARY KEY);
                    CREATE TABLE commit_probe_child (
                        id INTEGER REFERENCES commit_probe_parent(id) DEFERRABLE INITIALLY DEFERRED
                    );
                    CREATE TRIGGER interrupt_commit AFTER INSERT ON report_receipts
                    BEGIN INSERT INTO commit_probe_child VALUES (1); END;
                ''')
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                    assess_and_publish(writer, text, request)
                self.assertFalse(writer.in_transaction)
                self.assertEqual(writer.execute('SELECT COUNT(*) FROM commit_probe_child').fetchone()[0], 0)
                self.assertEqual(archive_counts(reader), (1, 1))
                self.assertEqual(retrieve_report(reader, existing[0].report_id), existing)
                writer.execute('DROP TRIGGER interrupt_commit')
                retried = assess_and_publish(writer, text, request)
                self.assertEqual(archive_counts(reader), (2, 2))
                self.assertEqual(retrieve_report(reader, retried[0].report_id), retried)

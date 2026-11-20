import tempfile
import unittest
from pathlib import Path

from demo import run_workday


class WorkdayTests(unittest.TestCase):
    def test_sample_handoff_from_intake_to_original_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario, original = run_workday(Path(directory))
        self.assertEqual(scenario['case_id'], 'N2')
        self.assertEqual(scenario['actual'], [
            [[None, '0', False, True], ['2', None, True, False]],
            [[None, '0', False, False], ['0', None, False, False]],
        ])
        self.assertTrue(scenario['downstream_actual']['corrected_bound_to_new_revision'])
        self.assertTrue(scenario['downstream_actual']['original_reports_and_receipts_retrieved'])
        self.assertEqual(original['ratios'], [[None, '0', False, True], ['2', None, True, False]])
        self.assertEqual(original['report_id'], original['receipt']['report_id'])
        self.assertEqual((original['inlet'], original['outlet']), ('in', 'out-a'))

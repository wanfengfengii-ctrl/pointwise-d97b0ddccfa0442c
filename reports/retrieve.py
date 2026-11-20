import sqlite3

from reports.receipts import decode_receipt
from reports.records import ReportRecord, decode_ratio_set


class ReportNotFound(LookupError):
    pass


def retrieve_report(connection: sqlite3.Connection, report_id):
    if type(report_id) is not int or not 0 < report_id <= 2**63 - 1:
        raise ReportNotFound(report_id)
    row = connection.execute('''
        SELECT r.report_id, r.artifact_id, r.revision_id, r.revision_fingerprint,
               r.inlet, r.outlet, r.ratio_set, p.receipt_id
        FROM ratio_reports AS r
        JOIN report_receipts AS p ON p.report_id = r.report_id
        WHERE r.report_id = ?
    ''', (report_id,)).fetchone()
    if row is None:
        raise ReportNotFound(report_id)
    number, artifact, revision, fingerprint, inlet, outlet, ratios, receipt = row
    return (
        ReportRecord(number, artifact, revision, fingerprint, inlet, outlet, decode_ratio_set(ratios)),
        decode_receipt(receipt, number),
    )

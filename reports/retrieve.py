import sqlite3

from reports.receipts import decode_receipt
from reports.records import ReportRecord, decode_ratio_set
from reports.tolerance_records import ToleranceReport, decode_tolerance_report


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


def retrieve_tolerance_report(connection: sqlite3.Connection, report_id):
    if type(report_id) is not int or not 0 < report_id <= 2**63 - 1:
        raise ReportNotFound(report_id)
    row = connection.execute('''
        SELECT t.report_id, t.artifact_id, t.revision_id, t.revision_fingerprint,
               t.payload, p.receipt_id
        FROM tolerance_reports AS t
        JOIN tolerance_receipts AS p ON p.report_id = t.report_id
        WHERE t.report_id = ?
    ''', (report_id,)).fetchone()
    if row is None:
        raise ReportNotFound(report_id)
    number, artifact, revision, fingerprint, payload, receipt = row
    decoded = decode_tolerance_report(payload)
    report = ToleranceReport(
        number, artifact, revision, fingerprint, decoded['limit'],
        decoded['intervals'], decoded['minimum_residual_sum'], decoded['within_budget'],
    )
    return report, decode_receipt(receipt, number)

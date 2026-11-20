import sqlite3

from reports.receipts import make_receipt
from reports.records import ReportRecord, encode_ratio_set


def _require_idle(connection):
    if connection.in_transaction:
        raise ValueError('archive write requires an idle connection')


def initialize_archive(connection: sqlite3.Connection):
    _require_idle(connection)
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('BEGIN IMMEDIATE')
    with connection:
        connection.execute('''
            CREATE TABLE IF NOT EXISTS ratio_reports (
                report_id INTEGER PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                revision_fingerprint TEXT NOT NULL,
                inlet TEXT NOT NULL,
                outlet TEXT NOT NULL,
                ratio_set TEXT NOT NULL
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS report_receipts (
                report_id INTEGER PRIMARY KEY REFERENCES ratio_reports(report_id),
                receipt_id TEXT NOT NULL UNIQUE
            )
        ''')


def publish_report(connection, *, artifact_id, revision_id, revision_fingerprint, inlet, outlet, ratios):
    _require_idle(connection)
    fields = (artifact_id, revision_id, revision_fingerprint, inlet, outlet)
    encoded = encode_ratio_set(ratios)
    connection.execute('BEGIN IMMEDIATE')
    with connection:
        cursor = connection.execute('''
            INSERT INTO ratio_reports (artifact_id, revision_id, revision_fingerprint, inlet, outlet, ratio_set)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (*fields, encoded))
        report = ReportRecord(cursor.lastrowid, *fields, ratios)
        receipt = make_receipt(report.report_id)
        connection.execute('''
            INSERT INTO report_receipts (report_id, receipt_id) VALUES (?, ?)
        ''', (receipt.report_id, receipt.receipt_id))
    return report, receipt

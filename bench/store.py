from contextlib import contextmanager

from bench.cohorts import apply_reading_corrections, decode_cohort, encode_cohort, prepare_cohort
from bench.revisions import decode_revision, encode_revision, freeze_cohort


class BenchLedger:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def _write(self):
        if self.connection.in_transaction:
            raise ValueError('bench write requires an idle connection')
        self.connection.execute('BEGIN IMMEDIATE')
        with self.connection:
            yield

    def initialize(self):
        with self._write():
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS bench_identity (
                    slot INTEGER PRIMARY KEY CHECK (slot = 1),
                    ledger_id TEXT NOT NULL
                )
            ''')
            self.connection.execute('''
                INSERT OR IGNORE INTO bench_identity VALUES (1, lower(hex(randomblob(16))))
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS bench_current (
                    slot INTEGER PRIMARY KEY CHECK (slot = 1),
                    work_version INTEGER NOT NULL,
                    body TEXT NOT NULL
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS bench_revisions (
                    revision_id TEXT PRIMARY KEY,
                    work_version INTEGER NOT NULL UNIQUE,
                    fingerprint TEXT NOT NULL,
                    body TEXT NOT NULL
                )
            ''')

    def _current(self):
        return self.connection.execute('''
            SELECT work_version, body FROM bench_current WHERE slot = 1
        ''').fetchone()

    def _require_current(self):
        current = self._current()
        if current is None:
            raise LookupError('no accepted cohort')
        return current

    def _save_current(self, version, body):
        self.connection.execute('''
            INSERT INTO bench_current (slot, work_version, body) VALUES (1, ?, ?)
            ON CONFLICT(slot) DO UPDATE SET work_version = excluded.work_version,
                                            body = excluded.body
        ''', (version, body))

    def accept_batch(self, columns, measurements, wiring):
        body = encode_cohort(prepare_cohort(columns, measurements, wiring))
        with self._write():
            current = self._current()
            if current is not None and current[1] == body:
                return current[0]
            version = 1 if current is None else current[0] + 1
            self._save_current(version, body)
        return version

    def correct_readings(self, corrections):
        with self._write():
            version, body = self._require_current()
            corrected = apply_reading_corrections(decode_cohort(body), corrections)
            updated_body = encode_cohort(corrected)
            if updated_body != body:
                version += 1
                self._save_current(version, updated_body)
        return version

    def freeze_current(self):
        with self._write():
            version, body = self._require_current()
            existing = self.connection.execute('''
                SELECT body FROM bench_revisions WHERE work_version = ?
            ''', (version,)).fetchone()
            if existing is not None:
                return decode_revision(existing[0])
            ledger_id, = self.connection.execute('SELECT ledger_id FROM bench_identity').fetchone()
            revision = freeze_cohort(decode_cohort(body), f'{ledger_id}/r{version}', version)
            self.connection.execute('''
                INSERT INTO bench_revisions (revision_id, work_version, fingerprint, body)
                VALUES (?, ?, ?, ?)
            ''', (revision.revision_id, version, revision.fingerprint, encode_revision(revision)))
        return revision

    def load_revision(self, revision_id):
        row = self.connection.execute('''
            SELECT body FROM bench_revisions WHERE revision_id = ?
        ''', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return decode_revision(row[0])

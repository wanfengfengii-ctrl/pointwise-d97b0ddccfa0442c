import sqlite3
from uuid import uuid4

from evidence.channels import PublicReadings
from evidence.codec import CalibrationArtifact, encode_artifact


class IssueRegister:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def _begin(self):
        if self.connection.in_transaction:
            raise ValueError('calibration register requires an idle connection')
        self.connection.execute('BEGIN IMMEDIATE')

    def initialize(self):
        self._begin()
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS issued_calibrations (
                    artifact_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL REFERENCES bench_revisions(revision_id),
                    body TEXT NOT NULL
                )
            ''')

    def record(self, revision_id, fingerprint, readings: PublicReadings):
        artifact = CalibrationArtifact(
            f'{revision_id}/c{uuid4().hex}', revision_id, fingerprint, readings
        )
        body = encode_artifact(artifact)
        self._begin()
        with self.connection:
            source = self.connection.execute('''
                SELECT fingerprint FROM bench_revisions WHERE revision_id = ?
            ''', (revision_id,)).fetchone()
            if source is None or source[0] != fingerprint:
                raise ValueError('calibration revision is absent from this bench register')
            self.connection.execute('''
                INSERT INTO issued_calibrations (artifact_id, revision_id, body) VALUES (?, ?, ?)
            ''', (artifact.artifact_id, revision_id, body))
        return artifact

    def get(self, artifact_id):
        row = self.connection.execute('''
            SELECT body FROM issued_calibrations WHERE artifact_id = ?
        ''', (artifact_id,)).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return row[0]

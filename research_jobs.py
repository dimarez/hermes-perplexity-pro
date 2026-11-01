"""Linux profile-private research jobs; no credentials, SDK imports or HTTP."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
import uuid

MAX_REPORT_BYTES = 5 * 1024 * 1024
ACTIVE = ('queued', 'running')


class JobError(Exception):
    """Static machine code only. Never render a local/remote exception."""


def storage_supported():
    """Check actual Linux file/locking primitives without process-FS access."""
    if os.name != 'posix' or sys.platform != 'linux':
        return False
    if not all(hasattr(os, name) for name in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK')):
        return False
    directory_functions = getattr(os, 'supports_dir_fd', ())
    if not all(fn in directory_functions for fn in (os.open, os.mkdir, os.stat, os.unlink)):
        return False
    try:
        import fcntl
    except ImportError:
        return False
    return hasattr(fcntl, 'flock')


def owner_key(owner):
    if not isinstance(owner, str) or not owner or len(owner) > 512:
        raise JobError('context')
    return hashlib.sha256(owner.encode()).hexdigest()


def valid_job_id(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}', value) is not None


class JobStore:
    def __init__(self, home):
        self.home = Path(home)
        self.root = self.home / 'plugin-results' / 'perplexity-pro' / 'research'
        self.database = self.root / 'jobs.sqlite3'

    @contextlib.contextmanager
    def _directory(self):
        descriptors = []
        try:
            if not storage_supported() or not self.home.is_absolute():
                raise JobError('storage')
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            fd = os.open(self.home, flags)
            descriptors.append(fd)
            for name in ('plugin-results', 'perplexity-pro', 'research'):
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                os.fsync(fd)
                fd = os.open(name, flags, dir_fd=fd)
                descriptors.append(fd)
                info = os.fstat(fd)
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                    raise JobError('storage')
            yield fd
        except OSError:
            raise JobError('storage') from None
        finally:
            for fd in reversed(descriptors):
                os.close(fd)

    @staticmethod
    def _check_file(fd, name):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise JobError('storage')

    @contextlib.contextmanager
    def _pinned_file(self, directory, name):
        fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=directory)
        try:
            self._check_file(directory, name)
            info = os.fstat(fd)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077 or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)):
                raise JobError('storage')
            yield fd, info
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def _connection(self):
        # Python sqlite3 cannot open an existing OS fd with SQLITE_OPEN_NOFOLLOW.
        # Never let SQLite's VFS resolve an untrusted filename: deserialize bytes
        # from an O_NOFOLLOW-pinned fd into memory, under a process-wide file lock,
        # and atomically publish the committed SQLite image back to this directory.
        if not storage_supported():
            raise JobError('storage')
        import fcntl
        if not all(hasattr(sqlite3.Connection, name) for name in ('serialize', 'deserialize')):
            raise JobError('dependency')
        with self._directory() as directory, self._pinned_file(directory, 'jobs.lock') as (lock_fd, lock_info):
            deadline = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise JobError('storage') from None
                    time.sleep(0.01)
            try:
                with self._pinned_file(directory, 'jobs.sqlite3') as (database_fd, database_info):
                    with os.fdopen(os.dup(database_fd), 'rb') as handle:
                        image = handle.read(64 * 1024 * 1024 + 1)
                    if len(image) > 64 * 1024 * 1024:
                        raise JobError('storage')
                    connection = sqlite3.connect(':memory:', isolation_level=None)
                    connection.row_factory = sqlite3.Row
                    try:
                        if image:
                            connection.deserialize(image)
                        connection.execute('PRAGMA trusted_schema=OFF')
                        connection.execute('''CREATE TABLE IF NOT EXISTS jobs (
                            id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL,
                            query TEXT NOT NULL, timeout INTEGER NOT NULL, status TEXT NOT NULL,
                            created REAL NOT NULL, updated REAL NOT NULL, pid INTEGER,
                            sources TEXT NOT NULL DEFAULT '[]', questions TEXT NOT NULL DEFAULT '[]',
                            code TEXT, UNIQUE(owner, request_id))''')
                        yield connection
                        if connection.in_transaction:
                            connection.rollback()
                        updated = connection.serialize()
                        if len(updated) > 64 * 1024 * 1024:
                            raise JobError('storage')
                        if updated != image:
                            for name, original in (('jobs.lock', lock_info), ('jobs.sqlite3', database_info)):
                                self._check_file(directory, name)
                                current = os.stat(name, dir_fd=directory, follow_symlinks=False)
                                if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
                                    raise JobError('storage')
                            temporary = '.jobs-' + uuid.uuid4().hex
                            try:
                                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                             0o600, dir_fd=directory)
                                with os.fdopen(fd, 'wb') as handle:
                                    handle.write(updated)
                                    handle.flush()
                                    os.fsync(handle.fileno())
                                os.replace(temporary, 'jobs.sqlite3', src_dir_fd=directory, dst_dir_fd=directory)
                                os.fsync(directory)
                            finally:
                                try:
                                    os.unlink(temporary, dir_fd=directory)
                                except FileNotFoundError:
                                    pass
                    finally:
                        connection.close()
            except (OSError, sqlite3.Error):
                raise JobError('storage') from None
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def create(self, owner, query, timeout, request_id):
        key = owner_key(owner)
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM jobs WHERE owner=? AND request_id=?', (key, request_id)).fetchone()
            if existing:
                if existing['query'] != query or existing['timeout'] != timeout:
                    raise JobError('conflict')
                return dict(existing), False
            for row in db.execute("SELECT * FROM jobs WHERE status IN ('queued','running')").fetchall():
                if self._stale(row):
                    db.execute("UPDATE jobs SET status='interrupted',code='interrupted',updated=? WHERE id=? AND status IN ('queued','running')",
                               (time.time(), row['id']))
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') LIMIT 1").fetchone():
                raise JobError('busy')
            job_id, now = uuid.uuid4().hex, time.time()
            db.execute('INSERT INTO jobs(id,owner,request_id,query,timeout,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                       (job_id, key, request_id, query, timeout, 'queued', now, now))
            db.commit()
        return self.get(job_id, owner), True

    def get(self, job_id, owner):
        if not valid_job_id(job_id):
            raise JobError('not_found')
        with self._connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job_id, owner_key(owner))).fetchone()
            if row is None:
                raise JobError('not_found')
            return dict(row)

    @staticmethod
    def _stale(row):
        if row['pid']:
            try:
                os.kill(row['pid'], 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            # Do not free an execution slot merely because wall time advanced.
            # A live (or reused) PID is ambiguous; only its owner may stop it.
            return False
        return time.time() - row['updated'] > 30

    def status(self, job_id, owner):
        row = self.get(job_id, owner)
        if row['status'] in ACTIVE and self._stale(row):
            with self._connection() as db:
                # Compare the exact inspected snapshot. A supervisor may have
                # claimed/refreshed the row while this reader was outside a transaction.
                db.execute("UPDATE jobs SET status='interrupted',code='interrupted',updated=? WHERE id=? AND status=? AND updated=? AND pid IS ?",
                           (time.time(), job_id, row['status'], row['updated'], row['pid']))
            row = self.get(job_id, owner)
        answer = {'job_id': row['id'], 'status': row['status']}
        if row['code']:
            answer['code'] = row['code']
        if row['status'] == 'needs_clarification':
            answer['questions'] = json.loads(row['questions'])
        return answer

    def claim(self, job_id):
        if not valid_job_id(job_id):
            raise JobError('not_found')
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute("UPDATE jobs SET status='running',updated=?,pid=? WHERE id=? AND status='queued'",
                                 (time.time(), os.getpid(), job_id)).rowcount
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone() if changed else None
            db.commit()
            return dict(row) if row else None

    def finish(self, job_id, payload):
        if not valid_job_id(job_id):
            raise JobError('not_found')
        if not isinstance(payload, dict):
            raise JobError('protocol')
        status_value = payload.get('status')
        sources, questions, code, report = [], [], None, None
        if status_value == 'completed':
            report = payload.get('report')
            if (payload.get('full_report') is not True or not isinstance(report, str)
                    or not report.strip() or len(report.encode('utf-8')) > MAX_REPORT_BYTES):
                raise JobError('incomplete')
            sources = safe_sources(payload.get('sources', []))
        elif status_value == 'needs_clarification':
            questions = payload.get('questions')
            if (not isinstance(questions, list) or not 1 <= len(questions) <= 20
                    or any(not isinstance(q, str) or not q.strip() or len(q) > 2000 for q in questions)):
                raise JobError('protocol')
        elif status_value == 'failed':
            code = payload.get('code')
            if code not in ERROR_CODES:
                raise JobError('protocol')
        else:
            raise JobError('protocol')
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None or row['status'] not in ACTIVE:
                return False
            if report is not None:
                if row['status'] != 'running':
                    raise JobError('protocol')
                self._write_report(job_id, report)
            db.execute('UPDATE jobs SET status=?,updated=?,sources=?,questions=?,code=? WHERE id=?',
                       (status_value, time.time(), json.dumps(sources), json.dumps(questions), code, job_id))
            db.commit()
            return True

    def _write_report(self, job_id, report):
        with self._directory() as directory:
            temporary = '.report-' + uuid.uuid4().hex
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(report.encode('utf-8'))
                    handle.flush()
                    os.fsync(handle.fileno())
                # Publish without replacing a preexisting file or symlink.
                os.link(temporary, job_id + '.md', src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass

    def result(self, job_id, owner):
        row = self.get(job_id, owner)
        answer = {'job_id': row['id'], 'status': row['status']}
        if row['code']:
            answer['code'] = row['code']
        if row['status'] == 'needs_clarification':
            answer['questions'] = json.loads(row['questions'])
        if row['status'] == 'completed':
            with self._directory() as directory:
                self._check_file(directory, job_id + '.md')
                fd = os.open(job_id + '.md', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(fd, 'rb') as handle:
                    info = os.fstat(handle.fileno())
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
                        raise JobError('storage')
                    raw = handle.read(MAX_REPORT_BYTES + 1)
                if len(raw) > MAX_REPORT_BYTES:
                    raise JobError('storage')
            try:
                answer['report'] = raw.decode('utf-8')
            except UnicodeError:
                raise JobError('storage') from None
            answer.update(full_report=True, sources=json.loads(row['sources']),
                          report_path=str(self.root / (job_id + '.md')))
        return answer


ERROR_CODES = frozenset({'auth', 'forbidden', 'quota', 'timeout', 'incomplete', 'dependency',
                         'storage', 'provider', 'runtime', 'protocol', 'interrupted'})


def safe_sources(sources):
    from urllib.parse import urlsplit
    if not isinstance(sources, list):
        raise JobError('protocol')
    clean, seen = [], set()
    for source in sources[:200]:
        if not isinstance(source, dict):
            continue
        url, title = source.get('url'), source.get('title', '')
        if not isinstance(url, str) or not isinstance(title, str) or len(url) > 8000:
            continue
        try:
            parsed = urlsplit(url)
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
                    or parsed.password or parsed.hostname.endswith('.cloudfront.net')
                    or any(key in parsed.query.lower() for key in ('signature=', 'policy=', 'key-pair-id=', 'token='))):
                continue
        except ValueError:
            continue
        if url not in seen:
            clean.append({'title': title[:500], 'url': url})
            seen.add(url)
    return clean

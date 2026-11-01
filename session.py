"""Private profile credentials, separate from replaceable plugin code/runtime.

POSIX-only: fail closed without directory descriptors and O_NOFOLLOW. The chosen
HERMES_HOME and its OS-owned ancestors are trusted; paths below it are not followed.
No SDK token loader, environment fallback or automatic migration is involved.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import secrets
import stat


class StoreError(Exception):
    """Opaque local storage error: callers must never render OS exception text."""


class ChangeUncertain(StoreError):
    """Rename/unlink committed, but directory durability could not be confirmed."""


class SessionStore:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.path = self.home / 'plugin-auth' / 'perplexity-pro' / 'token'

    @contextlib.contextmanager
    def _directory(self, create=False):
        descriptors = []
        try:
            if os.name != 'posix' or not self.home.is_absolute():
                raise StoreError()
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            try:
                descriptor = os.open(self.home, flags)
                descriptors.append(descriptor)
                for name in ('plugin-auth', 'perplexity-pro'):
                    if create:
                        try:
                            os.mkdir(name, 0o700, dir_fd=descriptor)
                        except FileExistsError:
                            pass
                        # Confirm ancestor entries even on a retry after mkdir
                        # succeeded but its previous directory fsync failed.
                        os.fsync(descriptor)
                    descriptor = os.open(name, flags, dir_fd=descriptor)
                    descriptors.append(descriptor)
                    info = os.fstat(descriptor)
                    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                        raise StoreError()
            except FileNotFoundError:
                if create:
                    raise StoreError() from None
                descriptor = None
            yield descriptor
        except OSError:
            raise StoreError() from None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    @staticmethod
    def _check_file(directory):
        try:
            info = os.stat('token', dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise StoreError()
        return True

    def read(self):
        with self._directory() as directory:
            if directory is None or not self._check_file(directory):
                return None
            descriptor = os.open('token', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(descriptor, 'r', encoding='utf-8') as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
                    raise StoreError()
                value = handle.read(65537)
            if not value.strip() or len(value) > 65536:
                raise StoreError()
            return value.strip()

    def save(self, token):
        if not isinstance(token, str) or not token.strip() or len(token) > 65536:
            raise StoreError()
        with self._directory(create=True) as directory:
            self._check_file(directory)
            temporary = '.token-' + secrets.token_hex(12)
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=directory)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                    handle.write(token.strip())
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, 'token', src_dir_fd=directory, dst_dir_fd=directory)
                self._sync_change(directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass

    @staticmethod
    def _sync_change(directory):
        try:
            os.fsync(directory)
        except (OSError, KeyboardInterrupt):
            raise ChangeUncertain() from None

    def logout(self):
        with self._directory() as directory:
            if directory is None or not self._check_file(directory):
                return False
            os.unlink('token', dir_fd=directory)
            self._sync_change(directory)
            return True

# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded snapshots and private run directories; no raw capture cleanup."""
import os
from pathlib import Path
import stat
import uuid
from .diagnostics import Failure, require


def real_path(path):
    path = Path(path).absolute()
    require(not str(path).startswith(('\\\\', '//')), 'SOURCE_UNSAFE')
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and
                not getattr(info, 'st_file_attributes', 0) & 0x400, 'SOURCE_UNSAFE')
    return path


def _handle_snapshot_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _windows_path_identity(info):
    # Windows fstat/lstat can expose different ctime semantics. Only this
    # cross-API comparison excludes ctime; the same-handle check remains strict.
    return (info.st_dev, info.st_ino, info.st_nlink, info.st_size, info.st_mtime_ns)


def read_regular(path, maximum, minimum=1):
    try:
        path = real_path(path)
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        if os.name == 'nt':
            # Do not follow a last-component reparse point even if it appeared
            # after lstat; deny writers/deletion for the snapshot lifetime.
            import ctypes
            import msvcrt
            from ctypes import wintypes as w
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                                          w.DWORD, w.DWORD, w.HANDLE]
            kernel.CreateFileW.restype = w.HANDLE
            handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
            require(handle not in (None, ctypes.c_void_p(-1).value), 'SOURCE_UNSAFE')
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        else:
            fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            first = os.fstat(stream.fileno())
            require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and
                    not getattr(first, 'st_file_attributes', 0) & 0x400, 'SOURCE_UNSAFE')
            require(minimum <= first.st_size <= maximum, 'SOURCE_UNSAFE')
            data = stream.read(maximum + 1)
            last = os.fstat(stream.fileno())
            current = path.lstat()
            require(len(data) == first.st_size and
                    _handle_snapshot_identity(first) == _handle_snapshot_identity(last),
                    'SOURCE_UNSAFE')
            if os.name == 'nt':
                require(stat.S_ISREG(current.st_mode) and not stat.S_ISLNK(current.st_mode) and
                        not getattr(current, 'st_file_attributes', 0) & 0x400 and
                        _windows_path_identity(first) == _windows_path_identity(last) ==
                        _windows_path_identity(current), 'SOURCE_UNSAFE')
            else:
                require(_handle_snapshot_identity(first) == _handle_snapshot_identity(current),
                        'SOURCE_UNSAFE')
            real_path(path)
            return data
    except OSError:
        raise Failure('SOURCE_UNSAFE') from None


def private_directory(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    real_path(path)
    if os.name == 'nt':
        from .windows import restrict_directory
        restrict_directory(path)
    else:
        path.chmod(0o700)
    return path


def create_run(base):
    base = real_path(base)
    run = private_directory(base / ('run-' + uuid.uuid4().hex))
    private_directory(run / 'raw')
    private_directory(run / 'diagnostics')
    return run


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())

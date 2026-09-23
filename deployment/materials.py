#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline device-bundle validation and atomic import; never accesses USB.

Python validates metadata, formats, digests and cross-file layout. Complete
cryptographic transport binding is checked by the required native_check callback
using the same USB-free C loader as the driver, before publication.
"""
import ctypes
from dataclasses import dataclass, field
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
from types import MappingProxyType


NAMES = ('target-material-manifest.json', 'transport-material.bin',
         'target-config-90.bin', 'gfusb.dll', 'fdt-cache.bin')
DESTINATION = Path('/var/lib/goodix-5125-poc')
DLL_SIZE = 5771496
DLL_SHA256 = '904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2'
SIZES = {NAMES[0]: (1, 4096), NAMES[1]: (88, 88), NAMES[2]: (224, 224),
         NAMES[3]: (DLL_SIZE, DLL_SIZE), NAMES[4]: (13520, 13520)}
IDENTITY = {'schema': 'goodix-5125-device-materials-v1', 'vid': '27c6',
            'pid': '5125', 'app': 'GF_ST411SEC_APP_12509'}
HASH_FIELDS = ('transport_sha256', 'config90_sha256', 'fdt_cache_sha256',
               'a2_response_sha256', 'chip82_response_sha256', 'otp_a6_response_sha256')
TRANSPORT_HEADER = b'G5125POC' + struct.pack('<8H', 1, 24, 0x27c6, 0x5125, 1, 32, 32, 0)


class MaterialError(RuntimeError):
    """Safe diagnostic: messages contain field/file names, never protected values."""


def require(ok, message):
    if not ok:
        raise MaterialError(message)


def sha256(value):
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, repr=False)
class Bundle:
    files: object = field(repr=False)
    manifest: object = field(repr=False)

    def __repr__(self):
        return '<ValidatedMaterialBundle: five protected files; contents hidden>'


def crc32_mpeg2(data):
    crc = 0xffffffff
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
    return crc


def parse_manifest(data):
    require(1 <= len(data) <= 4096 and b'\\' not in data and b'\0' not in data,
            'manifest size, escaped string or NUL is unsupported')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'manifest contains a duplicate field')
            result[key] = value
        return result
    try:
        value = json.loads(data.decode('ascii'), object_pairs_hook=unique)
    except (UnicodeError, ValueError) as error:
        raise MaterialError('manifest must be an ASCII JSON object') from error
    require(isinstance(value, dict) and set(value) == set(IDENTITY) | set(HASH_FIELDS),
            'manifest field set is unsupported')
    require(all(value[key] == expected for key, expected in IDENTITY.items()),
            'manifest hardware/firmware identity is unsupported')
    require(all(isinstance(value[key], str) and re.fullmatch('[0-9a-fA-F]{64}', value[key])
                for key in HASH_FIELDS), 'manifest digest syntax is invalid')
    return value


def validate_pe(data):
    """Check the globally qualified OEM identity and the C loader's seed layout."""
    require(len(data) == DLL_SIZE and sha256(data) == DLL_SHA256,
            'gfusb.dll does not match the supported OEM compatibility identity')
    require(data[:2] == b'MZ', 'gfusb.dll DOS header is invalid')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    require(pe <= len(data) - 24 and data[pe:pe + 4] == b'PE\0\0',
            'gfusb.dll PE header is invalid')
    count = struct.unpack_from('<H', data, pe + 6)[0]
    optional = struct.unpack_from('<H', data, pe + 20)[0]
    table = pe + 24 + optional
    require(1 <= count <= 96 and table + 40 * count <= len(data),
            'gfusb.dll PE section table is invalid')
    sections = [struct.unpack_from('<4I', data, table + 40 * i + 8) for i in range(count)]
    def rva_bytes(rva, wanted):
        for virtual_size, virtual_address, raw_size, raw_offset in sections:
            if virtual_address <= rva and rva + wanted <= virtual_address + min(virtual_size, raw_size):
                offset = raw_offset + rva - virtual_address
                require(offset + wanted <= len(data), 'gfusb.dll producer RVA exceeds file bounds')
                return data[offset:offset + wanted]
        raise MaterialError('gfusb.dll producer RVA is not file-backed')
    rva_bytes(0x56f030, 6)
    instruction = rva_bytes(0x69d0, 14)
    require(instruction[:3] == b'\xc7\x45\x9f' and instruction[7:10] == b'\xc7\x45\xa3',
            'gfusb.dll producer instruction is invalid')
    pattern = instruction[:12]
    first = data.find(pattern)
    require(first >= 0 and data.find(pattern, first + 1) < 0,
            'gfusb.dll producer instruction is ambiguous')


def validate_bytes(files):
    require(set(files) == set(NAMES), 'exactly the five named device files are required')
    for name in NAMES:
        require(isinstance(files[name], bytes), 'material snapshot must contain immutable file bytes')
        low, high = SIZES[name]
        require(low <= len(files[name]) <= high, f'{name}: invalid file size')
    manifest = parse_manifest(files[NAMES[0]])
    for name, key in ((NAMES[1], 'transport_sha256'), (NAMES[2], 'config90_sha256'),
                      (NAMES[4], 'fdt_cache_sha256')):
        require(sha256(files[name]) == manifest[key].lower(), f'{name}: manifest digest mismatch')
    transport, config, cache = (files[NAMES[i]] for i in (1, 2, 4))
    require(transport[:24] == TRANSPORT_HEADER, 'transport material header is invalid')
    require((sum(struct.unpack('<112H', config)) + 0xa5a5) & 0xffff == 0,
            'configuration finalizer is invalid')
    for offset, register in ((117, 0x0220), (121, 0x0236), (125, 0x0238), (129, 0x023a)):
        require(struct.unpack_from('<H', config, offset)[0] == register,
                'configuration DAC register layout is invalid')
    require(struct.unpack_from('<I', cache, 13516)[0] == crc32_mpeg2(cache[:13516]),
            'FDT cache CRC-32/MPEG-2 is invalid')
    require(sha256(cache[:64]) == manifest['otp_a6_response_sha256'].lower(),
            'FDT cache OTP binding is invalid')
    require(any(cache[64:76]), 'FDT cache seed is absent')
    validate_pe(files[NAMES[3]])
    return Bundle(MappingProxyType(dict(files)), MappingProxyType(manifest))


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def metadata_ok(info, *, directory, source, owner_uid, owner_gid=None):
    require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode),
            'material path must be a real directory or regular file, never a link/special file')
    require(info.st_uid == owner_uid and (owner_gid is None or info.st_gid == owner_gid),
            'material ownership is invalid')
    if not directory:
        require(info.st_nlink == 1, 'material hard links are not permitted')
    mode = stat.S_IMODE(info.st_mode)
    if source:
        require(not mode & (0o7022 if directory else 0o7133),
                'source material permissions allow unsafe modification or execution')
    else:
        require(mode == (0o700 if directory else 0o600), 'installed material permissions are invalid')


def validate_bundle(directory, source=True, owner_uid=None, owner_gid=None):
    """Read a stable five-file snapshot without following links or opening USB.

    Source files may be ordinarily readable (such as 0644), but not shared for
    writing or executable; import always creates private 0700/0600 root files.
    A privileged caller must pass the original staging user's UID explicitly.
    """
    directory = Path(directory).absolute()
    owner_uid = os.geteuid() if owner_uid is None else owner_uid
    if not source and owner_gid is None:
        owner_gid = 0 if owner_uid == 0 else os.getegid()
    for path in (directory, *directory.parents):
        require(not path.is_symlink(), 'material directory ancestors must not be symbolic links')
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(directory, flags | os.O_DIRECTORY)
    try:
        before = os.fstat(fd)
        metadata_ok(before, directory=True, source=source, owner_uid=owner_uid, owner_gid=owner_gid)
        require(set(os.listdir(fd)) == set(NAMES), 'exactly the five named device files are required')
        files = {}
        for name in NAMES:
            item = os.open(name, flags, dir_fd=fd)
            try:
                first = os.fstat(item)
                metadata_ok(first, directory=False, source=source, owner_uid=owner_uid, owner_gid=owner_gid)
                low, high = SIZES[name]
                require(low <= first.st_size <= high, f'{name}: invalid file size')
                chunks, total = [], 0
                while True:
                    chunk = os.read(item, min(65536, high + 1 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    require(total <= high, f'{name}: file grew during validation')
                require(total == first.st_size and fingerprint(os.fstat(item)) == fingerprint(first),
                        f'{name}: changed during validation')
                require(fingerprint(os.stat(name, dir_fd=fd, follow_symlinks=False)) == fingerprint(first),
                        f'{name}: replaced during validation')
                files[name] = b''.join(chunks)
            finally:
                os.close(item)
        require(fingerprint(os.fstat(fd)) == fingerprint(before) and
                fingerprint(directory.lstat()) == fingerprint(before),
                'material directory changed during validation')
        return validate_bytes(files)
    finally:
        os.close(fd)


def publish_without_replace(parent_fd, stage_name, destination_name):
    """Linux atomic publication with RENAME_NOREPLACE; never overwrite a collision."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    require(rename is not None, 'atomic material publication is unavailable')
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(parent_fd, os.fsencode(stage_name), parent_fd, os.fsencode(destination_name), 1) != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise MaterialError('material destination appeared during import; it was preserved')
        raise MaterialError('atomic material publication failed: ' + os.strerror(error))


def trusted_destination_parent(destination, owner_uid):
    """Only root-controlled ancestors may hold the protected published set."""
    for path in (destination.parent, *destination.parent.parents):
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner_uid and not info.st_mode & 0o022,
                'material destination parent is not a trusted directory')


def install_materials(bundle, destination=DESTINATION, *, native_check, owner_uid=0, owner_gid=0):
    """Publish a complete validated bundle, or preserve an identical existing set.

    native_check(Path) must raise on failed USB-free native/E4 validation. This
    function does not change SELinux; the enclosing quiesced installer owns that
    mapping and rollback. A fully published material set is preserved thereafter.
    """
    require(callable(native_check), 'native material binding validation is required')
    require(isinstance(bundle, Bundle), 'a validated material snapshot is required')
    bundle = validate_bytes(bundle.files)
    destination = Path(destination).absolute()
    trusted_destination_parent(destination, owner_uid)
    if destination.exists() or destination.is_symlink():
        existing = validate_bundle(destination, source=False, owner_uid=owner_uid, owner_gid=owner_gid)
        require(existing.files == bundle.files, 'existing installed material differs; it was preserved')
        native_check(destination)
        return False
    parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    stage = None
    identity = None
    try:
        stage = Path(tempfile.mkdtemp(prefix='.goodix-materials-', dir=destination.parent))
        metadata = stage.lstat()
        identity = (metadata.st_dev, metadata.st_ino)
        stage.chmod(0o700)
        if (metadata.st_uid, metadata.st_gid) != (owner_uid, owner_gid):
            os.chown(stage, owner_uid, owner_gid, follow_symlinks=False)
        for name in NAMES:
            fd = os.open(stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            with os.fdopen(fd, 'wb') as output:
                info = os.fstat(output.fileno())
                if (info.st_uid, info.st_gid) != (owner_uid, owner_gid):
                    os.fchown(output.fileno(), owner_uid, owner_gid)
                os.fchmod(output.fileno(), 0o600)
                output.write(bundle.files[name])
                output.flush()
                os.fsync(output.fileno())
        validate_bundle(stage, source=False, owner_uid=owner_uid, owner_gid=owner_gid)
        native_check(stage)
        # Revalidate after callback and before the single publication operation.
        require(validate_bundle(stage, source=False, owner_uid=owner_uid, owner_gid=owner_gid).files == bundle.files,
                'material staging changed before publication')
        stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(stage_fd)
        finally:
            os.close(stage_fd)
        publish_without_replace(parent_fd, stage.name, destination.name)
        stage = None
        os.fsync(parent_fd)
        return True
    finally:
        os.close(parent_fd)
        if stage is not None:
            info = stage.lstat()
            require((info.st_dev, info.st_ino) == identity and stat.S_ISDIR(info.st_mode),
                    'material staging path changed; retained for review')
            shutil.rmtree(stage)

# SPDX-License-Identifier: GPL-2.0-or-later
"""Material domain pipeline: no GUI, device IO, subprocesses or network."""
from dataclasses import dataclass, field
import hmac
import json
import os
from pathlib import Path
import struct
from deployment import materials
from . import binding
from .diagnostics import Failure, require
from .files import private_directory, read_regular, real_path, write_new


@dataclass(frozen=True, repr=False)
class Sources:
    cache: bytes = field(repr=False)
    fdt: bytes = field(repr=False)
    dll: bytes = field(repr=False)


def validate_sources(folder):
    folder = Path(folder)
    for name, code in [('Goodix_Cache.bin', 'GOODIX_CACHE'), ('goodix.dat', 'FDT'), ('gfusb.dll', 'DLL')]:
        require((folder / name).exists() or (folder / name).is_symlink(), f'SOURCE_{code}_MISSING')
    real_path(folder)
    for name in ('Goodix_Cache.bin', 'goodix.dat', 'gfusb.dll'):
        real_path(folder / name)
    require((folder / 'goodix.dat').lstat().st_size == 13520, 'FDT_INVALID_SIZE')
    require((folder / 'gfusb.dll').lstat().st_size == materials.DLL_SIZE, 'DLL_NOT_QUALIFIED')
    require(8 < (folder / 'Goodix_Cache.bin').lstat().st_size <= 1024 * 1024, 'SOURCE_CACHE_INVALID')
    cache = read_regular(folder / 'Goodix_Cache.bin', 1024 * 1024, 9)
    require(any(cache[-8:]), 'SOURCE_CACHE_INVALID')
    fdt = read_regular(folder / 'goodix.dat', 13520, 13520)
    require(struct.unpack_from('<I', fdt, 13516)[0] == materials.crc32_mpeg2(fdt[:13516]), 'FDT_CRC_INVALID')
    require(any(fdt[64:76]), 'FDT_SEED_MISSING')
    dll = read_regular(folder / 'gfusb.dll', materials.DLL_SIZE, materials.DLL_SIZE)
    try:
        materials.validate_pe(dll)
        a, b = binding._extract_seeds(dll)
        binding._zero(a)
        binding._zero(b)
    except (materials.MaterialError, ValueError):
        raise Failure('DLL_NOT_QUALIFIED') from None
    return Sources(cache, fdt, dll)


def validate_final(files):
    a = b = expected = None
    try:
        bundle = materials.validate_bytes(files)
        a, b = binding._extract_seeds(files['gfusb.dll'])
        transport = files['transport-material.bin']
        require(any(transport[24:56]), 'FINAL_BUNDLE_VALIDATION_FAILED')
        expected = binding._bind_validator(transport[24:56], a, b)
        require(hmac.compare_digest(expected, transport[56:88]), 'FINAL_BUNDLE_VALIDATION_FAILED')
        return bundle
    except (materials.MaterialError, ValueError):
        raise Failure('FINAL_BUNDLE_VALIDATION_FAILED') from None
    finally:
        for value in (a, b, expected):
            binding._zero(value)


def validate_available_binding(sources, evidence):
    """Do not suggest timing retries when available A6 already disproves binding."""
    if 'A6' in evidence.selected:
        require(hmac.compare_digest(evidence.selected['A6'], sources.fdt[:64]), 'A6_FDT_MISMATCH')


def build(sources, evidence, run, recover):
    """Recover PSK only after all capture/cross-material gates pass.

    recover is the native Windows DPAPI function; injection is for offline tests.
    Never creates a loose PSK. Sensitive immutable Python copies cannot be
    guaranteed erased; mutable native/temporary buffers are cleansed.
    """
    evidence.require_complete()
    validate_available_binding(sources, evidence)
    secret = a = b = validator = transport = None
    try:
        # Qualify DLL again before either producer seed or PSK is used.
        try:
            a, b = binding._extract_seeds(sources.dll)
        except ValueError:
            raise Failure('DLL_NOT_QUALIFIED') from None
        try:
            recovered = recover(sources.cache)
            secret = recovered if isinstance(recovered, bytearray) else bytearray(recovered)
            require(len(secret) == 32 and any(secret), 'DPAPI_RECOVERY_FAILED')
        except Exception:
            raise Failure('DPAPI_RECOVERY_FAILED') from None
        try:
            validator = binding._bind_validator(secret, a, b)
            transport = binding._build_poc(secret, validator)
        except Exception:
            raise Failure('TRANSPORT_BUILD_FAILED') from None
        files = {'transport-material.bin': bytes(transport), 'target-config-90.bin': evidence.selected['CONFIG90'],
                 'gfusb.dll': sources.dll, 'fdt-cache.bin': sources.fdt}
        try:
            manifest = dict(materials.IDENTITY)
            for filename, key in [('transport-material.bin', 'transport_sha256'),
                                  ('target-config-90.bin', 'config90_sha256'), ('fdt-cache.bin', 'fdt_cache_sha256')]:
                manifest[key] = materials.sha256(files[filename])
            for name, key in [('A2', 'a2_response_sha256'), ('CHIP82', 'chip82_response_sha256'), ('A6', 'otp_a6_response_sha256')]:
                manifest[key] = materials.sha256(evidence.selected[name])
            files['target-material-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode('ascii')
            materials.parse_manifest(files['target-material-manifest.json'])
        except Exception:
            raise Failure('MANIFEST_BUILD_FAILED') from None
        validate_final(files)
        return publish(files, run)
    finally:
        for value in (secret, a, b, validator, transport):
            binding._zero(value)


def publish(files, run):
    """Publish by directory rename. Failed staging remains explicitly incomplete."""
    import uuid
    try:
        validate_final(files)
        run = real_path(run)
        destination = run / 'goodix-5125-materials'
        require(not destination.exists(), 'FINAL_BUNDLE_VALIDATION_FAILED')
        stage = private_directory(run / ('.incomplete-' + uuid.uuid4().hex))
        for name in materials.NAMES:
            write_new(stage / name, files[name])
        require(set(p.name for p in stage.iterdir()) == set(materials.NAMES), 'FINAL_BUNDLE_VALIDATION_FAILED')
        snapshot = {name: read_regular(stage / name, materials.SIZES[name][1], materials.SIZES[name][0])
                    for name in materials.NAMES}
        validate_final(snapshot)
        require(snapshot == files, 'FINAL_BUNDLE_VALIDATION_FAILED')
        if os.name == 'nt':
            # Windows rename fails if destination exists, including an empty dir.
            os.rename(stage, destination)
        else:
            fd = os.open(run, os.O_RDONLY | os.O_DIRECTORY)
            try:
                materials.publish_without_replace(fd, stage.name, destination.name)
            finally:
                os.close(fd)
        return destination
    except (OSError, materials.MaterialError):
        raise Failure('FINAL_BUNDLE_VALIDATION_FAILED') from None

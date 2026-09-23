#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic, unprivileged material/import tests; no USB or real secrets.

The OEM DLL's production SHA cannot be reproduced without its actual bytes.
Tests use a generated full-size PE and monkeypatch ONLY that global digest.
The production digest is also tested without the seam and rejects the fixture.
Native E4 validation is a required callback. Set GOODIX_MATERIAL_TEST_NATIVE to
the compiled test_material_native binary to exercise the real loader/crypto
against both fixtures and malformed E4 binding. No physical reader is involved.
"""
import dataclasses
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location('goodix_public_materials', Path(__file__).with_name('materials.py'))
materials = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = materials
SPEC.loader.exec_module(materials)


def synthetic_dll():
    data = bytearray(materials.DLL_SIZE)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', data, 0x86, 1)
    # One file-backed section covers both production seed RVAs.
    struct.pack_into('<4I', data, 0x80 + 24 + 8,
                     len(data) - 0x200, 0, len(data) - 0x200, 0x200)
    data[0x200 + 0x56f030:0x200 + 0x56f036] = bytes(range(1, 7))
    data[0x200 + 0x69d0:0x200 + 0x69d0 + 14] = bytes.fromhex('c7459f11223344c745a355667788')
    return bytes(data)


DLL = synthetic_dll()
SYNTHETIC_DLL_SHA256 = hashlib.sha256(DLL).hexdigest()
SYNTHETIC_VALIDATORS = {
    1: bytes.fromhex('565ef72b408c135936e97c4dc00cea3020502a4a3559d5b959d815291fc0c611'),
    2: bytes.fromhex('0a1a51db6b8b08d25f66ea089702e84e8c614f69effa9e86a55c681063f6b815'),
}


def config_finalizer(config):
    struct.pack_into('<H', config, 222, (-0xa5a5 - sum(struct.unpack('<111H', config[:222]))) & 0xffff)


def refresh_manifest(files, **extra):
    manifest = dict(materials.IDENTITY)
    manifest.update({
        'transport_sha256': materials.sha256(files[materials.NAMES[1]]),
        'config90_sha256': materials.sha256(files[materials.NAMES[2]]),
        'fdt_cache_sha256': materials.sha256(files[materials.NAMES[4]]),
        'a2_response_sha256': materials.sha256(b'synthetic-A2'),
        'chip82_response_sha256': materials.sha256(b'synthetic-chip82'),
        'otp_a6_response_sha256': materials.sha256(files[materials.NAMES[4]][:64]),
    })
    manifest.update(extra)
    files[materials.NAMES[0]] = json.dumps(manifest, sort_keys=True).encode('ascii')
    return files


def synthetic_files(variant=1):
    """Two distinct valid synthetic reader sets, including native E4 binding."""
    transport = materials.TRANSPORT_HEADER + bytes((variant * 41 + i * 3 + 1) & 255 for i in range(32))
    # Fixed vectors generated from the public native binder with the synthetic
    # DLL seeds 01..06 and 11,22,33,44,55,66 and these two synthetic PSKs.
    transport += SYNTHETIC_VALIDATORS[variant]
    config = bytearray((variant * 29 + i * 7 + 3) & 255 for i in range(224))
    for i, (offset, register) in enumerate(((117, 0x220), (121, 0x236), (125, 0x238), (129, 0x23a))):
        struct.pack_into('<HH', config, offset, register, variant * 257 + i * 5)
    config_finalizer(config)
    cache = bytearray((variant * 23 + i * 5 + 7) & 255 for i in range(13520))
    struct.pack_into('<I', cache, 13516, materials.crc32_mpeg2(cache[:13516]))
    files = {materials.NAMES[1]: transport, materials.NAMES[2]: bytes(config),
             materials.NAMES[3]: DLL, materials.NAMES[4]: bytes(cache)}
    return refresh_manifest(files,
                            a2_response_sha256=materials.sha256(bytes([variant + 1, variant + 11, variant + 21])),
                            chip82_response_sha256=materials.sha256(bytes((variant * 13 + i + 1) & 255 for i in range(32))))


def write_bundle(directory, files=None, *, file_mode=0o600, directory_mode=0o700):
    directory.mkdir(mode=directory_mode)
    directory.chmod(directory_mode)
    for name, content in (synthetic_files() if files is None else files).items():
        (directory / name).write_bytes(content)
        (directory / name).chmod(file_mode)
    return directory


class MaterialFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goodix-material-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = synthetic_files()
        self.source = write_bundle(self.root / 'source', self.files)
        self.dll_seam = mock.patch.object(materials, 'DLL_SHA256', SYNTHETIC_DLL_SHA256)
        self.dll_seam.start()
        self.addCleanup(self.dll_seam.stop)

    def bundle(self):
        return materials.validate_bundle(self.source)

    def reject_bytes(self, files, message):
        with self.assertRaisesRegex(materials.MaterialError, message):
            materials.validate_bytes(files)


class MaterialTests(MaterialFixture):
    def test_two_distinct_reader_sets_are_accepted(self):
        first = self.bundle()
        second = materials.validate_bundle(write_bundle(self.root / 'reader-two', synthetic_files(2)))
        self.assertNotEqual(first.files, second.files)
        for field in materials.HASH_FIELDS:
            self.assertNotEqual(first.manifest[field], second.manifest[field], field)
        for name in (materials.NAMES[1], materials.NAMES[2], materials.NAMES[4]):
            self.assertNotEqual(first.files[name], second.files[name], name)

    def test_snapshot_is_immutable_and_repr_redacted(self):
        bundle = self.bundle()
        with self.assertRaises(TypeError):
            bundle.files[materials.NAMES[1]] = b'x'
        with self.assertRaises(dataclasses.FrozenInstanceError):
            bundle.files = {}
        self.assertNotIn(self.files[materials.NAMES[1]].hex(), repr(bundle))
        self.assertIn('contents hidden', repr(bundle))
        (self.source / materials.NAMES[1]).write_bytes(b'replaced')
        self.assertEqual(bundle.files[materials.NAMES[1]], self.files[materials.NAMES[1]])

    def test_global_dll_identity_is_enforced_without_test_seam(self):
        with mock.patch.object(materials, 'DLL_SHA256', '904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2'):
            self.reject_bytes(self.files, 'OEM compatibility identity')

    def test_exact_five_names_missing_and_extra(self):
        for name in materials.NAMES:
            with self.subTest(missing=name):
                files = dict(self.files)
                del files[name]
                self.reject_bytes(files, 'exactly the five')
        (self.source / 'extra').write_text('unexpected')
        with self.assertRaisesRegex(materials.MaterialError, 'exactly the five'):
            self.bundle()

    def test_size_limits_every_file(self):
        for name in materials.NAMES:
            for size in (0, materials.SIZES[name][1] + 1):
                with self.subTest(file=name, size=size):
                    files = dict(self.files)
                    files[name] = bytes(size)
                    self.reject_bytes(files, 'invalid file size')

    def test_manifest_schema_hardware_and_exact_fields(self):
        original = json.loads(self.files[materials.NAMES[0]])
        for field in materials.IDENTITY:
            for replacement in ('unsupported', 1, None):
                with self.subTest(field=field, value=replacement):
                    changed = dict(original, **{field: replacement})
                    self.reject_bytes(dict(self.files, **{materials.NAMES[0]: json.dumps(changed).encode()}), 'identity')
        for field in original:
            changed = dict(original)
            del changed[field]
            self.reject_bytes(dict(self.files, **{materials.NAMES[0]: json.dumps(changed).encode()}), 'field set')
        original['unexpected'] = 'value'
        self.reject_bytes(dict(self.files, **{materials.NAMES[0]: json.dumps(original).encode()}), 'field set')

    def test_manifest_duplicate_escape_nonascii_and_not_object(self):
        for data, message in ((b'{"vid":"27c6","vid":"27c6"}', 'duplicate'),
                              (b'{"vid":"\\u0032"}', 'escaped'),
                              (b'\xff', 'ASCII'), (b'[]', 'field set'),
                              (b'{}\0', 'NUL'), (b'{}trailing', 'ASCII')):
            with self.subTest(data=data):
                self.reject_bytes(dict(self.files, **{materials.NAMES[0]: data}), message)

    def test_manifest_digest_syntax_and_uppercase(self):
        original = json.loads(self.files[materials.NAMES[0]])
        for field in materials.HASH_FIELDS:
            for invalid in ('0' * 63, 'g' * 64, None, 1):
                changed = dict(original, **{field: invalid})
                self.reject_bytes(dict(self.files, **{materials.NAMES[0]: json.dumps(changed).encode()}), 'digest syntax')
        for field in materials.HASH_FIELDS:
            original[field] = original[field].upper()
        materials.validate_bytes(dict(self.files, **{materials.NAMES[0]: json.dumps(original).encode()}))

    def test_every_manifest_file_binding_is_checked(self):
        for name in (materials.NAMES[1], materials.NAMES[2], materials.NAMES[4]):
            changed = bytearray(self.files[name])
            changed[-1] ^= 1
            self.reject_bytes(dict(self.files, **{name: bytes(changed)}), 'manifest digest mismatch')

    def test_transport_header_each_byte_matters(self):
        for index in range(24):
            changed = bytearray(self.files[materials.NAMES[1]])
            changed[index] ^= 1
            self.reject_bytes(refresh_manifest(dict(self.files, **{materials.NAMES[1]: bytes(changed)})), 'header')

    def test_configuration_finalizer_and_dac_layout(self):
        config = bytearray(self.files[materials.NAMES[2]])
        config[-1] ^= 1
        self.reject_bytes(refresh_manifest(dict(self.files, **{materials.NAMES[2]: bytes(config)})), 'finalizer')
        for offset in (117, 121, 125, 129):
            config = bytearray(self.files[materials.NAMES[2]])
            config[offset] ^= 1
            config_finalizer(config)
            self.reject_bytes(refresh_manifest(dict(self.files, **{materials.NAMES[2]: bytes(config)})), 'register layout')

    def test_cache_crc_otp_binding_and_absent_seed(self):
        cache = bytearray(self.files[materials.NAMES[4]])
        cache[-1] ^= 1
        self.reject_bytes(refresh_manifest(dict(self.files, **{materials.NAMES[4]: bytes(cache)})), 'CRC')
        self.reject_bytes(refresh_manifest(dict(self.files), otp_a6_response_sha256='0' * 64), 'OTP binding')
        cache[64:76] = bytes(12)
        struct.pack_into('<I', cache, 13516, materials.crc32_mpeg2(cache[:13516]))
        self.reject_bytes(refresh_manifest(dict(self.files, **{materials.NAMES[4]: bytes(cache)})), 'seed is absent')

    def test_crc_known_check_value(self):
        self.assertEqual(materials.crc32_mpeg2(b'123456789'), 0x0376e6e7)

    def test_dll_headers_rvas_and_unique_instruction(self):
        for offset, content, message in ((0, b'NO', 'DOS'), (0x80, b'xx', 'PE header'),
                                         (0x86, bytes(2), 'section table'),
                                         (0x80 + 24 + 8, bytes(4), 'not file-backed'),
                                         (0x200 + 0x69d0, bytes(3), 'instruction'),
                                         (0x1000, DLL[0x200 + 0x69d0:0x200 + 0x69d0 + 12], 'ambiguous')):
            with self.subTest(message=message):
                changed = bytearray(DLL)
                changed[offset:offset + len(content)] = content
                changed = bytes(changed)
                with mock.patch.object(materials, 'DLL_SHA256', materials.sha256(changed)):
                    self.reject_bytes(dict(self.files, **{materials.NAMES[3]: changed}), message)

    def test_regular_readable_source_modes_supported(self):
        self.source.chmod(0o755)
        for name in materials.NAMES:
            (self.source / name).chmod(0o644)
        self.bundle()

    def test_shared_writable_executable_or_special_mode_rejected(self):
        path = self.source / materials.NAMES[1]
        for mode in (0o666, 0o620, 0o602, 0o700, 0o610, 0o601, 0o4600):
            path.chmod(mode)
            with self.subTest(mode=oct(mode)), self.assertRaisesRegex(materials.MaterialError, 'permissions'):
                self.bundle()
        path.chmod(0o600)
        for mode in (0o777, 0o770, 0o707, 0o2700):
            self.source.chmod(mode)
            with self.subTest(directory_mode=oct(mode)), self.assertRaisesRegex(materials.MaterialError, 'permissions'):
                self.bundle()

    def test_wrong_owner_rejected(self):
        with self.assertRaisesRegex(materials.MaterialError, 'ownership'):
            materials.validate_bundle(self.source, owner_uid=os.getuid() + 1)
        with self.assertRaisesRegex(materials.MaterialError, 'ownership'):
            materials.validate_bundle(self.source, owner_gid=os.getgid() + 1)

    def test_installed_modes_are_exact(self):
        materials.validate_bundle(self.source, source=False)
        (self.source / materials.NAMES[1]).chmod(0o644)
        with self.assertRaisesRegex(materials.MaterialError, 'installed material permissions'):
            materials.validate_bundle(self.source, source=False)

    def test_file_symlink_is_not_followed(self):
        path = self.source / materials.NAMES[1]
        outside = self.root / 'outside'
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaises(OSError):
            self.bundle()
        self.assertEqual(outside.read_bytes(), self.files[materials.NAMES[1]])

    def test_directory_and_ancestor_symlinks_rejected(self):
        link = self.root / 'link'
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(materials.MaterialError, 'symbolic links'):
            materials.validate_bundle(link)
        ancestor = self.root / 'ancestor'
        ancestor.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(materials.MaterialError, 'symbolic links'):
            materials.validate_bundle(ancestor / 'source')

    def test_hardlink_rejected(self):
        os.link(self.source / materials.NAMES[1], self.root / 'outside-link')
        with self.assertRaisesRegex(materials.MaterialError, 'hard links'):
            self.bundle()

    def test_fifo_is_rejected_without_waiting(self):
        path = self.source / materials.NAMES[1]
        path.unlink()
        os.mkfifo(path, 0o600)
        with self.assertRaisesRegex(materials.MaterialError, 'regular file'):
            self.bundle()

    def test_replace_during_read_is_rejected(self):
        real_read = os.read
        replaced = False
        def read_and_replace(fd, size):
            nonlocal replaced
            result = real_read(fd, size)
            if not replaced:
                replaced = True
                path = self.source / materials.NAMES[0]
                path.rename(self.root / 'old-manifest')
                path.write_bytes(self.files[materials.NAMES[0]])
                path.chmod(0o600)
            return result
        with mock.patch.object(materials.os, 'read', side_effect=read_and_replace):
            with self.assertRaisesRegex(materials.MaterialError, 'changed|replaced'):
                self.bundle()

    def test_growth_during_read_is_rejected(self):
        real_read = os.read
        changed = False
        def read_and_grow(fd, size):
            nonlocal changed
            result = real_read(fd, size)
            if not changed:
                changed = True
                with (self.source / materials.NAMES[0]).open('ab') as output:
                    output.write(b' ')
            return result
        with mock.patch.object(materials.os, 'read', side_effect=read_and_grow):
            with self.assertRaisesRegex(materials.MaterialError, 'changed'):
                self.bundle()


class ImportTests(MaterialFixture):
    def setUp(self):
        super().setUp()
        self.destination = self.root / 'installed'
        self.snapshot = self.bundle()
        self.native_calls = []
        self.parent_seam = mock.patch.object(materials, 'trusted_destination_parent', self.check_fixture_parent)
        self.parent_seam.start()
        self.addCleanup(self.parent_seam.stop)

    def check_fixture_parent(self, destination, owner_uid):
        self.assertEqual(destination.parent, self.root)
        info = self.root.lstat()
        materials.require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner_uid and stat.S_IMODE(info.st_mode) == 0o700,
                          'synthetic parent is unsafe')

    def native_check(self, stage):
        self.native_calls.append(stage)
        verified = materials.validate_bundle(stage, source=False, owner_uid=os.getuid(), owner_gid=os.getgid())
        self.assertEqual(verified.files, self.snapshot.files)

    def install(self, **kwargs):
        return materials.install_materials(self.snapshot, self.destination,
                                           owner_uid=os.getuid(), owner_gid=os.getgid(),
                                           native_check=kwargs.get('native_check', self.native_check))

    def test_import_is_complete_secure_atomic_and_native_checked_before_publish(self):
        def check(stage):
            self.assertFalse(self.destination.exists())
            self.native_check(stage)
        self.assertTrue(self.install(native_check=check))
        self.assertEqual(len(self.native_calls), 1)
        self.assertNotEqual(self.native_calls[0], self.destination)
        self.assertEqual(set(self.root.iterdir()), {self.source, self.destination})
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode), 0o700)
        for name in materials.NAMES:
            self.assertEqual((self.destination / name).read_bytes(), self.files[name])
            self.assertEqual(stat.S_IMODE((self.destination / name).stat().st_mode), 0o600)

    def test_repeat_import_revalidates_native_without_replacing_inodes(self):
        self.install()
        before = {name: (self.destination / name).stat().st_ino for name in materials.NAMES}
        self.assertFalse(self.install())
        self.assertEqual(self.native_calls[-1], self.destination)
        self.assertEqual(before, {name: (self.destination / name).stat().st_ino for name in materials.NAMES})

    def test_different_valid_existing_bundle_is_preserved(self):
        write_bundle(self.destination, synthetic_files(2))
        with self.assertRaisesRegex(materials.MaterialError, 'differs; it was preserved'):
            self.install()
        self.assertFalse(self.native_calls)
        self.assertEqual((self.destination / materials.NAMES[1]).read_bytes(), synthetic_files(2)[materials.NAMES[1]])

    def test_invalid_existing_set_is_preserved(self):
        write_bundle(self.destination)
        (self.destination / materials.NAMES[1]).write_bytes(b'invalid')
        with self.assertRaisesRegex(materials.MaterialError, 'size'):
            self.install()
        self.assertEqual((self.destination / materials.NAMES[1]).read_bytes(), b'invalid')

    def test_destination_symlink_preserved_and_target_untouched(self):
        outside = write_bundle(self.root / 'outside', synthetic_files(2))
        self.destination.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(materials.MaterialError, 'symbolic links'):
            self.install()
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual((outside / materials.NAMES[1]).read_bytes(), synthetic_files(2)[materials.NAMES[1]])

    def test_native_binding_failure_leaves_no_partial_install(self):
        def fail(stage):
            self.native_check(stage)
            raise materials.MaterialError('native E4 cross-binding mismatch')
        with self.assertRaisesRegex(materials.MaterialError, 'E4 cross-binding'):
            self.install(native_check=fail)
        self.assertEqual(set(self.root.iterdir()), {self.source})

    def test_existing_native_failure_is_not_success_or_overwrite(self):
        self.install()
        before = self.destination.stat().st_ino
        def fail(_):
            raise materials.MaterialError('native E4 cross-binding mismatch')
        with self.assertRaisesRegex(materials.MaterialError, 'E4 cross-binding'):
            self.install(native_check=fail)
        self.assertEqual(self.destination.stat().st_ino, before)

    def test_native_callback_required_before_writes(self):
        with self.assertRaisesRegex(materials.MaterialError, 'native material binding'):
            self.install(native_check=None)
        self.assertEqual(set(self.root.iterdir()), {self.source})

    def test_callback_mutation_rejected_before_publish(self):
        def change(stage):
            (stage / materials.NAMES[1]).write_bytes(b'bad')
        with self.assertRaisesRegex(materials.MaterialError, 'size'):
            self.install(native_check=change)
        self.assertEqual(set(self.root.iterdir()), {self.source})

    def test_copy_error_cleans_unpublished_stage(self):
        real_fsync = os.fsync
        calls = 0
        def fail(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('synthetic write failure')
            real_fsync(fd)
        with mock.patch.object(materials.os, 'fsync', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'synthetic write failure'):
                self.install()
        self.assertEqual(set(self.root.iterdir()), {self.source})

    def test_interrupt_cleans_unpublished_stage(self):
        with self.assertRaises(KeyboardInterrupt):
            self.install(native_check=mock.Mock(side_effect=KeyboardInterrupt))
        self.assertEqual(set(self.root.iterdir()), {self.source})

    def test_publication_race_never_overwrites(self):
        sentinel = b'foreign destination'
        def collide(stage):
            self.native_check(stage)
            self.destination.mkdir()
            (self.destination / 'sentinel').write_bytes(sentinel)
        with self.assertRaisesRegex(materials.MaterialError, 'appeared during import'):
            self.install(native_check=collide)
        self.assertEqual(list(self.destination.iterdir()), [self.destination / 'sentinel'])
        self.assertEqual((self.destination / 'sentinel').read_bytes(), sentinel)
        self.assertEqual(set(self.root.iterdir()), {self.source, self.destination})

    def test_invalid_snapshot_cannot_bypass_revalidation(self):
        self.snapshot = materials.Bundle({**self.files, materials.NAMES[1]: b'invalid'}, {})
        with self.assertRaisesRegex(materials.MaterialError, 'size'):
            self.install()
        self.assertEqual(set(self.root.iterdir()), {self.source})

    def test_parent_trust_rejects_untrusted_destination_without_seam(self):
        self.parent_seam.stop()
        with self.assertRaisesRegex(materials.MaterialError, 'trusted directory'):
            self.install()
        self.assertEqual(set(self.root.iterdir()), {self.source})


@unittest.skipUnless(os.environ.get('GOODIX_MATERIAL_TEST_NATIVE'), 'compile the synthetic native test to exercise OpenSSL binding')
class NativeTests(MaterialFixture):
    def native_check(self, path):
        result = subprocess.run([os.environ['GOODIX_MATERIAL_TEST_NATIVE'], str(path)],
                                text=True, capture_output=True, check=False)
        if result.returncode:
            raise materials.MaterialError(result.stderr.strip())
        self.assertIn('E4_BINDING=PASS USB_ACCESSED=false', result.stdout)

    def test_two_distinct_bundles_pass_real_native_crypto(self):
        for variant in (1, 2):
            source = write_bundle(self.root / f'native-{variant}', synthetic_files(variant))
            bundle = materials.validate_bundle(source)
            with mock.patch.object(materials, 'trusted_destination_parent'):
                self.assertTrue(materials.install_materials(
                    bundle, self.root / f'installed-{variant}',
                    native_check=self.native_check, owner_uid=os.getuid(), owner_gid=os.getgid()))

    def test_rebound_manifest_cannot_hide_invalid_e4(self):
        files = synthetic_files()
        transport = bytearray(files[materials.NAMES[1]])
        transport[-1] ^= 1
        files[materials.NAMES[1]] = bytes(transport)
        refresh_manifest(files)
        source = write_bundle(self.root / 'wrong-e4', files)
        bundle = materials.validate_bundle(source)
        destination = self.root / 'rejected'
        with mock.patch.object(materials, 'trusted_destination_parent'):
            with self.assertRaisesRegex(materials.MaterialError, 'E4|binding|validator'):
                materials.install_materials(bundle, destination,
                                            native_check=self.native_check, owner_uid=os.getuid(), owner_gid=os.getgid())
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob('.goodix-materials-*')))


if __name__ == '__main__':
    unittest.main(verbosity=2)

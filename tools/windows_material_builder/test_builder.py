# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic regression suite. Never opens private evidence or a USB device."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from deployment import test_materials as fixture
from deployment import materials
from . import backend, binding, capture, capture_session, diagnostics, windows
from .diagnostics import Failure
from .files import create_run, read_regular


def frame(control, body):
    length = len(body) + 4
    return (bytes([160]) + struct.pack('<H', length) + bytes([(160 + (length & 255) + (length >> 8)) & 255, control]) +
            struct.pack('<H', len(body) + 1) + body + bytes([(170 - ((control & 254) + len(body) + 1 + sum(body))) & 255]))


def usb(payload, irp, *, info=0, ep=1, transfer=3, stage=0, device=2, status=0):
    return (struct.pack('<HQIHBHHBBI', 28 if transfer == 2 else 27, irp, status,
                        8 if transfer == 2 else 9, info, 1, device, ep, transfer, len(payload)) +
            (bytes([stage]) if transfer == 2 else b'') + payload)


def descriptor(irp=1, device=2, identity=(0x27c6, 0x5125)):
    data = bytearray(18)
    data[:2] = b'\x12\x01'
    struct.pack_into('<HH', data, 8, *identity)
    return [usb(b'\x80\x06\x00\x01\x00\x00\x12\x00', irp, ep=128, transfer=2, device=device),
            usb(bytes(data), irp, ep=128, transfer=2, stage=3, info=1, device=device)]


def transfer(payload, irp, incoming=False, device=2):
    ep = 129 if incoming else 1
    return [usb(b'' if incoming else payload, irp, ep=ep, device=device),
            usb(payload if incoming else b'', irp, ep=ep, device=device, info=1)]


def records(*, missing=(), extras=(), identity=(0x27c6, 0x5125), variant=1):
    files = fixture.synthetic_files(variant)
    bodies = [('APP', 0xa8, capture.APP + b'\0', True),
              ('CONFIG90', 0x91, files['target-config-90.bin'], False),
              ('A2', 0xa2, bytes([variant, 2, 3]), True),
              ('CHIP82', 0x82, bytes([variant, 2, 3, 4]), True),
              ('A6', 0xa6, files['fdt-cache.bin'][:64], True)]
    rows = descriptor(identity=identity)
    for i, (name, control, body, incoming) in enumerate(bodies + list(extras), 10):
        if name not in missing:
            rows.extend(transfer(frame(control, body), i, incoming))
    return rows


def pcap(rows, endian='<'):
    result = struct.pack(endian + 'IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 249)
    for i, row in enumerate(rows):
        result += struct.pack(endian + 'IIII', 10, i, len(row), len(row)) + row
    return result


def block(kind, body):
    body += b'\0' * (-len(body) % 4)
    n = len(body) + 12
    return struct.pack('<II', kind, n) + body + struct.pack('<I', n)


def pcapng(rows):
    result = block(0x0a0d0d0a, struct.pack('<IHHq', 0x1a2b3c4d, 1, 0, -1))
    result += block(1, struct.pack('<HHI', 249, 0, 65535))
    for i, row in enumerate(rows):
        result += block(6, struct.pack('<IIIII', 0, 0, i, len(row), len(row)) + row)
    return result


class Case(unittest.TestCase):
    def fails(self, code, call, *args, **kwargs):
        with self.assertRaises(Failure) as result:
            call(*args, **kwargs)
        self.assertEqual(result.exception.diagnostic.code, code)


class ParserTests(Case):
    def test_classic_and_pcapng(self):
        for encoder in (pcap, lambda r: pcap(r, '>'), pcapng):
            evidence = capture.analyze_bytes(encoder(records()))
            evidence.require_complete()
            self.assertEqual(len(evidence.selected), 4)

    def test_truncated_headers_records_blocks(self):
        for value in (b'x', pcap(records())[:-1], pcapng(records())[:-1], pcap(records())[:30]):
            self.fails(capture.BAD, capture.analyze_bytes, value)

    def test_empty(self):
        for value in (b'', pcap([]), pcapng([])):
            self.fails('CAPTURE_EMPTY', capture.analyze_bytes, value)

    def test_bad_record_lengths_linktype_and_snaplen(self):
        for offset, value in [(20, 1), (16, 12), (32, 999999), (36, 99999)]:
            data = bytearray(pcap(records()))
            struct.pack_into('<I', data, offset, value)
            self.fails(capture.BAD, capture.analyze_bytes, bytes(data))

    def test_usb_lengths_reserved_info_and_stage(self):
        for offset, value in [(0, 1), (16, 3), (27, 7), (23, 255)]:
            rows = records()
            row = bytearray(rows[0]); row[offset] = value; rows[0] = bytes(row)
            self.fails(capture.BAD, capture.analyze_bytes, pcap(rows))

    def test_wrong_identity(self):
        self.fails('TARGET_WRONG_IDENTITY', capture.analyze_bytes, pcap(records(identity=(0x1234, 0x5678))))

    def test_multiple_target_devices(self):
        self.fails('TARGET_WRONG_IDENTITY', capture.analyze_bytes, pcap(records() + descriptor(99, device=3)))

    def test_no_descriptor_cannot_prove_identity(self):
        self.fails('TARGET_NOT_OBSERVED', capture.analyze_bytes, pcap(records()[2:]))

    def test_epoch_reuse_does_not_combine_material(self):
        rows = records(missing=('A6',)) + descriptor(100)
        rows += transfer(frame(0xa6, bytes(64)), 101, True)
        self.fails('TARGET_WRONG_IDENTITY', capture.analyze_bytes, pcap(rows))

    def test_descriptor_repeats_before_bulk_are_accepted(self):
        rows = descriptor(100) + records()
        capture.analyze_bytes(pcap(rows)).require_complete()

    def test_each_missing_and_identical_and_distinct(self):
        files = fixture.synthetic_files()
        classes = [('CONFIG90', 0x91, files['target-config-90.bin'], False),
                   ('A2', 0xa2, b'\1\2\3', True), ('CHIP82', 0x82, b'\1\2\3\4', True),
                   ('A6', 0xa6, files['fdt-cache.bin'][:64], True)]
        for name, control, body, incoming in classes:
            with self.subTest(name=name):
                e = capture.analyze_bytes(pcap(records(missing=(name,))))
                self.assertIn(name + '_MISSING', e.codes)
                capture.analyze_bytes(pcap(records(extras=[(name, control, body, incoming)]))).require_complete()
                changed = bytearray(body); changed[0] ^= 1
                if name == 'CONFIG90':
                    fixture.config_finalizer(changed)
                e = capture.analyze_bytes(pcap(records(extras=[(name, control, bytes(changed), incoming)])))
                self.assertIn(name + '_AMBIGUOUS', e.codes)

    def test_exact_wire_controls_and_body_lengths(self):
        for name, control, length in [('A2', 0xa2, 3), ('CHIP82', 0x82, 4), ('A6', 0xa6, 64)]:
            for wire, body in [(control | 1, bytes(length)), (control, bytes(length - 1))]:
                e = capture.analyze_bytes(pcap(records(missing=(name,), extras=[('extra', wire, body, True)])))
                self.assertIn(name + '_MISSING', e.codes)

    def test_bad_config_layout_and_checksum(self):
        body = bytearray(fixture.synthetic_files()['target-config-90.bin'])
        body[117] ^= 1; fixture.config_finalizer(body)
        e = capture.analyze_bytes(pcap(records(missing=('CONFIG90',), extras=[('extra', 0x91, bytes(body), False)])))
        self.assertIn('CONFIG90_MISSING', e.codes)
        rows = records(missing=('A2',))
        bad = bytearray(frame(0xa2, b'\1\2\3')); bad[-1] ^= 1
        rows += transfer(bytes(bad), 100, True)
        self.assertIn('A2_MISSING', capture.analyze_bytes(pcap(rows)).codes)

    def test_app_requires_exact_runtime_identity(self):
        for body in (capture.APP, capture.APP + b'\0\0', b'OTHER\0'):
            self.fails('APP_ID_MISSING_OR_WRONG', capture.analyze_bytes,
                       pcap(records(missing=('APP',), extras=[('extra', 0xa8, body, True)])))

    def test_fragmentation_order_and_incomplete_frame(self):
        rows = records(missing=('A6',))
        raw = frame(0xa6, fixture.synthetic_files()['fdt-cache.bin'][:64])
        for i, fragment in enumerate((raw[:2], raw[2:15], raw[15:]), 100):
            rows += transfer(fragment, i, True)
        capture.analyze_bytes(pcap(rows)).require_complete()
        self.fails(capture.BAD, capture.analyze_bytes, pcap(rows[:-2]))

    def test_outstanding_reuse_and_uncompleted_out(self):
        self.fails(capture.BAD, capture.analyze_bytes, pcap(records() + [usb(frame(0x91, bytes(224)), 999)]))
        rows = records(); rows.insert(1, rows[0])
        self.fails(capture.BAD, capture.analyze_bytes, pcap(rows))

    def test_d255_failure_class_is_synthetic(self):
        # No private capture or digest is used as a fixture.
        e = capture.analyze_bytes(pcapng(records(missing=('CONFIG90',))))
        self.assertEqual(e.codes, ('CONFIG90_MISSING',))
        self.assertEqual(set(e.selected), {'A2', 'CHIP82', 'A6'})


class MaterialTests(Case):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.sources = self.root / 'source'; self.sources.mkdir()
        self.files = fixture.synthetic_files()
        self.cache = b'SYNTHETIC DPAPI CIPHERTEXT' + b'12345678'
        for name, data in [('Goodix_Cache.bin', self.cache), ('gfusb.dll', fixture.DLL),
                           ('goodix.dat', self.files['fdt-cache.bin'])]:
            (self.sources / name).write_bytes(data)
        for module, name in [(materials, 'DLL_SHA256'), (binding, 'OEM_PE_SHA256')]:
            p = patch.object(module, name, fixture.SYNTHETIC_DLL_SHA256);p.start();self.addCleanup(p.stop)

    def test_missing_sources(self):
        for name, code in [('Goodix_Cache.bin', 'GOODIX_CACHE'), ('gfusb.dll', 'DLL'), ('goodix.dat', 'FDT')]:
            p = self.sources / name; data = p.read_bytes(); p.unlink()
            self.fails('SOURCE_' + code + '_MISSING', backend.validate_sources, self.sources)
            p.write_bytes(data)

    def test_sizes_crc_cache_seed(self):
        for name, value, code in [('goodix.dat', b'x', 'FDT_INVALID_SIZE'),
                                  ('gfusb.dll', b'x', 'DLL_NOT_QUALIFIED'),
                                  ('Goodix_Cache.bin', bytes(12), 'SOURCE_CACHE_INVALID'),
                                  ('goodix.dat', bytes(13520), 'FDT_CRC_INVALID')]:
            p = self.sources / name; old = p.read_bytes(); p.write_bytes(value)
            self.fails(code, backend.validate_sources, self.sources); p.write_bytes(old)

    def test_production_dll_pin_rejects_synthetic_without_seam(self):
        with patch.object(materials, 'DLL_SHA256', '904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2'):
            self.fails('DLL_NOT_QUALIFIED', backend.validate_sources, self.sources)

    def test_links_and_hardlinks_rejected(self):
        p = self.sources / 'gfusb.dll'; p.rename(self.root / 'dll')
        p.symlink_to(self.root / 'dll')
        self.fails('SOURCE_UNSAFE', backend.validate_sources, self.sources)
        p.unlink(); os.link(self.root / 'dll', p)
        self.fails('SOURCE_UNSAFE', backend.validate_sources, self.sources)

    def test_reparse_rejected(self):
        info = Mock(st_mode=0o100600, st_file_attributes=0x400)
        with patch('pathlib.Path.lstat', return_value=info):
            self.fails('SOURCE_UNSAFE', read_regular, self.sources / 'goodix.dat', 13520)

    def test_binding_matches_existing_native_generated_vectors(self):
        for variant in (1, 2):
            files = fixture.synthetic_files(variant)
            a, b = binding._extract_seeds(fixture.DLL)
            self.assertEqual(binding._bind_validator(files['transport-material.bin'][24:56], a, b),
                             fixture.SYNTHETIC_VALIDATORS[variant])

    def test_build_manifest_inventory_no_replace_and_retention(self):
        sources = backend.validate_sources(self.sources)
        evidence = capture.analyze_bytes(pcap(records()))
        run = create_run(self.root)
        raw = run / 'raw/oem-init.pcap'; original = pcap(records()); raw.write_bytes(original)
        secret = bytearray(self.files['transport-material.bin'][24:56])
        out = backend.build(sources, evidence, run, lambda _: secret)
        self.assertEqual(secret, bytes(32))
        self.assertEqual(set(p.name for p in out.iterdir()), set(materials.NAMES))
        snapshot = {p.name: p.read_bytes() for p in out.iterdir()}
        backend.validate_final(snapshot)
        self.assertEqual(set(json.loads(snapshot[materials.NAMES[0]])), set(materials.IDENTITY) | set(materials.HASH_FIELDS))
        self.fails('FINAL_BUNDLE_VALIDATION_FAILED', backend.publish, snapshot, run)
        self.assertEqual(raw.read_bytes(), original)
        self.fails('FINAL_BUNDLE_VALIDATION_FAILED', backend.validate_final, snapshot | {'sixth': b'x'})
        if os.environ.get('GOODIX_MATERIAL_TEST_NATIVE'):
            result = subprocess.run([os.environ['GOODIX_MATERIAL_TEST_NATIVE'], str(out)], capture_output=True)
            self.assertEqual(result.returncode, 0, 'native C material loader rejected synthetic builder output')

    def test_invalid_e4_not_hidden_by_rehashed_manifest(self):
        files = dict(self.files); t = bytearray(files['transport-material.bin']); t[-1] ^= 1
        files['transport-material.bin'] = bytes(t); fixture.refresh_manifest(files)
        self.fails('FINAL_BUNDLE_VALIDATION_FAILED', backend.validate_final, files)

    def test_a6_mismatch_and_missing_capture_block_dpapi(self):
        s = backend.validate_sources(self.sources)
        e = capture.analyze_bytes(pcap(records(variant=2)))
        recover = Mock()
        self.fails('A6_FDT_MISMATCH', backend.build, s, e, self.root, recover)
        recover.assert_not_called()
        e = capture.analyze_bytes(pcap(records(missing=('CONFIG90',))))
        self.fails('CONFIG90_MISSING', backend.build, s, e, self.root, recover)
        recover.assert_not_called()

    def test_failed_build_is_not_plausibly_complete(self):
        with patch.object(backend, 'write_new', side_effect=OSError('synthetic failure')):
            self.fails('FINAL_BUNDLE_VALIDATION_FAILED', backend.publish, self.files, self.root)
        self.assertFalse((self.root / 'goodix-5125-materials').exists())

    def test_dpapi_failure_has_no_secret_exception(self):
        secret_text = 'SYNTHETIC_SENSITIVE_EXCEPTION'
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            self.fails('DPAPI_RECOVERY_FAILED', backend.build, backend.validate_sources(self.sources),
                       capture.analyze_bytes(pcap(records())), self.root, Mock(side_effect=ValueError(secret_text)))
        self.assertNotIn(secret_text, stream.getvalue())


class DiagnosticTests(Case):
    def test_every_code_has_fact_hypothesis_action(self):
        for code, value in diagnostics.CATALOG.items():
            with self.subTest(code=code):
                self.assertEqual(value.code, code)
                self.assertGreater(len(value.observed), 15)
                self.assertIn('may', value.possible_cause)
                self.assertGreater(len(value.action), 15)
                self.assertIn('Possible cause:', Failure(code).diagnostic.text())


class WindowsTests(Case):
    def test_dpapi_entropy_native_buffers_and_cleanup(self):
        import ctypes
        cache = b'SYNTHETIC CIPHERTEXT' + b'12345678'
        native = ctypes.create_string_buffer(bytes(range(1, 33)), 32)
        crypt, kernel = Mock(), Mock()
        def unprotect(source, description, entropy, reserved, prompt, flags, output):
            h1 = hashlib.sha256(cache[-8:]).digest()
            expected = h1[16:] + hashlib.sha256(h1[:16] + bytes.fromhex('04e0b0f3f5598417dde298e467c795f7')).digest()
            self.assertEqual(ctypes.string_at(source._obj.data, source._obj.length), cache[:-8])
            self.assertEqual(ctypes.string_at(entropy._obj.data, entropy._obj.length), expected)
            self.assertEqual(flags, 1)
            output._obj.length, output._obj.data = 32, ctypes.addressof(native)
            return True
        crypt.CryptUnprotectData.side_effect = unprotect
        def free(pointer):
            self.assertEqual(ctypes.string_at(pointer, 32), bytes(32))
        kernel.LocalFree.side_effect = free
        with patch.object(windows, 'normal_user') as normal, \
                patch.object(windows.ctypes, 'WinDLL', side_effect=[crypt, kernel], create=True):
            self.assertEqual(windows.recover_dpapi(cache), bytes(range(1, 33)))
            normal.assert_called_once()
            kernel.LocalFree.assert_called_once()

    def test_detection_absent_present_and_unsupported_version(self):
        import types
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / 'USBPcapCMD.exe'; exe.write_bytes(b'synthetic executable')
            driver = root / 'USBPcap.sys'; driver.write_bytes(b'synthetic driver')
            key = contextlib.nullcontext(object())
            registry = types.SimpleNamespace(HKEY_LOCAL_MACHINE=1, KEY_READ=1, KEY_WOW64_64KEY=2,
                                             OpenKey=Mock(return_value=key))
            values = {'DisplayVersion': windows.VERSION, 'UninstallString': '"' + str(root / 'Uninstall.exe') + '"',
                      'ImagePath': str(driver)}
            registry.QueryValueEx = lambda key, name: (values[name], 1)
            def cmd(executable, *args):
                return 'extcap {version=1.5.4.0}' if args == ('--extcap-version',) else 'interface {value=\\\\.\\USBPcap1}{display=USBPcap1}'
            with patch.dict('sys.modules', {'winreg': registry}), patch.object(windows, 'normal_user'), \
                    patch.object(windows, 'powershell', return_value='Running'), \
                    patch.object(windows, 'boot_identity', return_value='after'), \
                    patch.object(windows, 'file_version', return_value=windows.VERSION), \
                    patch.object(windows, 'command', side_effect=cmd), patch.dict(os.environ, {'SystemRoot': str(root)}):
                self.assertTrue(windows.detect(root).driver)
                self.assertEqual(windows.detect(root).interfaces, ('\\\\.\\USBPcap1',))
                values['DisplayVersion'] = '0.0.0.0'
                self.fails('USBPCAP_VERSION_UNSUPPORTED', windows.detect, root)
                registry.OpenKey.side_effect = FileNotFoundError()
                self.assertIsNone(windows.detect(root).executable)

    def test_uac_launcher_error(self):
        fake = Mock()
        fake.ShellExecuteExW.return_value = False
        with patch.object(windows.ctypes, 'WinDLL', return_value=fake, create=True):
            self.fails('USBPCAP_INSTALL_FAILED', windows.launch_installer, Path('synthetic.exe'))

    def test_download_hash_mismatch_is_closed(self):
        response = contextlib.nullcontext(io.BytesIO(b'synthetic wrong installer'))
        opener = Mock(); opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            self.fails('USBPCAP_HASH_OR_PROVENANCE_FAILURE', windows.download_installer)
            opener.open.assert_called_once_with(windows.URL, timeout=30)

    def test_network_failure_is_safe(self):
        with patch('urllib.request.build_opener', side_effect=OSError('synthetic private error text')):
            self.fails('USBPCAP_HASH_OR_PROVENANCE_FAILURE', windows.download_installer)

    def test_interface_selection_and_absent_version_reboot(self):
        p = windows.Prerequisites(Path('USBPcapCMD.exe'), True, windows.VERSION, ('\\\\.\\USBPcap1',), False)
        self.assertEqual(windows.choose_interface(p), p.interfaces[0])
        from dataclasses import replace
        self.fails('USBPCAP_NOT_INSTALLED', windows.choose_interface, replace(p, executable=None))
        self.fails('USBPCAP_INTERFACE_NONE', windows.choose_interface, replace(p, interfaces=()))
        self.fails('USBPCAP_REBOOT_REQUIRED', windows.choose_interface, replace(p, reboot_required=True))
        multi = replace(p, interfaces=p.interfaces + ('\\\\.\\USBPcap2',))
        self.fails('USBPCAP_INTERFACE_AMBIGUOUS', windows.choose_interface, multi)
        self.assertEqual(windows.choose_interface(multi, multi.interfaces[1], True), multi.interfaces[1])

    def test_hash_mismatch(self):
        self.fails('USBPCAP_HASH_OR_PROVENANCE_FAILURE', windows.verify_installer, bytes(windows.INSTALLER_SIZE))

    def test_target_query_absent_present_invalid(self):
        for value in ('0', '1', '2'):
            with patch.object(windows, 'powershell', return_value=value):
                self.assertEqual(windows.target_count(), int(value))
                if value != '0':
                    self.fails('TARGET_PRESENT_BEFORE_CAPTURE', windows.require_detached)
        with patch.object(windows, 'powershell', return_value='unknown'):
            self.fails('TARGET_QUERY_FAILED', windows.target_count)

    def test_reboot_marker_survives_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp);(p / 'install-request-synthetic.json').write_text('{"boot":"before"}')
            self.assertTrue(windows.reboot_pending(p, 'before'))
            self.assertFalse(windows.reboot_pending(p, 'after'))

    def test_installer_failure_and_reboot_state_persist(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(windows, 'normal_user'), \
                patch.object(windows, 'download_installer', return_value=b'synthetic'), \
                patch.object(windows, 'verify_installer'), patch.object(windows, 'read_regular', return_value=b'synthetic'), \
                patch.object(windows, 'boot_identity', return_value='before'), \
                patch.object(windows, 'launch_installer', side_effect=Failure('USBPCAP_INSTALL_FAILED')):
            root = Path(tmp)
            self.fails('USBPCAP_INSTALL_FAILED', windows.install, root)
            self.assertEqual(len(list(root.glob('install-request-*.json'))), 1)

    def test_failed_hash_never_launches(self):
        with patch.object(windows, 'normal_user'), patch.object(windows, 'download_installer',
                side_effect=Failure('USBPCAP_HASH_OR_PROVENANCE_FAILURE')), patch.object(windows, 'launch_installer') as launch:
            self.fails('USBPCAP_HASH_OR_PROVENANCE_FAILURE', windows.install, Path('unused'))
            launch.assert_not_called()


class WorkflowTests(Case):
    def test_capture_subprocess_start_stop_and_error(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.return_value = 0
        process.stdout = io.StringIO('READY\nSTOPPED\n')
        flags = {'CREATE_NEW_CONSOLE': 16, 'STARTF_USESHOWWINDOW': 1}
        with patch.object(capture_session.subprocess, 'STARTUPINFO', return_value=Mock(dwFlags=0), create=True), \
                patch.multiple(capture_session.subprocess, create=True, **flags), \
                patch.object(capture_session.subprocess, 'Popen', return_value=process) as popen:
            owner = capture_session.CaptureProcess(Path('USBPcapCMD.exe'), '\\\\.\\USBPcap1', Path('raw.pcap'))
            owner.start(threading.Event())
            self.assertTrue(owner.alive())
            owner.stop()
            process.stdin.write.assert_called_once_with('STOP\n')
            self.assertIn('tools.windows_material_builder.capture_worker', popen.call_args.args[0])
            self.assertNotIn('-A', popen.call_args.args[0])
            process.stdout = io.StringIO('FAILED\n')
            other = capture_session.CaptureProcess(Path('USBPcapCMD.exe'), '\\\\.\\USBPcap1', Path('raw.pcap'))
            self.fails('CAPTURE_PROCESS_FAILED', other.start, threading.Event())

    def workflow(self, counts, *, missing=(), cancel=False, fail_start=False, fail_stop=False):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name); (root / 'runs').mkdir()
        recording = pcap(records(missing=missing))
        class Process:
            def __init__(self, exe, interface, path): self.path = path
            def start(self, cancelled):
                self.path.write_bytes(recording)
                if fail_start: raise Failure('CAPTURE_PROCESS_FAILED')
            def alive(self): return True
            def stop(self):
                if fail_stop: raise Failure('CAPTURE_PROCESS_FAILED')
        prereq = windows.Prerequisites(Path('synthetic'), True, windows.VERSION, ('\\\\.\\USBPcap1',), False)
        event = threading.Event()
        if cancel: event.set()
        now = iter(range(0, 1000, 10))
        with patch.object(windows, 'target_count', side_effect=counts):
            try:
                result = capture_session.acquire(root, prereq, None, False, event, lambda *_: None,
                                                  process_type=Process, clock=lambda: next(now), pause=lambda _: None)
                return root, result, None
            except Failure as error:
                return root, None, error.diagnostic.code

    def test_success_retains_capture(self):
        root, result, code = self.workflow([0, 0, 1, 1, 1])
        self.assertIsNone(code)
        result[1].require_complete()
        self.assertEqual(len(list((root / 'runs').glob('*/raw/oem-init.pcap'))), 1)

    def test_failure_cancel_and_new_runs_preserve_raw(self):
        for kwargs, code in [({'fail_start': True}, 'CAPTURE_PROCESS_FAILED'),
                              ({'fail_stop': True}, 'CAPTURE_PROCESS_FAILED'),
                              ({'cancel': True}, 'CAPTURE_CANCELLED')]:
            root, result, actual = self.workflow([0, 0, 1, 1, 1], **kwargs)
            self.assertEqual(actual, code)
            self.assertEqual(len(list((root / 'runs').glob('*/raw/oem-init.pcap'))), 1)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotEqual(create_run(Path(tmp)), create_run(Path(tmp)))

    def test_target_present_gate(self):
        with patch.object(windows, 'target_count', return_value=1):
            self.fails('TARGET_PRESENT_BEFORE_CAPTURE', windows.require_detached)

    def test_early_attach_disappearance_and_timeout(self):
        for counts, code in [([0, 1], 'TARGET_PRESENT_BEFORE_CAPTURE'),
                              ([0, 0, 1, 0], 'TARGET_WRONG_IDENTITY'),
                              ([0] * 20, 'TARGET_NOT_OBSERVED')]:
            root, result, actual = self.workflow(counts)
            self.assertEqual(actual, code)
            self.assertEqual(len(list((root / 'runs').glob('*/raw/oem-init.pcap'))), 1)


class PrivacyTests(Case):
    def test_source_has_no_telemetry_or_private_dependencies(self):
        import ast
        root = Path(__file__).parent
        forbidden_imports = {'requests', 'httpx', 'socket', 'scapy', 'pyshark', 'usb', 'pyusb'}
        for path in root.glob('*.py'):
            if path.name.startswith('test_'):
                continue
            text = path.read_text()
            self.assertNotIn('development/private-root', text)
            self.assertNotIn('psk.bin', text)
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({a.name.split('.')[0] for a in node.names} & forbidden_imports)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], forbidden_imports)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, ('unlink', 'rmtree', 'remove'))
            if path.name != 'windows.py':
                self.assertNotIn('urllib', text)

    def test_diagnostic_output_contains_only_safe_facts(self):
        for value in diagnostics.CATALOG.values():
            self.assertNotRegex(value.text(), r'[a-fA-F0-9]{64}|[A-Za-z]:\\|/home/')

    def test_gui_module_contains_no_crypto_or_protocol(self):
        text = (Path(__file__).parent / 'gui.py').read_text()
        for word in ('hashlib', 'CryptUnprotectData', 'struct.unpack', 'AESGCM', '0xa6'):
            self.assertNotIn(word, text)


if __name__ == '__main__':
    unittest.main(verbosity=2)

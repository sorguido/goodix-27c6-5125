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
from . import backend, binding, capture, capture_session, diagnostics, windows, gui, files, capture_worker
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
    data[:4] = b'\x12\x01\x00\x02'
    data[7], data[17] = 64, 1
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


def pcap(rows, endian='<', stamps=None, nano=False):
    result = struct.pack(endian + 'IHHIIII', 0xa1b23c4d if nano else 0xa1b2c3d4, 2, 4, 0, 0, 65535, 249)
    for i, row in enumerate(rows):
        result += struct.pack(endian + 'IIII', *(stamps[i] if stamps else (10, i)), len(row), len(row)) + row
    return result


def block(kind, body):
    body += b'\0' * (-len(body) % 4)
    n = len(body) + 12
    return struct.pack('<II', kind, n) + body + struct.pack('<I', n)


def pcapng(rows, stamps=None):
    result = block(0x0a0d0d0a, struct.pack('<IHHq', 0x1a2b3c4d, 1, 0, -1))
    result += block(1, struct.pack('<HHI', 249, 0, 65535))
    for i, row in enumerate(rows):
        result += block(6, struct.pack('<IIIII', 0, *(stamps[i] if stamps else (0, i)), len(row), len(row)) + row)
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

    def test_nonmonotonic_classic_preserves_file_order_and_evidence(self):
        rows = records()
        stamps = [(20 - i, len(rows) - i) for i in range(len(rows))]
        for endian in ('<', '>'):
            for nano in (False, True):
                normal = capture.analyze_bytes(pcap(rows, endian, nano=nano))
                inverted = pcap(rows, endian, stamps, nano)
                self.assertEqual([raw for _, raw in capture.packets(inverted)], rows)
                result = capture.analyze_bytes(inverted)
                self.assertEqual(result.selected, normal.selected)
                self.assertEqual(result.codes, normal.codes)

    def test_nonmonotonic_pcapng_preserves_file_order_and_evidence(self):
        rows = records()
        # Both halves are unsigned fields; every 64-bit tick value is valid.
        stamps = [(0xffffffff if i % 2 == 0 else 0, 0xffffffff - i) for i in range(len(rows))]
        normal = capture.analyze_bytes(pcapng(rows))
        inverted = pcapng(rows, stamps)
        self.assertEqual([raw for _, raw in capture.packets(inverted)], rows)
        result = capture.analyze_bytes(inverted)
        self.assertEqual(result.selected, normal.selected)
        self.assertEqual(result.codes, normal.codes)

    def test_timestamp_field_bounds_and_truncated_encoding(self):
        rows = records()
        for endian in ('<', '>'):
            for nano, limit in ((False, 1000000), (True, 1000000000)):
                stamps = [(10, i) for i in range(len(rows))]
                stamps[0] = (0xffffffff, limit - 1)
                capture.analyze_bytes(pcap(rows, endian, stamps, nano)).require_complete()
                stamps[0] = (10, limit)
                self.fails(capture.BAD, capture.analyze_bytes, pcap(rows, endian, stamps, nano))
        # Truncated EPB timestamp (no complete fixed header), valid block envelope.
        self.fails(capture.BAD, capture.analyze_bytes,
                   pcapng([]) + block(6, struct.pack('<II', 0, 1)))

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


class Config90Tests(Case):
    def body(self):
        return fixture.synthetic_files()['target-config-90.bin']

    def evidence(self, payload, *, incoming=False, device=2, endpoint=None):
        rows = records(missing=('CONFIG90',))
        pair = transfer(payload, 100, incoming, device)
        if endpoint is not None:
            pair = [row[:21] + bytes([endpoint]) + row[22:] for row in pair]
        return capture.analyze_bytes(pcap(rows + pair))

    def test_wire_90_and_91_follow_logical_contract(self):
        for wire in (0x90, 0x91):
            payload = frame(wire, self.body())
            self.assertEqual(capture.parse_a0(payload)[:2], (wire, 0x90))
            e = self.evidence(payload)
            e.require_complete()
            self.assertEqual(e.selected['CONFIG90'], self.body())

    def test_unrelated_logical_controls_are_not_config(self):
        for wire in (0x8e, 0x8f, 0x92, 0x93, 0xa2):
            self.assertIn('CONFIG90_MISSING', self.evidence(frame(wire, self.body())).codes)

    def test_direction_endpoint_and_device_binding(self):
        for wire in (0x90, 0x91):
            for options in ({'incoming': True}, {'endpoint': 2}, {'device': 3}):
                self.assertIn('CONFIG90_MISSING', self.evidence(frame(wire, self.body()), **options).codes)

    def test_invalid_framing_and_checksum(self):
        for wire in (0x90, 0x91):
            for offset in (3, 5, -1):
                bad = bytearray(frame(wire, self.body())); bad[offset] ^= 1
                self.assertIn('CONFIG90_MISSING', self.evidence(bytes(bad)).codes)
            self.fails(capture.BAD, self.evidence, frame(wire, self.body())[:-1])

    def test_invalid_length_finalizer_and_layout(self):
        bad_finalizer = bytearray(self.body()); bad_finalizer[-1] ^= 1
        bad_layout = bytearray(self.body()); bad_layout[117] ^= 1; fixture.config_finalizer(bad_layout)
        for wire in (0x90, 0x91):
            for body in (self.body()[:-1], self.body() + b'\0', bytes(bad_finalizer), bytes(bad_layout)):
                self.assertIn('CONFIG90_MISSING', self.evidence(frame(wire, body)).codes)

    def test_identical_candidates_across_wire_variants(self):
        rows = records(missing=('CONFIG90',))
        for irp, wire in enumerate((0x90, 0x90, 0x91), 100):
            rows += transfer(frame(wire, self.body()), irp)
        capture.analyze_bytes(pcap(rows)).require_complete()

    def test_distinct_valid_bodies_are_ambiguous(self):
        changed = bytearray(self.body()); changed[0] ^= 1; fixture.config_finalizer(changed)
        self.assertTrue(capture.config_valid(changed))
        rows = records(missing=('CONFIG90',))
        rows += transfer(frame(0x90, self.body()), 100)
        rows += transfer(frame(0x91, bytes(changed)), 101)
        e = capture.analyze_bytes(pcap(rows))
        self.assertEqual(e.codes, ('CONFIG90_AMBIGUOUS',))
        self.fails('CONFIG90_AMBIGUOUS', e.require_complete)

    def test_unknown_enumeration_and_wire_90_complete_stream(self):
        rows = records(missing=('CONFIG90',))
        first = bytearray(rows[0]); struct.pack_into('<H', first, 19, 255)
        struct.pack_into('<H', first, 14, 11); rows[0] = bytes(first)
        rows += transfer(frame(0x90, self.body()), 100)
        for encode in (pcap, pcapng):
            capture.analyze_bytes(encode(rows)).require_complete()

    def test_unpaired_or_mismatched_usb_is_not_accepted(self):
        payload = frame(0x90, self.body())
        rows = records(missing=('CONFIG90',))
        self.fails(capture.BAD, capture.analyze_bytes, pcap(rows + [usb(payload, 100)]))
        pair = transfer(payload, 100)
        pair[1] = usb(b'', 100, info=1, device=3)
        self.fails(capture.BAD, capture.analyze_bytes, pcap(rows + pair))


class EnumerationTests(Case):
    def rows(self):
        # Reproduce metadata only: UNKNOWN submit, assigned completion, URB 11 -> 8.
        rows = records()
        first = bytearray(rows[0]); struct.pack_into('<H', first, 19, 255)
        struct.pack_into('<H', first, 14, 11)
        rows[0] = bytes(first)
        return rows

    def test_initial_descriptor_transition_accepts_complete_material(self):
        for encode in (pcap, pcapng):
            actual = capture.analyze_bytes(encode(self.rows()))
            expected = capture.analyze_bytes(encode(records()))
            self.assertEqual(actual.selected, expected.selected)
            actual.require_complete()

    def test_transition_metadata_near_misses_rejected(self):
        from dataclasses import replace
        req, done = [capture.decode(i, 0, r) for i, r in enumerate(self.rows()[:2])]
        for side, field, value in [(0, 'interface', 1), (0, 'bus', 2), (0, 'irp', 9),
                (0, 'device', 0), (0, 'device', 3), (1, 'device', 0), (1, 'device', 128),
                (1, 'device', 255), (0, 'transfer', 3), (1, 'transfer', 3),
                (0, 'stage', 3), (1, 'stage', 0), (1, 'status', 1),
                (0, 'endpoint', 0), (1, 'endpoint', 0x81), (0, 'info', 1), (1, 'info', 0)]:
            with self.subTest(side=side, field=field, value=value):
                pair = [req, done]; pair[side] = replace(pair[side], **{field: value})
                self.assertFalse(capture.enumeration_transition(*pair))
        for offset in range(8):
            body = bytearray(req.payload); body[offset] ^= 1
            self.assertFalse(capture.enumeration_transition(replace(req, payload=bytes(body)), done))
        for body in (done.payload[:-1], done.payload + b'\0', b'\0' * 18):
            self.assertFalse(capture.enumeration_transition(req, replace(done, payload=body)))
        for offset, value in ((0, 17), (1, 2), (7, 0), (17, 0)):
            body = bytearray(done.payload); body[offset] = value
            self.assertFalse(capture.enumeration_transition(req, replace(done, payload=bytes(body))))

    def test_parser_rejects_assigned_changes_wrong_target_and_late_transition(self):
        for side, offset, fmt, value in [(0, 19, '<H', 3), (1, 19, '<H', 0),
                (1, 19, '<H', 128), (1, 10, '<I', 1), (0, 21, '<B', 0x81),
                (0, 27, '<B', 3), (1, 29, '<B', 2), (0, 34, '<B', 64)]:
            rows = self.rows(); row = bytearray(rows[side]);struct.pack_into(fmt, row, offset, value);rows[side] = bytes(row)
            self.fails(capture.BAD, capture.analyze_bytes, pcap(rows))
        rows = self.rows(); row = bytearray(rows[1]);struct.pack_into('<H', row, 36, 0x1234);rows[1] = bytes(row)
        self.fails('TARGET_WRONG_IDENTITY', capture.analyze_bytes, pcap(rows))
        self.fails('TARGET_WRONG_IDENTITY', capture.analyze_bytes, pcap(records() + self.rows()[:2]))
        self.fails('TARGET_WRONG_IDENTITY', capture.analyze_bytes,
                   pcap(self.rows() + descriptor(99, device=3)))
        # Bulk pairing stays strict, including function equality.
        rows = self.rows(); row = bytearray(rows[3]);struct.pack_into('<H', row, 14, 11);rows[3] = bytes(row)
        self.fails(capture.BAD, capture.analyze_bytes, pcap(rows))


class LifecycleTests(Case):
    """Mock Win32 decisions and ownership; these do not qualify the native ABI."""
    def kernel_job(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 123
        with patch.object(capture_worker.ctypes, 'WinDLL', return_value=kernel, create=True):
            job = capture_worker.CaptureJob()
        return kernel, job

    def test_private_job_assignment_limits_and_quiescence(self):
        kernel, job = self.kernel_job()
        kernel.CreateJobObjectW.assert_called_once_with(None, None)
        limits = kernel.SetInformationJobObject.call_args.args[2]._obj
        self.assertEqual(limits.basic.flags, 0x2000)  # No breakaway, kill on owner close.
        job.assign(Mock(_handle=456))
        kernel.AssignProcessToJobObject.assert_called_once_with(123, 456)
        populations = iter([(3, 3), (3, 1), (3, 0)])
        def query(handle, kind, data, size, returned):
            self.assertEqual((handle, kind), (123, 1))
            data._obj.total, data._obj.active = next(populations)
            return 1
        kernel.QueryInformationJobObject.side_effect = query
        self.assertEqual(job.population(), (3, 3))
        with patch.object(capture_worker.time, 'sleep') as sleep:
            job.terminate()
        kernel.TerminateJobObject.assert_called_once_with(123, capture_worker.STOP_EXIT_CODE)
        sleep.assert_called_once_with(0.025)
        job.close()
        kernel.CloseHandle.assert_called_once_with(123)
        self.assertIsNone(job.handle)
        # Operations target only the created job/known process, with no global scan.
        self.assertEqual({call[0] for call in kernel.method_calls},
                         {'CreateJobObjectW', 'SetInformationJobObject', 'AssignProcessToJobObject',
                          'QueryInformationJobObject', 'TerminateJobObject', 'CloseHandle'})

    def test_job_pins_only_two_native_members_and_waits_for_both_handles(self):
        for mode in ('valid', 'wrong_image', 'access_denied', 'missing_helper', 'duplicate',
                     'overflow', 'query_error', 'wait_timeout', 'wait_error'):
            with self.subTest(mode=mode):
                kernel, job = self.kernel_job()
                stopped = False
                def query(handle, kind, data, size, returned):
                    self.assertEqual(handle, 123)
                    if kind == 1:
                        data._obj.total, data._obj.active = 3, 0 if stopped else 3
                    else:
                        self.assertEqual(kind, 3)
                        if mode == 'query_error': return 0
                        data._obj.assigned, data._obj.count = (4 if mode == 'overflow' else 3), 3
                        ids = [101 if mode == 'missing_helper' else 100, 200,
                               200 if mode == 'duplicate' else 300]
                        for i, pid in enumerate(ids): data._obj.ids[i] = pid
                    return 1
                def open_process(rights, inherit, pid):
                    self.assertEqual((rights, inherit), (0x101000, False))
                    self.assertIn(pid, (200, 300))
                    return 0 if mode == 'access_denied' else pid + 500
                def image_name(handle, flags, name, length):
                    self.assertIn(handle, (700, 800)); self.assertEqual(flags, 0)
                    name.value = '/synthetic/' + ('conhost.exe' if mode == 'wrong_image' else 'USBPcapCMD.exe')
                    return 1
                def terminate(handle, code):
                    nonlocal stopped
                    self.assertEqual((handle, code), (123, capture_worker.STOP_EXIT_CODE))
                    stopped = True
                    return 1
                def wait(handle, milliseconds):
                    self.assertTrue(stopped); self.assertIn(handle, (700, 800))
                    self.assertTrue(0 <= milliseconds <= 5000)
                    return 258 if mode == 'wait_timeout' else 0xffffffff if mode == 'wait_error' else 0
                kernel.QueryInformationJobObject.side_effect = query
                kernel.OpenProcess.side_effect = open_process
                kernel.QueryFullProcessImageNameW.side_effect = image_name
                kernel.TerminateJobObject.side_effect = terminate
                kernel.WaitForSingleObject.side_effect = wait
                if mode in ('valid', 'wait_timeout', 'wait_error'):
                    job.verify_members(100, Path('/synthetic/USBPcapCMD.exe'))
                    self.assertEqual(job.members, [700, 800])
                    if mode == 'valid':
                        job.terminate()
                        self.assertEqual(kernel.WaitForSingleObject.call_count, 2)
                    else: self.fails('CAPTURE_PROCESS_FAILED', job.terminate)
                else: self.fails('CAPTURE_PROCESS_FAILED', job.verify_members, 100, Path('/synthetic/USBPcapCMD.exe'))
                held = job.members.copy()
                job.close()
                self.assertEqual([c.args[0] for c in kernel.CloseHandle.call_args_list], held + [123])

    def test_job_api_errors_and_cleanup_timeout_fail_closed(self):
        for failing in ('AssignProcessToJobObject', 'QueryInformationJobObject', 'TerminateJobObject'):
            kernel, job = self.kernel_job()
            getattr(kernel, failing).return_value = 0
            call = {'AssignProcessToJobObject': lambda: job.assign(Mock(_handle=456)),
                    'QueryInformationJobObject': job.population, 'TerminateJobObject': job.terminate}[failing]
            self.fails('CAPTURE_PROCESS_FAILED', call)
            job.close()
        kernel, job = self.kernel_job()
        with patch.object(job, 'population', return_value=(3, 1)), \
                patch.object(capture_worker.time, 'monotonic', side_effect=[0, 6]):
            self.fails('CAPTURE_PROCESS_FAILED', job.terminate)
        job.close()
        kernel.CloseHandle.assert_called_once_with(123)

    def test_job_limit_failure_closes_noninherited_handle(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 123
        kernel.SetInformationJobObject.return_value = 0
        with patch.object(capture_worker.ctypes, 'WinDLL', return_value=kernel, create=True):
            self.fails('CAPTURE_PROCESS_FAILED', capture_worker.CaptureJob)
        kernel.CloseHandle.assert_called_once_with(123)
        kernel.AssignProcessToJobObject.assert_not_called()

    def test_intentional_exit_marker_distinguishes_early_crash_and_native_exits(self):
        marker = capture_worker.STOP_EXIT_CODE
        for before, api, result, success in [(None, 1, marker, True),
                (0, 1, marker, False), (1, 1, marker, False), (7, 1, marker, False),
                (None, 0, marker, False), (None, 1, 0, False), (None, 1, 1, False),
                (None, 1, subprocess.TimeoutExpired('synthetic', 5), False)]:
            with self.subTest(before=before, api=api, result=result):
                kernel, process = Mock(), Mock(_handle=456)
                kernel.TerminateProcess.return_value = api
                process.poll.return_value = before
                if isinstance(result, Exception): process.wait.side_effect = result
                else: process.wait.return_value = result
                with patch.object(capture_worker.ctypes, 'WinDLL', return_value=kernel, create=True), \
                        patch.object(capture_worker, 'report') as report:
                    if success: capture_worker.intentional_stop(process)
                    else: self.fails('CAPTURE_PROCESS_FAILED', capture_worker.intentional_stop, process)
                stages = [call.args[0] for call in report.call_args_list]
                self.assertEqual('RELAY_TERMINATED' in stages, success)
                if before is not None: kernel.TerminateProcess.assert_not_called()
                else: kernel.TerminateProcess.assert_called_once_with(456, marker)
                if before is None and api: process.wait.assert_called_once_with(timeout=5)
                self.assertTrue(all(diagnostics.safe_lifecycle_status(s) for s in stages))

    def test_worker_raw_only_launch_retains_output_on_success_and_failure(self):
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                raw = create_run(Path(tmp)) / 'raw/oem-init.pcap'
                console, stop, received = io.BytesIO(), Mock(), Mock()
                stop.wait.side_effect = [False, True]
                received.is_set.return_value = True
                process = Mock()
                process.poll.return_value = None
                recording = pcap(records())
                def launch(args, **kwargs):
                    self.assertEqual(args, ['synthetic.exe', '-d', r'\\.\USBPcap1',
                                          '--capture-from-new-devices', '-s', '65535', '-o', '-'])
                    self.assertEqual(set(kwargs), {'stdin', 'stdout', 'stderr', 'close_fds'})
                    self.assertIs(kwargs['stdin'], console)
                    self.assertEqual(Path(kwargs['stdout'].name), raw)
                    self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
                    self.assertTrue(kwargs['close_fds'])
                    kwargs['stdout'].write(recording)
                    return process
                def open_capture(path, *args, **kwargs):
                    return console if path == 'CONIN$' else open(path, *args, **kwargs)
                with patch.object(capture_worker, 'normal_user') as normal, \
                        patch.object(capture_worker, 'read_command', return_value=(True, b'START\n')) as command, \
                        patch.object(capture_worker, 'real_path'), \
                        patch.object(capture_worker, 'open', open_capture, create=True), \
                        patch.object(capture_worker.threading, 'Thread'), \
                        patch.object(capture_worker.threading, 'Event', side_effect=[stop, received]), \
                        patch.object(capture_worker.subprocess, 'Popen', side_effect=launch), \
                        patch.object(capture_worker, 'intentional_stop',
                                     side_effect=Failure('CAPTURE_PROCESS_FAILED') if failure else None) as terminate, \
                        patch.object(capture_worker, 'report') as report:
                    if failure: self.fails('CAPTURE_PROCESS_FAILED', capture_worker.capture,
                                           Path('synthetic.exe'), r'\\.\USBPcap1', raw)
                    else: capture_worker.capture(Path('synthetic.exe'), r'\\.\USBPcap1', raw)
                command.assert_called_once_with(b'START')
                normal.assert_called_once(); terminate.assert_called_once_with(process)
                self.assertEqual(raw.read_bytes(), recording)
                self.assertTrue(console.closed)
                self.assertIn('READY', [call.args[0] for call in report.call_args_list])

    def test_start_handshake_is_required_before_native_launch(self):
        from types import SimpleNamespace
        for command in (b'', b'STOP\n', b'START', b'private path\n'):
            with patch.object(capture_worker, 'normal_user'), \
                    patch.object(capture_worker.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(command))), \
                    patch.object(capture_worker.subprocess, 'Popen') as launch:
                self.fails('CAPTURE_PROCESS_FAILED', capture_worker.capture,
                           Path('synthetic.exe'), r'\\.\USBPcap1', Path('unused'))
                launch.assert_not_called()
        for command in (b'START\n', b'START\r\n'):
            with patch.object(capture_worker.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(command))):
                self.assertTrue(capture_worker.read_command(b'START')[0])

    def test_stop_control_eof_is_not_explicit_stop_and_broken_status_signals_stop(self):
        from types import SimpleNamespace
        for raw, expected in [(b'STOP\n', 'STOP_RECEIVED'), (b'STOP\r\n', 'STOP_RECEIVED'),
                              (b'', 'CONTROL_EOF'), (b'junk\n', 'CONTROL_INVALID'),
                              (b'STOP', 'CONTROL_INVALID'), (b'STOP \n', 'CONTROL_INVALID')]:
            stop, received = threading.Event(), threading.Event()
            with patch.object(capture_worker.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(raw))), \
                    patch.object(capture_worker, 'report') as report:
                capture_worker.stop_request(stop, received)
            self.assertTrue(stop.is_set())
            self.assertEqual(received.is_set(), expected == 'STOP_RECEIVED')
            report.assert_called_once_with(expected)
        stop, received = threading.Event(), threading.Event()
        with patch.object(capture_worker.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'STOP\n'))), \
                patch.object(capture_worker, 'report', side_effect=BrokenPipeError):
            with self.assertRaises(BrokenPipeError): capture_worker.stop_request(stop, received)
        self.assertTrue(stop.is_set()); self.assertTrue(received.is_set())

    def owner(self, raw, code=0):
        owner = capture_session.CaptureProcess(Path('synthetic.exe'), r'\\.\USBPcap1', raw)
        process, job = Mock(returncode=None), Mock()
        process.poll.side_effect = lambda: process.returncode
        def wait(timeout):
            process.returncode = code
            return code
        process.wait.side_effect = wait
        process.stdin.closed = False
        job.population.return_value = (3, 3)
        owner.process, owner.job = process, job
        owner.assigned = owner.ready = True
        owner.events.put('RELAY_TERMINATED'); owner.events.put('EOF')
        return owner, process, job

    def test_parent_flush_only_after_whole_scope_quiescence_and_worker_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = create_run(Path(tmp)) / 'raw/oem-init.pcap'; raw.write_bytes(pcap(records()))
            original = raw.read_bytes()
            owner, process, job = self.owner(raw)
            def flush(fd):
                job.terminate.assert_called_once()
                self.assertEqual(process.returncode, 0)
                self.assertIn('SCOPE_QUIESCENT', owner.trace)
            with patch.object(capture_session, 'os', Mock(wraps=os, fsync=Mock(side_effect=flush))) as raw_os:
                owner.stop()
            raw_os.fsync.assert_called_once(); job.close.assert_called_once()
            process.terminate.assert_not_called()
            self.assertEqual(raw.read_bytes(), original)
            trace = (raw.parent.parent / 'diagnostics/lifecycle.txt').read_text().splitlines()
            self.assertLess(trace.index('SCOPE_QUIESCENT'), trace.index('RAW_FLUSH'))
            self.assertLess(trace.index('RAW_FLUSHED'), trace.index('STOPPED'))
            self.assertIsNone(owner.job); self.assertIsNone(owner.process)

    def test_parent_failures_never_flush_or_accept_even_valid_raw(self):
        for failure in ('early_exit', 'missing_member', 'extra_member', 'worker_nonzero',
                        'worker_timeout', 'scope_timeout', 'scope_error', 'control_write', 'control_close',
                        'status_failed', 'no_relay_marker', 'no_eof'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                raw = create_run(Path(tmp)) / 'raw/oem-init.pcap'; raw.write_bytes(pcap(records()))
                original = raw.read_bytes()
                owner, process, job = self.owner(raw, code=1 if failure == 'worker_nonzero' else 0)
                if failure == 'early_exit': process.returncode = 1
                if failure == 'missing_member': job.population.return_value = (3, 2)
                if failure == 'extra_member': job.population.return_value = (4, 4)
                if failure == 'worker_timeout': process.wait.side_effect = [subprocess.TimeoutExpired('synthetic', 10), 0]
                if failure.startswith('scope_'): job.terminate.side_effect = Failure('CAPTURE_PROCESS_FAILED')
                if failure == 'control_write': process.stdin.write.side_effect = BrokenPipeError('private')
                if failure == 'control_close': process.stdin.close.side_effect = BrokenPipeError('private')
                if failure in ('status_failed', 'no_relay_marker', 'no_eof'):
                    owner.events = __import__('queue').Queue()
                    if failure != 'no_relay_marker': owner.events.put('RELAY_TERMINATED')
                    if failure == 'status_failed': owner.events.put('FAILED')
                    if failure != 'no_eof': owner.events.put('EOF')
                with contextlib.ExitStack() as stack:
                    raw_os = stack.enter_context(patch.object(capture_session, 'os', Mock(wraps=os)))
                    fsync = raw_os.fsync
                    if failure == 'no_eof':
                        stack.enter_context(patch.object(capture_session.time, 'monotonic', side_effect=[0, 0, 3]))
                    self.fails('CAPTURE_PROCESS_FAILED', owner.stop)
                fsync.assert_not_called(); job.terminate.assert_called_once(); job.close.assert_called_once()
                self.assertEqual(raw.read_bytes(), original)
                trace = (raw.parent.parent / 'diagnostics/lifecycle.txt').read_text()
                self.assertNotIn('STOPPED', trace); self.assertNotIn('private', trace)
                self.assertIsNone(owner.process); self.assertIsNone(owner.job)

    def test_flush_failure_or_file_growth_prevents_success(self):
        for mode in ('error', 'growth'):
            with tempfile.TemporaryDirectory() as tmp:
                raw = create_run(Path(tmp)) / 'raw/oem-init.pcap'; raw.write_bytes(pcap(records()))
                owner, process, job = self.owner(raw)
                def flush(fd):
                    if mode == 'error': raise OSError('private path')
                    with raw.open('ab') as extra: extra.write(b'bad')
                with patch.object(capture_session, 'os', Mock(wraps=os, fsync=Mock(side_effect=flush))):
                    self.fails('CAPTURE_PROCESS_FAILED', owner.stop)
                self.assertTrue(raw.exists())
                self.assertNotIn('STOPPED', owner.trace)
                job.terminate.assert_called_once(); job.close.assert_called_once()

    def test_parent_assignment_precedes_start_and_checks_pinned_scope(self):
        for population, assign_error in [((3, 3), False), ((2, 2), False), ((4, 4), False), ((3, 3), True)]:
            with self.subTest(population=population, assign_error=assign_error), tempfile.TemporaryDirectory() as tmp:
                raw = create_run(Path(tmp)) / 'raw/oem-init.pcap'; raw.write_bytes(pcap([]))
                owner, process, job = self.owner(raw)
                owner.ready = owner.assigned = False
                owner.events = __import__('queue').Queue()
                process.stdout = io.StringIO('STARTING\nREADY\nRELAY_TERMINATED\n')
                job.population.return_value = population
                if population != (3, 3): job.verify_members.side_effect = Failure('CAPTURE_PROCESS_FAILED')
                if assign_error: job.assign.side_effect = Failure('CAPTURE_PROCESS_FAILED')
                def send(command):
                    self.assertTrue(owner.assigned)
                    job.assign.assert_called_once_with(process)
                process.stdin.write.side_effect = send
                with patch.object(capture_session, 'CaptureJob', return_value=job), \
                        patch.object(capture_session.subprocess, 'STARTUPINFO', return_value=Mock(dwFlags=0), create=True), \
                        patch.multiple(capture_session.subprocess, create=True, CREATE_NEW_CONSOLE=16, STARTF_USESHOWWINDOW=1), \
                        patch.object(capture_session.subprocess, 'Popen', return_value=process):
                    if population == (3, 3) and not assign_error:
                        owner.start(threading.Event()); self.assertTrue(owner.alive()); owner.stop()
                    else:
                        self.fails('CAPTURE_PROCESS_FAILED', owner.start, threading.Event())
                        self.fails('CAPTURE_PROCESS_FAILED', owner.stop)
                if assign_error:
                    process.stdin.write.assert_not_called(); process.terminate.assert_called_once()
                    self.assertTrue(process.stdout.closed)
                else: process.terminate.assert_not_called()
                job.terminate.assert_called_once(); job.close.assert_called_once()

    def test_status_reader_bounds_and_rejects_untrusted_output(self):
        for output in ('READY\nprotected arbitrary text\n', 'READY\n' + 'STARTING\n' * 70,
                       'READY\n' + 'x' * 100 + '\n'):
            with tempfile.TemporaryDirectory() as tmp:
                raw = create_run(Path(tmp)) / 'raw/oem-init.pcap'; raw.write_bytes(pcap(records()))
                owner, process, job = self.owner(raw)
                owner.events = __import__('queue').Queue()
                process.stdout = io.StringIO(output)
                with patch.object(capture_session, 'CaptureJob', return_value=job), \
                        patch.object(capture_session.subprocess, 'STARTUPINFO', return_value=Mock(dwFlags=0), create=True), \
                        patch.multiple(capture_session.subprocess, create=True, CREATE_NEW_CONSOLE=16, STARTF_USESHOWWINDOW=1), \
                        patch.object(capture_session.subprocess, 'Popen', return_value=process), \
                        patch.object(capture_session.time, 'monotonic', side_effect=[0, 0, 0, 3]):
                    owner.start(threading.Event())
                    self.fails('CAPTURE_PROCESS_FAILED', owner.stop)
                text = (raw.parent.parent / 'diagnostics/lifecycle.txt').read_text()
                self.assertLessEqual(len(text.splitlines()), 64)
                self.assertTrue(all(diagnostics.safe_lifecycle_status(v) for v in text.splitlines()))
                self.assertNotIn('protected', text)
                self.assertTrue(raw.exists())

    def test_status_vocabulary_rejects_old_probes_paths_payloads_and_unbounded_values(self):
        for text in ('C:\\private\\secret', 'payload=abcd', 'CHILD_EXIT=0 extra',
                     'CHILD_EXIT=4294967296', 'WORKER_EXIT=-2147483649', 'hash=' + 'a' * 64,
                     'Q_INJECTED', 'CHILD_CONSOLE_SHARED', 'CONSOLE_Q_PENDING', 'LAUNCH_STDERR_UNKNOWN'):
            self.assertFalse(diagnostics.safe_lifecycle_status(text))
        for text in ('CHILD_EXIT=0', 'WORKER_EXIT=-1', 'CHILD_EXIT=4294967295',
                     'STOP_REASON_BUILDER_BOUNDED_TERMINATION', 'SCOPE_QUIESCENT'):
            self.assertTrue(diagnostics.safe_lifecycle_status(text))


class SnapshotTests(Case):
    def info(self, **changes):
        from types import SimpleNamespace
        fields = dict(st_dev=1, st_ino=2, st_nlink=1, st_size=4,
                      st_mtime_ns=100, st_ctime_ns=200, st_mode=0o100600,
                      st_file_attributes=0x20)
        fields.update(changes)
        return SimpleNamespace(**fields)

    def snapshot(self, *, first=None, last=None, current=None, data=b'data', maximum=4, platform='nt'):
        import ctypes
        from types import SimpleNamespace
        first = first or self.info()
        last = last or first
        current = current or first
        path = Mock()
        path.lstat.return_value = current
        stream = Mock()
        stream.read.return_value = data
        stream.fileno.return_value = 123
        manager = Mock()
        manager.__enter__ = Mock(return_value=stream)
        manager.__exit__ = Mock(return_value=False)
        native_os = Mock(wraps=os)
        native_os.name = platform
        native_os.O_RDONLY = os.O_RDONLY
        native_os.O_NOFOLLOW = getattr(os, 'O_NOFOLLOW', 0)
        native_os.O_NONBLOCK = getattr(os, 'O_NONBLOCK', 0)
        native_os.O_BINARY = 0
        native_os.open.return_value = 123
        native_os.fdopen.return_value = manager
        native_os.fstat.side_effect = [first, last]
        kernel = Mock()
        kernel.CreateFileW.return_value = 456
        crt = SimpleNamespace(open_osfhandle=Mock(return_value=123))
        with patch.object(files, 'os', native_os), patch.object(files, 'real_path', return_value=path), \
                patch.object(ctypes, 'WinDLL', return_value=kernel, create=True), \
                patch.dict('sys.modules', {'msvcrt': crt}):
            return files.read_regular(path, maximum)

    def test_windows_cross_api_ctime_difference_is_accepted(self):
        self.assertEqual(self.snapshot(current=self.info(st_ctime_ns=999)), b'data')
        # Ordinary archive/read-only bits are not identity or reparse failures.
        self.assertEqual(self.snapshot(current=self.info(st_ctime_ns=999, st_file_attributes=1)), b'data')

    def test_windows_path_identity_changes_are_rejected(self):
        for field, value in [('st_dev', 9), ('st_ino', 9), ('st_nlink', 2),
                             ('st_size', 5), ('st_mtime_ns', 101)]:
            with self.subTest(field=field):
                self.fails('SOURCE_UNSAFE', self.snapshot,
                           current=self.info(st_ctime_ns=999, **{field: value}))

    def test_same_handle_mutation_including_ctime_is_rejected(self):
        for field, value in [('st_dev', 9), ('st_ino', 9), ('st_nlink', 2),
                             ('st_size', 5), ('st_mtime_ns', 101), ('st_ctime_ns', 201)]:
            with self.subTest(field=field):
                self.fails('SOURCE_UNSAFE', self.snapshot, last=self.info(**{field: value}))

    def test_windows_path_symlink_reparse_and_nonregular_are_rejected(self):
        for changes in ({'st_mode': 0o120777}, {'st_file_attributes': 0x400},
                        {'st_mode': 0o010600}, {'st_mode': 0o040700}):
            with self.subTest(changes=changes):
                self.fails('SOURCE_UNSAFE', self.snapshot, current=self.info(**changes))

    def test_unsafe_handle_metadata_is_rejected(self):
        for changes in ({'st_mode': 0o120777}, {'st_file_attributes': 0x400},
                        {'st_mode': 0o010600}, {'st_nlink': 0}, {'st_nlink': 2}):
            with self.subTest(changes=changes):
                self.fails('SOURCE_UNSAFE', self.snapshot, first=self.info(**changes))

    def test_short_oversized_and_empty_reads_are_rejected(self):
        self.fails('SOURCE_UNSAFE', self.snapshot, data=b'dat')
        self.fails('SOURCE_UNSAFE', self.snapshot, data=b'data!')
        self.fails('SOURCE_UNSAFE', self.snapshot, maximum=3)
        self.fails('SOURCE_UNSAFE', self.snapshot, first=self.info(st_size=0), data=b'')

    def test_posix_retains_strict_cross_api_and_handle_ctime(self):
        self.assertEqual(self.snapshot(platform='posix'), b'data')
        self.fails('SOURCE_UNSAFE', self.snapshot, platform='posix', current=self.info(st_ctime_ns=999))
        self.fails('SOURCE_UNSAFE', self.snapshot, platform='posix', last=self.info(st_ctime_ns=999))


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
    def test_bounded_acquisition_validates_only_after_quiescence_flush_and_close(self):
        for outcome in ('valid', 'truncated', 'scope_failure', 'early_exit', 'cancel_stop', 'cancel_analysis'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                root, cancel = Path(tmp), threading.Event()
                (root / 'runs').mkdir()
                state = {'empty': False, 'flushed': False}
                recording = pcap(records())
                if outcome == 'truncated': recording = recording[:-1]
                process, job = Mock(returncode=None), Mock()
                process.poll.side_effect = lambda: process.returncode
                process.stdout = io.StringIO('STARTING\nREADY\nSTOP_RECEIVED\n'
                    'STOP_REASON_BUILDER_BOUNDED_TERMINATION\nRELAY_TERMINATED\n')
                def launch(args, **kwargs):
                    Path(args[-1]).write_bytes(recording)
                    self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
                    self.assertEqual(kwargs['stdin'], subprocess.PIPE)
                    return process
                def wait(timeout):
                    process.returncode = 0
                    if outcome == 'cancel_stop': cancel.set()
                    return 0
                process.wait.side_effect = wait
                job.population.return_value = (3, 3)
                def terminate():
                    if outcome == 'scope_failure': raise Failure('CAPTURE_PROCESS_FAILED')
                    state['empty'] = True
                job.terminate.side_effect = terminate
                def flush(fd):
                    self.assertTrue(state['empty'])
                    state['flushed'] = True
                    os.fsync(fd)
                def analyze(raw):
                    self.assertTrue(state['empty'] and state['flushed'])
                    self.assertEqual(raw.read_bytes(), recording)
                    if outcome == 'cancel_analysis': cancel.set()
                    return capture.analyze(raw)
                def update(stage, value):
                    if stage == 'SETTLING' and outcome == 'early_exit': process.returncode = 1
                now = iter(range(0, 1000, 10))
                prereq = windows.Prerequisites(Path('synthetic'), True, windows.VERSION, (r'\\.\USBPcap1',), False)
                with patch.object(windows, 'target_count', side_effect=[0, 0, 1, 1, 1]), \
                        patch.object(capture_session, 'CaptureJob', return_value=job), \
                        patch.object(capture_session.subprocess, 'STARTUPINFO', return_value=Mock(dwFlags=0), create=True), \
                        patch.multiple(capture_session.subprocess, create=True, CREATE_NEW_CONSOLE=16, STARTF_USESHOWWINDOW=1), \
                        patch.object(capture_session.subprocess, 'Popen', side_effect=launch), \
                        patch.object(capture_session, 'os', Mock(wraps=os, fsync=Mock(side_effect=flush))), \
                        patch.object(capture_session, 'analyze', side_effect=analyze) as parser:
                    args = (root, prereq, None, False, cancel, update)
                    kwargs = dict(clock=lambda: next(now), pause=lambda _: None)
                    if outcome == 'valid':
                        run, evidence = capture_session.acquire(*args, **kwargs)
                        evidence.require_complete()
                    else:
                        code = (capture.BAD if outcome == 'truncated' else
                                'CAPTURE_CANCELLED' if outcome.startswith('cancel') else 'CAPTURE_PROCESS_FAILED')
                        self.fails(code, capture_session.acquire, *args, **kwargs)
                self.assertEqual(parser.call_count, int(outcome in ('valid', 'truncated', 'cancel_analysis')))
                job.terminate.assert_called_once(); job.close.assert_called_once()
                raw = next(root.glob('runs/*/raw/oem-init.pcap'))
                self.assertEqual(raw.read_bytes(), recording)
                self.assertFalse(list(root.glob('runs/*/goodix-5125-materials')))

    def test_cancel_after_ready_with_reader_detached_stops_without_analysis(self):
        for stop_failed in (False, True):
            with self.subTest(stop_failed=stop_failed), tempfile.TemporaryDirectory() as tmp:
                root, cancel, stages = Path(tmp), threading.Event(), []
                (root / 'runs').mkdir()
                process = Mock()
                process.alive.return_value = True
                if stop_failed: process.stop.side_effect = Failure('CAPTURE_PROCESS_FAILED')
                def factory(exe, interface, raw):
                    process.start.side_effect = lambda _: raw.write_bytes(pcap([]))
                    return process
                def update(stage, value):
                    stages.append(stage)
                    if stage == 'ATTACH': cancel.set()
                prereq = windows.Prerequisites(Path('synthetic'), True, windows.VERSION, (r'\\.\USBPcap1',), False)
                with patch.object(windows, 'target_count', return_value=0), \
                        patch.object(capture_session, 'analyze') as analyze:
                    self.fails('CAPTURE_CANCELLED', capture_session.acquire,
                               root, prereq, None, False, cancel, update, process_type=factory)
                process.start.assert_called_once(); process.stop.assert_called_once()
                analyze.assert_not_called()
                self.assertEqual(stages, ['RUN', 'STARTING', 'ATTACH'])
                self.assertEqual(next(root.glob('runs/*/raw/oem-init.pcap')).read_bytes(), pcap([]))
                # Cancellation alone cannot prove the child stopped cleanly.
                self.assertIn('CAPTURE_CANCELLED', next(root.glob('runs/*/diagnostics/result.txt')).read_text())

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


class CorrectiveTests(Case):
    def app(self):
        app = object.__new__(gui.App)
        app.busy = False
        app.settle_seconds = capture_session.SETTLE_SECONDS
        app.clear = Mock(); app.label = Mock(); app.button = Mock()
        app.preflight = Mock()
        app.panel = None
        app.sources = backend.Sources(b'', fixture.synthetic_files()['fdt-cache.bin'], b'')
        return app

    def test_gui_extended_choice_is_explicit_and_has_no_third_tier(self):
        app = self.app()
        evidence = capture.analyze_bytes(pcap(records(missing=('A2',))))
        with patch.object(gui, 'ScrolledText'):
            app.diagnose((Path('synthetic-run'), evidence))
        app.clear.assert_called_once_with('Capture incomplete')
        callbacks = {call.args[0]: call.args[1] for call in app.button.call_args_list}
        self.assertNotIn('Build private bundle', callbacks)
        self.assertIn('Retry with extended initialization window', callbacks)
        app.preflight.assert_not_called()
        callbacks['Retry with extended initialization window']()
        self.assertEqual(app.settle_seconds, 60)
        app.preflight.assert_called_once_with()
        app.button.reset_mock()
        with patch.object(gui, 'ScrolledText'):
            app.diagnose((Path('synthetic-second-run'), evidence))
        self.assertNotIn('Retry with extended initialization window',
                         [c.args[0] for c in app.button.call_args_list])
        app.retry_extended()
        app.preflight.assert_called_once_with()
        app.retry_default()
        self.assertEqual(app.settle_seconds, 30)

    def test_only_missing_evidence_is_eligible(self):
        for name in ('A2', 'CHIP82', 'A6'):
            evidence = capture.analyze_bytes(pcap(records(missing=(name,))))
            self.assertTrue(capture_session.can_extend(evidence, 30))
            self.assertFalse(capture_session.can_extend(evidence, 60))
        for code in diagnostics.CATALOG:
            if code in capture_session.MISSING_CODES:
                continue
            self.assertFalse(capture_session.can_extend(capture.Evidence(codes=(code,)), 30))
            self.assertFalse(capture_session.can_extend(
                capture.Evidence(codes=('CONFIG90_MISSING', code)), 30))
        self.assertFalse(capture_session.can_extend(capture.analyze_bytes(pcap(records())), 30))
        app = self.app()
        ambiguous = capture.analyze_bytes(pcap(records(
            missing=('CONFIG90',), extras=[('extra', 0xa2, b'abc', True)])))
        with patch.object(gui, 'ScrolledText'):
            app.diagnose((Path('synthetic-run'), ambiguous))
        self.assertNotIn('Retry with extended initialization window', [c.args[0] for c in app.button.call_args_list])
        for code in ('TARGET_WRONG_IDENTITY', capture.BAD, 'A6_FDT_MISMATCH',
                     'DPAPI_RECOVERY_FAILED', 'DLL_NOT_QUALIFIED'):
            app.run = app.storage = None
            app.button.reset_mock()
            app.failure(code)
            self.assertNotIn('Retry with extended initialization window', [c.args[0] for c in app.button.call_args_list])

    def test_config90_missing_stops_without_timing_retry(self):
        for missing in [('CONFIG90',), ('CONFIG90', 'A2')]:
            evidence = capture.analyze_bytes(pcap(records(missing=missing)))
            self.assertFalse(capture_session.can_extend(evidence, 30))
            app = self.app()
            with patch.object(gui, 'ScrolledText'):
                app.diagnose((Path('synthetic-run'), evidence))
            labels = [c.args[0] for c in app.button.call_args_list]
            self.assertNotIn('Retry with extended initialization window', labels)
            self.assertNotIn('Recheck for a new default capture', labels)
        self.assertIn('Stop and retain', diagnostics.CATALOG['CONFIG90_MISSING'].action)

    def test_missing_config_with_known_a6_mismatch_has_no_extended_retry(self):
        app = self.app()
        app.failure = Mock()
        evidence = capture.analyze_bytes(pcap(records(missing=('CONFIG90',), variant=2)))
        with patch.object(gui, 'ScrolledText'):
            app.diagnose((Path('synthetic-run'), evidence))
        app.failure.assert_called_once_with('A6_FDT_MISMATCH')
        self.assertNotIn('Retry with extended initialization window', [c.args[0] for c in app.button.call_args_list])

    def test_default_and_extended_runs_keep_both_raws_and_gates(self):
        recording = pcap(records(missing=('CONFIG90',)))
        starts, updates = [], []
        class Process:
            def __init__(self, exe, interface, path): self.path = path
            def start(self, cancel):
                starts.append(self.path)
                self.path.write_bytes(recording)
            def alive(self): return True
            def stop(self): pass
        prereq = windows.Prerequisites(Path('synthetic'), True, windows.VERSION, ('\\\\.\\USBPcap1',), False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'runs').mkdir()
            results = []
            for seconds in (30, 60):
                now = [0.0]
                def pause(value): now[0] += value
                def update(event, value): updates.append((event, value, now[0]))
                with patch.object(windows, 'target_count', side_effect=[0, 0] + [1] * 130) as count:
                    kwargs = {} if seconds == 30 else {'settle_seconds': seconds}
                    results.append(capture_session.acquire(root, prereq, None, False, threading.Event(), update,
                        process_type=Process, clock=lambda: now[0], pause=pause, **kwargs))
                    self.assertGreater(count.call_count, 2)
                self.assertEqual(now[0], seconds)
                self.assertEqual(len(starts), len(results))  # no automatic retry
            self.assertNotEqual(results[0][0], results[1][0])
            self.assertEqual([p.read_bytes() for p in starts], [recording, recording])
            self.assertEqual([v for event, v, _ in updates if event == 'SETTLING'], [30, 60])
            self.assertEqual([event for event, _, _ in updates],
                             ['RUN', 'STARTING', 'ATTACH', 'SETTLING', 'ANALYZING'] * 2)
            with patch.object(windows, 'target_count', return_value=1):
                self.fails('TARGET_PRESENT_BEFORE_CAPTURE', capture_session.acquire,
                    root, prereq, None, False, threading.Event(), update, process_type=Process, settle_seconds=60)
            self.fails('CAPTURE_PROCESS_FAILED', capture_session.acquire,
                root, prereq, None, False, threading.Event(), update, process_type=Process, settle_seconds=120)
            self.assertEqual(len(list((root / 'runs').iterdir())), 2)

    def test_gui_passes_selected_interval_and_labels_it(self):
        app = self.app()
        app.choice = Mock(); app.mapped = Mock(); app.cancel = threading.Event()
        app.events = Mock(); app.storage = Path('synthetic'); app.prerequisites = Mock()
        app.work = lambda function, done, *args: function()
        for seconds in (30, 60):
            app.settle_seconds = seconds
            with patch.object(capture_session, 'acquire') as acquire:
                app.start_capture()
                self.assertEqual(acquire.call_args.kwargs['settle_seconds'], seconds)
            app.status_label = Mock()
            app.capture_status('SETTLING')
            self.assertIn(str(seconds), app.status_label.configure.call_args.kwargs['text'])

    def test_installer_guidance_preserves_upstream_choices(self):
        root = Path(__file__).parent
        for name in ('gui.py', 'README.md', 'AUDIT.md'):
            text = (root / name).read_text()
            self.assertNotRegex(text.lower(), r'leave[^.]*unchecked|disable[^.]*detect usb|detect usb[^.]*disabled')
        app = self.app()
        app.storage = Path('synthetic'); app.work = Mock()
        app.install()
        text = ' '.join(c.args[0] for c in app.label.call_args_list)
        self.assertIn('defaults', text)
        self.assertIn('accept', text)
        self.assertIn('pending live qualification', text)
        for path in root.glob('*.py'):
            if path.name.startswith('test_'): continue
            self.assertNotRegex(path.read_text(), r"['\"]-I['\"]")

    def test_windows_baseline_reports_only_requested_metadata(self):
        data = {'Caption': 'Microsoft Windows 11 Pro', 'Version': '10.0.26100',
                'BuildNumber': '26100', 'SerialNumber': 'NOT-FOR-REPORT'}
        with patch.object(windows, 'powershell', return_value=json.dumps(data)) as ps, \
                patch.object(windows.platform, 'python_version', return_value='3.12.9'):
            report = windows.baseline_report()
        for text in ('Microsoft Windows 11 Pro', '10.0.26100', '26100', '3.12.9', 'pending'):
            self.assertIn(text, report)
        self.assertNotIn('NOT-FOR-REPORT', report)
        self.assertIn('Select-Object Caption,Version,BuildNumber', ps.call_args.args[0])

    def test_windows_baseline_unavailable_or_malformed_does_not_block(self):
        for raw in ('invalid', '[]', '{}', '{"Version": "injected\\ntext", "BuildNumber": 123}'):
            with patch.object(windows, 'powershell', return_value=raw):
                self.assertIn('Windows build: UNKNOWN', windows.baseline_report())
        with patch.object(windows, 'powershell', side_effect=Failure('TARGET_QUERY_FAILED')):
            self.assertIn('Windows product: UNKNOWN', windows.baseline_report())



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

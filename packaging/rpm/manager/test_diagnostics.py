# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline fixture tests. No host package/service/journal/sensor command is run."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnostics import (Collector, DROPIN_BYTES, MAX_REPORT, PROJECT_DROPIN, Result,
                         Runner, event_category, parse_events, parse_service,
                         installation_reference, package_query, rpm_verification, save_report,
                         snapshot_metadata, time_arguments)
from model import Status

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)
SERVICE = '\n'.join(('LoadState=loaded', 'ActiveState=inactive', 'SubState=dead',
    'FragmentPath=/usr/lib/systemd/system/fprintd.service',
    'ExecStart={ path=/usr/libexec/fprintd ; argv[]=/usr/libexec/fprintd ; }',
    'DropInPaths=', 'Environment=')) + '\n'


def snapshot(**operation):
    return {'status': Status(state='absent', payload_version='3.0.1',
                             package_version='3.0.1-4.fc44', message_code='not_installed'),
            'observedAt': (NOW - timedelta(minutes=10)).isoformat(),
            'lastOperation': operation}


class Fixtures:
    def __init__(self):
        self.calls = []
        self.results = {}
        self.files = {'/usr/lib/os-release': b'ID=fedora\nVERSION_ID=45\n',
                      PROJECT_DROPIN: DROPIN_BYTES}
        self.ids = [('27c6', '5125')]

    def run(self, args, timeout=5):
        self.calls.append(args)
        key = tuple(args)
        if key in self.results:
            return self.results[key]
        if args[0] == '/usr/bin/rpm':
            if args[1] == '-q':
                return Result(stdout='1.94.9-1.fc45\n')
            if args[1] == '-qf':
                return Result(stdout='plasma-login-manager')
            return Result()
        if args[0] == '/usr/bin/systemctl':
            return Result(stdout=SERVICE)
        if args[0] == '/usr/sbin/getenforce':
            return Result(stdout='Enforcing\n')
        if args[0] == '/usr/bin/journalctl':
            return Result()
        raise AssertionError('Unexpected fixture command')

    def read(self, path):
        try:
            return self.files[path]
        except KeyError:
            raise FileNotFoundError() from None

    def collector(self, **kwargs):
        return Collector(runner=self.run, read=self.read, usb=lambda: self.ids,
                         now=lambda: NOW, machine=lambda: 'x86_64',
                         kernel=lambda: '6.17.7-200.fc45.x86_64',
                         metadata=lambda: ['trusted', 'trusted', 'absent', 'absent'], **kwargs)


def event(message, timestamp='1794167999000001', source='fprintd.service', boot='a' * 32, **changes):
    item = dict(MESSAGE=message, __REALTIME_TIMESTAMP=timestamp, _SYSTEMD_UNIT=source, _BOOT_ID=boot)
    item.update(changes)
    return json.dumps(item)


class DiagnosticTests(unittest.TestCase):
    def test_static_checks_never_promote_partial_evidence_to_authentication_pass(self):
        f = Fixtures()
        data = f.collector().checks(snapshot())
        rows = {c['id']: c for c in data['checks']}
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows['driver']['outcome'], 'not_checked')
        self.assertEqual(rows['auth']['outcome'], 'not_checked')
        self.assertEqual(rows['security']['outcome'], 'not_checked')
        self.assertEqual(rows['components']['outcome'], 'pass')
        self.assertEqual(rows['service']['outcome'], 'pass')
        self.assertIn('incomplete', data['overview'])
        self.assertEqual(data['host']['release'], '45')
        self.assertFalse(any('pkexec' in ' '.join(c) for c in f.calls))

    def test_issue55_has_two_independent_findings_and_safe_path(self):
        f = Fixtures()
        f.results[('/usr/bin/rpm', '-V', '--noscripts', '--nodeps', 'libfprint')] = Result(1, 'missing     /usr/lib64/libfprint-2.so.2\n')
        service_args = ('/usr/bin/systemctl', 'show', 'fprintd.service', '--property=LoadState,ActiveState,SubState,FragmentPath,ExecStart,DropInPaths,Environment')
        f.results[service_args] = Result(stdout=SERVICE.replace('DropInPaths=', 'DropInPaths=/etc/systemd/system/fprintd.service.d/keepalive.conf'))
        data = f.collector().report('install', 'current', False, True, status_snapshot=snapshot())
        rows = {c['id']: c for c in data['checks']}
        self.assertEqual(rows['components']['code'], 'libfprint_missing_files')
        self.assertEqual(rows['service']['code'], 'service_override_unrecognized')
        self.assertIn('/etc/systemd/system/fprintd.service.d/keepalive.conf', data['reportText'])
        self.assertNotIn('Installation not activated', data['reportText'])
        self.assertNotIn('exit 127', data['reportText'])
        self.assertIn('not establish the cause', data['reportText'])

    def test_rpm_absence_drift_unknown_attributes_and_failure_are_distinct(self):
        self.assertEqual(package_query(Result(1, 'package libfprint is not installed\n'), 'libfprint'), 'absent')
        self.assertEqual(package_query(Result(1, 'database failed'), 'libfprint'), 'unavailable')
        self.assertEqual(rpm_verification(Result()), 'pass')
        self.assertEqual(rpm_verification(Result(1, 'S.5....T.    /usr/lib64/libfprint.so\n')), 'changed')
        self.assertEqual(rpm_verification(Result(1, '?????????    /usr/lib64/libfprint.so\n')), 'unavailable')
        self.assertEqual(rpm_verification(Result(1, 'S???????T    /usr/lib64/libfprint.so\n')), 'changed_incomplete')
        self.assertEqual(rpm_verification(Result(1, 'missing     /usr/lib64/a\n?????????    /usr/lib64/b\n')), 'missing_incomplete')
        for result in (Result(2, 'failed secret'), Result(0, 'unexpected'), Result(code='timeout'),
                       Result(code='output_limit'), Result(0, '', stderr_present=True),
                       Result(1, 'totally invalid secret')):
            self.assertEqual(rpm_verification(result), 'unavailable')

    def test_service_configuration_not_service_liveness(self):
        self.assertEqual(parse_service(Result(stdout=SERVICE))['outcome'], 'pass')
        for output in ('x', SERVICE + 'LoadState=loaded\n', SERVICE.replace('FragmentPath=/usr/lib/systemd/system/fprintd.service', 'FragmentPath=/tmp/foreign')):
            self.assertNotEqual(parse_service(Result(stdout=output))['outcome'], 'pass')
        item = parse_service(Result(stdout=SERVICE.replace('Environment=', 'Environment=LD_PRELOAD=SECRET')))
        self.assertEqual(item['code'], 'service_library_environment')
        self.assertNotIn('SECRET', json.dumps(item))
        item = parse_service(Result(stdout=SERVICE.replace('DropInPaths=', 'DropInPaths=/tmp/SECRET')))
        self.assertEqual(item['outcome'], 'anomaly')
        self.assertNotIn('SECRET', json.dumps(item))
        self.assertEqual(parse_service(Result(code='timeout'))['outcome'], 'unavailable')

    def test_project_dropin_requires_exact_bytes_and_consistent_environment(self):
        text = SERVICE.replace('DropInPaths=', 'DropInPaths=' + PROJECT_DROPIN).replace('Environment=', 'Environment=LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125')
        self.assertEqual(parse_service(Result(stdout=text), lambda p: DROPIN_BYTES)['outcome'], 'pass')
        self.assertEqual(parse_service(Result(stdout=text), lambda p: b'foreign')['outcome'], 'anomaly')
        self.assertEqual(parse_service(Result(stdout=text), lambda p: (_ for _ in ()).throw(PermissionError()))['outcome'], 'unavailable')

    def test_before_install_absent_runtime_and_metadata_are_honest(self):
        f = Fixtures()
        f.ids = []
        data = f.collector().checks()
        self.assertEqual(data['checks'][0]['code'], 'runtime_not_checked')
        self.assertEqual(data['checks'][-1]['code'], 'reader_not_detected')
        f.files['/usr/lib/os-release'] = b'ID=other\nVERSION_ID=45\nSECRET=do-not-export\n'
        data = f.collector().report('system', 'current', False, True)
        self.assertEqual(data['checks'][0]['code'], 'unsupported_host')
        self.assertNotIn('SECRET', data['reportText'])
        self.assertNotIn('do-not-export', data['reportText'])

    def test_plasma_selector_baseline_and_software_metadata_are_independent(self):
        f = Fixtures()
        original = Path(__file__).resolve().parents[3] / 'deployment/plasma-login-opt-in/plasmalogin.pam'
        f.files['/etc/pam.d/plasmalogin'] = original.read_bytes()
        data = f.collector().checks()
        self.assertEqual(data['checks'][3]['code'], 'pam_selector_checked')
        self.assertIn('byte-for-byte verified', data['checks'][3]['detail'])
        f.files['/etc/pam.d/plasmalogin'] = b'foreign contents SECRET'
        data = f.collector().checks()
        self.assertEqual(data['checks'][3]['code'], 'pam_selector_changed')
        self.assertNotIn('SECRET', json.dumps(data))
        collector = f.collector()
        collector.metadata = lambda: ['changed', 'trusted', 'absent', 'trusted']
        self.assertEqual(collector.checks()['checks'][4]['code'], 'software_permissions_changed')
        collector.metadata = lambda: ['unavailable', 'trusted', 'absent', 'trusted']
        self.assertIn('unavailable', collector.checks()['checks'][4]['detail'])

    def test_security_retains_concurrent_selinux_and_permissions_anomalies_with_partial_source(self):
        f = Fixtures()
        f.results[('/usr/sbin/getenforce',)] = Result(stdout='Permissive\n')
        collector = f.collector()
        collector.metadata = lambda: ['changed', 'unavailable', 'absent', 'trusted']
        report = collector.report('system', 'current', False, True)
        security = next(c for c in report['checks'] if c['id'] == 'security')
        findings = {item['code']: item for item in security['findings']}
        self.assertEqual(security['outcome'], 'anomaly')
        self.assertEqual(findings['selinux_not_enforcing']['outcome'], 'anomaly')
        self.assertEqual(findings['software_permissions_changed']['outcome'], 'anomaly')
        self.assertEqual(findings['software_metadata_unavailable']['outcome'], 'unavailable')
        self.assertEqual(findings['software_paths_absent']['outcome'], 'not_checked')
        for text in ('Permissive', 'unexpected ownership', 'metadata was unavailable'):
            self.assertIn(text, security['detail'])
            self.assertIn(text, report['reportText'])
        for code in ('selinux_not_enforcing', 'software_permissions_changed', 'software_metadata_unavailable'):
            self.assertIn('[' + code + ']', report['reportText'])
        self.assertEqual(findings['selinux_not_enforcing']['source'], 'selinux_mode')
        self.assertEqual(findings['software_permissions_changed']['source'], 'software_metadata')

    def test_security_source_failure_never_replaces_an_observed_problem(self):
        f = Fixtures()
        f.results[('/usr/sbin/getenforce',)] = Result(code='source_unavailable')
        collector = f.collector()
        collector.metadata = lambda: ['changed', 'trusted', 'absent', 'absent']
        report = collector.report('system', 'current', False, True)
        security = next(c for c in report['checks'] if c['id'] == 'security')
        self.assertEqual(security['code'], 'software_permissions_changed')
        self.assertEqual(security['outcome'], 'anomaly')
        self.assertIn('selinux_unavailable', {f['code'] for f in security['findings']})
        f.results[('/usr/sbin/getenforce',)] = Result(stdout='Disabled\n')
        collector.metadata = lambda: (_ for _ in ()).throw(PermissionError('SECRET source failure'))
        report = collector.report('system', 'current', False, True)
        security = next(c for c in report['checks'] if c['id'] == 'security')
        self.assertEqual(security['code'], 'selinux_not_enforcing')
        self.assertIn('software_metadata_unavailable', {f['code'] for f in security['findings']})
        self.assertNotIn('SECRET', report['reportText'])
        self.assertIn('metadata was unavailable', report['reportText'])

    def test_consent_and_selection_are_validated_before_any_collection(self):
        for args in [('system', 'current', False, False), ('unknown', 'current', False, True),
                     ('system', '--root=/private', False, True), ('system', 'installation', False, True),
                     ('system', 'custom', False, True, '2026-11-08T19:00:00', '2026-11-08T20:00:00')]:
            f = Fixtures()
            data = f.collector().report(*args)
            self.assertFalse(data['reportReady'])
            self.assertEqual(f.calls, [])

    def test_snapshot_provenance_and_installation_window_are_retained_separately(self):
        f = Fixtures()
        state = snapshot(action='install', result='failed', message_code='operation_failed', observedAt=(NOW - timedelta(minutes=10)).isoformat())
        data = f.collector().report('install', 'installation', False, True, status_snapshot=state)
        self.assertTrue(data['reportReady'])
        self.assertIn('Cached operation: install failed [operation_failed]', data['reportText'])
        self.assertIn('Current collection does not revalidate', data['reportText'])
        command = next(c for c in f.calls if c[0] == '/usr/bin/journalctl')
        self.assertTrue(any(c.startswith('--since=@') for c in command))
        self.assertNotIn('--boot=0', command)
        for invalid in ({'status': 'arbitrary'}, snapshot(action='install', result='rolled_back', message_code='operation_failed', observedAt=NOW.isoformat())):
            with self.assertRaises(ValueError):
                snapshot_metadata(invalid, NOW)

    def test_installation_choice_and_collector_share_effective_window_validation(self):
        valid = snapshot(action='install', result='failed', message_code='operation_failed', observedAt=NOW.isoformat())
        reference = installation_reference(valid, NOW)
        self.assertIsNotNone(reference)
        self.assertTrue(time_arguments('custom', now=NOW, **reference))
        self.assertTrue(Fixtures().collector().report('install', 'installation', False, True, status_snapshot=valid)['reportReady'])
        for changes in ({'action': 'remove'},
                        {'observedAt': (NOW + timedelta(minutes=1)).isoformat()},
                        {'observedAt': (NOW + timedelta(microseconds=1)).isoformat()},
                        {'observedAt': (NOW + timedelta(microseconds=500000)).isoformat()},
                        {'observedAt': '2026-11-08T20:00:00'},
                        {'observedAt': 'not a timestamp'}):
            invalid = snapshot(**(valid['lastOperation'] | changes))
            self.assertIsNone(installation_reference(invalid, NOW))
            f = Fixtures()
            self.assertFalse(f.collector().report('install', 'installation', False, True, status_snapshot=invalid)['reportReady'])
            self.assertEqual(f.calls, [])
        before_epoch = {'status': None, 'observedAt': '', 'lastOperation': dict(valid['lastOperation'], observedAt='1970-01-01T00:01:00+00:00')}
        self.assertIsNone(installation_reference(before_epoch, datetime(1970, 1, 1, 0, 1, tzinfo=timezone.utc)))
        self.assertIsNone(installation_reference(None, NOW))

    def test_profiles_use_fixed_sources_and_no_network_or_privileged_commands(self):
        for profile in ('system', 'install', 'recognition', 'login', 'other'):
            f = Fixtures()
            data = f.collector().report(profile, 'previous', True, True)
            self.assertTrue(data['reportReady'])
            journal = [c for c in f.calls if c[0] == '/usr/bin/journalctl']
            self.assertEqual(bool(journal), profile != 'system')
            if journal:
                self.assertIn('--boot=-1', journal[0])
            for args in f.calls:
                self.assertIn(args[0], ('/usr/bin/rpm', '/usr/bin/systemctl', '/usr/sbin/getenforce', '/usr/bin/journalctl'))
                self.assertNotIn('start', args)
                self.assertNotIn('sudo', args)

    def test_cancellation_never_creates_a_report(self):
        stop = threading.Event()
        stop.set()
        f = Fixtures()
        data = f.collector(cancel=stop).report('other', 'current', True, True)
        self.assertFalse(data['reportReady'])
        self.assertEqual(f.calls, [])


class EventTests(unittest.TestCase):
    def test_event_projection_separates_real_markers_and_strips_all_raw_details(self):
        messages = [
            'GOODIX_STOCK_CAPTURE_RESULT attempt=1 outcome=NO_MATCH terminal=1 SECRET=',
            'post-TLS FDT initialization deadline expired SECRET=',
            'verify-disconnected SECRET=',
            'TLS handshake failed closed SECRET=',
            'GOODIX_PRODUCTION_EPOCH_AUDIT action=VERIFY secure_failure=1 secure_phase=E4 secure_failure_kind=TYPED_VALUE_MISMATCH pairing_secret=SECRET=',
        ]
        parsed = parse_events(Result(stdout='\n'.join(event(m) for m in messages)), 'recognition')
        self.assertEqual({e['category'] for e in parsed['events']}, {'no_match', 'fdt_initialization_timeout', 'transport_disconnected', 'tls_handshake_failure', 'secure_protocol_failure:E4:TYPED_VALUE_MISMATCH'})
        self.assertNotIn('SECRET', json.dumps(parsed))
        self.assertNotIn('pairing', json.dumps(parsed))
        self.assertNotIn('MESSAGE', json.dumps(parsed))
        self.assertIsNone(event_category('GOODIX_PRODUCTION_EPOCH_AUDIT secure_failure=0 secure_phase=TLS secure_failure_kind=NONE', 'fprintd'))
        self.assertIsNone(event_category('GOODIX_LOGIN_READY', 'fprintd'))
        self.assertIsNone(event_category('timeout', 'fprintd'))
        self.assertIsNone(event_category('GOODIX_PRODUCTION_EPOCH_AUDIT secure_failure=1 secure_phase=SECRET secure_failure_kind=MALFORMED_FRAME', 'fprintd'))

    def test_microsecond_order_and_boot_identity_are_preserved_internally(self):
        raw = '\n'.join((event('verify-match', '1794167999000002'), event('verify-no-match', '1794167999000001')))
        data = parse_events(Result(stdout=raw), 'recognition')
        self.assertEqual([e['category'] for e in data['events']], ['no_match', 'match'])
        self.assertIn('.000001', data['events'][0]['time'])
        self.assertNotIn('a' * 32, json.dumps(data))
        data = parse_events(Result(stdout=raw + '\n' + event('verify-match', boot='b' * 32)), 'recognition')
        self.assertEqual(data['availability'], 'mixed_boot_history')
        self.assertEqual(data['events'], [])

    def test_history_permission_missing_invalid_partial_and_limit_do_not_mean_healthy(self):
        for result in (Result(1), Result(code='source_unavailable'), Result(code='timeout'), Result(code='output_limit'), Result(stdout='{"MESSAGE": "SECRET"}'), Result(stdout='not json')):
            data = parse_events(result, 'other')
            self.assertNotEqual(data['availability'], 'visible_history')
            self.assertEqual(data['events'], [])
        self.assertEqual(parse_events(Result(), 'login')['availability'], 'no_visible_events')
        self.assertEqual(parse_events(Result(stdout=event('verify-match'), stderr_present=True), 'login')['availability'], 'partial_history')
        self.assertEqual(parse_events(Result(stdout='\n'.join(event('verify-match') for _ in range(1001))), 'login')['availability'], 'history_truncated')

    def test_unknown_sources_raw_metadata_and_security_are_not_exported(self):
        raw = '\n'.join((event('SECRET psk password template image'), event('verify-match', source='unrelated.service', SYSLOG_IDENTIFIER='SECRET'), event('avc:  denied SECRET')))
        essential = parse_events(Result(stdout=raw), 'other')
        self.assertEqual(essential['events'], [])
        extended = parse_events(Result(stdout=raw), 'other', True)
        self.assertEqual([e['category'] for e in extended['events']], ['security_denial'])
        self.assertNotIn('SECRET', json.dumps(extended))

    def test_authentication_event_is_context_not_causality(self):
        raw = event('pam_unix(sudo:auth): authentication failure; user=SECRET', source='foreign.service', SYSLOG_IDENTIFIER='sudo', _EXE='/usr/bin/sudo', _COMM='sudo')
        result = parse_events(Result(stdout=raw), 'login')
        self.assertEqual(result['events'][0]['category'], 'authentication_failure')
        self.assertEqual(result['events'][0]['source'], 'sudo')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_sender_controlled_identifiers_cannot_spoof_a_trusted_event_source(self):
        for identifier in ('fprintd', 'sudo', 'polkitd', 'plasmalogin', 'sddm'):
            raw = event('verify-match', source='unrelated.service', SYSLOG_IDENTIFIER=identifier)
            self.assertEqual(parse_events(Result(stdout=raw), 'other')['events'], [])


class BoundaryTests(unittest.TestCase):
    def test_time_ranges_enums_previous_boot_and_injection_rejection(self):
        self.assertEqual(time_arguments('previous', now=NOW), ['--boot=-1'])
        self.assertEqual(time_arguments('current', now=NOW), ['--boot=0'])
        for window in ('today', 'last30'):
            self.assertTrue(time_arguments(window, now=NOW)[0].startswith('--since=@'))
        for start, end in [('2026-11-08T20:00:00+00:00', '2026-11-08T19:00:00+00:00'),
                           ('2026-11-06T20:00:00+00:00', '2026-11-08T20:00:00+00:00'),
                           ('--root=/tmp', '2026-11-08T20:00:00+00:00')]:
            with self.assertRaises(ValueError):
                time_arguments('custom', start, end, NOW)

    def test_export_new_regular_0600_file_without_overwrite_or_symlink(self):
        text = 'GOODIX MANAGER DIAGNOSTIC REPORT\nfixture\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.txt'
            save_report(path, text)
            self.assertEqual(path.read_text(), text)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                save_report(path, text + 'different')
            link = Path(tmp) / 'link'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                save_report(link, text)
            self.assertEqual(path.read_text(), text)
            with self.assertRaises(ValueError):
                save_report(Path(tmp) / 'invalid', 'untrusted')
            with self.assertRaises(ValueError):
                save_report(Path(tmp) / 'overflow', text + 'x' * MAX_REPORT)

    def test_runner_bounds_both_streams_and_rejects_invalid_encoding(self):
        for script, expected in [('import sys;sys.stdout.write("x"*300000)', 'output_limit'),
                                 ('import sys;sys.stderr.write("x"*20000)', 'output_limit'),
                                 ('import os;os.write(1,b"\\xff")', 'invalid_output')]:
            result = Runner()([sys.executable, '-c', script], timeout=2)
            self.assertEqual(result.code, expected)
            self.assertEqual(result.stdout, '')

    def test_export_failure_preserves_replacement_and_leaves_partial_file_restrictive(self):
        text = 'GOODIX MANAGER DIAGNOSTIC REPORT\nfixture\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report'
            def replace(_fd):
                path.unlink()
                path.write_text('UNRELATED_REPLACEMENT')
                raise OSError('fixture fsync failure')
            with patch('diagnostics.os.fsync', side_effect=replace):
                with self.assertRaises(OSError):
                    save_report(path, text)
            self.assertEqual(path.read_text(), 'UNRELATED_REPLACEMENT')
            path.unlink()
            with patch('diagnostics.os.fsync', side_effect=OSError('fixture fsync failure')):
                with self.assertRaises(OSError):
                    save_report(path, text)
            self.assertTrue(path.exists())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_runner_cancellation_timeout_and_whole_request_budget(self):
        stop = threading.Event()
        timer = threading.Timer(.05, stop.set)
        timer.start()
        try:
            self.assertEqual(Runner(stop)([sys.executable, '-c', 'import time;time.sleep(5)'], timeout=2).code, 'cancelled')
        finally:
            timer.cancel()
        self.assertEqual(Runner()([sys.executable, '-c', 'import time;time.sleep(5)'], timeout=.05).code, 'timeout')
        runner = Runner()
        runner.deadline = time.monotonic() - 1
        with patch('diagnostics.subprocess.Popen', side_effect=AssertionError('must not spawn')):
            self.assertEqual(runner(['/fake']).code, 'timeout')

    def test_exited_leader_cannot_leave_a_running_pipe_holding_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            child_pid = Path(tmp) / 'pid'
            script = 'import os,time,pathlib;pid=os.fork();pathlib.Path(' + repr(str(child_pid)) + ').write_text(str(pid)) if pid else None;time.sleep(5) if pid==0 else None'
            result = Runner()([sys.executable, '-c', script], timeout=.1)
            self.assertEqual(result.code, 'timeout')
            pid = int(child_pid.read_text())
            for _ in range(20):
                try:
                    status = Path('/proc') / str(pid) / 'status'
                    if '\nState:\tZ' in status.read_text():
                        break
                except FileNotFoundError:
                    break
                time.sleep(.01)
            else:
                self.fail('descendant survived timeout')

    def test_cancellation_remains_responsive_after_both_pipes_close(self):
        cancel = threading.Event()
        timer = threading.Timer(.1, cancel.set)
        timer.start()
        started = time.monotonic()
        try:
            result = Runner(cancel)([sys.executable, '-c', 'import os,time;os.close(1);os.close(2);time.sleep(5)'], timeout=30)
        finally:
            timer.cancel()
        self.assertEqual(result.code, 'cancelled')
        self.assertLess(time.monotonic() - started, 2)


if __name__ == '__main__':
    unittest.main()

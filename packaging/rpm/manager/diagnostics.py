# SPDX-License-Identifier: GPL-2.0-or-later
"""On-demand, unprivileged diagnostics. Raw source text never crosses this boundary.

Tests inject Runner/files/USB/clock; import does not query the host or a bus.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import time

from model import MESSAGES, Status

ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
MAX_OUTPUT = 256 * 1024
MAX_ERROR = 16 * 1024
MAX_REPORT = 512 * 1024
PROJECT_DROPIN = '/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf'
DROPIN_BYTES = b'[Service]\nEnvironment=LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125\n'
PROFILES = {'system': 'System status', 'install': 'Installation or update failed',
            'recognition': 'Fingerprint recognition problem',
            'login': 'Fingerprint sign-in problem', 'other': 'Other problem'}
TIMES = {'current', 'previous', 'last30', 'today', 'custom', 'installation'}
TITLES = {'driver': 'Goodix driver', 'components': 'Fingerprint components',
          'service': 'Fingerprint service', 'auth': 'Sign-in integration',
          'security': 'Security settings', 'reader': 'Fingerprint reader'}
SOURCES = {'fprintd.service': 'fprintd', 'plasma-login-manager.service': 'plasma',
           'sddm.service': 'sddm', 'polkit.service': 'polkit'}
PAM_SELECTOR_SHA256 = '5d537fe653d2051b1cf95a9d5e7cf1dac3688ba96dc7559d9586c619bc70bcea'
SOFTWARE_PATHS = {'/usr/libexec/goodix-manager-helper': False,
                  '/usr/lib/goodix-manager': True,
                  '/usr/local/lib64/goodix-27c6-5125': True,
                  '/etc/pam.d/plasmalogin': False}
SECURE_PHASES = frozenset(('REENTRY_RECOVERY_A2', 'A8', 'E4', 'OEM_COLD_START_A2_1',
    'CHIP_82', 'OTP_A6', 'OEM_COLD_START_A2_2', 'MODE_70', 'DAC_220', 'DAC_236',
    'DAC_238', 'DAC_23A', 'CONFIG_90', 'D1', 'TLS', 'STOP', 'TERMINAL'))
FAILURE_KINDS = frozenset(('ACK_STATUS_REJECTED', 'ACK_ECHO_MISMATCH', 'ACK_SHAPE_MISMATCH',
    'TYPED_CONTROL_MISMATCH', 'TYPED_SHAPE_MISMATCH', 'TYPED_VALUE_MISMATCH',
    'UNEXPECTED_OUTER_CLASS', 'MALFORMED_FRAME'))


@dataclass(frozen=True)
class Result:
    returncode: int = 0
    stdout: str = ''
    code: str = 'ok'
    stderr_present: bool = False


class Runner:
    """Bound both pipes while the process runs, and kill the process group on stop."""
    def __init__(self, cancel=None):
        self.cancel = cancel
        self.deadline = time.monotonic() + 120

    def __call__(self, args, timeout=5):
        if self.cancel is not None and self.cancel.is_set():
            return Result(code='cancelled')
        end = min(self.deadline, time.monotonic() + timeout)
        if end <= time.monotonic():
            return Result(code='timeout')
        process = None
        buffers = {'out': bytearray(), 'err': bytearray()}
        try:
            process = subprocess.Popen(args, env=ENV, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True, close_fds=True)
            with selectors.DefaultSelector() as poll:
                for stream, label in ((process.stdout, 'out'), (process.stderr, 'err')):
                    os.set_blocking(stream.fileno(), False)
                    poll.register(stream, selectors.EVENT_READ, label)
                failure = None
                while poll.get_map():
                    if self.cancel is not None and self.cancel.is_set():
                        failure = 'cancelled'
                        break
                    if time.monotonic() >= end:
                        failure = 'timeout'
                        break
                    for key, _ in poll.select(min(.05, max(0, end - time.monotonic()))):
                        data = os.read(key.fileobj.fileno(), 8192)
                        if not data:
                            poll.unregister(key.fileobj)
                            continue
                        buffer = buffers[key.data]
                        buffer.extend(data)
                        if len(buffer) > (MAX_OUTPUT if key.data == 'out' else MAX_ERROR):
                            failure = 'output_limit'
                            break
                    if failure:
                        break
                if failure:
                    return Result(code=failure)
                # EOF is not process completion: a child can close both pipes
                # then remain alive. Continue honoring cancellation/deadline.
                while process.poll() is None:
                    if self.cancel is not None and self.cancel.is_set():
                        return Result(code='cancelled')
                    remaining = end - time.monotonic()
                    if remaining <= 0:
                        return Result(code='timeout')
                    try:
                        process.wait(timeout=min(.05, remaining))
                    except subprocess.TimeoutExpired:
                        pass
            return Result(process.returncode, bytes(buffers['out']).decode('utf-8', 'strict'),
                          stderr_present=bool(buffers['err']))
        except subprocess.TimeoutExpired:
            return Result(code='timeout')
        except UnicodeError:
            return Result(code='invalid_output')
        except (OSError, ValueError):
            return Result(code='source_unavailable')
        finally:
            if process is not None:
                # The parent may have exited while descendants still hold pipes.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                process.stdout.close()
                process.stderr.close()


FILE_PATHS = frozenset(('/usr/lib/os-release', PROJECT_DROPIN,
                        '/usr/lib/pam.d/plasmalogin', '/etc/pam.d/plasmalogin'))


def read_file(name):
    """Only fixed ordinary configuration files, no redirected/writable parents."""
    if name not in FILE_PATHS:
        raise ValueError('unapproved source')
    path = Path(name)
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise OSError('untrusted source')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise OSError('untrusted source')
        data = stream.read(65537)
    if len(data) > 65536:
        raise OSError('source limit')
    return data


def usb_ids():
    """Read only two kernel-enumeration attributes, never the device node."""
    found = []
    devices = list(Path('/sys/bus/usb/devices').iterdir())
    if len(devices) > 512:
        raise OSError('enumeration limit')
    for entry in devices:
        target = entry.resolve(strict=True)
        if not target.is_relative_to('/sys/devices'):
            raise OSError('unsafe kernel path')
        pair = []
        try:
            for attribute in ('idVendor', 'idProduct'):
                fd = os.open(target / attribute, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, 'rb') as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise OSError('invalid kernel attribute')
                    raw = stream.read(8)
                if not re.fullmatch(b'[0-9a-f]{4}\n?', raw):
                    raise OSError('invalid kernel attribute')
                pair.append(raw.decode().strip())
        except FileNotFoundError:
            continue
        found.append(tuple(pair))
    return found


def software_metadata():
    """Only ordinary fixed software paths; no protected data or directory walk."""
    states = []
    for name, directory in SOFTWARE_PATHS.items():
        path = Path(name)
        try:
            for parent in reversed(path.parents):
                info = parent.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022:
                    raise ValueError('unsafe software parent')
            info = path.lstat()
            safe = ((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode) and
                    info.st_uid == 0 and info.st_gid == 0 and not info.st_mode & 0o022)
            states.append('trusted' if safe else 'changed')
        except FileNotFoundError:
            states.append('absent')
        except ValueError:
            states.append('changed')
        except OSError:
            states.append('unavailable')
    return states


def row(identifier, outcome, code, summary, detail):
    source = {'driver': 'rpm_and_cached_helper', 'components': 'fedora_rpm',
              'service': 'effective_systemd_configuration', 'auth': 'vendor_rpm_and_project_selector',
              'security': 'selinux_mode_and_software_metadata', 'reader': 'kernel_usb_enumeration'}[identifier]
    return dict(id=identifier, title=TITLES[identifier], outcome=outcome,
                code=code, summary=summary, detail=detail, source=source, evidence='OBSERVED')


def unavailable(identifier, code='source_unavailable'):
    return row(identifier, 'unavailable', code, 'Data unavailable',
               'The source could not be checked completely. No positive result is claimed.')


def package_query(result, package):
    if result.code != 'ok' or result.stderr_present:
        return 'unavailable'
    if result.returncode == 1 and result.stdout.strip() == f'package {package} is not installed':
        return 'absent'
    if (result.returncode == 0 and
            re.fullmatch(r'[0-9][0-9.]*-[0-9][0-9A-Za-z_.]*\n?', result.stdout)):
        return 'present'
    return 'unavailable'


def rpm_verification(result):
    if result.code != 'ok' or result.stderr_present:
        return 'unavailable'
    if result.returncode == 0 and not result.stdout:
        return 'pass'
    if result.returncode != 1 or not result.stdout:
        return 'unavailable'
    missing = False
    incomplete = False
    changed = False
    for line in result.stdout.splitlines():
        if len(line) > 4096:
            return 'unavailable'
        if re.fullmatch(r'missing\s+(?:[cdglr]\s+)?/[^\x00-\x1f]+', line):
            missing = True
        else:
            match = re.fullmatch(r'([.SM5DLUGTP?]{9})\s+(?:[cdglr]\s+)?/[^\x00-\x1f]+', line)
            if not match:
                return 'unavailable'
            incomplete |= '?' in match[1]
            changed |= any(c not in '.?' for c in match[1])
    state = 'missing' if missing else 'changed' if changed else 'unavailable'
    return state + '_incomplete' if incomplete and state != 'unavailable' else state


def parse_service(result, read=read_file):
    if result.code != 'ok' or result.returncode or result.stderr_present:
        return unavailable('service', result.code if result.code != 'ok' else 'service_query_failed')
    properties = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition('=')
        if not sep or key in properties:
            return unavailable('service', 'service_output_invalid')
        properties[key] = value
    required = {'LoadState', 'ActiveState', 'SubState', 'FragmentPath', 'ExecStart', 'DropInPaths', 'Environment'}
    if set(properties) != required:
        return unavailable('service', 'service_output_invalid')
    if properties['LoadState'] == 'not-found':
        return row('service', 'anomaly', 'service_missing', 'Service unavailable',
                   'The fprintd service unit was not found.')
    if properties['LoadState'] != 'loaded':
        return unavailable('service', 'service_not_loaded')
    import shlex
    try:
        drops = shlex.split(properties['DropInPaths'])
        environment = shlex.split(properties['Environment'])
    except ValueError:
        return unavailable('service', 'service_output_invalid')
    if any(not p.startswith('/') or '..' in Path(p).parts for p in drops):
        return unavailable('service', 'service_output_invalid')
    if any(p != PROJECT_DROPIN and not p.startswith('/usr/lib/systemd/system/') for p in drops):
        safe = [p for p in drops if re.fullmatch(r'/(?:etc|run)/systemd/system/fprintd[.]service[.]d/[A-Za-z0-9_.-]{1,80}[.]conf', p)
                and '..' not in Path(p).name]
        location = (' File: ' + safe[0] + '.') if safe else ' The exact override location cannot be safely displayed.'
        return row('service', 'anomaly', 'service_override_unrecognized', 'Unrecognized service override',
                   'An effective local fprintd override can block installation.' + location + ' No configuration was changed.')
    paths = re.findall(r'path=([^ ;]+)', properties['ExecStart'])
    if properties['FragmentPath'] != '/usr/lib/systemd/system/fprintd.service' or paths != ['/usr/libexec/fprintd']:
        return row('service', 'anomaly', 'service_baseline_changed', 'Service configuration changed',
                   'The effective service fragment or executable differs from the supported Fedora baseline.')
    libraries = [v for v in environment if v.startswith('LD_LIBRARY_PATH=')]
    if (any(v.startswith('LD_PRELOAD=') for v in environment) or
            libraries and libraries != ['LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125']):
        return row('service', 'anomaly', 'service_library_environment', 'Library environment changed',
                   'An unsupported fprintd library environment can block installation.')
    if PROJECT_DROPIN in drops or libraries:
        try:
            exact = read(PROJECT_DROPIN) == DROPIN_BYTES
        except (OSError, ValueError):
            return unavailable('service', 'project_dropin_unavailable')
        if not exact or libraries and PROJECT_DROPIN not in drops:
            return row('service', 'anomaly', 'project_dropin_changed', 'Project service override changed',
                       'The project fprintd override does not match the supported configuration.')
    if properties['ActiveState'] == 'failed':
        return row('service', 'anomaly', 'service_failed', 'Service reported failure',
                   'The current service state is failed. Event history may provide context.')
    if properties['ActiveState'] not in {'active', 'inactive', 'activating', 'deactivating', 'reloading'}:
        return unavailable('service', 'service_state_unknown')
    return row('service', 'pass', 'service_configuration_checked', 'Configuration checked',
               'Known service configuration checks passed. An idle on-demand service is allowed; D-Bus and login were not tested.')


def _now():
    return datetime.now(timezone.utc)


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError('invalid observation time')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed.astimezone(timezone.utc)


def snapshot_metadata(snapshot, now):
    """Validate dated evidence separately from the current collection."""
    if snapshot is None:
        return {'status': None, 'observedAt': '', 'lastOperation': {}}
    if not isinstance(snapshot, dict) or set(snapshot) != {'status', 'observedAt', 'lastOperation'}:
        raise ValueError('invalid software snapshot')
    status_value = snapshot['status']
    observed = ''
    if status_value is not None:
        if type(status_value) is not Status:
            raise ValueError('invalid software snapshot')
        fields = json.loads(status_value.diagnostic())
        fields['result'] = 'blocked' if status_value.state == 'blocked' else 'success'
        status_value = Status.parse(fields)
        moment = _timestamp(snapshot['observedAt'])
        if moment > now + timedelta(minutes=5) or moment.timestamp() < 0:
            raise ValueError('invalid software snapshot time')
        observed = moment.isoformat(timespec='seconds')
    elif snapshot['observedAt']:
        raise ValueError('snapshot time without status')
    operation = snapshot['lastOperation']
    if not isinstance(operation, dict):
        raise ValueError('invalid operation snapshot')
    if operation:
        if (set(operation) != {'action', 'result', 'message_code', 'observedAt'} or
                operation['action'] not in {'install', 'update', 'remove'} or
                operation['result'] not in {'success', 'failed', 'blocked', 'rolled_back'} or
                operation['message_code'] not in MESSAGES):
            raise ValueError('invalid operation snapshot')
        moment = _timestamp(operation['observedAt'])
        if moment > now + timedelta(minutes=5) or moment.timestamp() < 0:
            raise ValueError('invalid operation snapshot time')
        if (operation['result'] == 'rolled_back' and operation['message_code'] != 'rollback_complete' or
                operation['result'] == 'success' and operation['message_code'] not in {'installed', 'removed'}):
            raise ValueError('contradictory operation snapshot')
        operation = dict(operation, observedAt=moment.isoformat(timespec='seconds'))
    return {'status': status_value, 'observedAt': observed, 'lastOperation': operation}


def time_arguments(window, since='', until='', now=None):
    if window not in TIMES:
        raise ValueError('invalid time selection')
    now = now or _now()
    if window in {'current', 'previous'}:
        return ['--boot=' + ('0' if window == 'current' else '-1')]
    if window == 'installation':
        raise ValueError('installation time unavailable')
    if window == 'custom':
        if not isinstance(since, str) or not isinstance(until, str) or max(len(since), len(until)) > 40:
            raise ValueError('invalid time range')
        start, end = datetime.fromisoformat(since), datetime.fromisoformat(until)
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError('timezone required')
    else:
        end = now
        start = now - timedelta(minutes=30) if window == 'last30' else now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    if (end <= start or end - start > timedelta(hours=24) or
            start.timestamp() < 0 or end > now + timedelta(minutes=5)):
        raise ValueError('invalid time range')
    return ['--since=@' + str(int(start.timestamp())), '--until=@' + str(int(end.timestamp()))]


def event_category(message, source):
    """Exact source markers only; never copy message fragments or biometric counts."""
    if not isinstance(message, str) or len(message) > 16384:
        return None
    if source == 'fprintd':
        capture = re.search(r'\bGOODIX_STOCK_CAPTURE_RESULT attempt=[0-9]+ outcome=(ERROR|MATCH|NO_MATCH) terminal=[01](?:\s|$)', message)
        if capture:
            return {'ERROR': 'capture_error', 'MATCH': 'match', 'NO_MATCH': 'no_match'}[capture[1]]
        if re.search(r'\bGOODIX_LOGIN_NO_MATCH attempt=[0-9]+ limit=3 release=1 next_explicit_verify_required=1(?:\s|$)', message):
            return 'no_match'
        if 'post-TLS FDT initialization deadline expired' in message:
            return 'fdt_initialization_timeout'
        if 'GOODIX_PRODUCTION_EPOCH_AUDIT ' in message:
            failure = re.search(r'\bsecure_failure=1 secure_phase=([A-Z0-9_]+) secure_failure_kind=([A-Z0-9_]+)(?:\s|$)', message)
            if failure and failure[1] in SECURE_PHASES and failure[2] in FAILURE_KINDS:
                return 'secure_protocol_failure:' + failure[1] + ':' + failure[2]
        if 'TLS handshake failed closed' in message:
            return 'tls_handshake_failure'
        if re.search(r'\bverify-no-match\b', message):
            return 'no_match'
        if re.search(r'\bverify-match\b', message):
            return 'match'
        if re.search(r'\bverify-(?:retry-scan|swipe-too-short|finger-not-centered|remove-and-retry|too-fast)\b', message):
            return 'acquisition_retry'
        if re.search(r'\bverify-disconnected\b', message):
            return 'transport_disconnected'
    if source in {'plasma', 'sddm', 'sudo', 'polkit'}:
        if re.search(r'\bpam_[a-z0-9_]+\([^\r\n]{1,128}\): authentication failure(?:\s|;|$)', message):
            return 'authentication_failure'
    if 'avc:  denied' in message or 'avc: denied' in message:
        return 'security_denial'
    return None


def parse_events(result, profile, extended=False):
    if result.code != 'ok' or result.returncode:
        return {'availability': result.code if result.code != 'ok' else 'history_unavailable', 'events': [], 'unclassified': 0}
    events = []
    unknown = 0
    boot = None
    lines = result.stdout.splitlines()
    if len(lines) > 1001:
        return {'availability': 'output_limit', 'events': [], 'unclassified': 0}
    for line in lines[:1000]:
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError()
            timestamp = item.get('__REALTIME_TIMESTAMP')
            item_boot = item.get('_BOOT_ID')
            if not isinstance(timestamp, str) or not re.fullmatch(r'[0-9]{1,17}', timestamp):
                raise ValueError()
            if not isinstance(item_boot, str) or not re.fullmatch('[a-f0-9]{32}', item_boot):
                raise ValueError()
            source = SOURCES.get(item.get('_SYSTEMD_UNIT'))
            # SYSLOG_IDENTIFIER is sender-controlled; trusted journald attributes
            # are needed for sudo, which has no dedicated system service unit.
            if source is None and item.get('SYSLOG_IDENTIFIER') == 'sudo' and item.get('_EXE') == '/usr/bin/sudo' and item.get('_COMM') == 'sudo':
                source = 'sudo'
            if source is None or profile == 'recognition' and source != 'fprintd':
                unknown += 1
                continue
            category = event_category(item.get('MESSAGE'), source)
            if category == 'security_denial' and not extended:
                category = None
            if category:
                seconds, micros = divmod(int(timestamp), 1000000)
                timestamp = datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=micros).isoformat(timespec='microseconds')
                if boot is None:
                    boot = item_boot
                elif boot != item_boot:
                    return {'availability': 'mixed_boot_history', 'events': [], 'unclassified': 0}
                events.append({'time': timestamp, 'source': source, 'category': category})
            else:
                unknown += 1
        except (ValueError, TypeError, OverflowError, OSError):
            return {'availability': 'history_output_invalid', 'events': [], 'unclassified': 0}
    events.sort(key=lambda e: e['time'])
    availability = ('history_truncated' if len(lines) > 1000 else
                    'partial_history' if result.stderr_present else
                    'visible_history' if lines else 'no_visible_events')
    return {'availability': availability, 'events': events, 'unclassified': unknown}


class Collector:
    def __init__(self, runner=None, read=read_file, usb=usb_ids, now=_now, cancel=None, machine=platform.machine, kernel=platform.release, metadata=software_metadata):
        self.run = runner or Runner(cancel)
        self.read, self.usb, self.now, self.cancel = read, usb, now, cancel
        self.machine = machine
        self.kernel = kernel
        self.metadata = metadata
        self.versions = {}

    def command(self, args, timeout=5):
        if self.cancel is not None and self.cancel.is_set():
            return Result(code='cancelled')
        return self.run(args, timeout=timeout)

    def package(self, name):
        result = self.command(['/usr/bin/rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}\n', name], 30)
        state = package_query(result, name)
        if state == 'present':
            version = result.stdout.strip()
            self.versions[name] = version if re.fullmatch(r'[0-9]+(?:[.][0-9]+){0,4}-[0-9]+(?:[.](?:fc[0-9]+|[0-9]+)){1,3}', version) else 'unavailable'
            state = rpm_verification(self.command(['/usr/bin/rpm', '-V', '--noscripts', '--nodeps', name], 30))
        return state

    def checks(self, status_snapshot=None):
        provenance = snapshot_metadata(status_snapshot, self.now())
        status_snapshot = provenance['status']
        if self.cancel is not None and self.cancel.is_set():
            return {'checks': [unavailable(name, 'cancelled') for name in TITLES],
                    'overview': 'Collection cancelled', 'generatedAt': self.now().isoformat(timespec='seconds'),
                    'host': {}, 'cachedEvidence': {}, 'packageVersions': {}}
        host = {'distribution': 'unavailable', 'release': '', 'architecture': 'unavailable', 'kernel': 'unavailable'}
        try:
            os_release = self.read('/usr/lib/os-release').decode('utf-8', 'strict')
            # Project only fixed identity and numeric release, never arbitrary values.
            identities = re.findall(r'^ID=(?:"([a-z0-9_-]+)"|([a-z0-9_-]+))$', os_release, re.M)
            releases = re.findall(r'^VERSION_ID="?([0-9]{1,3})"?$', os_release, re.M)
            architecture = self.machine()
            if len(identities) == 1 and len(releases) == 1:
                host['distribution'] = 'fedora' if ''.join(identities[0]) == 'fedora' else 'other'
                host['release'] = releases[0]
            host['architecture'] = 'x86_64' if architecture == 'x86_64' else 'other'
            kernel = self.kernel()
            if isinstance(kernel, str) and re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}(?:\.[0-9]{1,3})?(?:-[0-9]{1,5}[.]fc[0-9]{1,3}[.]x86_64)?', kernel):
                host['kernel'] = kernel
        except (OSError, ValueError, UnicodeError):
            pass
        package = self.package('goodix-manager')
        if package in {'missing', 'changed', 'absent', 'missing_incomplete', 'changed_incomplete'}:
            driver = row('driver', 'anomaly', 'manager_package_' + package, 'Manager package needs attention',
                         'The Manager package is absent or its files differ from RPM metadata. Runtime authentication was not tested.')
        elif package == 'unavailable':
            driver = unavailable('driver', 'manager_package_unavailable')
        elif status_snapshot is None:
            driver = row('driver', 'not_checked', 'runtime_not_checked', 'Runtime not checked',
                         'Manager RPM files passed verification. No verified runtime snapshot is available.')
        else:
            code = status_snapshot.message_code
            if code not in {'ready', 'not_installed', 'up_to_date', 'installed', 'removed', 'rollback_complete', 'operation_failed', 'integrity_failed', 'runtime_changed', 'missing_dependencies', 'source_mismatch', 'version_unknown', 'legacy_upgrade_available', 'legacy_unqualified', 'downgrade_blocked', 'update_available'}:
                code = 'runtime_not_checked'
            driver = row('driver', 'not_checked', 'cached_' + code, 'Previous software status available',
                         'Manager RPM files passed verification. The cached helper status is not a fresh runtime or authentication check.')
        if (host['distribution'] == 'other' or host['architecture'] == 'other' or
                host['release'] and int(host['release']) < 44) and driver['outcome'] != 'anomaly':
            driver = row('driver', 'anomaly', 'unsupported_host', 'Host outside supported baseline',
                         'The observed host is not Fedora 44 or newer x86_64. This diagnostic does not modify host settings.')
        components = {name: self.package(name) for name in ('libfprint', 'fprintd', 'fprintd-pam')}
        issues = [(name, value) for name, value in components.items() if value in {'missing', 'changed', 'absent', 'missing_incomplete', 'changed_incomplete'}]
        if issues:
            name, value = issues[0]
            component = row('components', 'anomaly', name.replace('-', '_') + '_' + value + '_files' if value != 'absent' else name.replace('-', '_') + '_package_absent',
                            'Fedora package files need attention',
                            '; '.join(name + ': ' + {'missing': 'missing files', 'changed': 'changed files', 'missing_incomplete': 'missing files; other attributes unavailable', 'changed_incomplete': 'changed files; other attributes unavailable', 'absent': 'package absent', 'pass': 'files checked', 'unavailable': 'verification unavailable'}[state] for name, state in components.items()) + '. This does not establish the cause of a past service failure.')
        elif any(v == 'unavailable' for v in components.values()):
            component = unavailable('components', 'component_verification_unavailable')
        else:
            component = row('components', 'pass', 'components_checked', 'Package files checked',
                            'Fedora libfprint, fprintd and fprintd-pam RPM file checks passed. A biometric action was not tested.')
        service = parse_service(self.command(['/usr/bin/systemctl', 'show', 'fprintd.service',
                            '--property=LoadState,ActiveState,SubState,FragmentPath,ExecStart,DropInPaths,Environment']), self.read)
        owner = self.command(['/usr/bin/rpm', '-qf', '--qf', '%{NAME}', '/usr/lib/pam.d/plasmalogin'])
        vendor_known = owner.code == 'ok' and owner.returncode == 0 and not owner.stderr_present and owner.stdout == 'plasma-login-manager'
        try:
            selector = self.read('/etc/pam.d/plasmalogin')
            selector_state = 'checked' if hashlib.sha256(selector).hexdigest() == PAM_SELECTOR_SHA256 else 'changed'
        except FileNotFoundError:
            selector_state = 'absent'
        except (OSError, ValueError):
            selector_state = 'unavailable'
        if selector_state == 'changed':
            auth = row('auth', 'anomaly', 'pam_selector_changed', 'Plasma selector differs',
                       'The local Plasma PAM selector differs from the reviewed project selector. No authentication configuration was modified.')
        elif not vendor_known or selector_state == 'unavailable':
            auth = unavailable('auth', 'pam_owner_unavailable' if not vendor_known else 'pam_selector_unavailable')
        else:
            auth = row('auth', 'not_checked', 'pam_selector_' + selector_state, 'Integration partially checked',
                       'The vendor Plasma PAM file belongs to its Fedora package. The project selector is ' + ('byte-for-byte verified' if selector_state == 'checked' else 'absent; the project login integration is not activated') + '. sudo/polkit behavior and login remain unverified.')
        enforcement = self.command(['/usr/sbin/getenforce'])
        if enforcement.code == 'ok' and enforcement.returncode == 0 and not enforcement.stderr_present and enforcement.stdout.strip() == 'Enforcing':
            security = row('security', 'not_checked', 'security_partial', 'SELinux Enforcing',
                           'SELinux reports Enforcing. Protected state labels, permissions and policy behavior were not inspected.')
        elif enforcement.code == 'ok' and enforcement.returncode == 0 and not enforcement.stderr_present and enforcement.stdout.strip() in {'Permissive', 'Disabled'}:
            security = row('security', 'anomaly', 'selinux_not_enforcing', 'SELinux is not Enforcing',
                           'The observed SELinux mode differs from the required baseline. No setting was changed.')
        else:
            security = unavailable('security', 'selinux_unavailable')
        try:
            metadata = self.metadata()
            if len(metadata) != len(SOFTWARE_PATHS) or any(v not in {'trusted', 'absent', 'changed', 'unavailable'} for v in metadata):
                raise ValueError('invalid metadata')
            if 'changed' in metadata:
                security = row('security', 'anomaly', 'software_permissions_changed', 'Software permissions need attention',
                               'An ordinary software path or its parent has unexpected ownership, permissions or type. Protected data paths were not accessed.')
            elif 'unavailable' in metadata:
                security['detail'] += ' Some ordinary software path metadata was unavailable.'
            else:
                security['detail'] += ' Existing ordinary software paths have trusted root ownership/type/mode; absent paths were not verified. File labels remain unverified.'
        except (OSError, ValueError):
            security['detail'] += ' Ordinary software path metadata was unavailable.'
        try:
            if self.cancel is not None and self.cancel.is_set():
                raise OSError('cancelled')
            detected = ('27c6', '5125') in self.usb()
            reader = row('reader', 'pass' if detected else 'not_checked', 'reader_detected' if detected else 'reader_not_detected',
                         'Detected' if detected else 'Not detected',
                         'Kernel USB enumeration only. No device was opened, initialized, claimed or tested.')
        except (OSError, ValueError):
            reader = unavailable('reader', 'reader_enumeration_unavailable')
        checks = [driver, component, service, auth, security, reader]
        observed_at = self.now().isoformat(timespec='seconds')
        for check in checks:
            check['observedAt'] = observed_at
        overview = ('One or more observed problems need attention' if any(c['outcome'] == 'anomaly' for c in checks) else
                    'Some checks are unavailable or incomplete' if any(c['outcome'] != 'pass' for c in checks) else
                    'No known configuration problems found in the completed checks')
        cached = {'observedAt': provenance['observedAt'],
                  'lastOperation': provenance['lastOperation']}
        if status_snapshot is not None:
            cached.update(state=status_snapshot.state, messageCode=status_snapshot.message_code)
        return {'checks': checks, 'overview': overview, 'generatedAt': observed_at,
                'host': host, 'cachedEvidence': cached, 'packageVersions': dict(self.versions)}

    def report(self, profile, time_window, extended, consent, since='', until='', status_snapshot=None):
        failure = dict(reportText='', reportTitle='', reportSummary='', reportReady=False, reportError='The report request is invalid.')
        if consent is not True:
            failure['reportError'] = 'Consent is required before collecting a report.'
            return failure
        if not isinstance(profile, str) or profile not in PROFILES or type(extended) is not bool or not isinstance(time_window, str) or time_window not in TIMES:
            return failure
        try:
            provenance = snapshot_metadata(status_snapshot, self.now())
            if time_window == 'installation':
                operation = provenance['lastOperation']
                if not operation:
                    raise ValueError('installation time unavailable')
                moment = _timestamp(operation['observedAt'])
                args = time_arguments('custom', (moment - timedelta(minutes=5)).isoformat(),
                                      min(self.now(), moment + timedelta(minutes=5)).isoformat(), self.now())
            else:
                args = time_arguments(time_window, since, until, self.now())
        except (ValueError, TypeError, OverflowError):
            failure['reportError'] = ('The time of the last installation is unavailable. Choose a time range.' if time_window == 'installation' else 'Choose a valid time range with a timezone, at most 24 hours.')
            return failure
        if self.cancel is not None and self.cancel.is_set():
            failure['reportError'] = 'Collection was cancelled. No report was created.'
            return failure
        data = self.checks(status_snapshot)
        history = None
        if profile != 'system':
            journal = ['/usr/bin/journalctl', '--quiet', '--no-pager', '--output=json', '--lines=1001',
                       '--output-fields=__REALTIME_TIMESTAMP,_BOOT_ID,_SYSTEMD_UNIT,SYSLOG_IDENTIFIER,_EXE,_COMM,MESSAGE', *args]
            units = ['fprintd.service'] if profile in {'install', 'recognition'} else list(SOURCES)
            for index, unit in enumerate(units):
                if index:
                    journal.append('+')
                journal.append('_SYSTEMD_UNIT=' + unit)
            if profile in {'login', 'other'}:
                journal.extend(['+', '_EXE=/usr/bin/sudo', '_COMM=sudo'])
            history = parse_events(self.command(journal, 15), profile, extended)
        if self.cancel is not None and self.cancel.is_set():
            failure['reportError'] = 'Collection was cancelled. No report was created.'
            return failure
        lines = ['GOODIX MANAGER DIAGNOSTIC REPORT', 'Schema: 1', 'Profile: ' + PROFILES[profile],
                 'Collected: ' + data['generatedAt'], 'Time selection: ' + time_window,
                 'Event window filter: ' + ' '.join(args),
                 'Extended details: ' + ('requested' if extended else 'not requested'),
                 'Evidence: OBSERVED unless a limitation states otherwise.',
                 'Authentication and sensor behavior are not established by these static checks.', '']
        lines.append('Host: ' + json.dumps(data['host'], sort_keys=True))
        lines.append('Fedora package versions: ' + json.dumps(data['packageVersions'], sort_keys=True))
        lines.append('Current collection does not revalidate cached helper evidence.')
        lines.append('Cached software observation: ' + (data['cachedEvidence']['observedAt'] or 'unavailable'))
        if provenance['status'] is not None:
            lines.append('Cached software state: ' + provenance['status'].state + ' [' + provenance['status'].message_code + ']')
            lines.append('Cached runtime/payload/Manager versions: ' + json.dumps([provenance['status'].runtime_version, provenance['status'].payload_version, provenance['status'].package_version]))
        operation = provenance['lastOperation']
        if operation:
            lines.append('Cached operation: ' + operation['action'] + ' ' + operation['result'] + ' [' + operation['message_code'] + '] at ' + operation['observedAt'])
        else:
            lines.append('Previous operation phase/result/time: unavailable')
        if time_window == 'custom':
            lines.append('Requested range: ' + _timestamp(since).isoformat() + ' to ' + _timestamp(until).isoformat())
        for check in data['checks']:
            lines.extend([check['title'] + ': ' + check['outcome'] + ' [' + check['code'] + ']', check['detail']])
        if history is not None:
            lines.extend(['', 'History availability: ' + history['availability'],
                          'Unclassified records: ' + str(history['unclassified']),
                          'Missing or inaccessible history does not prove absence of problems.'])
            for event in history['events']:
                lines.append(event['time'] + ' ' + event['source'] + ': ' + event['category'])
            lines.append('Temporal ordering is observed; causal attribution remains UNKNOWN.')
            if extended:
                lines.append('Security history scope: relevant selected service events only; kernel/audit records were not collected.')
        lines.extend(['', 'Excluded: protected state, credentials, biometric data, raw messages and USB data.',
                      'No repair, sensor action or upload was performed. Review before sharing.'])
        text = '\n'.join(lines) + '\n'
        if len(text.encode()) > MAX_REPORT:
            failure['reportError'] = 'The report exceeded its limit. Choose a smaller time range.'
            return failure
        data.update(reportText=text, reportTitle=PROFILES[profile], reportSummary=data['overview'], reportReady=True, reportError='')
        return data


def collect_checks(status_snapshot=None, *, cancel=None):
    return Collector(cancel=cancel).checks(status_snapshot)


def collect_report(profile, time_window, extended, consent, since='', until='', status_snapshot=None, *, cancel=None):
    return Collector(cancel=cancel).report(profile, time_window, extended, consent, since, until, status_snapshot)


def save_report(path, text):
    """Explicit export: a new ordinary 0600 file, never replace an existing target."""
    if not isinstance(text, str) or not text.startswith('GOODIX MANAGER DIAGNOSTIC REPORT\n') or len(text.encode()) > MAX_REPORT:
        raise ValueError('invalid report')
    target = Path(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    # Never unlink by pathname after an I/O error: another process may have
    # replaced it. A partial 0600 file can remain; the caller reports failure.
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text.encode())
        stream.flush()
        os.fsync(stream.fileno())

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Behavioral regression for the real D293/04 scripts with isolated mocks."""

from __future__ import annotations

import os
import pathlib
import queue
import shutil
import stat
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
EXP = ROOT / "operator_kit/live_probe/experiments/d293-kde-new-user"
PAYLOAD = EXP / "payload.sh"
SANITIZER = EXP / "sanitize.sh"
NORMALIZER = EXP / "normalize-journal.sh"
RECOVER = EXP / "recover.sh"
HEAD = "a" * 40
LIBRARY = "b" * 64
RUN_ID = "d293-04-20260913T120000Z-" + "a" * 12


def epoch(action: str, *, stages: int = 0, contacts: int = 0) -> str:
    first_image = 0 if action == "FPI_DEVICE_ACTION_ENROLL" else 1
    return (
        "GOODIX_PRODUCTION_EPOCH_AUDIT "
        f"action={action} attempts=1 consumed=1 tls=1 first_image={first_image} "
        "secure_retry=0 post_retry=0 reopen=0 reset=0 clear_halt=0 "
        "persistent=0 outstanding=0 drained=1 context_closed=1 "
        f"enroll_stages={stages} enroll_contacts={contacts} enroll_retry_scans=0\n"
    )


class FakeCollector(threading.Thread):
    def __init__(
        self,
        control: pathlib.Path,
        results: pathlib.Path,
        duplicate: bool = False,
        journal_mode: str = "normal",
    ):
        super().__init__(daemon=True)
        self.control = control
        self.results = results
        self.duplicate = duplicate
        self.journal_mode = journal_mode
        self.requests: list[str] = []
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            for request in sorted(self.control.iterdir()):
                if not request.is_file() or request.name == "release":
                    continue
                if self.journal_mode == "ignore-control":
                    continue
                name = request.name
                request.unlink()
                self.requests.append(name)
                if name == "finish-enroll":
                    lines = epoch("FPI_DEVICE_ACTION_IDENTIFY")
                    if not self.duplicate:
                        lines += epoch("FPI_DEVICE_ACTION_ENROLL", stages=8, contacts=8)
                        if self.journal_mode == "extra-enroll":
                            lines += epoch("FPI_DEVICE_ACTION_ENROLL", stages=8, contacts=8)
                    (self.results / "enroll-journal.log").write_text(lines, encoding="utf-8")
                elif name.startswith("finish-verify-"):
                    number = name.rsplit("-", 1)[1]
                    line = epoch("FPI_DEVICE_ACTION_VERIFY")
                    if self.journal_mode == "missing-field":
                        line = line.replace(" drained=1", "")
                    (self.results / f"verify-{number}-journal.log").write_text(
                        line, encoding="utf-8"
                    )
                (self.results / f"{name}.env").write_text(
                    f"D293_04_CONTROL={name}\nD293_04_CONTROL_RESULT=PASS\n",
                    encoding="utf-8",
                )
            time.sleep(0.005)

    def stop(self) -> None:
        self.stop_event.set()
        self.join(timeout=2)


class PayloadRun:
    def __init__(
        self,
        verify: str = "match",
        duplicate: bool = False,
        list_mode: str = "normal",
        journal_mode: str = "normal",
    ):
        self.temp = tempfile.TemporaryDirectory(prefix="d293-04-script-test.", dir="/tmp")
        self.base = pathlib.Path(self.temp.name)
        self.commands = self.base / "commands"
        self.public = self.base / "public"
        self.control = self.public / "control"
        self.results = self.public / "results"
        self.work = self.base / "work"
        self.capture_root = self.base / "capture-root"
        self.capture = self.capture_root / "case" / "sanitized"
        for path in (self.commands, self.control, self.results, self.work, self.capture):
            path.mkdir(parents=True, exist_ok=True)
        self.telemetry = self.work / "telemetry.env"
        self.state = self.base / "mock-state"
        self.state.mkdir()
        self.verify = verify
        self.duplicate = duplicate
        self.list_mode = list_mode
        user = subprocess.check_output(["id", "-un"], text=True).strip()
        (self.public / "public.env").write_text(
            "\n".join(
                (
                    "D293_04_PHASE=READY_FOR_NEW_USER",
                    f"D293_04_PRODUCTION_HEAD={HEAD}",
                    f"D293_04_LIBRARY_SHA256={LIBRARY}",
                    f"D293_04_RUN_ID={RUN_ID}",
                    f"D293_04_CAPTURE_ROOT={self.capture_root}",
                    f"D293_04_TEST_USER={user}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (self.results / "runtime-audit.env").write_text(
            f"D293_04_RUNTIME_AUDIT head={HEAD} library_sha={LIBRARY} "
            f"manifest=pass run_id={RUN_ID}\n",
            encoding="utf-8",
        )
        self._write_commands()
        self.collector = FakeCollector(self.control, self.results, duplicate, journal_mode)

    def _executable(self, name: str, content: str) -> None:
        path = self.commands / name
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _write_commands(self) -> None:
        self._executable(
            "systemsettings",
            """
            #!/usr/bin/env bash
            set -euo pipefail
            state=${D293_MOCK_STATE:?}
            lock=$state/kcm-count
            count=0
            [[ ! -f $lock ]] || count=$(<"$lock")
            count=$((count + 1))
            printf '%s\n' "$count" >"$lock"
            while [[ ! -e $state/kcm-close-$count ]]; do sleep 0.01; done
            """,
        )
        self._executable(
            "fprintd-list",
            """
            #!/usr/bin/env bash
            set -euo pipefail
            state=${D293_MOCK_STATE:?}
            if [[ ${D293_LIST_MODE:-normal} == fail ]]; then
              exit 1
            fi
            case ${D293_LIST_MODE:-normal} in
              no-device) echo 'No devices available'; exit 1 ;;
              denied) echo 'PermissionDenied'; exit 1 ;;
              dbus) echo 'Failed to connect to D-Bus service'; exit 1 ;;
            esac
            if [[ ${D293_LIST_MODE:-normal} == malformed ]]; then
              printf '%s\n' 'found 1 devices' 'Using device /mock/device' 'User malformed output'
              exit 0
            fi
            lock=$state/list-count
            count=0
            [[ ! -f $lock ]] || count=$(<"$lock")
            count=$((count + 1))
            printf '%s\n' "$count" >"$lock"
            user=$1
            printf '%s\n' 'found 1 devices' 'Device at /mock/device' 'Using device /mock/device'
            if [[ $count -eq 2 ]]; then
              printf 'Fingerprints for user %s on Mock Goodix (press):\n' "$user"
              printf '%s\n' ' - #0: left-index-finger'
            else
              printf 'User %s has no fingers enrolled for Mock Goodix.\n' "$user"
            fi
            """,
        )
        self._executable(
            "fprintd-verify",
            """
            #!/usr/bin/env bash
            set -euo pipefail
            state=${D293_MOCK_STATE:?}
            lock=$state/verify-count
            count=0
            [[ ! -f $lock ]] || count=$(<"$lock")
            count=$((count + 1))
            printf '%s\n' "$count" >"$lock"
            IFS=, read -r -a outcomes <<<"${D293_VERIFY_SEQUENCE:-match}"
            outcome=${outcomes[$((count - 1))]:-no-match}
            case $outcome in
              match) echo 'Verify result: verify-match (done)' ;;
              no-match) echo 'Verify result: verify-no-match (done)' ;;
              busy) echo 'Device was already claimed' >&2; exit 1 ;;
              denied) echo 'PermissionDenied' >&2; exit 1 ;;
              *) exit 1 ;;
            esac
            """,
        )

    def start(self) -> subprocess.Popen[str]:
        env = os.environ.copy()
        env.update(
            {
                "LIVE_PROBE_MODE": "offline-script-test",
                "LIVE_PROBE_WORK_DIR": str(self.work),
                "LIVE_PROBE_CAPTURE_DIR": str(self.capture),
                "LIVE_PROBE_TELEMETRY_FILE": str(self.telemetry),
                "D293_04_PUBLIC_ROOT": str(self.public),
                "D293_04_TEST_COMMAND_DIR": str(self.commands),
                "D293_MOCK_STATE": str(self.state),
                "D293_VERIFY_SEQUENCE": self.verify,
                "D293_LIST_MODE": self.list_mode,
            }
        )
        self.collector.start()
        command = (
            'set -o pipefail; "$1" --max-actions 5 --max-contacts 24 '
            '--max-retries 0 --timeout-seconds 1800 2>&1 | "$2"'
        )
        return subprocess.Popen(
            ["bash", "-c", command, "d293-test", str(PAYLOAD), str(SANITIZER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

    def close_kcm(self, number: int) -> None:
        (self.state / f"kcm-close-{number}").touch()

    def cleanup(self) -> None:
        self.collector.stop()
        for number in (1, 2):
            self.close_kcm(number)
        self.temp.cleanup()


def wait_line(proc: subprocess.Popen[str], token: str, timeout: float = 4.0) -> list[str]:
    assert proc.stdout is not None
    output: list[str] = []
    received: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        line = proc.stdout.readline()
        received.put(line if line else None)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        try:
            line = received.get(timeout=min(0.5, deadline - time.monotonic()))
        except queue.Empty:
            continue
        if line is None:
            break
        output.append(line)
        if token in line:
            return output
    raise AssertionError(f"prompt {token!r} not visible before input; output={output!r}")


def send(proc: subprocess.Popen[str], value: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write(value + "\n")
    proc.stdin.flush()


def run_mocked_root_recovery(scenario: str, twice: bool = False) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, tempfile.TemporaryDirectory[str]]:
    """Execute the actual recover() body with every privileged external mocked."""
    holder: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(
        prefix="d293-04-script-test.", dir="/tmp"
    )
    base = pathlib.Path(holder.name)
    helper = (EXP / "root-helper.sh").read_text(encoding="utf-8")
    helper = helper.replace('[[ $EUID -eq 0 ]] || fail root_required\n', "")
    helper = helper.split("\ncase ${1:-} in\n", 1)[0]
    mock_fprint = base / "fprint"
    (mock_fprint / "d293-phase-b-test").mkdir(parents=True)
    helper = helper.replace("/var/lib/fprint", str(mock_fprint))
    current_user = subprocess.check_output(["id", "-un"], text=True).strip()
    current_uid = os.getuid()
    current_gid = os.getgid()
    private = base / "private"
    public = base / "public"
    capture_base = base / "captures"
    run_root = capture_base / RUN_ID
    capture = run_root / "capture"
    for path in (private, public, capture):
        path.mkdir(parents=True, exist_ok=True)
    (capture / "evidence.env").write_text("CAPTURE=PRESERVED\n", encoding="utf-8")
    metadata = run_root / "run.env"
    test_uid = 29991
    recorded_uid = test_uid + 1 if scenario == "identity-mismatch" else test_uid
    metadata.write_text(
        "\n".join(
            (
                f"D293_04_RUN_ID={RUN_ID}",
                "D293_04_TEST_USER=d293-phase-b-test",
                f"D293_04_TEST_UID={recorded_uid}",
                "D293_04_TEST_GID=29991",
                "D293_04_TEST_HOME=/home/d293-phase-b-test",
                f"D293_04_ORIGINAL_USER={current_user}",
                f"D293_04_ORIGINAL_UID={current_uid}",
                f"D293_04_ORIGINAL_GID={current_gid}",
                f"D293_04_PRODUCTION_HEAD={HEAD}",
                "D293_04_ORIGINAL_PRINCIPAL_DIGEST=baseline-digest",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    metadata.chmod(0o400)
    script = helper + textwrap.dedent(
        f"""

        private={private!s}
        public={public!s}
        mountpoint_path={public!s}/repo
        capture_base={capture_base!s}
        unit=mock-supervisor.service
        test_user=d293-phase-b-test
        repo={ROOT!s}
        SCENARIO={scenario}
        PKEXEC_UID={current_uid}
        ACCOUNT_PRESENT=1
        MOUNT_ACTIVE=0
        [[ $SCENARIO != umount-fail ]] || MOUNT_ACTIVE=1

        systemctl() {{
          if [[ $1 == is-active ]]; then
            [[ $SCENARIO == supervisor-active ]] && return 0
            return 1
          fi
          return 0
        }}
        sleep() {{ :; }}
        rollback_runtime() {{ [[ $SCENARIO != rollback-fail ]]; }}
        resolve_incomplete_run() {{
          if [[ -f {run_root!s}/recovery.env ]] &&
             grep -Fx D293_04_FINAL_RECOVERY=PASS {run_root!s}/recovery.env >/dev/null; then
            return 1
          fi
          printf '%s\\n' {metadata!s}
        }}
        getent() {{
          [[ $1 == passwd ]] || return 1
          case $2 in
            {current_uid}|{current_user}) printf '{current_user}:x:{current_uid}:{current_gid}::/home/{current_user}:/bin/bash\\n' ;;
            d293-phase-b-test)
              [[ $ACCOUNT_PRESENT -eq 1 ]] || return 2
              printf 'd293-phase-b-test:x:{test_uid}:29991::/home/d293-phase-b-test:/bin/bash\\n'
              ;;
            *) return 2 ;;
          esac
        }}
        id() {{
          case $1:$2 in
            -u:{current_user}) echo {current_uid} ;;
            -g:{current_user}) echo {current_gid} ;;
            -u:d293-phase-b-test) echo {test_uid} ;;
            -g:d293-phase-b-test) echo 29991 ;;
            *) return 1 ;;
          esac
        }}
        mountpoint() {{ [[ $MOUNT_ACTIVE -eq 1 ]]; }}
        umount() {{
          [[ $SCENARIO != umount-fail ]] || return 1
          MOUNT_ACTIVE=0
        }}
        pgrep() {{ return 1; }}
        find() {{
          if [[ $1 == {mock_fprint!s}/d293-phase-b-test ]]; then
            [[ $SCENARIO == residual-template ]] && echo {mock_fprint!s}/d293-phase-b-test/template
            return 0
          fi
          if [[ $1 == {capture!s} ]]; then return 0; fi
          command /usr/bin/find "$@"
        }}
        chown() {{ return 0; }}
        userdel() {{ ACCOUNT_PRESENT=0; return 0; }}
        principal_digest() {{ echo baseline-digest; }}
        audit_d285() {{ return 0; }}
        remove_tree() {{ return 0; }}

        rc=0
        recover || rc=$?
        printf 'MOCK_RECOVERY_RC=%s\\n' "$rc"
        """
    )
    if twice:
        script += "rc2=0\nrecover || rc2=$?\nprintf 'MOCK_RECOVERY_SECOND_RC=%s\\n' \"$rc2\"\n"
    harness = base / "root-recovery-harness.sh"
    harness.write_text(script, encoding="utf-8")
    harness.chmod(0o700)
    result = subprocess.run([str(harness)], text=True, capture_output=True, timeout=8)
    return result, capture, holder


class D293OperatorScriptsTest(unittest.TestCase):
    def drive_enrollment_closed(self, fixture: PayloadRun) -> subprocess.Popen[str]:
        proc = fixture.start()
        wait_line(proc, "RISPOSTA_ATTESA=ENROLLMENT")
        send(proc, "ENROLLMENT KCM COMPLETATO")
        wait_line(proc, "RISPOSTA_ATTESA=KCM CHIUSO DOPO ENROLLMENT")
        fixture.close_kcm(1)
        send(proc, "KCM CHIUSO DOPO ENROLLMENT")
        return proc

    def run_success_flow(self, sequence: str) -> tuple[PayloadRun, subprocess.Popen[str], str]:
        fixture = PayloadRun(verify=sequence)
        proc = fixture.start()
        wait_line(proc, "RISPOSTA_ATTESA=ENROLLMENT")
        send(proc, "ENROLLMENT KCM COMPLETATO")
        wait_line(proc, "RISPOSTA_ATTESA=KCM CHIUSO DOPO ENROLLMENT")
        fixture.close_kcm(1)
        send(proc, "KCM CHIUSO DOPO ENROLLMENT")
        if sequence.startswith("no-match"):
            wait_line(proc, "RISPOSTA_ATTESA=TENTATIVO 2")
            send(proc, "TENTATIVO 2")
        if sequence.startswith("no-match,no-match"):
            wait_line(proc, "RISPOSTA_ATTESA=TENTATIVO 3")
            send(proc, "TENTATIVO 3")
        wait_line(proc, "RISPOSTA_ATTESA=IMPRONTA KCM CANCELLATA")
        send(proc, "IMPRONTA KCM CANCELLATA")
        wait_line(proc, "RISPOSTA_ATTESA=KCM CHIUSO DOPO DELETE")
        fixture.close_kcm(2)
        send(proc, "KCM CHIUSO DOPO DELETE")
        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.stdout is not None
        tail = proc.stdout.read()
        proc.stdout.close()
        proc.wait(timeout=5)
        return fixture, proc, tail

    def test_match_first_stops_and_reopens_kcm_only_for_delete(self) -> None:
        fixture, proc, tail = self.run_success_flow("match")
        try:
            self.assertEqual(proc.returncode, 0, tail)
            self.assertEqual(
                fixture.collector.requests,
                ["arm-enroll", "finish-enroll", "arm-verify-1", "finish-verify-1", "complete-verify"],
            )
            telemetry = fixture.telemetry.read_text(encoding="utf-8")
            self.assertIn("ACTION_ATTEMPT_COUNT=3\n", telemetry)
            self.assertIn("CONTACT_COUNT=10\n", telemetry)
            self.assertIn("D293_04_OBSERVATION_COMPLETE=true\n", telemetry)
            self.assertIn("D293_04_PAYLOAD_OUTCOME=KDE_NEW_USER_MATCH", tail)
        finally:
            fixture.cleanup()

    def test_no_match_then_match_never_requests_third_or_fourth(self) -> None:
        fixture, proc, tail = self.run_success_flow("no-match,match")
        try:
            self.assertEqual(proc.returncode, 0, tail)
            self.assertNotIn("arm-verify-3", fixture.collector.requests)
            self.assertFalse(any("verify-4" in item for item in fixture.collector.requests))
        finally:
            fixture.cleanup()

    def test_three_no_match_is_terminal_and_no_fourth_request(self) -> None:
        fixture, proc, tail = self.run_success_flow("no-match,no-match,no-match")
        try:
            self.assertEqual(proc.returncode, 21, tail)
            self.assertIn("arm-verify-3", fixture.collector.requests)
            self.assertFalse(any("verify-4" in item for item in fixture.collector.requests))
            self.assertIn("PAYLOAD_OUTCOME=KDE_NEW_USER_NO_MATCH_SERIES", fixture.telemetry.read_text())
        finally:
            fixture.cleanup()

    def test_duplicate_is_distinct_and_does_not_enroll_or_retry(self) -> None:
        fixture = PayloadRun(duplicate=True)
        proc = fixture.start()
        try:
            wait_line(proc, "RISPOSTA_ATTESA=ENROLLMENT")
            send(proc, "DUPLICATO RILEVATO")
            wait_line(proc, "RISPOSTA_ATTESA=KCM CHIUSO DOPO ENROLLMENT")
            fixture.close_kcm(1)
            send(proc, "KCM CHIUSO DOPO ENROLLMENT")
            assert proc.stdin is not None
            proc.stdin.close()
            assert proc.stdout is not None
            output = proc.stdout.read()
            proc.stdout.close()
            proc.wait(timeout=5)
            self.assertEqual(proc.returncode, 20, output)
            self.assertEqual(fixture.collector.requests, ["arm-enroll", "finish-enroll"])
            self.assertIn("PAYLOAD_OUTCOME=D293_04_DUPLICATE_RECOGNIZED", fixture.telemetry.read_text())
        finally:
            fixture.cleanup()

    def test_list_failure_is_not_zero_and_writes_partial_telemetry(self) -> None:
        fixture = PayloadRun(list_mode="fail")
        proc = fixture.start()
        try:
            output, _ = proc.communicate(timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("reason=list_technical_error", output)
            telemetry = fixture.telemetry.read_text(encoding="utf-8")
            self.assertIn("D293_04_OBSERVATION_COMPLETE=false", telemetry)
            self.assertIn("D293_04_FAILURE_REASON=list_technical_error", telemetry)
            self.assertIn("RETRY_COUNT=UNKNOWN", telemetry)
            self.assertIn("PERSISTENT_WRITE_FAMILY_COUNT=UNKNOWN", telemetry)
            self.assertIn("OUTSTANDING_COUNT=UNKNOWN", telemetry)
        finally:
            fixture.cleanup()

    def test_malformed_list_is_not_accepted_as_zero(self) -> None:
        fixture = PayloadRun(list_mode="malformed")
        proc = fixture.start()
        try:
            output, _ = proc.communicate(timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("reason=list_malformed_output", output)
            self.assertIn("D293_04_OBSERVATION_COMPLETE=false", fixture.telemetry.read_text())
        finally:
            fixture.cleanup()

    def test_list_error_classes_are_not_zero(self) -> None:
        for mode, reason in (
            ("no-device", "list_no_device"),
            ("denied", "list_permission_denied"),
            ("dbus", "list_service_or_dbus_error"),
        ):
            with self.subTest(mode=mode):
                fixture = PayloadRun(list_mode=mode)
                proc = fixture.start()
                try:
                    output, _ = proc.communicate(timeout=5)
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn(f"reason={reason}", output)
                    self.assertIn("CONTACT_COUNT=0", fixture.telemetry.read_text())
                finally:
                    fixture.cleanup()

    def test_eof_is_reported_at_visible_prompt(self) -> None:
        fixture = PayloadRun()
        proc = fixture.start()
        try:
            wait_line(proc, "RISPOSTA_ATTESA=ENROLLMENT")
            assert proc.stdin is not None
            proc.stdin.close()
            assert proc.stdout is not None
            output = proc.stdout.read()
            proc.stdout.close()
            proc.wait(timeout=5)
            self.assertIn("reason=terminal_input_closed", output)
            self.assertIn("D293_04_OBSERVATION_COMPLETE=false", fixture.telemetry.read_text())
        finally:
            fixture.cleanup()

    def test_control_timeout_is_explicit(self) -> None:
        fixture = PayloadRun(journal_mode="ignore-control")
        proc = fixture.start()
        try:
            output, _ = proc.communicate(timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("reason=control_arm-enroll_timeout", output)
        finally:
            fixture.cleanup()

    def test_extra_ui_enrollment_is_detected_and_live_stays_blocked(self) -> None:
        fixture = PayloadRun(journal_mode="extra-enroll")
        proc = self.drive_enrollment_closed(fixture)
        try:
            assert proc.stdin is not None
            proc.stdin.close()
            assert proc.stdout is not None
            output = proc.stdout.read()
            proc.stdout.close()
            proc.wait(timeout=5)
            self.assertIn("reason=enrollment_action_cardinality", output)
            self.assertNotIn("arm-verify-1", fixture.collector.requests)
            self.assertIn("LIVE_CAPABLE=false", (EXP / "experiment.conf").read_text())
        finally:
            fixture.cleanup()

    def test_missing_audit_field_fails_closed(self) -> None:
        fixture = PayloadRun(journal_mode="missing-field")
        proc = self.drive_enrollment_closed(fixture)
        try:
            assert proc.stdin is not None
            proc.stdin.close()
            assert proc.stdout is not None
            output = proc.stdout.read()
            proc.stdout.close()
            proc.wait(timeout=5)
            self.assertIn("reason=verify_epoch_invalid", output)
            self.assertIn("D293_04_OBSERVATION_COMPLETE=false", fixture.telemetry.read_text())
        finally:
            fixture.cleanup()

    def test_verify_errors_are_distinct(self) -> None:
        for outcome, reason in (
            ("busy", "verify_device_busy"),
            ("denied", "verify_permission_denied"),
            ("technical", "verify_technical_error"),
        ):
            with self.subTest(outcome=outcome):
                fixture = PayloadRun(verify=outcome)
                proc = self.drive_enrollment_closed(fixture)
                try:
                    assert proc.stdin is not None
                    proc.stdin.close()
                    assert proc.stdout is not None
                    output = proc.stdout.read()
                    proc.stdout.close()
                    proc.wait(timeout=5)
                    self.assertIn(f"reason={reason}", output)
                    self.assertNotIn("arm-verify-2", fixture.collector.requests)
                finally:
                    fixture.cleanup()

    def test_claim_still_held_is_reported_before_verify(self) -> None:
        fixture = PayloadRun()
        proc = fixture.start()
        try:
            wait_line(proc, "RISPOSTA_ATTESA=ENROLLMENT")
            send(proc, "ENROLLMENT KCM COMPLETATO")
            wait_line(proc, "RISPOSTA_ATTESA=KCM CHIUSO DOPO ENROLLMENT")
            send(proc, "KCM CHIUSO DOPO ENROLLMENT")
            assert proc.stdin is not None
            proc.stdin.close()
            assert proc.stdout is not None
            output = proc.stdout.read()
            proc.stdout.close()
            proc.wait(timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("reason=kcm_process_still_holds_session", output)
            self.assertNotIn("arm-verify-1", fixture.collector.requests)
        finally:
            fixture.cleanup()

    def test_normalizer_rejects_missing_duplicate_and_accepts_prefixed_message(self) -> None:
        marker = epoch("FPI_DEVICE_ACTION_VERIFY").strip()
        prefixed = f"2026-09-13T13:00:00+0200 host fprintd[123]: {marker}\n"
        accepted = subprocess.run([str(NORMALIZER)], input=prefixed, text=True, capture_output=True)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted.stdout, marker + "\n")
        for rejected in ("unrelated message\n", "", f"{marker} {marker}\n"):
            result = subprocess.run([str(NORMALIZER)], input=rejected, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_classifier_is_self_contained_and_rejects_provenance_drift(self) -> None:
        fixture, proc, tail = self.run_success_flow("match")
        try:
            self.assertEqual(proc.returncode, 0, tail)
            shutil.copy2(fixture.telemetry, fixture.capture / "telemetry.env")
            (fixture.capture / "context.env").write_text(
                f"LIVE_PROBE_MODE=operator-run\nLIVE_PROBE_BASELINE={HEAD}\n",
                encoding="utf-8",
            )
            (fixture.capture / "common-classification.env").write_text(
                "LIVE_PROBE_COMMON_CLASSIFICATION=PASS\n",
                encoding="utf-8",
            )
            (fixture.capture / "cleanup.log").write_text(
                "D293_04_RUNTIME_ROLLBACK=PASS\n"
                "D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED=true\n"
                "D293_04_TEST_STORAGE_CLEAN=true\n",
                encoding="utf-8",
            )
            valid = subprocess.run(
                [str(EXP / "classify.sh"), str(fixture.capture)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("PASS_LIVE", valid.stdout)

            cases = {
                "missing-marker": lambda path: (path / "runtime-audit.env").unlink(),
                "duplicate-marker": lambda path: (path / "runtime-audit.env").write_text(
                    (path / "runtime-audit.env").read_text() * 2, encoding="utf-8"
                ),
                "wrong-marker-sha": lambda path: (path / "runtime-audit.env").write_text(
                    (path / "runtime-audit.env").read_text().replace(LIBRARY, "c" * 64),
                    encoding="utf-8",
                ),
                "wrong-head": lambda path: (path / "context.env").write_text(
                    f"LIVE_PROBE_MODE=operator-run\nLIVE_PROBE_BASELINE={'d' * 40}\n",
                    encoding="utf-8",
                ),
                "incomplete": lambda path: (path / "runtime-provenance.env").write_text(
                    f"D293_04_PRODUCTION_HEAD={HEAD}\n",
                    encoding="utf-8",
                ),
                "missing-telemetry": lambda path: (path / "telemetry.env").unlink(),
            }
            for name, corrupt in cases.items():
                with self.subTest(name=name):
                    target = fixture.base / f"classifier-{name}"
                    shutil.copytree(fixture.capture, target)
                    corrupt(target)
                    rejected = subprocess.run(
                        [str(EXP / "classify.sh"), str(target)],
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(rejected.returncode, 0)
        finally:
            fixture.cleanup()

    def test_sanitizer_flushes_prompt_before_input(self) -> None:
        command = "printf 'DOMANDA CON NEWLINE\\n'; read -r answer; printf 'RISPOSTA=%s\\n' \"$answer\""
        pipeline = 'set -o pipefail; bash -c "$1" 2>&1 | "$2"'
        proc = subprocess.Popen(
            ["bash", "-c", pipeline, "d293-stream", command, str(SANITIZER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        wait_line(proc, "DOMANDA CON NEWLINE")
        send(proc, "OK")
        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.stdout is not None
        self.assertIn("RISPOSTA=OK", proc.stdout.read())
        proc.stdout.close()
        self.assertEqual(proc.wait(timeout=3), 0)

    def test_prepare_blocks_before_build_or_pkexec(self) -> None:
        result = subprocess.run([str(EXP / "prepare.sh")], text=True, capture_output=True)
        self.assertEqual(result.returncode, 3)
        self.assertIn("D293_04_PREPARE=BLOCKED", result.stderr)
        self.assertIn("nessuna predisposizione", result.stderr)
        prepare = (EXP / "prepare.sh").read_text(encoding="utf-8")
        for forbidden in ("pkexec", "sysfs", "build.sh", "systemctl", "mount "):
            self.assertNotIn(forbidden, prepare)

    def test_common_operator_run_rejects_before_capture_or_runtime_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d293-04-script-test.", dir="/tmp") as tmp:
            capture = pathlib.Path(tmp) / "must-not-exist"
            result = subprocess.run(
                [
                    str(ROOT / "operator_kit/live_probe/run.sh"),
                    "d293-kde-new-user",
                    "--operator-run",
                    "--capture-root",
                    str(capture),
                ],
                cwd="/tmp",
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("LIVE_PROBE_ERROR=EXPERIMENT_NOT_LIVE_CAPABLE", result.stderr)
            self.assertFalse(capture.exists())

    def test_recover_frontend_propagates_helper_failure_and_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d293-04-script-test.", dir="/tmp") as tmp:
            mock = pathlib.Path(tmp) / "pkexec"
            mock.write_text("#!/usr/bin/env bash\necho D293_04_RUNTIME_ROLLBACK=FAIL\nexit 7\n")
            mock.chmod(0o700)
            env = os.environ.copy()
            env["PATH"] = f"{tmp}:{env['PATH']}"
            failed = subprocess.run([str(RECOVER)], text=True, capture_output=True, env=env)
            self.assertEqual(failed.returncode, 7)
            mock.write_text(
                "#!/usr/bin/env bash\n"
                "echo D293_04_RECOVERY_STATE=ALREADY_COMPLETE\n"
                "echo D293_04_FINAL_RECOVERY=PASS\n"
            )
            mock.chmod(0o700)
            passed = subprocess.run([str(RECOVER)], text=True, capture_output=True, env=env)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertIn("D293_04_FINAL_RECOVERY=PASS", passed.stdout)

    def test_actual_root_recover_propagates_rollback_and_supervisor_failures(self) -> None:
        for scenario in ("rollback-fail", "supervisor-active"):
            with self.subTest(scenario=scenario):
                result, _capture, holder = run_mocked_root_recovery(scenario)
                try:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("D293_04_FINAL_RECOVERY=FAIL", result.stdout)
                    self.assertIn("MOCK_RECOVERY_RC=1", result.stdout)
                finally:
                    holder.cleanup()

    def test_actual_root_recover_fails_on_template_umount_and_identity(self) -> None:
        expected = {
            "residual-template": "test_storage_remains_use_kcm",
            "umount-fail": "D293_04_FINAL_RECOVERY=FAIL",
            "identity-mismatch": "test_account_identity_drift",
        }
        for scenario, marker in expected.items():
            with self.subTest(scenario=scenario):
                result, capture, holder = run_mocked_root_recovery(scenario)
                try:
                    self.assertIn(marker, result.stdout + result.stderr)
                    self.assertNotIn("MOCK_RECOVERY_RC=0", result.stdout)
                    self.assertTrue((capture / "evidence.env").exists())
                finally:
                    holder.cleanup()

    def test_actual_root_recover_preserves_capture_and_is_idempotent(self) -> None:
        result, capture, holder = run_mocked_root_recovery("success", twice=True)
        try:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("MOCK_RECOVERY_RC=0", result.stdout)
            self.assertIn("MOCK_RECOVERY_SECOND_RC=0", result.stdout)
            self.assertGreaterEqual(result.stdout.count("D293_04_FINAL_RECOVERY=PASS"), 2)
            self.assertEqual((capture / "evidence.env").read_text(), "CAPTURE=PRESERVED\n")
            recovery = capture.parent / "recovery.env"
            self.assertIn("D293_04_FINAL_RECOVERY=PASS", recovery.read_text())
        finally:
            holder.cleanup()

    def test_permission_shape_and_recovery_guards_are_present(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d293-04-script-test.", dir="/tmp") as tmp:
            base = pathlib.Path(tmp)
            private = base / "private"
            public = base / "public"
            subprocess.run(
                [
                    "bash",
                    "-c",
                    'umask 077; install -d -m 0700 "$1"; install -d -m 0755 "$2"',
                    "d293-permissions",
                    str(private),
                    str(public),
                ],
                check=True,
            )
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(public.stat().st_mode), 0o755)
            secret = private / "state.env"
            metadata = public / "public.env"
            secret.write_text("protected\n")
            metadata.write_text("public\n")
            secret.chmod(0o000)
            metadata.chmod(0o444)
            self.assertFalse(os.access(secret, os.R_OK))
            self.assertTrue(os.access(metadata, os.R_OK))
        helper = (EXP / "root-helper.sh").read_text(encoding="utf-8")
        self.assertIn('flock 9', helper)
        self.assertNotIn('rollback_runtime || true', helper)
        self.assertIn('! systemctl is-active --quiet "$unit" || supervisor_rc=1', helper)
        self.assertIn('mountpoint -q "$mountpoint_path" && result=FAIL', helper)
        self.assertIn('test_account_identity_drift', helper)
        self.assertIn('D293_04_FINAL_RECOVERY_IDEMPOTENT', helper)


if __name__ == "__main__":
    unittest.main(verbosity=2)

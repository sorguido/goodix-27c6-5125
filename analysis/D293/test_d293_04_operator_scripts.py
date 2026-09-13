#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Behavioral regression for the real D293/04 scripts with isolated mocks."""

from __future__ import annotations

import os
import pathlib
import queue
import hashlib
import shlex
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
                    if self.journal_mode == "duplicate-action-field":
                        lines = lines.replace(
                            "action=FPI_DEVICE_ACTION_ENROLL",
                            "action=FPI_DEVICE_ACTION_ENROLL "
                            "action=FPI_DEVICE_ACTION_IDENTIFY",
                            1,
                        )
                    (self.results / "enroll-journal.log").write_text(lines, encoding="utf-8")
                elif name.startswith("finish-verify-"):
                    number = name.rsplit("-", 1)[1]
                    line = epoch("FPI_DEVICE_ACTION_VERIFY")
                    if self.journal_mode == "missing-field":
                        line = line.replace(" drained=1", "")
                    (self.results / f"verify-{number}-journal.log").write_text(
                        line, encoding="utf-8"
                    )
                elif name == "finish-delete":
                    (self.results / "delete-journal.log").write_text("", encoding="utf-8")
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


def root_helper_prefix() -> str:
    helper = (EXP / "root-helper.sh").read_text(encoding="utf-8")
    helper = helper.replace('[[ $EUID -eq 0 ]] || fail root_required\n', "")
    return helper.split("\ncase ${1:-} in\n", 1)[0]


def run_mocked_root_recovery(scenario: str, twice: bool = False) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, tempfile.TemporaryDirectory[str]]:
    """Execute the actual recover() body with every privileged external mocked."""
    holder: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(
        prefix="d293-04-script-test.", dir="/tmp"
    )
    base = pathlib.Path(holder.name)
    helper = root_helper_prefix()
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
    capture_base.chmod(0o711)
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
                f"D293_04_ORIGINAL_PRINCIPAL_DIGEST={'c' * 64}",
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
        capture_base_owner="$EUID:$(id -g)"
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
        principal_digest() {{ echo {'c' * 64}; }}
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


def run_compositional_recovery(
    scenario: str,
) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, tempfile.TemporaryDirectory[str]]:
    """Run real rollback/resolve/recover/remove functions with external effects mocked."""
    holder: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(
        prefix="d293-04-script-test.", dir="/tmp"
    )
    base = pathlib.Path(holder.name)
    private = base / "private"
    public = base / "public"
    capture_base = base / "captures"
    run_root = capture_base / RUN_ID
    capture = run_root / "capture"
    dropin = base / "dropin" / "override.conf"
    fprint = base / "fprint"
    original_fprint = fprint / subprocess.check_output(["id", "-un"], text=True).strip()
    test_fprint = fprint / "d293-phase-b-test"
    no_run = scenario == "no-attributed-run"
    for path in (private / "runtime", public / "results", dropin.parent, test_fprint):
        path.mkdir(parents=True, exist_ok=True)
    (private / "runtime" / "candidate").write_text("runtime\n", encoding="utf-8")
    (private / "wrapper").write_text("wrapper\n", encoding="utf-8")
    dropin.write_text("dropin\n", encoding="utf-8")
    if scenario == "residual-template":
        (test_fprint / "template").write_text("synthetic\n", encoding="utf-8")
    if scenario == "digest-sticky":
        original_fprint.mkdir(parents=True)
        (original_fprint / "drift").write_text("synthetic-drift\n", encoding="utf-8")
    current_user = subprocess.check_output(["id", "-un"], text=True).strip()
    current_uid = os.getuid()
    current_gid = os.getgid()
    test_uid = 29991
    capture_root = run_root / "capture"
    metadata = run_root / "run.env"
    if not no_run:
        capture.mkdir(parents=True)
        capture_base.chmod(0o711)
        (capture / "evidence.env").write_text("CAPTURE=PRESERVED\n", encoding="utf-8")
        digest_value = "malformed" if scenario == "metadata-digest-malformed-sticky" else "ABSENT"
        original_gid_value = (
            str(current_gid + 1)
            if scenario == "metadata-original-gid-mismatch-sticky"
            else str(current_gid)
        )
        metadata_lines = [
            f"D293_04_RUN_ID={RUN_ID}",
            "D293_04_TEST_USER=d293-phase-b-test",
            f"D293_04_TEST_UID={test_uid}",
            "D293_04_TEST_GID=29991",
            "D293_04_TEST_HOME=/home/d293-phase-b-test",
            f"D293_04_ORIGINAL_USER={current_user}",
            f"D293_04_ORIGINAL_UID={current_uid}",
            f"D293_04_PRODUCTION_HEAD={HEAD}",
        ]
        if scenario != "metadata-original-gid-missing-sticky":
            metadata_lines.append(f"D293_04_ORIGINAL_GID={original_gid_value}")
        if scenario != "metadata-digest-missing-sticky":
            metadata_lines.append(f"D293_04_ORIGINAL_PRINCIPAL_DIGEST={digest_value}")
        metadata.write_text(
            "\n".join(metadata_lines) + "\n",
            encoding="utf-8",
        )
        metadata.chmod(0o400)
    (private / "state.env").write_text(
        "\n".join(
            (
                f"PRODUCTION_HEAD={HEAD}",
                f"LIBRARY_SHA256={LIBRARY}",
                f"ORIGINAL_USER={current_user}",
                "ORIGINAL_PRINCIPAL_DIGEST=ABSENT",
                "SERVICE_BEFORE=inactive",
                f"REPO_ROOT={ROOT}",
                f"RUN_ID={RUN_ID}",
                f"CAPTURE_ROOT={capture_root}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (private / "state.env").chmod(0o600)
    if scenario in ("legacy-fail-retry", "legacy-integrity-sticky"):
        preserved = "false" if scenario == "legacy-integrity-sticky" else "true"
        (private / "rollback.complete").write_text(
            "D293_04_RUNTIME_ROLLBACK=FAIL\n"
            f"D293_04_PREEXISTING_PRINCIPAL_CONTENT_AND_METADATA_PRESERVED={preserved}\n"
            "D293_04_TEST_STORAGE=REMAINS\n"
            "D293_04_D285_D286_POST_ROLLBACK=PASS\n",
            encoding="utf-8",
        )
        (private / "rollback.complete").chmod(0o444)

    helper = root_helper_prefix().replace("/var/lib/fprint", str(fprint))
    script = helper + textwrap.dedent(
        f"""

        private={shlex.quote(str(private))}
        public={shlex.quote(str(public))}
        mountpoint_path={shlex.quote(str(public / 'repo'))}
        capture_base={shlex.quote(str(capture_base))}
        capture_base_owner="$EUID:$(id -g)"
        dropin={shlex.quote(str(dropin))}
        unit=mock-supervisor.service
        test_user=d293-phase-b-test
        repo={shlex.quote(str(ROOT))}
        PKEXEC_UID={current_uid}
        ACCOUNT_PRESENT={0 if no_run else 1}
        CAPTURE_OWNER=test
        SERVICE_ACTIVE=1
        SUPERVISOR_ACTIVE=0
        MOUNT_ACTIVE=0
        STOP_FAILURES=0
        PUBLIC_REMOVE_FAILURES=0
        PRIVATE_REMOVE_FAILURES=0
        INTENT_COMPLETE_FAILURES=0
        RECOVERY_PUBLISH_FAILURES=0
        IDENTITY_DRIFT=0
        INTENT_FAIL_MARKER={shlex.quote(str(base / 'fail-intent-complete-once'))}
        RECOVERY_FAIL_MARKER={shlex.quote(str(base / 'fail-recovery-publish-once'))}

        install() {{
          local -a filtered=()
          while (( $# )); do
            case $1 in -o|-g) shift 2 ;; *) filtered+=("$1"); shift ;; esac
          done
          command /usr/bin/install "${{filtered[@]}}"
        }}
        cp() {{
          local destination=${{!#}}
          [[ ! -e $destination ]] || chmod u+w "$destination"
          command /usr/bin/cp "$@"
        }}
        systemctl() {{
          case $1 in
            is-active)
              if [[ $3 == "$unit" ]]; then [[ $SUPERVISOR_ACTIVE -eq 1 ]]; return; fi
              [[ $3 == fprintd.service && $SERVICE_ACTIVE -eq 1 ]]
              ;;
            stop)
              if [[ $2 == fprintd.service ]]; then
                if (( STOP_FAILURES > 0 )); then STOP_FAILURES=$((STOP_FAILURES - 1)); return 1; fi
                SERVICE_ACTIVE=0
              fi
              ;;
            start) [[ $2 != fprintd.service ]] || SERVICE_ACTIVE=1 ;;
            kill) SUPERVISOR_ACTIVE=0 ;;
            daemon-reload|reset-failed) return 0 ;;
            *) return 0 ;;
          esac
        }}
        sleep() {{ :; }}
        audit_d285() {{ return 0; }}
        getent() {{
          [[ $1 == passwd ]] || return 1
          case $2 in
            {current_uid}|{current_user})
              printf '{current_user}:x:{current_uid}:{current_gid}::/home/{current_user}:/bin/bash\\n'
              ;;
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
            -u:d293-phase-b-test)
              if [[ $IDENTITY_DRIFT -eq 1 ]]; then echo {test_uid + 1}; else echo {test_uid}; fi
              ;;
            -g:d293-phase-b-test) echo 29991 ;;
            *) return 1 ;;
          esac
        }}
        mountpoint() {{ [[ $MOUNT_ACTIVE -eq 1 ]]; }}
        umount() {{ MOUNT_ACTIVE=0; }}
        pgrep() {{ return 1; }}
        chown() {{ CAPTURE_OWNER=original; }}
        userdel() {{ ACCOUNT_PRESENT=0; }}
        find() {{
          local joined=" $* "
          if [[ $1 == {shlex.quote(str(capture))} && $joined == *' -user '* ]]; then
            if [[ $joined == *' -user d293-phase-b-test '* &&
                  $joined == *' -user {current_user} '* ]]; then
              return 0
            elif [[ $joined == *' -user d293-phase-b-test '* ]]; then
              [[ $CAPTURE_OWNER == test ]] || printf '%s\\n' "$1"
              return 0
            elif [[ $joined == *' -user {current_user} '* ]]; then
              [[ $CAPTURE_OWNER == original ]] || printf '%s\\n' "$1"
              return 0
            fi
          fi
          if [[ $joined == *' -delete '* ]]; then
            if [[ $1 == "$public" && $PUBLIC_REMOVE_FAILURES -gt 0 ]]; then
              PUBLIC_REMOVE_FAILURES=$((PUBLIC_REMOVE_FAILURES - 1)); return 1
            fi
            if [[ $1 == "$private" && $PRIVATE_REMOVE_FAILURES -gt 0 ]]; then
              PRIVATE_REMOVE_FAILURES=$((PRIVATE_REMOVE_FAILURES - 1)); return 1
            fi
          fi
          command /usr/bin/find "$@"
        }}
        mv() {{
          local -a args=("$@")
          local source=${{args[${{#args[@]}}-2]}} destination=${{args[${{#args[@]}}-1]}}
          if [[ $destination == {shlex.quote(str(run_root / 'account-removal.intent'))} &&
                -f $INTENT_FAIL_MARKER ]] &&
             grep -Fx D293_04_ACCOUNT_REMOVAL_STATE=COMPLETE "$source" >/dev/null; then
            /usr/bin/rm -f -- "$INTENT_FAIL_MARKER"; return 1
          fi
          if [[ $destination == {shlex.quote(str(run_root / 'recovery.env'))} &&
                -f $RECOVERY_FAIL_MARKER ]]; then
            /usr/bin/rm -f -- "$RECOVERY_FAIL_MARKER"; return 1
          fi
          command /usr/bin/mv "$@"
        }}

        case {shlex.quote(scenario)} in
          residual-template)
            rc1=0; recover || rc1=$?
            [[ $rc1 -ne 0 && ! -e {shlex.quote(str(run_root / 'recovery.env'))} ]]
            /usr/bin/rm -f -- {shlex.quote(str(test_fprint / 'template'))}
            SERVICE_ACTIVE=1
            rc2=0; recover || rc2=$?
            ;;
          stop-temporary)
            STOP_FAILURES=1
            rc1=0; recover || rc1=$?
            [[ $rc1 -ne 0 && -e "$private/runtime/candidate" && -e "$dropin" ]]
            rc2=0; recover || rc2=$?
            ;;
          public-remove-failure)
            PUBLIC_REMOVE_FAILURES=1
            rc1=0; recover || rc1=$?
            [[ $rc1 -ne 0 && ! -e {shlex.quote(str(run_root / 'recovery.env'))} ]]
            rc2=0; recover || rc2=$?
            ;;
          private-remove-failure)
            PRIVATE_REMOVE_FAILURES=1
            rc1=0; recover || rc1=$?
            [[ $rc1 -ne 0 && ! -e {shlex.quote(str(run_root / 'recovery.env'))} ]]
            rc2=0; recover || rc2=$?
            ;;
          recovery-publish-failure)
            : >"$RECOVERY_FAIL_MARKER"
            rc1=0; recover || rc1=$?
            [[ $rc1 -ne 0 && ! -e {shlex.quote(str(run_root / 'recovery.env'))} ]]
            rc2=0; recover || rc2=$?
            ;;
          intent-complete-failure)
            : >"$INTENT_FAIL_MARKER"
            rc1=0; recover || rc1=$?
            [[ $rc1 -ne 0 && $ACCOUNT_PRESENT -eq 1 && $CAPTURE_OWNER == original ]]
            grep -Fx D293_04_ACCOUNT_REMOVAL_STATE=PENDING \
              {shlex.quote(str(run_root / 'account-removal.intent'))} >/dev/null
            rc2=0; recover || rc2=$?
            ;;
          identity-sticky)
            IDENTITY_DRIFT=1
            rc1=0; recover || rc1=$?
            IDENTITY_DRIFT=0
            rc2=0; recover || rc2=$?
            [[ $rc1 -ne 0 && $rc2 -ne 0 && $ACCOUNT_PRESENT -eq 1 ]]
            grep -Fx D293_04_RECOVERY_INTEGRITY_FAILURE=true \
              {shlex.quote(str(run_root / 'recovery-integrity-failure.env'))} >/dev/null
            ;;
          metadata-*-sticky)
            rc1=0; recover || rc1=$?
            chmod 0600 {shlex.quote(str(metadata))}
            case {shlex.quote(scenario)} in
              metadata-digest-missing-sticky)
                printf '%s\\n' D293_04_ORIGINAL_PRINCIPAL_DIGEST=ABSENT >>{shlex.quote(str(metadata))}
                ;;
              metadata-digest-malformed-sticky)
                /usr/bin/sed -i 's/D293_04_ORIGINAL_PRINCIPAL_DIGEST=.*/D293_04_ORIGINAL_PRINCIPAL_DIGEST=ABSENT/' \
                  {shlex.quote(str(metadata))}
                ;;
              metadata-original-gid-missing-sticky)
                printf '%s\\n' D293_04_ORIGINAL_GID={current_gid} >>{shlex.quote(str(metadata))}
                ;;
              metadata-original-gid-mismatch-sticky)
                /usr/bin/sed -i 's/D293_04_ORIGINAL_GID=.*/D293_04_ORIGINAL_GID={current_gid}/' \
                  {shlex.quote(str(metadata))}
                ;;
            esac
            chmod 0400 {shlex.quote(str(metadata))}
            rc2=0; recover || rc2=$?
            [[ $rc1 -ne 0 && $rc2 -ne 0 && $ACCOUNT_PRESENT -eq 1 ]]
            grep -Fx D293_04_RECOVERY_INTEGRITY_FAILURE=true \
              {shlex.quote(str(run_root / 'recovery-integrity-failure.env'))} >/dev/null
            ;;
          digest-sticky)
            rc1=0; recover || rc1=$?
            /usr/bin/rm -f -- {shlex.quote(str(original_fprint / 'drift'))}
            /usr/bin/rmdir --ignore-fail-on-non-empty {shlex.quote(str(original_fprint))}
            rc2=0; recover || rc2=$?
            [[ $rc1 -ne 0 && $rc2 -ne 0 && $ACCOUNT_PRESENT -eq 1 ]]
            ;;
          legacy-fail-retry)
            rc1=0; recover || rc1=$?
            rc2=$rc1
            [[ $rc1 -eq 0 ]]
            grep -Fx D293_04_RUNTIME_ROLLBACK=FAIL \
              {shlex.quote(str(run_root / 'rollback-history.log'))} >/dev/null
            grep -Fx D293_04_RUNTIME_ROLLBACK=PASS \
              {shlex.quote(str(run_root / 'rollback-history.log'))} >/dev/null
            ;;
          legacy-integrity-sticky)
            rc1=0; recover || rc1=$?
            rc2=0; recover || rc2=$?
            [[ $rc1 -ne 0 && $rc2 -ne 0 && $ACCOUNT_PRESENT -eq 1 ]]
            grep -Fx D293_04_INTEGRITY_FAILURE=true "$private/rollback.integrity-failure" >/dev/null
            ;;
          success-idempotent)
            rc1=0; recover || rc1=$?
            rc2=0; recover || rc2=$?
            [[ $rc1 -eq 0 && $rc2 -eq 0 && $ACCOUNT_PRESENT -eq 0 ]]
            ;;
          no-attributed-run)
            rc1=0; recover || rc1=$?
            rc2=$rc1
            [[ $rc1 -eq 0 && ! -e $public && ! -e $private ]]
            ;;
          *) exit 90 ;;
        esac

        if [[ {shlex.quote(scenario)} != identity-sticky &&
              {shlex.quote(scenario)} != digest-sticky &&
              {shlex.quote(scenario)} != metadata-*-sticky &&
              {shlex.quote(scenario)} != legacy-fail-retry &&
              {shlex.quote(scenario)} != legacy-integrity-sticky &&
              {shlex.quote(scenario)} != success-idempotent &&
              {shlex.quote(scenario)} != no-attributed-run ]]; then
          [[ $rc1 -ne 0 && $rc2 -eq 0 ]]
          grep -Fx D293_04_FINAL_RECOVERY=PASS {shlex.quote(str(run_root / 'recovery.env'))} >/dev/null
          [[ $ACCOUNT_PRESENT -eq 0 && -d {shlex.quote(str(capture))} ]]
        fi
        printf 'COMPOSITION_SCENARIO=%s RC1=%s RC2=%s\\n' {shlex.quote(scenario)} "$rc1" "$rc2"
        """
    )
    harness = base / "recovery-composition.sh"
    harness.write_text(script, encoding="utf-8")
    harness.chmod(0o700)
    result = subprocess.run([str(harness)], text=True, capture_output=True, timeout=10)
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
                [
                    "arm-enroll",
                    "finish-enroll",
                    "arm-verify-1",
                    "finish-verify-1",
                    "complete-verify",
                    "arm-delete",
                    "finish-delete",
                ],
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
            telemetry = fixture.telemetry.read_text(encoding="utf-8")
            self.assertIn("D293_04_OBSERVATION_COMPLETE=false", telemetry)
            self.assertIn("ACTION_ATTEMPT_COUNT=UNKNOWN", telemetry)
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

    def test_extra_ui_enrollment_is_detected_as_protocol_deviation(self) -> None:
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
            config = (EXP / "experiment.conf").read_text(encoding="utf-8")
            self.assertIn("LIVE_CAPABLE=true", config)
            self.assertIn("EXTRA_MANUAL_UI_ACTION=PROTOCOL_DEVIATION_STOP", config)
            telemetry = fixture.telemetry.read_text(encoding="utf-8")
            for field in (
                "ACTION_ATTEMPT_COUNT=UNKNOWN",
                "CONTACT_COUNT=UNKNOWN",
                "DRAINED_COUNT=UNKNOWN",
                "CONTEXT_CLOSED_COUNT=UNKNOWN",
            ):
                self.assertIn(field, telemetry)
        finally:
            fixture.cleanup()

    def test_duplicate_action_field_fails_payload_closed(self) -> None:
        fixture = PayloadRun(journal_mode="duplicate-action-field")
        proc = self.drive_enrollment_closed(fixture)
        try:
            assert proc.stdin is not None
            proc.stdin.close()
            assert proc.stdout is not None
            output = proc.stdout.read()
            proc.stdout.close()
            proc.wait(timeout=5)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("reason=enrollment_action_cardinality", output)
            self.assertNotIn("arm-verify-1", fixture.collector.requests)
            telemetry = fixture.telemetry.read_text(encoding="utf-8")
            self.assertIn("ACTION_ATTEMPT_COUNT=UNKNOWN", telemetry)
            self.assertIn("CONTACT_COUNT=UNKNOWN", telemetry)
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
            telemetry = fixture.telemetry.read_text(encoding="utf-8")
            self.assertIn("D293_04_OBSERVATION_COMPLETE=false", telemetry)
            for field in (
                "ACTION_ATTEMPT_COUNT=UNKNOWN",
                "CONTACT_COUNT=UNKNOWN",
                "DRAINED_COUNT=UNKNOWN",
                "CONTEXT_CLOSED_COUNT=UNKNOWN",
            ):
                self.assertIn(field, telemetry)
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
            self.assertIn(
                "ACTION_ATTEMPT_COUNT=UNKNOWN",
                fixture.telemetry.read_text(encoding="utf-8"),
            )
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

    def test_real_root_journal_functions_and_runtime_publication(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d293-04-script-test.", dir="/tmp") as tmp:
            base = pathlib.Path(tmp)
            private = base / "private"
            runtime = private / "runtime"
            public = base / "public"
            results = public / "results"
            for path in (runtime, results):
                path.mkdir(parents=True)
            artifact = runtime / "libfprint-2.so.2.0.0"
            artifact.write_text("candidate\n", encoding="utf-8")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            (runtime / "artifacts.sha256").write_text(
                f"{digest}  libfprint-2.so.2.0.0\n", encoding="utf-8"
            )
            shutil.copy2(NORMALIZER, private / "normalize-journal.sh")
            daemon = base / "mock-fprintd"
            daemon.write_text("#!/usr/bin/env bash\necho MOCK_FPRINTD=RUN\n", encoding="utf-8")
            daemon.chmod(0o700)
            (private / "state.env").write_text(
                f"PRODUCTION_HEAD={HEAD}\nLIBRARY_SHA256={digest}\nRUN_ID={RUN_ID}\n"
                f"DAEMON_PATH={daemon}\n",
                encoding="utf-8",
            )
            marker = (
                f"D293_04_RUNTIME_AUDIT head={HEAD} library_sha={digest} "
                f"manifest=pass run_id={RUN_ID}"
            )
            proc = base / "proc"
            pid_dir = proc / "4242"
            pid_dir.mkdir(parents=True)
            (pid_dir / "exe").symlink_to(daemon)
            maps = pid_dir / "maps"
            maps.write_text(
                f"7f000000-7f001000 r--p 00000000 00:00 1 {artifact}\n"
                f"7f001000-7f002000 r-xp 00001000 00:00 1 {artifact}\n",
                encoding="utf-8",
            )
            verify_epoch = epoch("FPI_DEVICE_ACTION_VERIFY").strip()
            script = root_helper_prefix() + textwrap.dedent(
                f"""

                private={shlex.quote(str(private))}
                public={shlex.quote(str(public))}
                capture_base={shlex.quote(str(base / 'captures'))}
                proc_root={shlex.quote(str(proc))}
                RUNTIME_LINE={shlex.quote(marker)}
                EPOCH_LINE={shlex.quote(verify_epoch)}
                JOURNAL_MODE=runtime
                MAIN_PID=4242
                SERVICE_ACTIVE=1
                journalctl() {{
                  case $JOURNAL_MODE in
                    runtime) printf '%s\\n' "$RUNTIME_LINE" ;;
                    runtime-wrong) printf '%s\\n' 'D293_04_RUNTIME_AUDIT head={'c' * 40} library_sha={digest} manifest=pass run_id={RUN_ID}' ;;
                    empty) : ;;
                    no-entry) printf '%s\\n' '-- No entries --' ;;
                    unrelated) printf '%s\\n' 'ordinary fprintd diagnostic' ;;
                    event) printf '%s\\n' "$EPOCH_LINE" ;;
                    error) return 13 ;;
                    *) return 14 ;;
                  esac
                }}
                systemctl() {{
                  case $1 in
                    is-active) [[ $3 == fprintd.service && $SERVICE_ACTIVE -eq 1 ]] ;;
                    show) printf '%s\\n' "$MAIN_PID" ;;
                    *) return 1 ;;
                  esac
                }}

                write_runtime_wrapper {HEAD} {digest} {RUN_ID} {shlex.quote(str(daemon))}
                chmod 0555 "$public/results"
                wrapper_output=$("$private/wrapper")
                grep -Fx "$RUNTIME_LINE" <<<"$wrapper_output" >/dev/null
                grep -Fx MOCK_FPRINTD=RUN <<<"$wrapper_output" >/dev/null
                [[ ! -e $public/results/runtime-audit.env ]]
                chmod 0755 "$public/results"

                JOURNAL_MODE=no-entry
                runtime_rc=0; publish_runtime_audit cursor-runtime-none || runtime_rc=$?
                [[ $runtime_rc -eq 3 && ! -e $public/results/runtime-audit.env ]]
                JOURNAL_MODE=runtime-wrong
                runtime_rc=0; publish_runtime_audit cursor-runtime-wrong || runtime_rc=$?
                [[ $runtime_rc -eq 1 && ! -e $public/results/runtime-audit.env ]]

                JOURNAL_MODE=runtime
                for process_case in pid-missing pid-invalid proc-missing exe-missing exe-wrong maps-missing maps-wrong maps-extra; do
                  MAIN_PID=4242
                  case $process_case in
                    pid-missing) MAIN_PID=0 ;;
                    pid-invalid) MAIN_PID=not-a-pid ;;
                    proc-missing) MAIN_PID=9898 ;;
                    exe-missing) /usr/bin/rm -f -- "$proc_root/4242/exe" ;;
                    exe-wrong)
                      /usr/bin/rm -f -- "$proc_root/4242/exe"
                      ln -s /usr/bin/false "$proc_root/4242/exe"
                      ;;
                    maps-missing) /usr/bin/rm -f -- "$proc_root/4242/maps" ;;
                    maps-wrong)
                      printf '%s\\n' '7f000000-7f001000 r-xp 0 00:00 1 /usr/lib64/libfprint-2.so.2.0.0' >"$proc_root/4242/maps"
                      ;;
                    maps-extra)
                      printf '%s\\n%s\\n' \
                        '7f000000-7f001000 r-xp 0 00:00 1 {artifact}' \
                        '7f001000-7f002000 r-xp 0 00:00 1 /usr/lib64/libfprint-2.so.2.0.0' >"$proc_root/4242/maps"
                      ;;
                  esac
                  process_rc=0; publish_runtime_audit "cursor-$process_case" || process_rc=$?
                  [[ $process_rc -ne 0 && ! -e $public/results/runtime-audit.env ]]
                  MAIN_PID=4242
                  /usr/bin/rm -f -- "$proc_root/4242/exe"
                  ln -s {shlex.quote(str(daemon))} "$proc_root/4242/exe"
                  printf '%s\\n%s\\n' \
                    '7f000000-7f001000 r--p 0 00:00 1 {artifact}' \
                    '7f001000-7f002000 r-xp 0 00:00 1 {artifact}' >"$proc_root/4242/maps"
                done
                publish_runtime_audit cursor-runtime
                grep -Fx "$RUNTIME_LINE" "$public/results/runtime-audit.env" >/dev/null
                [[ $(wc -l <"$public/results/runtime-audit.env") -eq 1 ]]
                ! find "$private" -maxdepth 1 -name '.runtime-*' -print -quit | grep -q .

                JOURNAL_MODE=empty
                collect_epoch_journal delete cursor-delete-empty
                [[ -f $public/results/delete-journal.log && ! -s $public/results/delete-journal.log ]]
                /usr/bin/rm -f -- "$public/results/delete-journal.log"
                JOURNAL_MODE=no-entry
                collect_epoch_journal delete cursor-delete-no-entry
                [[ -f $public/results/delete-journal.log && ! -s $public/results/delete-journal.log ]]
                /usr/bin/rm -f -- "$public/results/delete-journal.log"
                JOURNAL_MODE=unrelated
                collect_epoch_journal delete cursor-delete-unrelated
                [[ -f $public/results/delete-journal.log && ! -s $public/results/delete-journal.log ]]
                /usr/bin/rm -f -- "$public/results/delete-journal.log"
                JOURNAL_MODE=empty
                if collect_epoch_journal enroll cursor-enroll-empty; then exit 31; fi
                [[ ! -e $public/results/enroll-journal.log ]]
                JOURNAL_MODE=error
                if collect_epoch_journal verify-1 cursor-verify-error; then exit 32; fi
                [[ ! -e $public/results/verify-1-journal.log ]]
                JOURNAL_MODE=event
                collect_epoch_journal delete cursor-delete-event
                grep -Fx "$EPOCH_LINE" "$public/results/delete-journal.log" >/dev/null
                ! find "$private" -maxdepth 1 -name '.journal-*' -print -quit | grep -q .
                printf '%s\\n' F1_F2_REAL_FUNCTIONS=PASS
                """
            )
            harness = base / "journal-harness.sh"
            harness.write_text(script, encoding="utf-8")
            harness.chmod(0o700)
            result = subprocess.run([str(harness)], text=True, capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("F1_F2_REAL_FUNCTIONS=PASS", result.stdout)

            unit = (
                ROOT / "reference/fprintd-fedora44-1.94.5/source/data/fprintd.service.in"
            ).read_text(encoding="utf-8")
            self.assertIn("ProtectSystem=strict", unit)
            self.assertNotIn("/run/goodix-d293-04-public", unit)
            helper = (EXP / "root-helper.sh").read_text(encoding="utf-8")
            wrapper_body = helper.split("write_runtime_wrapper()", 1)[1].split(
                "publish_runtime_audit()", 1
            )[0]
            self.assertNotIn("goodix-d293-04-public", wrapper_body)

    def test_compositional_recovery_retries_recoverable_failures(self) -> None:
        for scenario in ("residual-template", "stop-temporary", "intent-complete-failure"):
            with self.subTest(scenario=scenario):
                result, capture, holder = run_compositional_recovery(scenario)
                try:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f"COMPOSITION_SCENARIO={scenario} RC1=1 RC2=0", result.stdout)
                    self.assertEqual(
                        (capture / "evidence.env").read_text(encoding="utf-8"),
                        "CAPTURE=PRESERVED\n",
                    )
                    history = capture.parent / "rollback-history.log"
                    self.assertTrue(history.is_file())
                    history_text = history.read_text(encoding="utf-8")
                    self.assertIn("D293_04_RUNTIME_ROLLBACK=PASS", history_text)
                    if scenario != "intent-complete-failure":
                        self.assertIn("D293_04_RUNTIME_ROLLBACK=FAIL", history_text)
                finally:
                    holder.cleanup()

    def test_compositional_final_cleanup_failure_remains_resumable(self) -> None:
        for scenario in (
            "public-remove-failure",
            "private-remove-failure",
            "recovery-publish-failure",
        ):
            with self.subTest(scenario=scenario):
                result, capture, holder = run_compositional_recovery(scenario)
                try:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f"COMPOSITION_SCENARIO={scenario} RC1=1 RC2=0", result.stdout)
                    recovery = capture.parent / "recovery.env"
                    self.assertEqual(
                        recovery.read_text(encoding="utf-8").count(
                            "D293_04_FINAL_RECOVERY=PASS"
                        ),
                        1,
                    )
                finally:
                    holder.cleanup()

    def test_compositional_integrity_failure_is_sticky(self) -> None:
        for scenario in ("identity-sticky", "digest-sticky", "legacy-integrity-sticky"):
            with self.subTest(scenario=scenario):
                result, capture, holder = run_compositional_recovery(scenario)
                try:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f"COMPOSITION_SCENARIO={scenario} RC1=1 RC2=1", result.stdout)
                    self.assertFalse((capture.parent / "recovery.env").exists())
                finally:
                    holder.cleanup()

    def test_compositional_missing_or_malformed_metadata_is_sticky(self) -> None:
        for scenario in (
            "metadata-digest-missing-sticky",
            "metadata-digest-malformed-sticky",
            "metadata-original-gid-missing-sticky",
            "metadata-original-gid-mismatch-sticky",
        ):
            with self.subTest(scenario=scenario):
                result, _capture, holder = run_compositional_recovery(scenario)
                try:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(
                        f"COMPOSITION_SCENARIO={scenario} RC1=1 RC2=1",
                        result.stdout,
                    )
                finally:
                    holder.cleanup()

    def test_compositional_legacy_fail_is_imported_before_retry(self) -> None:
        result, capture, holder = run_compositional_recovery("legacy-fail-retry")
        try:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("COMPOSITION_SCENARIO=legacy-fail-retry RC1=0 RC2=0", result.stdout)
            history = (capture.parent / "rollback-history.log").read_text(encoding="utf-8")
            self.assertLess(
                history.index("D293_04_RUNTIME_ROLLBACK=FAIL"),
                history.rindex("D293_04_RUNTIME_ROLLBACK=PASS"),
            )
        finally:
            holder.cleanup()

    def test_compositional_success_is_idempotent_after_final_cleanup(self) -> None:
        result, capture, holder = run_compositional_recovery("success-idempotent")
        try:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("COMPOSITION_SCENARIO=success-idempotent RC1=0 RC2=0", result.stdout)
            self.assertIn(
                "D293_04_FINAL_RECOVERY=PASS",
                (capture.parent / "recovery.env").read_text(encoding="utf-8"),
            )
        finally:
            holder.cleanup()

    def test_compositional_no_run_deploy_failure_cleans_containers(self) -> None:
        result, _capture, holder = run_compositional_recovery("no-attributed-run")
        try:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("COMPOSITION_SCENARIO=no-attributed-run RC1=0 RC2=0", result.stdout)
        finally:
            holder.cleanup()

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
                "duplicate-action-field": lambda path: (path / "enroll-journal.log").write_text(
                    (path / "enroll-journal.log")
                    .read_text(encoding="utf-8")
                    .replace(
                        "action=FPI_DEVICE_ACTION_ENROLL",
                        "action=FPI_DEVICE_ACTION_ENROLL "
                        "action=FPI_DEVICE_ACTION_IDENTIFY",
                        1,
                    ),
                    encoding="utf-8",
                ),
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

    def test_prepare_full_entrypoint_with_isolated_external_seam(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d293-04-prepare-test.", dir="/tmp") as tmp:
            base = pathlib.Path(tmp)
            commands = base / "commands"
            device = base / "sysfs" / "mock-device"
            historical = base / "captures" / "historical-complete-run"
            for path in (commands, device, historical):
                path.mkdir(parents=True)
            (device / "idVendor").write_text("27c6\n", encoding="utf-8")
            (device / "idProduct").write_text("5125\n", encoding="utf-8")
            record = base / "pkexec-arguments"

            def command(name: str, body: str) -> None:
                path = commands / name
                path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
                path.chmod(0o700)

            command(
                "git",
                textwrap.dedent(
                    f"""
                    case "$*" in
                      *'rev-parse --show-toplevel') echo {shlex.quote(str(ROOT))} ;;
                      *'branch --show-current') echo development ;;
                      *'rev-parse origin/development') echo {HEAD} ;;
                      *'rev-parse HEAD') echo {HEAD} ;;
                      *'status --porcelain=v1'*) : ;;
                      *) exit 9 ;;
                    esac
                    """
                ),
            )
            command(
                "rpm",
                "case $2 in fprintd) echo fprintd-1.94.5-5.fc44.x86_64 ;; "
                "libfprint) echo libfprint-1.94.100-1.fc44.x86_64 ;; "
                "plasma-workspace-libs) echo plasma-workspace-libs-6.7.5-1.fc44.x86_64 ;; "
                "*) exit 1 ;; esac\n",
            )
            command("getent", "exit 2\n")
            command("pgrep", "exit 1\n")
            command(
                "build",
                "out=$2; mkdir -p \"$out\"; for name in libfprint-2.so.2.0.0 "
                "libgusb.so.2 libopencv_core.so.413 libopencv_features2d.so.413 "
                "libopencv_flann.so.413 libopencv_imgproc.so.413; do "
                "printf '%s\\n' \"$name\" >\"$out/$name\"; done\n",
            )
            command("pkexec", "printf '%s\\n' \"$@\" >\"${D293_PREPARE_RECORD:?}\"\n")
            env = os.environ.copy()
            env.update(
                {
                    "D293_04_PREPARE_MODE": "offline-script-test",
                    "D293_04_PREPARE_TEST_ROOT": str(base),
                    "D293_PREPARE_RECORD": str(record),
                }
            )
            result = subprocess.run(
                [str(EXP / "prepare.sh")], text=True, capture_output=True, env=env, timeout=8
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("D293_04_PREPARE=PASS", result.stdout)
            arguments = record.read_text(encoding="utf-8").splitlines()
            self.assertEqual(arguments[1], "--deploy")
            self.assertEqual(arguments[3], HEAD)
            self.assertEqual(arguments[4], subprocess.check_output(["id", "-un"], text=True).strip())
            self.assertRegex(arguments[5], r"^d293-04-\d{8}T\d{6}Z-[0-9a-f]{12}$")
            self.assertTrue(historical.is_dir(), "historical capture root must be preserved")

    def test_capture_base_is_created_owned_preserved_and_rechecked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d293-04-script-test.", dir="/tmp") as tmp:
            base = pathlib.Path(tmp)
            capture_base = base / "captures"
            symlink_base = base / "captures-link"
            symlink_target = base / "captures-target"
            symlink_target.mkdir()
            symlink_base.symlink_to(symlink_target, target_is_directory=True)
            script = root_helper_prefix() + textwrap.dedent(
                f"""

                capture_base={shlex.quote(str(capture_base))}
                capture_base_owner="$EUID:$(id -g)"
                prepare_capture_base
                [[ $(stat -c %a "$capture_base") == 711 ]]
                mkdir "$capture_base/historical-run"
                printf '%s\\n' PRESERVED >"$capture_base/historical-run/evidence"
                prepare_capture_base
                grep -Fx PRESERVED "$capture_base/historical-run/evidence" >/dev/null

                chmod 0755 "$capture_base"
                if validate_capture_base; then exit 41; fi
                chmod 0711 "$capture_base"
                saved_owner=$capture_base_owner
                capture_base_owner=1:1
                if validate_capture_base; then exit 42; fi
                capture_base_owner=$saved_owner
                validate_capture_base

                capture_base={shlex.quote(str(symlink_base))}
                if prepare_capture_base; then exit 43; fi

                capture_base={shlex.quote(str(capture_base))}
                candidate={shlex.quote(str(base / 'candidate'))}
                private={shlex.quote(str(base / 'private'))}
                public={shlex.quote(str(base / 'public'))}
                dropin={shlex.quote(str(base / 'dropin'))}
                mkdir "$candidate" "$capture_base/{RUN_ID}"
                : >"$candidate/deploy.sha256"
                PKEXEC_UID=$EUID
                set +e
                deploy_output=$(deploy "$candidate" {HEAD} "$(id -un)" {RUN_ID} 2>&1)
                deploy_rc=$?
                set -e
                [[ $deploy_rc -ne 0 ]]
                grep -F 'reason=deployment_collision' <<<"$deploy_output" >/dev/null
                grep -Fx PRESERVED "$capture_base/historical-run/evidence" >/dev/null
                printf '%s\\n' CAPTURE_BASE_REGRESSION=PASS
                """
            )
            harness = base / "capture-base-harness.sh"
            harness.write_text(script, encoding="utf-8")
            harness.chmod(0o700)
            result = subprocess.run(
                [str(harness)], text=True, capture_output=True, timeout=5
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CAPTURE_BASE_REGRESSION=PASS", result.stdout)

            helper = (EXP / "root-helper.sh").read_text(encoding="utf-8")
            deploy = helper[helper.index("deploy()"):helper.index("resolve_incomplete_run()")]
            self.assertLess(
                deploy.index("prepare_capture_base"),
                deploy.index("deployment_collision"),
            )
            supervise = helper[helper.index("supervise()"):helper.index("deploy()")]
            self.assertLess(
                supervise.index("validate_capture_base"),
                supervise.index("run_capture_collision"),
            )
            self.assertIn("capture_base_owner=0:0", helper)

    def test_live_configuration_declares_operator_protocol_not_gui_hard_cap(self) -> None:
        config = (EXP / "experiment.conf").read_text(encoding="utf-8")
        for marker in (
            "LIVE_CAPABLE=true",
            "GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL",
            "GUI_SESSION_HARD_CAP_REQUIRED=false",
            "VERIFY_SERIES_CONTROL=SCRIPT_BOUNDED",
            "RUN_TOTALS_CHECK=OBSERVED_PROTOCOL_BOUNDS",
        ):
            self.assertIn(marker, config)

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

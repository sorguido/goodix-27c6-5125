# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import os
import pty
import secrets
import select
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "operator_kit/live_probe"
EXP = HARNESS / "experiments/d290-plasmalogin"
SECOND_CAPTURE = ROOT / "captures/live_probe/d290-plasmalogin_20260912T144942Z_603a47cdf1c1/sanitized"


class D290PlasmaLoginContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = (EXP / "experiment.conf").read_text()
        cls.payload = (EXP / "payload.sh").read_text()
        cls.helper = (EXP / "root-overlay.sh").read_text()
        cls.audit = (EXP / "audit.sh").read_text()
        cls.classifier = (EXP / "classify.sh").read_text()
        cls.session_model = (EXP / "session-model.sh").read_text()
        cls.privileged_channel = (EXP / "privileged-channel.sh").read_text()
        cls.root_lib = (EXP / "root-overlay-lib.sh").read_text()
        cls.readme = (EXP / "README_IT.md").read_text()
        cls.candidate = (EXP / "goodix-d290-plasmalogin.pam").read_text()

    def session_records(self, sessions, function, *args):
        with tempfile.TemporaryDirectory() as td:
            fixture = Path(td)
            lines = []
            for session in sessions:
                sid = str(session["id"])
                lines.append(f'{sid} {session.get("uid", 1000)} user seat0 1 user tty2 no -')
                for prop in ("Service", "Type", "Class", "State", "TTY"):
                    (fixture / f"{sid}.{prop}").write_text(session[prop] + "\n")
            (fixture / "sessions").write_text("\n".join(lines) + ("\n" if lines else ""))
            fake = fixture / "loginctl"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "case $1 in\n"
                "  list-sessions) cat \"$D290_FIXTURE_DIR/sessions\" ;;\n"
                "  show-session) cat \"$D290_FIXTURE_DIR/$2.$4\" ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n"
            )
            fake.chmod(0o755)
            command = [
                "bash", "-c",
                'source "$1"; shift; "$@"',
                "bash", str(EXP / "session-model.sh"), function, *map(str, args),
            ]
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                env={
                    "PATH": "/usr/bin:/bin",
                    "D290_LOGINCTL": str(fake),
                    "D290_FIXTURE_DIR": str(fixture),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return [line.split("|") for line in result.stdout.splitlines() if line]

    def run_overlay_fixture(self, operation, scenario="normal"):
        with tempfile.TemporaryDirectory(prefix="d290-overlay-") as td:
            base = Path(td)
            target = base / "host-pam"
            candidate = base / "candidate-pam"
            target.write_text("HOST_PAM_FIXTURE\n")
            candidate.write_text("CANDIDATE_PAM_FIXTURE\n")
            host_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            driver = base / "driver.sh"
            driver.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                "operation=$1; scenario=$2; base=$3; library=$4\n"
                "target=$base/host-pam; candidate=$base/candidate-pam; runtime=$base/runtime\n"
                "expected_runtime=$runtime; expected_host=$5; expected_candidate=$6\n"
                "operator_uid=$(id -u); mounted=false; control_parent=$base/goodix-live-probe.fixture\n"
                "mkdir -m 0700 \"$control_parent\"; control_fifo=$control_parent/d290-root-control.fifo\n"
                "owner_pid=$$; owner_start_time=$(awk '{print $22}' /proc/$$/stat); control_watchdog_pid=\n"
                "mount_marker=$base/mounted; saved_host=$base/saved-host; cleanup_log=$base/cleanup.log\n"
                "source \"$library\"\n"
                "d290_validate_daemon_identity () { [[ $scenario != daemon_fail ]]; }\n"
                "mountpoint () { [[ -f $mount_marker ]]; }\n"
                "install () {\n"
                "  local -a a=(\"$@\"); local n=${#a[@]}\n"
                "  if [[ ${a[0]} == -d ]]; then mkdir -p \"${a[n-1]}\"; chmod 0700 \"${a[n-1]}\"; return; fi\n"
                "  cp \"${a[n-2]}\" \"${a[n-1]}\"; chmod 0644 \"${a[n-1]}\"\n"
                "}\n"
                "chcon () { [[ $scenario != after_runtime_fail ]]; }\n"
                "mount () {\n"
                "  if [[ $1 == --bind ]]; then\n"
                "    [[ $scenario != bind_fail ]] || return 73\n"
                "    cp \"$target\" \"$saved_host\"; cp \"$2\" \"$target\"; : >\"$mount_marker\"; return\n"
                "  fi\n"
                "  [[ $scenario != remount_fail ]]\n"
                "}\n"
                "umount () { cp \"$saved_host\" \"$target\"; rm -f \"$mount_marker\"; }\n"
                "findmnt () { echo ro; }\n"
                "on_exit () { local rc=$?; trap - EXIT; set +e; d290_cleanup_overlay >\"$cleanup_log\" 2>&1; exit $rc; }\n"
                "trap on_exit EXIT\n"
                "case $scenario in\n"
                "  mount_already) : >\"$mount_marker\" ;;\n"
                "  wrong_host) printf 'WRONG_HOST\\n' >\"$target\" ;;\n"
                "  recover_expected) cp \"$target\" \"$saved_host\"; cp \"$candidate\" \"$target\"; : >\"$mount_marker\" ;;\n"
                "  recover_wrong) cp \"$target\" \"$saved_host\"; printf 'WRONG_CANDIDATE\\n' >\"$target\"; : >\"$mount_marker\" ;;\n"
                "esac\n"
                "case $operation in\n"
                "  prepare) d290_prepare_overlay; d290_cleanup_overlay; d290_cleanup_overlay ;;\n"
                "  hold)\n"
                "    mkfifo \"$control_fifo\"; chmod 0600 \"$control_fifo\"\n"
                "    [[ $scenario != fifo_wrong_mode ]] || chmod 0644 \"$control_fifo\"\n"
                "    [[ $scenario != parent_wrong_mode ]] || chmod 0755 \"$control_parent\"\n"
                "    if [[ $scenario == fifo_symlink ]]; then mv \"$control_fifo\" \"$control_fifo.real\"; ln -s \"$control_fifo.real\" \"$control_fifo\"; fi\n"
                "    exec 9<>\"$control_fifo\"; printf 'RELEASE\\n' >&9; d290_hold_overlay; exec 9>&-; d290_cleanup_overlay ;;\n"
                "  owner_death)\n"
                "    mkfifo \"$control_fifo\"; chmod 0600 \"$control_fifo\"; exec 9<>\"$control_fifo\"\n"
                "    sleep 0.2 & owner_pid=$!; owner_start_time=$(awk '{print $22}' /proc/$owner_pid/stat)\n"
                "    d290_hold_overlay ;;\n"
                "  recover) d290_recover_overlay; d290_cleanup_overlay ;;\n"
                "esac\n"
                "trap - EXIT\n"
            )
            driver.chmod(0o755)
            result = subprocess.run(
                [str(driver), operation, scenario, str(base), str(EXP / "root-overlay-lib.sh"), host_hash, candidate_hash],
                text=True,
                capture_output=True,
            )
            state = {
                "target": target.read_text(),
                "runtime": (base / "runtime").exists(),
                "mounted": (base / "mounted").exists(),
                "cleanup": (base / "cleanup.log").read_text() if (base / "cleanup.log").exists() else "",
            }
            return result, state

    def run_privilege_pty(self, phase="normal"):
        with tempfile.TemporaryDirectory(prefix="goodix-live-probe.") as td:
            base = Path(td)
            capture = base / "capture"
            capture.mkdir()
            target = base / "overlay-target"
            target.write_text("CANDIDATE_VISIBLE\n")
            expected = hashlib.sha256(target.read_bytes()).hexdigest()
            state_file = base / "helper-state.log"
            fake_bin = base / "bin"
            fake_bin.mkdir()
            fake = fake_bin / "pkexec"
            fake.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                "if [[ ! -t 0 ]]; then echo D290_TEST_AUTH_STDIN_NOT_TTY; exit 41; fi\n"
                "fifo=; while [[ $# -gt 0 ]]; do if [[ $1 == --control-fifo ]]; then fifo=$2; break; fi; shift; done; [[ -p $fifo ]]\n"
                "saved=$(stty -g </dev/tty); trap 'stty \"$saved\" </dev/tty' EXIT\n"
                "on_signal () { echo D290_TEST_HELPER_SIGNAL_CLEANUP >>\"$D290_TEST_STATE\"; printf '%s\\n' D290_ROOT_OVERLAY_UNMOUNTED=true D290_ROOT_HOST_PAM_RESTORED=true D290_ROOT_RUNTIME_REMOVED=true; exit 130; }\n"
                "trap on_signal HUP INT TERM\n"
                "stty -echo </dev/tty\n"
                "printf 'D290_TEST_AUTH_PROMPT\\n' >/dev/tty\n"
                "if [[ ${D290_TEST_PHASE:-} == signal_auth ]]; then kill -INT \"$D290_TEST_DRIVER_PID\"; fi\n"
                "IFS= read -r auth_input </dev/tty\n"
                "unset auth_input\n"
                "stty \"$saved\" </dev/tty; trap - EXIT\n"
                "printf 'D290_TEST_AUTH_COMPLETE\\n' >/dev/tty\n"
                "echo D290_TEST_AUTH_STDIN_TTY=true >>\"$D290_TEST_STATE\"\n"
                "echo D290_TEST_CONTROL_FIFO=true >>\"$D290_TEST_STATE\"\n"
                "exec 8<\"$fifo\"\n"
                "if [[ ${D290_TEST_PHASE:-} == signal_setup ]]; then kill -INT \"$D290_TEST_DRIVER_PID\"; sleep 1; fi\n"
                "printf '%s\\n' D290_ROOT_DAEMON_IDENTITY=true D290_ROOT_NAMESPACE_MATCH=true D290_ROOT_OVERLAY_READ_ONLY=true D290_ROOT_OVERLAY_READY=true\n"
                "echo D290_TEST_HELPER_BEFORE_CONTROL_READ=true\n"
                "if IFS= read -r command <&8; then\n"
                "  [[ $command == RELEASE ]]; echo D290_TEST_HELPER_RELEASE >>\"$D290_TEST_STATE\"\n"
                "else\n"
                "  echo D290_TEST_HELPER_EOF >>\"$D290_TEST_STATE\"\n"
                "fi\n"
                "printf '%s\\n' D290_ROOT_OVERLAY_UNMOUNTED=true D290_ROOT_HOST_PAM_RESTORED=true D290_ROOT_RUNTIME_REMOVED=true\n"
            )
            fake.chmod(0o755)
            driver = base / "driver.sh"
            driver.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                "base=$1; phase=$2; library=$3\n"
                "work=$base; capture=$base/capture; root_log=$work/root-overlay.log\n"
                "control_fifo=$work/d290-root-control.fifo; root_helper=$base/ignored-helper\n"
                "overlay_target=$base/overlay-target; overlay_expected_hash=$D290_TEST_EXPECTED\n"
                "helper_started=false; overlay_ready=false; overlay_closed=false\n"
                "root_pid=; root_control_fd=; root_out_fd=; root_unused_fd=\n"
                "export D290_TEST_DRIVER_PID=$$\n"
                "source \"$library\"\n"
                "on_exit () { local rc=$?; trap - EXIT; set +e; echo \"D290_TEST_PARENT_EXIT_TRAP_START=true helper=$helper_started closed=$overlay_closed fd=$root_control_fd\"; d290_release_overlay; d290_close_unstarted_channel; echo D290_TEST_PARENT_CLEANUP=true; exit $rc; }\n"
                "trap 'exit 130' HUP INT TERM; trap on_exit EXIT\n"
                "if [[ $phase == signal_before ]]; then echo D290_TEST_PHASE_BEFORE; kill -INT $$; sleep 30; fi\n"
                "coproc OLD_COLLISION { pkexec ignored --hold --control-fifo /dev/null; }\n"
                "IFS= read -r old_result <&\"${OLD_COLLISION[0]}\"; wait \"$OLD_COLLISION_PID\" || true\n"
                "echo \"$old_result\"\n"
                "d290_start_overlay\n"
                "echo D290_TEST_DRIVER_READY=true\n"
                "if [[ $phase == eof ]]; then\n"
                "  exec {root_control_fd}>&-; while IFS= read -r line <&\"$root_out_fd\"; do echo \"$line\"; done\n"
                "  set +e; wait \"$root_pid\"; set -e; overlay_closed=true; rm -f \"$control_fifo\"; exit 0\n"
                "fi\n"
                "if [[ $phase == signal_ready ]]; then echo D290_TEST_PHASE_READY; kill -INT $$; sleep 30; fi\n"
                "if [[ $phase == signal_after ]]; then echo D290_TEST_PHASE_AFTER_OUTCOME; kill -INT $$; sleep 30; fi\n"
                "d290_release_overlay\n"
                "echo D290_TEST_DRIVER_RELEASED=true\n"
                "trap - EXIT HUP INT TERM\n"
            )
            driver.chmod(0o755)
            runtime_token = secrets.token_hex(24)
            pid, master = pty.fork()
            if pid == 0:
                env = os.environ.copy()
                env.update({
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "D290_TEST_EXPECTED": expected,
                    "D290_TEST_PHASE": phase,
                    "D290_TEST_STATE": str(state_file),
                })
                os.execve(str(driver), [str(driver), str(base), phase, str(EXP / "privileged-channel.sh")], env)
            output = bytearray()
            sent_auth = False
            status = None
            deadline = time.time() + 8
            while time.time() < deadline:
                ready, _, _ = select.select([master], [], [], 0.05)
                if ready:
                    try:
                        output.extend(os.read(master, 4096))
                    except OSError:
                        pass
                text_output = output.decode(errors="replace")
                if "D290_TEST_AUTH_PROMPT" in text_output and not sent_auth and phase != "signal_auth":
                    os.write(master, (runtime_token + "\n").encode())
                    sent_auth = True
                waited, candidate_status = os.waitpid(pid, os.WNOHANG)
                if waited == pid:
                    status = candidate_status
                    break
            if status is None:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                self.fail(f"PTY fixture timed out for {phase}: {output.decode(errors='replace')}")
            os.close(master)
            decoded = output.decode(errors="replace")
            return os.waitstatus_to_exitcode(status), decoded, runtime_token, (
                state_file.read_text() if state_file.exists() else ""
            ), (base / "root-overlay.log").read_text() if (base / "root-overlay.log").exists() else ""

    def run_full_payload_pty(self, fingerprint_result):
        with tempfile.TemporaryDirectory(prefix="goodix-live-probe.") as td:
            base = Path(td)
            capture = base / "capture"
            state = base / "state"
            fake_bin = base / "bin"
            capture.mkdir()
            state.mkdir()
            fake_bin.mkdir()
            uid = os.getuid()

            def executable(name, content):
                path = fake_bin / name
                path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content)
                path.chmod(0o755)

            executable("id", f'if [[ ${{1:-}} == -u && $# -eq 1 ]]; then echo {uid}; elif [[ ${{1:-}} == -u && ${{2:-}} == plasmalogin ]]; then echo 987; else exec /usr/bin/id "$@"; fi\n')
            executable(
                "loginctl",
                f"""
if [[ $1 == list-sessions ]]; then
  if [[ -f $D290_TEST_STATE/outcome ]]; then
    [[ $D290_TEST_RESULT != match ]] || echo '6 {uid} user seat0 1 user tty2 no -'
    echo '5 987 plasmalogin seat0 1 greeter tty2 no -'
    echo '4 {uid} user seat0 1 user tty3 no -'
  elif [[ -f $D290_TEST_STATE/logged-out ]]; then
    echo '5 987 plasmalogin seat0 1 greeter tty2 no -'
    echo '4 {uid} user seat0 1 user tty3 no -'
  else
    echo '2 {uid} user seat0 1 user tty2 no -'
    echo '3 {uid} user - 1 manager - no -'
    echo '4 {uid} user seat0 1 user tty3 no -'
  fi
  exit 0
fi
sid=$2; prop=$4
if [[ $sid == 2 && $prop == State ]]; then
  count=0; [[ ! -f $D290_TEST_STATE/session2-state-count ]] || count=$(<$D290_TEST_STATE/session2-state-count)
  count=$((count + 1)); echo "$count" >$D290_TEST_STATE/session2-state-count
  if (( count > 1 )); then : >$D290_TEST_STATE/logged-out; exit 1; fi
fi
case "$sid:$prop" in
  2:Service) echo plasmalogin ;; 2:Type) echo wayland ;; 2:Class) echo user ;; 2:State) echo online ;; 2:TTY) echo tty2 ;;
  3:Service) echo systemd-user ;; 3:Type) echo unspecified ;; 3:Class) echo manager ;; 3:State) echo active ;; 3:TTY) echo '' ;;
  4:Service) echo login ;; 4:Type) echo tty ;; 4:Class) echo user ;; 4:State) echo active ;; 4:TTY) echo tty3 ;;
  5:Service) echo plasmalogin-greeter ;; 5:Type) echo wayland ;; 5:Class) echo greeter ;; 5:State) echo active ;; 5:TTY) echo tty2 ;;
  6:Service) echo plasmalogin ;; 6:Type) echo wayland ;; 6:Class) echo user ;; 6:State) echo online ;; 6:TTY) echo tty2 ;;
  *) exit 1 ;;
esac
""",
            )
            executable("pgrep", 'echo "$D290_TEST_GREETER_PID"\n')
            executable(
                "awk",
                'for arg in "$@"; do if [[ $arg == /proc/*/cgroup ]]; then echo /user.slice/user-987.slice/session-5.scope; exit 0; fi; done\nexec /usr/bin/awk "$@"\n',
            )
            executable(
                "journalctl",
                f"""
if [[ " $* " == *' --show-cursor '* ]]; then echo '-- cursor: s=d290-synthetic'; exit 0; fi
if [[ " $* " == *' -u fprintd.service '* ]]; then
  : >$D290_TEST_STATE/outcome
  echo 'GOODIX_SIGFM_MATCH_AUDIT event=outcome result={fingerprint_result}'
  echo 'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY attempts=1 rejected=0 consumed=1 tls=1 first_image=1 secure_retry=0 post_retry=0 reopen=0 reset=0 clear_halt=0 persistent=0 outstanding=0 drained=1 context_closed=1'
else
  echo 'PLASMALOGIN_SYNTHETIC_HOST_LOG=true'
fi
""",
            )
            executable(
                "sha256sum",
                "if [[ ${1:-} == /usr/lib/pam.d/plasmalogin ]]; then echo '89d389e6c2ee59dcee374029a5428a81dc9138c4f5e86068159b3d5a2c77ab2d  /usr/lib/pam.d/plasmalogin'; else exec /usr/bin/sha256sum \"$@\"; fi\n",
            )
            executable(
                "pkexec",
                """
[[ -t 0 ]]; fifo=; while [[ $# -gt 0 ]]; do if [[ $1 == --control-fifo ]]; then fifo=$2; break; fi; shift; done; [[ -p $fifo ]]
saved=$(stty -g </dev/tty); trap 'stty "$saved" </dev/tty' EXIT
stty -echo </dev/tty; printf 'D290_FULL_AUTH_PROMPT\n' >/dev/tty
IFS= read -r auth_input </dev/tty; unset auth_input
stty "$saved" </dev/tty; trap - EXIT; printf 'D290_FULL_AUTH_COMPLETE\n' >/dev/tty
exec 8<"$fifo"
printf '%s\n' D290_ROOT_DAEMON_IDENTITY=true D290_ROOT_NAMESPACE_MATCH=true D290_ROOT_OVERLAY_READ_ONLY=true D290_ROOT_OVERLAY_READY=true
if IFS= read -r command <&8; then [[ $command == RELEASE ]]; fi
printf '%s\n' D290_ROOT_OVERLAY_UNMOUNTED=true D290_ROOT_HOST_PAM_RESTORED=true D290_ROOT_RUNTIME_REMOVED=true
""",
            )
            telemetry = base / "telemetry.env"
            payload = EXP / "payload.sh"
            args = [
                str(payload), "--max-actions", "1", "--max-contacts", "1",
                "--max-retries", "0", "--timeout-seconds", "1200",
            ]
            token = secrets.token_hex(24)
            pid, master = pty.fork()
            if pid == 0:
                env = os.environ.copy()
                env.update({
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "LIVE_PROBE_MODE": "operator-run",
                    "LIVE_PROBE_WORK_DIR": str(base),
                    "LIVE_PROBE_CAPTURE_DIR": str(capture),
                    "LIVE_PROBE_TELEMETRY_FILE": str(telemetry),
                    "XDG_SESSION_TYPE": "tty",
                    "XDG_SESSION_ID": "4",
                    "XDG_VTNR": "3",
                    "D290_LOGINCTL": str(fake_bin / "loginctl"),
                    "D290_TEST_STATE": str(state),
                    "D290_TEST_RESULT": fingerprint_result,
                    "D290_TEST_GREETER_PID": str(os.getpid()),
                })
                os.execve(str(payload), args, env)
            output = bytearray()
            auth_sent = close_sent = False
            status = None
            deadline = time.time() + 10
            while time.time() < deadline:
                ready, _, _ = select.select([master], [], [], 0.05)
                if ready:
                    try:
                        output.extend(os.read(master, 8192))
                    except OSError:
                        pass
                decoded = output.decode(errors="replace")
                if "D290_FULL_AUTH_PROMPT" in decoded and not auth_sent:
                    os.write(master, (token + "\n").encode()); auth_sent = True
                if "CHIUDI D290:" in decoded and not close_sent:
                    os.write(master, b"CHIUDI D290\n"); close_sent = True
                waited, candidate_status = os.waitpid(pid, os.WNOHANG)
                if waited == pid:
                    status = candidate_status
                    break
            if status is None:
                os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
                self.fail(f"Full payload fixture timed out: {output.decode(errors='replace')}")
            os.close(master)
            decoded = output.decode(errors="replace")
            (capture / "payload.log").write_text(decoded)
            (capture / "context.env").write_text("LIVE_PROBE_MODE=operator-run\n")
            common = subprocess.run(
                [str(HARNESS / "classify_common.sh"), str(telemetry), "1", "1", "0", "PLASMALOGIN_MATCH_NEW_SESSION PLASMALOGIN_NO_MATCH_PASSWORD_RECOVERY_READY"],
                text=True, capture_output=True,
            )
            (capture / "common-classification.env").write_text(common.stdout)
            classified = subprocess.run([str(EXP / "classify.sh"), str(capture)], text=True, capture_output=True)
            all_capture = "".join(path.read_text(errors="replace") for path in capture.iterdir() if path.is_file())
            artifacts = {path.name: path.read_text(errors="replace") for path in capture.iterdir() if path.is_file()}
            return os.waitstatus_to_exitcode(status), decoded, token, common, classified, all_capture, artifacts

    def test_01_shell_syntax_and_executable(self):
        for name in (
            "payload.sh", "root-overlay.sh", "audit.sh", "cleanup.sh", "classify.sh", "sanitize.sh",
            "session-model.sh", "privileged-channel.sh", "root-overlay-lib.sh",
        ):
            path = EXP / name
            if name not in ("session-model.sh", "privileged-channel.sh", "root-overlay-lib.sh"):
                self.assertTrue(path.stat().st_mode & 0o111, name)
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_02_reuses_common_harness_with_one_shot_budget(self):
        for marker in (
            "EXPERIMENT_ID=d290-plasmalogin",
            "ACTION=PLASMALOGIN_ONE_SHOT_VERIFY",
            "MAX_ACTIONS=1",
            "MAX_CONTACTS=1",
            "MAX_RETRIES=0",
            "REQUIRES_ACTIVE_USER_SESSION=false",
            "LIVE_CAPABLE=true",
        ):
            self.assertIn(marker, self.config)

    def test_03_candidate_is_exact_host_stack_plus_bounded_fingerprint(self):
        host = Path("/usr/lib/pam.d/plasmalogin").read_text()
        fingerprint = "auth        sufficient    /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45 debug\n"
        first_auth = "auth     [success=done ignore=ignore default=bad] pam_selinux_permit.so\n"
        self.assertEqual(self.candidate, host.replace(first_auth, first_auth + fingerprint))
        self.assertEqual(self.candidate.count("pam_fprintd.so"), 1)
        self.assertEqual(self.candidate.count("password-auth"), host.count("password-auth"))

    def test_04_overlay_is_exact_read_only_and_recoverable(self):
        self.assertIn("target=/usr/lib/pam.d/plasmalogin", self.helper)
        self.assertIn('mount --bind "$runtime/plasmalogin" "$target"', self.root_lib)
        self.assertIn('mount -o remount,bind,ro "$target"', self.root_lib)
        self.assertIn("--recover", self.helper)
        self.assertIn("D290_ROOT_HOST_PAM_RESTORED=true", self.root_lib)
        self.assertIn("D290_ROOT_RUNTIME_REMOVED=true", self.root_lib)
        self.assertNotIn("authselect", self.helper + self.root_lib)

    def test_05_root_helper_pins_real_daemon_and_namespace_before_mount(self):
        identity = self.root_lib.index("daemon_pid=$(systemctl show plasmalogin.service")
        namespace = self.root_lib.index('stat -Lc %i "/proc/$daemon_pid/ns/mnt"')
        bind = self.root_lib.index('mount --bind "$runtime/plasmalogin" "$target"')
        self.assertLess(identity, namespace)
        self.assertLess(namespace, bind)
        for marker in (
            "/usr/bin/plasmalogin",
            "/system.slice/plasmalogin.service",
            "D290_ROOT_DAEMON_IDENTITY=true",
        ):
            self.assertIn(marker, self.root_lib)

    def test_06_tty_lifecycle_is_explicit_and_logout_is_manual(self):
        self.assertIn("XDG_SESSION_TYPE:-} == tty", self.payload)
        self.assertIn("XDG_VTNR:-} == 3", self.payload)
        self.assertIn("Ctrl+Alt+F2", self.payload)
        self.assertIn("Ctrl+Alt+F3", self.payload)
        self.assertNotIn("terminate-session", self.payload)
        self.assertNotIn("logout-session", self.payload)
        self.assertNotIn("org.kde.Shutdown", self.payload)

    def test_07_real_greeter_and_new_session_are_required(self):
        for marker in (
            "/usr/libexec/plasma-login-greeter",
            "plasmalogin-greeter",
            "greeter",
            "plasma-login.service",
            "d290_new_graphical_session_records",
            "PLASMALOGIN_MATCH_NEW_SESSION",
            "D290_NEW_GRAPHICAL_SESSION_CREATED=$session_created",
        ):
            self.assertIn(marker, self.payload)

    def test_08_exact_one_epoch_and_zero_retry_families(self):
        for field in (
            "attempts", "rejected", "consumed", "tls", "first_image",
            "secure_retry", "post_retry", "reopen", "reset", "clear_halt",
            "persistent", "outstanding", "drained", "context_closed",
        ):
            self.assertIn(f'field_sum {field} "$finger_log"', self.payload)
        self.assertNotIn("for attempt in", self.payload)
        self.assertIn("MAX_RETRIES=0", self.config)

    def test_09_overlay_is_released_before_operator_password_recovery(self):
        release = self.payload.index("\nd290_release_overlay\n", self.payload.index("if [[ $result == match ]]"))
        recovery = self.payload.index("usare la password", release)
        close = self.payload.index("CHIUDI D290", release)
        self.assertLess(release, recovery)
        self.assertLess(release, close)
        self.assertIn("D290_OVERLAY_RELEASED_BEFORE_PASSWORD_RECOVERY=true", self.payload)
        self.assertIn("cleanup overlay non confermato", self.payload)

    def test_10_privilege_and_control_channels_are_separate(self):
        self.assertIn('exec pkexec "$root_helper" --hold --control-fifo "$control_fifo"', self.privileged_channel)
        self.assertIn('--owner-pid $$ --owner-start-time "$owner_start_time" </dev/tty', self.privileged_channel)
        self.assertIn('exec {root_control_fd}<>"$control_fifo"', self.privileged_channel)
        self.assertIn('printf \'RELEASE\\n\' >&"$root_control_fd"', self.privileged_channel)
        self.assertIn('PAYLOAD_REQUIRES_FOREGROUND_TTY=true', self.config)
        self.assertNotIn('root_in_fd', self.payload + self.privileged_channel)

    def test_11_pre_post_audit_pins_host_and_d286_state(self):
        for marker in (
            "plasma-login-manager-6.7.5-1.fc44.x86_64",
            "root:root:644",
            "OPERATOR_SESSION_TTY tty3",
            "D290_INITIAL_GRAPHICAL_SESSION_COUNT",
            "D290_INITIAL_GRAPHICAL_SESSION_STATE",
            "d290_initial_graphical_session_records",
            "D286_01_STATE_COHERENCE=PASS_ROOT_ONLY",
            "D286_01_PASSWORD_FALLBACK=PASS",
            "D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES",
        ):
            self.assertIn(marker, self.audit)

    def test_12_classifier_requires_session_causality_and_cleanup(self):
        for marker in (
            "D290_NEW_GRAPHICAL_SESSION_CREATED=true",
            "D290_NEW_GRAPHICAL_SESSION_CREATED=false",
            "D290_NEW_GRAPHICAL_SESSION_SERVICE=plasmalogin",
            'new_session != "$initial_session"',
            "D290_ROOT_OVERLAY_UNMOUNTED=true",
            "D290_ROOT_HOST_PAM_RESTORED=true",
            "D290_ROOT_RUNTIME_REMOVED=true",
        ):
            self.assertIn(marker, self.classifier)

    def test_13_operator_instructions_are_direct_and_fail_closed(self):
        for marker in (
            "Human Gate",
            "PREPARA LOGIN D290",
            "CHIUDI D290",
            "campo password, premere",
            "appoggiare una sola volta l'indice destro",
            "non rilanciare",
            "--recover",
        ):
            self.assertIn(marker, self.readme)

    def test_14_no_direct_usb_or_persistent_sensor_command(self):
        combined = "\n".join((self.payload, self.helper, self.root_lib, self.privileged_channel, self.audit))
        for forbidden in ("/dev/bus/usb", "usb.core", "ClearApp", "provision", "IAP", "flash"):
            self.assertNotIn(forbidden, combined)

    def test_15_observed_nonforeground_initial_graphical_session_is_unique(self):
        records = self.session_records(
            [
                {"id": 2, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": "online", "TTY": "tty2"},
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_initial_graphical_session_records", 1000, 4,
        )
        self.assertEqual(records, [["2", "tty2", "plasmalogin", "wayland", "user", "online"]])

    def test_16_missing_tty2_graphical_session_fails_cardinality(self):
        records = self.session_records(
            [
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_initial_graphical_session_records", 1000, 4,
        )
        self.assertEqual(records, [])

    def test_17_two_initial_wayland_candidates_fail_cardinality(self):
        sessions = [
            {"id": sid, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": state, "TTY": "tty2"}
            for sid, state in ((2, "online"), (5, "active"))
        ]
        records = self.session_records(sessions, "d290_initial_graphical_session_records", 1000, 4)
        self.assertEqual([record[0] for record in records], ["2", "5"])

    def test_18_manager_and_operator_tty_are_not_graphical_candidates(self):
        records = self.session_records(
            [
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_initial_graphical_session_records", 1000, 4,
        )
        self.assertEqual(records, [])

    def test_19_wrong_initial_identity_property_is_rejected(self):
        valid = {"id": 2, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": "online", "TTY": "tty2"}
        for prop, wrong in (("Service", "sddm"), ("Type", "x11"), ("Class", "greeter"), ("TTY", "tty1"), ("State", "closing")):
            with self.subTest(prop=prop):
                session = dict(valid)
                session[prop] = wrong
                self.assertEqual(
                    self.session_records([session], "d290_initial_graphical_session_records", 1000, 4),
                    [],
                )

    def test_20_match_detects_only_a_new_plasmalogin_wayland_id(self):
        records = self.session_records(
            [
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
                {"id": 5, "Service": "plasmalogin", "Type": "wayland", "Class": "user", "State": "online", "TTY": "tty2"},
            ],
            "d290_new_graphical_session_records", 1000, 4, 2,
        )
        self.assertEqual(records[0][0], "5")

    def test_21_no_match_has_no_new_graphical_session(self):
        records = self.session_records(
            [
                {"id": 3, "Service": "systemd-user", "Type": "unspecified", "Class": "manager", "State": "active", "TTY": ""},
                {"id": 4, "Service": "login", "Type": "tty", "Class": "user", "State": "active", "TTY": "tty3"},
            ],
            "d290_new_graphical_session_records", 1000, 4, 2,
        )
        self.assertEqual(records, [])

    def test_22_pre_audit_failure_skips_payload_artifacts_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            experiment = root / "experiment"
            captures = root / "captures"
            experiment.mkdir()
            (experiment / "experiment.conf").write_text(
                "EXPERIMENT_ID=d290-preaudit-test\n"
                "GOAL='Test D290 pre-audit failure'\nACTION=OFFLINE_TEST\n"
                "PAYLOAD=payload.sh\nMAX_ACTIONS=1\nMAX_CONTACTS=1\nMAX_RETRIES=0\nTIMEOUT_SECONDS=10\n"
                "REQUIRES_ROOT=false\nREQUIRES_ACTIVE_USER_SESSION=false\nLIVE_CAPABLE=false\n"
                "OFFLINE_TEST_CAPABLE=true\nOUTPUT_IS_SANITIZED=true\nEXPECTED_TELEMETRY=NEVER\n"
                "STOP_CONDITIONS='pre audit failure'\nCONFIRMATION_TEXT=NEVER\n"
                "PRE_AUDIT=audit.sh\nPOST_AUDIT=audit.sh\nCLEANUP=cleanup.sh\nCLASSIFIER=classify.sh\n"
                "PAYLOAD_ACCEPTED_RETURN_CODES=0\nCOLLECT_JOURNAL=false\n"
            )
            scripts = {
                "payload.sh": "#!/usr/bin/env bash\necho PAYLOAD_MUST_NOT_RUN\n",
                "audit.sh": (
                    "#!/usr/bin/env bash\n"
                    "if [[ $2 == pre ]]; then echo D290_PRE_AUDIT=FAIL; exit 1; fi\n"
                    "echo D290_POST_AUDIT=PASS\n"
                ),
                "cleanup.sh": "#!/usr/bin/env bash\necho D290_CLEANUP=PASS\n",
            }
            for name, content in scripts.items():
                path = experiment / name
                path.write_text(content)
                path.chmod(0o755)
            (experiment / "classify.sh").symlink_to(EXP / "classify.sh")
            result = subprocess.run(
                [str(HARNESS / "run.sh"), "d290-preaudit-test", "--offline-test", "--capture-root", str(captures)],
                cwd="/tmp",
                text=True,
                capture_output=True,
                env={"PATH": "/usr/bin:/bin", "LIVE_PROBE_TEST_EXPERIMENT_DIR": str(experiment)},
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("No such file", result.stdout + result.stderr)
            self.assertNotIn("PAYLOAD_MUST_NOT_RUN", result.stdout + result.stderr)
            sanitized = next(captures.glob("*/sanitized"))
            self.assertFalse((sanitized / "payload.log").exists())
            self.assertEqual(
                (sanitized / "payload-classification.env").read_text().strip(),
                "D290_PAYLOAD_CLASSIFICATION=NOT_APPLICABLE_PRE_AUDIT_FAILURE",
            )
            summary = (sanitized / "summary.env").read_text()
            self.assertIn("LIVE_PROBE_RESULT=FAIL_PRE_AUDIT", summary)
            self.assertIn("LIVE_PROBE_PRIMARY_FAILURE=PRE_AUDIT", summary)
            self.assertIn("LIVE_PROBE_PAYLOAD_STARTED=false", summary)
            self.assertIn("LIVE_PROBE_PAYLOAD_CLASSIFIER_RETURN_CODE=0", summary)

    def test_23_overlay_prepare_release_and_idempotent_cleanup(self):
        result, state = self.run_overlay_fixture("prepare")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("D290_ROOT_HOST_PAM_RESTORED=true"), 2)
        self.assertEqual(state, {"target": "HOST_PAM_FIXTURE\n", "runtime": False, "mounted": False, "cleanup": ""})

    def test_24_control_fifo_release_exits_cleanly(self):
        result, state = self.run_overlay_fixture("hold")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("D290_ROOT_OVERLAY_READY=true", result.stdout)
        self.assertFalse(state["runtime"])
        self.assertFalse(state["mounted"])
        self.assertEqual(state["target"], "HOST_PAM_FIXTURE\n")

    def test_24b_control_fifo_wrong_mode_parent_or_symlink_is_refused(self):
        for scenario in ("fifo_wrong_mode", "parent_wrong_mode", "fifo_symlink"):
            with self.subTest(scenario=scenario):
                result, state = self.run_overlay_fixture("hold", scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(state["runtime"])
                self.assertFalse(state["mounted"])

    def test_25_prepare_failure_before_runtime_is_clean(self):
        result, state = self.run_overlay_fixture("prepare", "daemon_fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state["runtime"])
        self.assertFalse(state["mounted"])
        self.assertIn("D290_ROOT_HOST_PAM_RESTORED=true", state["cleanup"])

    def test_26_prepare_failure_after_runtime_creation_is_clean(self):
        result, state = self.run_overlay_fixture("prepare", "after_runtime_fail")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state["runtime"])
        self.assertFalse(state["mounted"])
        self.assertEqual(state["target"], "HOST_PAM_FIXTURE\n")

    def test_27_bind_or_remount_failure_cleans_owned_state(self):
        for scenario in ("bind_fail", "remount_fail"):
            with self.subTest(scenario=scenario):
                result, state = self.run_overlay_fixture("prepare", scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(state["runtime"])
                self.assertFalse(state["mounted"])
                self.assertEqual(state["target"], "HOST_PAM_FIXTURE\n")

    def test_28_preexisting_mount_and_unexpected_host_content_are_refused(self):
        mounted_result, mounted_state = self.run_overlay_fixture("prepare", "mount_already")
        self.assertNotEqual(mounted_result.returncode, 0)
        self.assertTrue(mounted_state["mounted"])
        wrong_result, wrong_state = self.run_overlay_fixture("prepare", "wrong_host")
        self.assertNotEqual(wrong_result.returncode, 0)
        self.assertFalse(wrong_state["mounted"])
        self.assertFalse(wrong_state["runtime"])

    def test_29_recovery_accepts_only_expected_candidate(self):
        good_result, good_state = self.run_overlay_fixture("recover", "recover_expected")
        self.assertEqual(good_result.returncode, 0, good_result.stdout + good_result.stderr)
        self.assertEqual(good_state["target"], "HOST_PAM_FIXTURE\n")
        self.assertFalse(good_state["mounted"])
        bad_result, bad_state = self.run_overlay_fixture("recover", "recover_wrong")
        self.assertNotEqual(bad_result.returncode, 0)
        self.assertTrue(bad_state["mounted"])
        self.assertEqual(bad_state["target"], "WRONG_CANDIDATE\n")

    def test_30_interactive_auth_uses_tty_and_fifo_control_without_echo(self):
        rc, output, token, state, root_log = self.run_privilege_pty()
        self.assertEqual(rc, 0, output)
        self.assertIn("D290_TEST_AUTH_STDIN_NOT_TTY", output)
        self.assertIn("D290_TEST_AUTH_STDIN_TTY=true", state)
        self.assertIn("D290_TEST_CONTROL_FIFO=true", state)
        self.assertIn("D290_TEST_DRIVER_READY=true", output)
        self.assertIn("D290_TEST_DRIVER_RELEASED=true", output)
        self.assertIn("D290_TEST_HELPER_RELEASE", state)
        self.assertNotIn(token, output + root_log + state)

    def test_31_parent_control_eof_is_bounded_cleanup(self):
        rc, output, token, state, root_log = self.run_privilege_pty("eof")
        self.assertEqual(rc, 0, output)
        self.assertIn("D290_TEST_HELPER_EOF", state)
        self.assertIn("D290_ROOT_HOST_PAM_RESTORED=true", output)
        self.assertNotIn(token, output + root_log + state)

    def test_31b_owner_pid_starttime_watchdog_cleans_parent_death(self):
        result, state = self.run_overlay_fixture("owner_death")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state["runtime"])
        self.assertFalse(state["mounted"])
        self.assertEqual(state["target"], "HOST_PAM_FIXTURE\n")
        self.assertIn("D290_ROOT_RUNTIME_REMOVED=true", state["cleanup"])

    def test_32_signals_before_setup_during_setup_and_when_ready_cleanup(self):
        for phase in ("signal_before", "signal_auth", "signal_setup", "signal_ready"):
            with self.subTest(phase=phase):
                rc, output, token, state, root_log = self.run_privilege_pty(phase)
                self.assertEqual(rc, 130, output)
                self.assertIn("D290_TEST_PARENT_CLEANUP=true", output)
                if phase != "signal_before":
                    self.assertTrue(
                        "D290_TEST_HELPER_RELEASE" in state or "D290_TEST_HELPER_SIGNAL_CLEANUP" in state,
                        state,
                    )
                self.assertNotIn(token, output + root_log)

    def test_33_signal_after_outcome_releases_before_exit(self):
        rc, output, token, state, root_log = self.run_privilege_pty("signal_after")
        self.assertEqual(rc, 130, output)
        self.assertIn("D290_TEST_PHASE_AFTER_OUTCOME", output)
        self.assertTrue(
            "D290_TEST_HELPER_RELEASE" in state or "D290_TEST_HELPER_SIGNAL_CLEANUP" in state,
            state,
        )
        self.assertIn("D290_ROOT_OVERLAY_UNMOUNTED=true", output)
        self.assertNotIn(token, output + root_log)

    def test_34_full_host_payload_match_and_no_match_paths(self):
        for result_name, expected_outcome, expected_session in (
            ("match", "PLASMALOGIN_MATCH_NEW_SESSION", "D290_NEW_GRAPHICAL_SESSION=6"),
            ("no_match", "PLASMALOGIN_NO_MATCH_PASSWORD_RECOVERY_READY", "D290_NEW_GRAPHICAL_SESSION=NONE"),
        ):
            with self.subTest(result=result_name):
                rc, output, token, common, classified, all_capture, artifacts = self.run_full_payload_pty(result_name)
                self.assertEqual(rc, 0, output)
                self.assertEqual(common.returncode, 0, common.stdout + common.stderr)
                self.assertEqual(classified.returncode, 0, classified.stdout + classified.stderr)
                self.assertIn(f"D290_OUTCOME={expected_outcome}", artifacts["payload-details.env"])
                self.assertIn(expected_session, artifacts["login-state.env"])
                self.assertIn("D290_INITIAL_GRAPHICAL_LOGOUT_OBSERVED=true", artifacts["login-state.env"])
                self.assertIn("D290_REAL_GREETER_SESSION=5", artifacts["login-state.env"])
                self.assertIn("D290_PAYLOAD_CLASSIFICATION=PASS_LIVE_PENDING_INDEPENDENT_REVIEW", classified.stdout)
                self.assertIn("D290_ROOT_OVERLAY_UNMOUNTED=true", artifacts["root-overlay.log"])
                self.assertNotIn(token, output + all_capture)

    def test_35_second_operator_abort_capture_is_integral_and_pre_verify(self):
        check = subprocess.run(
            ["sha256sum", "-c", "capture.sha256"], cwd=SECOND_CAPTURE, text=True, capture_output=True,
        )
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn(
            "LIVE_PROBE_BASELINE=603a47cdf1c1b6672c6d26c589648aab973aeeaf",
            (SECOND_CAPTURE / "context.env").read_text(),
        )
        self.assertIn("D290_PRE_AUDIT=PASS", (SECOND_CAPTURE / "pre-audit.log").read_text())
        self.assertEqual((SECOND_CAPTURE / "payload.log").read_bytes(), b"")
        summary = (SECOND_CAPTURE / "summary.env").read_text()
        self.assertIn("LIVE_PROBE_RESULT=INTERRUPTED", summary)
        self.assertIn("LIVE_PROBE_PAYLOAD_STARTED=true", summary)
        self.assertIn("LIVE_PROBE_PAYLOAD_RETURN_CODE=130", summary)
        self.assertIn("D290_CLEANUP=PASS", (SECOND_CAPTURE / "cleanup.log").read_text())
        self.assertNotIn("GOODIX_", (SECOND_CAPTURE / "diagnostic-journal.log").read_text())
        for absent in ("telemetry.env", "payload-details.env", "login-state.env", "root-overlay.log"):
            self.assertFalse((SECOND_CAPTURE / absent).exists(), absent)

    def test_36_real_offline_harness_path(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [str(HARNESS / "run.sh"), "d290-plasmalogin", "--offline-test", "--capture-root", td],
                cwd="/tmp",
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("LIVE_PROBE_RESULT=PASS", result.stdout)
            captures = list(Path(td).glob("*/sanitized"))
            self.assertEqual(len(captures), 1)
            self.assertIn(
                "D290_PAYLOAD_CLASSIFICATION=PASS_OFFLINE",
                (captures[0] / "payload-classification.env").read_text(),
            )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d282-03-balanced-same-different"
LAUNCHER = KIT / "run-d282-03.sh"
README = KIT / "README_IT.md"
AUDITOR = ROOT / "analysis/D282/d282_03_trial_audit.py"
D28201 = ROOT / "operator_kit/d282-01-fprintd-target/run-d282-01.sh"
D28202 = ROOT / "operator_kit/d282-02-matcher-order/run-d282-02.sh"
D283 = ROOT / "operator_kit/d283-01-pam-dedicated/run-d283-01.sh"
ATTEMPT_02 = (ROOT / "captures/D282_02" /
              "D28202_ATTEMPT_02_20260910T220312Z_f868ad127b30" /
              "sanitized")
FINGERS = ("RIGHT_INDEX", "LEFT_INDEX", "RIGHT_INDEX",
           "LEFT_INDEX", "RIGHT_INDEX", "LEFT_INDEX")


def function_slice(text: str, start: str, end: str) -> str:
    offset = text.index(start)
    return text[offset:text.index(end, offset)]


def write_trial(root: Path, trial: int, result: str) -> None:
    block = "A" if trial <= 3 else "B"
    position = trial if trial <= 3 else trial - 3
    finger = FINGERS[trial - 1]
    identity = "SAME" if finger == "RIGHT_INDEX" else "DIFFERENT"
    rc = 0 if result == "match" else 1
    stem = root / f"trial-{trial:02d}"
    (stem.with_suffix(".meta")).write_text(
        f"TRIAL={trial}\nGLOBAL_ORDER={trial}\nBLOCK={block}\n"
        f"BLOCK_POSITION={position}\nPHYSICAL_FINGER={finger}\n"
        f"IDENTITY_CLASS={identity}\n"
        f"OPERATOR_CONFIRMATION={'DESTRO' if finger == 'RIGHT_INDEX' else 'SINISTRO'}\n"
        f"DAEMON_PID={100 if block == 'A' else 200}\n"
        f"DAEMON_INVOCATION_ID={'a' * 32 if block == 'A' else 'b' * 32}\n"
        f"ACTION_RETURN_CODE={rc}\n")
    client = "verify-match" if result == "match" else "verify-no-match"
    (stem.with_suffix(".raw")).write_text(
        f"Verify result: {client} (done)\n")
    lines = [
        "GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=8 threshold=40",
    ]
    scores = [55] if result == "match" else list(range(10, 18))
    lines.extend(
        f"GOODIX_SIGFM_MATCH_AUDIT event=comparison sample={index} "
        f"score={score} threshold=40"
        for index, score in enumerate(scores, 1))
    lines.append(
        "GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match matched_sample=1 "
        "comparisons=1 threshold=40" if result == "match" else
        "GOODIX_SIGFM_MATCH_AUDIT event=outcome result=no_match matched_sample=0 "
        "comparisons=8 threshold=40")
    lines.extend([
        "GOODIX_SIGFM_EXTRACT_AUDIT keypoints=131",
        "GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY "
        "attempts=1 rejected=0 consumed=1 tls=1 first_image=1 "
        "release_tail=1 single_terminal=1 rearm32=0 enroll_stages=0 "
        "enroll_rearm32=0 enroll_terminal=0 secure_retry=0 post_retry=0 "
        "reopen=0 reset=0 clear_halt=0 persistent=0 real_submit=82 "
        "outstanding=0 drained=1 context_closed=1",
    ])
    (root / f"trial-{trial:02d}.journal.raw").write_text("\n".join(lines) + "\n")


class D28203OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = LAUNCHER.read_text()
        cls.readme = README.read_text()
        cls.auditor = AUDITOR.read_text()
        cls.d28201 = D28201.read_text()
        cls.d28202 = D28202.read_text()
        cls.d283 = D283.read_text()

    def test_01_attempt_02_evidence_is_hash_pinned(self):
        expected = {
            "operator.log": "8152304946f7d5d3ab4d8859d80970331c4505fb931644251fd320ba9eda3afb",
            "summary.env": "a1f84c32d23283966bf68e9f3944e676faf5e2b638f0fae78e7bb2e782cf028f",
            "trials.tsv": "ba115e1772e3d31d90a98bbd103526ee2fd377558664e4290cb7a72ee9ce87ab",
            "terminal-transcript.log": "cacc131befbd20ff5cbce56ad7dbf1d2a37eac28eb8ac42e22ab5112a2be69f5",
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ATTEMPT_02 / name).read_bytes()).hexdigest(), digest)

    def test_02_d28202_live_entrypoints_are_closed(self):
        self.assertIn("d28202_live_closed=true", self.d28202)
        self.assertEqual(self.d28202.count("D282_02_LIVE_CLOSED_DO_NOT_RERUN"), 2)

    def test_03_schedule_is_balanced_and_fixed(self):
        live = function_slice(self.launcher, "run_d28203_live ()", "export_d28203_results ()")
        self.assertIn("for trial in 1 2 3", live)
        self.assertIn("for trial in 4 5 6", live)
        self.assertIn('case $1 in', self.launcher)
        self.assertIn('1|3|5) echo RIGHT_INDEX', self.launcher)
        self.assertIn('2|4|6) echo LEFT_INDEX', self.launcher)

    def test_04_no_algorithm_or_stage_change(self):
        self.assertIn("D282_03_ENROLLMENT_CONTACT_COUNT=8", self.launcher)
        self.assertIn("D282_03_SIGFM_THRESHOLD_EXPECTED=40", self.launcher)
        self.assertIn("D282_03_ALGORITHM_CHANGE=false", self.launcher)
        self.assertNotIn("score_threshold =", self.launcher)

    def test_05_each_trial_is_one_command_without_retry(self):
        trial = function_slice(self.launcher, "run_d28203_verify_trial ()", "run_d28203_live ()")
        self.assertEqual(trial.count('fprintd-verify "$user"'), 1)
        self.assertNotIn("while", trial)
        self.assertIn("verify-retry-", trial)
        self.assertIn("return 1", trial)

    def test_06_process_blocks_and_pre_action_gate(self):
        live = function_slice(self.launcher, "run_d28203_live ()", "export_d28203_results ()")
        self.assertEqual(live.count("systemctl restart fprintd.service"), 2)
        self.assertIn("verify_daemon_map BLOCK_A", live)
        self.assertIn("verify_daemon_map BLOCK_B", live)
        self.assertIn("PROCESS_BLOCK_DRIFT_PRE_ACTION", self.launcher)

    def test_07_poka_yoke_and_hidden_client_output(self):
        trial = function_slice(self.launcher, "run_d28203_verify_trial ()", "run_d28203_live ()")
        self.assertIn("Digita %s, poi appoggia quel dito", trial)
        self.assertIn('>"$raw" 2>&1', trial)
        self.assertNotIn("tee", trial)
        self.assertIn("FINGER_NOT_CONFIRMED", trial)

    def test_08_budgets_are_seven_actions_and_fourteen_contacts(self):
        self.assertIn("BIOMETRIC_ACTION_MAX=7", self.launcher)
        self.assertIn("EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=14", self.launcher)
        self.assertIn("VERIFY_ACTION_COUNT=6", self.launcher)

    def test_09_auditor_accepts_mixed_outcomes_and_marks_censoring(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d282-03-audit-") as td:
            work = Path(td)
            for trial, result in enumerate(
                    ("match", "no_match", "match", "no_match", "match", "no_match"), 1):
                write_trial(work, trial, result)
            output, env = work / "trials.tsv", work / "summary.env"
            subprocess.run([str(AUDITOR), str(work), str(output), str(env)], check=True)
            rows = output.read_text().splitlines()
            self.assertEqual(len(rows), 7)
            self.assertIn("score_vector_complete", rows[0])
            self.assertIn("observed_max_score", rows[0])
            self.assertIn("D282_03_SAME_FINGER_MATCH_COUNT=3", env.read_text())
            self.assertIn("D282_03_DIFFERENT_FINGER_MATCH_COUNT=0", env.read_text())

    def test_10_auditor_rejects_finger_schedule_drift(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d282-03-audit-") as td:
            work = Path(td)
            for trial in range(1, 7):
                write_trial(work, trial, "match")
            meta = work / "trial-02.meta"
            meta.write_text(meta.read_text().replace("LEFT_INDEX", "RIGHT_INDEX"))
            result = subprocess.run([str(AUDITOR), str(work), str(work / "out.tsv"),
                                     str(work / "out.env")], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_11_cleanup_and_export_are_bounded(self):
        self.assertIn("/run/goodix-d282-03/*", self.d28201)
        self.assertIn("/var/lib/fprint/.goodix-d282-03-*", self.d28201)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", self.launcher)
        self.assertNotIn("rm -rf /var/lib/fprint", self.launcher)

    def test_12_d283_remains_fail_closed(self):
        self.assertIn("D282_03_D283_LIVE_STANDBY=true", self.launcher)
        self.assertIn("d283_live_standby=true", self.d283)

    def test_13_operator_entrypoint_is_direct(self):
        operator = function_slice(self.launcher, "operator_d28203_run ()", "offline_preflight ()")
        self.assertIn("Digitare ESEGUI", operator)
        self.assertIn("--run-live", operator)
        self.assertIn("--export-results", operator)
        self.assertNotIn("grant", operator.lower())

    def test_14_offline_preflight_cannot_call_live(self):
        offline = function_slice(self.launcher, "offline_preflight ()", "case ${1:-} in")
        self.assertIn("REAL_USB_ENUMERATION_ATTEMPTED=false", offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)
        self.assertIn("LIVE_EXECUTION_PERFORMED=false", offline)
        self.assertNotIn("run_d28203_live", offline)

    def test_15_preaction_export_does_not_require_trials(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d282-03-export-") as td:
            work = Path(td); result = work / "result"; export = work / "export"
            (result / "private").mkdir(parents=True); export.mkdir()
            (result / "operator.log").write_text("D282_03_FAILURE_PHASE=PRE_SENSOR_STAGING\n")
            (result / "summary.env").write_text("D282_03_RESULT=FAIL_PRE_SENSOR_STAGING\n")
            completed = subprocess.run(
                ["bash", "-c", 'D28203_LIBRARY_ONLY=true; source "$0"; copy_d28203_result_set "$1" "$2" "$(id -u)" "$(id -g)"',
                 str(LAUNCHER), str(result), str(export)], check=True,
                capture_output=True, text=True)
            self.assertIn("D282_03_TRIALS_TSV_EXPORTED=false", completed.stdout)
            self.assertTrue((export / "operator.log").is_file())
            self.assertTrue((export / "summary.env").is_file())
            self.assertFalse((export / "trials.tsv").exists())

    def test_16_readme_forbids_rerun_and_explains_early_return(self):
        self.assertIn("non deve essere ripetuto", self.readme)
        self.assertIn("score_vector_complete", self.readme)
        self.assertIn("non un verdetto statistico", self.readme)


if __name__ == "__main__":
    unittest.main()

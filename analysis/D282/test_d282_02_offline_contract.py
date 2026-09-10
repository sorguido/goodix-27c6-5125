#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d282-02-matcher-order"
LAUNCHER = KIT / "run-d282-02.sh"
AUDITOR = ROOT / "analysis/D282/d282_02_trial_audit.py"
FPI_PRINT = ROOT / "reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-print.c"
FP_IMAGE = ROOT / "reference/libfprint-fedora44-1.94.100/source/libfprint/fp-image.c"
D282 = ROOT / "operator_kit/d282-01-fprintd-target/run-d282-01.sh"
D283 = ROOT / "operator_kit/d283-01-pam-dedicated/run-d283-01.sh"


def function_slice(text: str, start: str, end: str) -> str:
    offset = text.index(start)
    return text[offset:text.index(end, offset)]


def write_trial(root: Path, trial: int, result: str) -> None:
    block = "A" if trial <= 2 else "B"
    position = 1 if trial % 2 else 2
    rc = 0 if result == "match" else 1
    stem = root / f"trial-{trial:02d}"
    (stem.with_suffix(".meta")).write_text(
        f"TRIAL={trial}\nGLOBAL_ORDER={trial}\nBLOCK={block}\n"
        f"BLOCK_POSITION={position}\nPHYSICAL_FINGER=RIGHT_INDEX\n"
        f"DAEMON_PID={100 if block == 'A' else 200}\n"
        f"DAEMON_INVOCATION_ID={'a' * 32 if block == 'A' else 'b' * 32}\n"
        f"ACTION_RETURN_CODE={rc}\n")
    client = ("verify-match" if result == "match" else "verify-no-match")
    (stem.with_suffix(".raw")).write_text(
        "Verifying: right-index-finger\n"
        f"Verify result: {client} (done)\n")
    lines = [
        "GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=8 threshold=40",
    ]
    scores = [55] if result == "match" else list(range(10, 18))
    lines.extend(
        f"GOODIX_SIGFM_MATCH_AUDIT event=comparison sample={index} "
        f"score={score} threshold=40"
        for index, score in enumerate(scores, 1))
    if result == "match":
        lines.append(
            "GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match "
            "matched_sample=1 comparisons=1 threshold=40")
    else:
        lines.append(
            "GOODIX_SIGFM_MATCH_AUDIT event=outcome result=no_match "
            "matched_sample=0 comparisons=8 threshold=40")
    lines.extend([
        "GOODIX_SIGFM_EXTRACT_AUDIT keypoints=31",
        "GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_VERIFY "
        "attempts=1 rejected=0 consumed=1 tls=1 first_image=1 "
        "release_tail=1 single_terminal=1 rearm32=0 enroll_stages=0 "
        "enroll_rearm32=0 enroll_terminal=0 secure_retry=0 post_retry=0 "
        "reopen=0 reset=0 clear_halt=0 persistent=0 real_submit=82 "
        "outstanding=0 drained=1 context_closed=1",
    ])
    (root / f"trial-{trial:02d}.journal.raw").write_text("\n".join(lines) + "\n")


class D28202OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = LAUNCHER.read_text()
        cls.auditor = AUDITOR.read_text()
        cls.fpi_print = FPI_PRINT.read_text()
        cls.fp_image = FP_IMAGE.read_text()
        cls.d282 = D282.read_text()
        cls.d283 = D283.read_text()

    def test_01_matcher_telemetry_is_observational(self):
        match = function_slice(
            self.fpi_print, "fpi_print_sigfm_match (", "fpi_print_generate_user_id:")
        self.assertIn("GOODIX_SIGFM_MATCH_AUDIT event=start", match)
        self.assertIn("GOODIX_SIGFM_MATCH_AUDIT event=comparison", match)
        self.assertIn("GOODIX_SIGFM_MATCH_AUDIT event=outcome", match)
        self.assertIn("if (score >= score_threshold)", match)
        self.assertIn("return FPI_MATCH_SUCCESS", match)
        self.assertIn("return FPI_MATCH_FAIL", match)
        self.assertNotIn("score_threshold =", match)

    def test_02_probe_keypoints_are_logged_without_pixels(self):
        self.assertIn("GOODIX_SIGFM_EXTRACT_AUDIT keypoints=%d", self.fp_image)
        telemetry_line = next(line for line in self.fp_image.splitlines()
                              if "GOODIX_SIGFM_EXTRACT_AUDIT" in line)
        self.assertNotIn("pixel", telemetry_line.lower())
        self.assertNotIn("image", telemetry_line.lower())

    def test_03_schedule_is_four_planned_same_finger_trials(self):
        live = function_slice(self.launcher, "run_d28202_live ()", "export_d28202_results ()")
        self.assertIn("for trial in 1 2", live)
        self.assertIn("for trial in 3 4", live)
        self.assertEqual(live.count('run_verify_trial "$trial"'), 2)
        self.assertIn("PHYSICAL_FINGER=RIGHT_INDEX", self.launcher)
        self.assertNotIn("INDICE SINISTRO", self.launcher)

    def test_04_two_process_blocks_are_separated_by_restart(self):
        live = function_slice(self.launcher, "run_d28202_live ()", "export_d28202_results ()")
        self.assertEqual(live.count("systemctl restart fprintd.service"), 2)
        self.assertIn("verify_daemon_map BLOCK_A", live)
        self.assertIn("verify_daemon_map BLOCK_B", live)
        self.assertIn("DAEMON_RESTART_INVOCATION_ID_UNCHANGED", live)
        self.assertIn("PROCESS_BLOCK_DRIFT_PRE_ACTION", self.launcher)
        self.assertIn("D282_02_DAEMON_PROCESS_BLOCKS_VERIFIED", self.auditor)
        self.assertIn("DAEMON_PROCESS_BLOCK_COUNT=2", live)

    def test_05_each_trial_is_one_explicit_command_without_retry(self):
        trial = function_slice(self.launcher, "run_verify_trial ()", "run_d28202_live ()")
        self.assertEqual(trial.count('fprintd-verify "$user"'), 1)
        self.assertNotIn("while", trial)
        self.assertIn("verify-retry-", trial)
        self.assertIn("return 1", trial)

    def test_06_human_factors_hide_client_output_and_number_trials(self):
        trial = function_slice(self.launcher, "run_verify_trial ()", "run_d28202_live ()")
        self.assertIn("TEST %02d/04", trial)
        self.assertIn(">>> INDICE DESTRO <<<", trial)
        self.assertIn('>"$raw" 2>&1', trial)
        self.assertNotIn("tee", trial)
        self.assertIn("RISULTATO TEST", trial)

    def test_07_budget_is_five_actions_and_twelve_contacts(self):
        self.assertIn("BIOMETRIC_ACTION_MAX=5", self.launcher)
        self.assertIn("EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=12", self.launcher)
        self.assertIn("ENROLL_ACTION_COUNT=1", self.launcher)
        self.assertIn("VERIFY_ACTION_COUNT=4", self.launcher)

    def test_08_auditor_requires_real_scores_threshold_and_keypoints(self):
        self.assertIn('template_samples != 8 or threshold != 40', self.auditor)
        self.assertIn('comparison["score"]', self.auditor)
        self.assertIn('extracts[0]["keypoints"]', self.auditor)
        self.assertIn('"scores_by_enrolled_sample"', self.auditor)

    def test_09_auditor_accepts_mixed_outcomes_without_generalizing(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d282-02-audit-") as td:
            work = Path(td)
            for trial, result in enumerate(
                    ("match", "no_match", "match", "no_match"), 1):
                write_trial(work, trial, result)
            output = work / "trials.tsv"
            env = work / "summary.env"
            subprocess.run(
                [str(AUDITOR), str(work), str(output), str(env)], check=True)
            self.assertEqual(len(output.read_text().splitlines()), 5)
            self.assertIn("D282_02_TRIAL_AUDIT=PASS", env.read_text())
            self.assertIn(
                "D282_02_STATISTICAL_GENERALIZATION_ALLOWED=false",
                env.read_text())

    def test_10_auditor_rejects_outcome_or_process_disagreement(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d282-02-audit-") as td:
            work = Path(td)
            for trial in range(1, 5):
                write_trial(work, trial, "match")
            journal = work / "trial-02.journal.raw"
            journal.write_text(journal.read_text().replace(
                "event=outcome result=match", "event=outcome result=no_match"))
            result = subprocess.run(
                [str(AUDITOR), str(work), str(work / "out.tsv"),
                 str(work / "out.env")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
        with tempfile.TemporaryDirectory(prefix="goodix-d282-02-audit-") as td:
            work = Path(td)
            for trial in range(1, 5):
                write_trial(work, trial, "match")
            meta = work / "trial-02.meta"
            meta.write_text(meta.read_text().replace("a" * 32, "c" * 32))
            result = subprocess.run(
                [str(AUDITOR), str(work), str(work / "out.tsv"),
                 str(work / "out.env")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_11_cleanup_and_export_are_bounded(self):
        self.assertIn("/run/goodix-d282-02/*", self.d282)
        self.assertIn("/var/lib/fprint/.goodix-d282-02-*", self.d282)
        self.assertIn("trials.tsv", self.launcher)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", self.launcher)
        self.assertNotIn("rm -rf /var/lib/fprint", self.launcher)

    def test_12_d283_live_is_fail_closed_in_standby(self):
        self.assertIn("d283_live_standby=true", self.d283)
        self.assertEqual(
            self.d283.count("D283_LIVE_STANDBY_MATCHER_CHARACTERIZATION_REQUIRED"),
            2)

    def test_13_operator_entrypoint_is_direct_and_keeps_transcript(self):
        operator = function_slice(
            self.launcher, "operator_d28202_run ()", "offline_preflight ()")
        self.assertIn("Digitare ESEGUI", operator)
        self.assertIn("--run-live", operator)
        self.assertIn("--export-results", operator)
        self.assertIn("TERMINAL_TRANSCRIPT", operator)
        self.assertNotIn("grant", operator.lower())

    def test_14_offline_preflight_cannot_call_live(self):
        offline = function_slice(self.launcher, "offline_preflight ()", "case ${1:-} in")
        self.assertIn("REAL_USB_ENUMERATION_ATTEMPTED=false", offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)
        self.assertIn("LIVE_EXECUTION_PERFORMED=false", offline)
        self.assertNotIn("run_d28202_live", offline)


if __name__ == "__main__":
    unittest.main()

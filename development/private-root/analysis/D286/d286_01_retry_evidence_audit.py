#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from hashlib import sha256
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_ROOT = ROOT / "captures/D286_01"
RECOVERED = ROOT / "analysis/D286/D286_01_RETRY_RECOVERED_JOURNAL.log"
SCRIPT_PATH = "operator_kit/d286-01-reboot-survival/run-d286-01.sh"
BOOT_ID = "351d5424-2894-4d0c-ba9a-596c42481ab7"
CAPTURES = {
    "D28601_RETRY_20260911T192824Z_d1463b41ed26": {
        "attempt-1.audit.log": "5e564f2e12f2c475da22fc40768116340302784d58bee3205f529bf6b30baf1d",
        "attempt-1.sudo.log": "18aefd19f17fc9bb422dadf02991b93585d025b5a0742485c3393f34ccbefdbc",
        "pre-retry-root-audit.log": "19ffcf776224190386282b769a1f4b613e51dd782f75fb4fb28789593b1add2a",
    },
    "D28601_RETRY_20260911T193758Z_61c387b33b6f": {
        "attempt-1.audit.log": "376f608134bea46906447d81e16826606c817e45d96a9a52d4261d966e08b87a",
        "attempt-1.sudo.log": "18aefd19f17fc9bb422dadf02991b93585d025b5a0742485c3393f34ccbefdbc",
        "pre-retry-root-audit.log": "19ffcf776224190386282b769a1f4b613e51dd782f75fb4fb28789593b1add2a",
    },
    "D28601_RETRY_20260911T194718Z_62808112777a": {
        "attempt-1.audit.log": "900cde5876ff477a87c4dda34ab130759069a6a214fa6baad15915ef7244abcc",
        "attempt-1.sudo.log": "18aefd19f17fc9bb422dadf02991b93585d025b5a0742485c3393f34ccbefdbc",
        "post-retry-root-audit.log": "d4771a24d69488d1e36120fcecd69debdfe395ad420cb203c47b9c1579fc36cc",
        "pre-retry-root-audit.log": "19ffcf776224190386282b769a1f4b613e51dd782f75fb4fb28789593b1add2a",
        "summary.env": "b587217c6c50a3debaa0b169dbe299ae8d8c820cbe06133416ee6463a6bc97b2",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        require(key not in result, f"duplicate key: {path}: {key}")
        result[key] = value
    return result


def commit_file(commit: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{SCRIPT_PATH}"],
        check=True, capture_output=True, text=True,
    ).stdout


def audit_capture_sets() -> None:
    for directory, expected in CAPTURES.items():
        sanitized = CAPTURE_ROOT / directory / "sanitized"
        require(sanitized.is_dir() and not sanitized.is_symlink(), f"unsafe capture: {directory}")
        require({p.name for p in sanitized.iterdir()} == set(expected), f"file-set drift: {directory}")
        for name, digest in expected.items():
            actual = sha256((sanitized / name).read_bytes()).hexdigest()
            require(actual == digest, f"hash drift: {directory}/{name}")


def audit_host_failures() -> None:
    names = list(CAPTURES)
    first = CAPTURE_ROOT / names[0] / "sanitized"
    second = CAPTURE_ROOT / names[1] / "sanitized"
    require("D286_01_REFUSAL_REASON=USAGE" in (first / "attempt-1.audit.log").read_text(),
            "first host failure drift")
    require("D286_01_REFUSAL_REASON=ATTEMPT_AUDIT_ARGUMENT_INVALID" in
            (second / "attempt-1.audit.log").read_text(), "second host failure drift")
    for capture in (first, second):
        pre = (capture / "pre-retry-root-audit.log").read_text()
        for marker in (
            "D286_01_STATE_COHERENCE=PASS_ROOT_ONLY",
            "D286_01_RUNTIME_INTEGRITY=PASS",
            "D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES",
            f"D286_01_BOOT_ID={BOOT_ID}",
        ):
            require(marker in pre, f"pre-audit marker missing: {marker}")
        require((capture / "attempt-1.sudo.log").read_text() ==
                "Place your right index finger on the fingerprint reader\n", "sudo log drift")

    first_fix = commit_file("61c387b33b6fd6b71016e7479e74186d258d7be2")
    final_fix = commit_file("62808112777a989fecf56c1924a36abbd474ad9f")
    require("${10} == --fallback-blocked" in first_fix and
            "${12} == --watchdog-timeout" in first_fix, "first parser fix missing")
    require('d286_root_attempt_audit "$3" "$5" "$7" "$9" "$11" "$13"' in first_fix,
            "first fix no longer exposes second defect")
    require('d286_root_attempt_audit "$3" "$5" "$7" "$9" "${11}" "${13}"' in final_fix,
            "final parser fix missing")


def audit_recovered_journal() -> None:
    text = RECOVERED.read_text()
    require(f"D286_01_RECOVERY_BOOT_ID={BOOT_ID}" in text, "recovery boot drift")
    require(text.count("GOODIX_D282_EPOCH_AUDIT") == 2, "recovered epoch count drift")
    require(text.count("event=outcome result=match") == 2, "recovered match count drift")
    for tokens in (
        ("keypoints=153", "sample=2 score=527 threshold=40", "real_submit=76"),
        ("keypoints=148", "sample=2 score=340 threshold=40", "real_submit=77"),
    ):
        for token in tokens:
            require(token in text, f"recovered token missing: {token}")
    for line in (line for line in text.splitlines() if line.startswith("GOODIX_D282_EPOCH_AUDIT")):
        for token in (
            "action=FPI_DEVICE_ACTION_VERIFY", "attempts=1", "consumed=1", "tls=1",
            "secure_retry=0", "post_retry=0", "reopen=0", "reset=0", "clear_halt=0",
            "persistent=0", "outstanding=0", "drained=1", "context_closed=1",
        ):
            require(token in line, f"recovered epoch token missing: {token}")


def audit_final_run() -> None:
    final = CAPTURE_ROOT / "D28601_RETRY_20260911T194718Z_62808112777a" / "sanitized"
    summary = env(final / "summary.env")
    expected = {
        "D286_01_RESULT": "PASS_LIVE_PENDING_INDEPENDENT_REVIEW",
        "D286_01_REPO_BASELINE": "62808112777a989fecf56c1924a36abbd474ad9f",
        "D286_01_VERIFY_ATTEMPTS_PERFORMED": "1",
        "D286_01_VERIFY_EPOCH_COUNT": "1",
        "D286_01_MATCHED_ATTEMPT": "1",
        "D286_01_ATTEMPT_OUTCOMES": "MATCH",
        "D286_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED": "false",
        "D286_01_PASSWORD_INPUT_POSSIBLE_DURING_SUDO_TEST": "false",
        "REAL_SENSOR_ACCESSED": "true",
        "LIVE_EXECUTION_PERFORMED": "true",
    }
    for key, value in expected.items():
        require(summary.get(key) == value, f"final summary drift: {key}")
    attempt = (final / "attempt-1.audit.log").read_text()
    for marker in (
        "D286_01_ATTEMPT_OUTCOME=MATCH", "D286_01_ATTEMPT_SUDO_RETURN_CODE=0",
        "D286_01_ATTEMPT_PASSWORD_FALLBACK_BLOCKED=false",
        "D286_01_ATTEMPT_WATCHDOG_TIMEOUT=false", "keypoints=160",
        "sample=1 score=75 threshold=40", "matched_sample=1 comparisons=1 threshold=40",
        "D286_01_ATTEMPT_RETRY_COUNT=0", "D286_01_ATTEMPT_REOPEN_COUNT=0",
        "D286_01_ATTEMPT_RESET_COUNT=0", "D286_01_ATTEMPT_CLEAR_HALT_COUNT=0",
        "D286_01_ATTEMPT_PERSISTENT_WRITE_FAMILY_COUNT=0",
    ):
        require(marker in attempt, f"final attempt marker missing: {marker}")
    for audit_name in ("pre-retry-root-audit.log", "attempt-1.audit.log",
                       "post-retry-root-audit.log"):
        audit = (final / audit_name).read_text()
        require("D286_01_STATE_COHERENCE=PASS_ROOT_ONLY" in audit and
                "D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES" in audit,
                f"root audit incomplete: {audit_name}")


def main() -> None:
    audit_capture_sets()
    audit_host_failures()
    audit_recovered_journal()
    audit_final_run()
    print("D286_01_RETRY_EVIDENCE_AUDIT=PASS_HASH_PINNED_HOST_FAILURES_AND_FINAL_MATCH")


if __name__ == "__main__":
    main()

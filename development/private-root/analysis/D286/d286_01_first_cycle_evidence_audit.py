#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from hashlib import sha256
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / (
    "captures/D286_01/"
    "D28601_CYCLE_20260911T184820Z_f9bb4551a477/sanitized"
)
RECOVERED = ROOT / "analysis/D286/D286_01_FIRST_CYCLE_RECOVERED_JOURNAL.log"
EXPECTED_HASHES = {
    "cycle.env": "ea98a3fee015ac81c7172fcda656a95cb6176c1db51e0ef3905033126db74bd3",
    "failure-summary.env": "8402d4694d738b5181def67f125379a35ad94b9375baba1084dd538673667805",
    "post-reboot-failure-audit.log": "fa50f5bdc8d57c89c046ca77a05a07618c48a61ea37d941df4afc5317bc144b0",
    "post-reboot-pre-verify.log": "e145c959365744111ec4724228665fcf37e435e52253b7ecc300ebbd20160782",
    "pre-reboot.log": "81bf8f4777e002d77170242c747e5f1acdea0509948ddf3e430734341c6fab07",
    "sudo-verify.log": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}


def env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        if key in values:
            raise AssertionError(f"duplicate key in {path}: {key}")
        values[key] = value
    return values


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(CAPTURE.is_dir() and not CAPTURE.is_symlink(), "capture missing or unsafe")
    require({p.name for p in CAPTURE.iterdir()} == set(EXPECTED_HASHES), "capture file set drift")
    for name, expected in EXPECTED_HASHES.items():
        actual = sha256((CAPTURE / name).read_bytes()).hexdigest()
        require(actual == expected, f"hash drift: {name}")

    cycle = env(CAPTURE / "cycle.env")
    failure = env(CAPTURE / "failure-summary.env")
    require(cycle["D286_01_REPO_BASELINE"] == failure["D286_01_REPO_BASELINE"] ==
            "f9bb4551a47704bb007f2877b6b112c5d9d39fed", "baseline drift")
    require(failure["D286_01_REBOOT_OBSERVED"] == "true", "reboot not recorded")
    require(failure["D286_01_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED"] == "false",
            "retry contract drift")
    require(failure["D286_01_SUDO_VALIDATE_RETURN_CODE"] == "137", "sudo rc drift")
    require(failure["D286_01_FAILURE_AUDIT_RETURN_CODE"] == "3", "audit rc drift")

    pre = (CAPTURE / "pre-reboot.log").read_text()
    post = (CAPTURE / "post-reboot-pre-verify.log").read_text()
    failed_audit = (CAPTURE / "post-reboot-failure-audit.log").read_text()
    for text in (pre, post, failed_audit):
        for marker in (
            "D286_01_STATE_COHERENCE=PASS_ROOT_ONLY",
            "D286_01_RUNTIME_INTEGRITY=PASS",
            "D286_01_TEMPLATE_OWNERSHIP=PASS_PINNED_EXACTLY_ONE",
            "D286_01_UNINSTALL_READINESS=PASS_ALL_PREDELETE_GATES",
        ):
            require(marker in text, f"missing root audit marker: {marker}")
    before = re.search(r"D286_01_BOOT_ID=([0-9a-f-]{36})", pre)
    after = re.search(r"D286_01_BOOT_ID=([0-9a-f-]{36})", post)
    require(before is not None and after is not None and before.group(1) != after.group(1),
            "boot id did not change")
    require("Failed to parse timestamp: 2026-09-11T20:51:25,647518798+02:00" in failed_audit,
            "locale timestamp failure missing")
    require("D286_01_REFUSAL_REASON=JOURNAL_READ_FAILED" in failed_audit,
            "failure audit classification drift")

    recovered = RECOVERED.read_text()
    require(recovered.count("GOODIX_D282_EPOCH_AUDIT") == 1, "epoch count drift")
    require(recovered.count("event=comparison") == 8, "comparison count drift")
    require(recovered.count("event=outcome result=no_match") == 1, "outcome drift")
    require("keypoints=112" in recovered and "sample=1 score=14 threshold=40" in recovered,
            "matcher telemetry drift")
    epoch = next(line for line in recovered.splitlines()
                 if line.startswith("GOODIX_D282_EPOCH_AUDIT"))
    for token in (
        "action=FPI_DEVICE_ACTION_VERIFY", "attempts=1", "consumed=1", "tls=1",
        "secure_retry=0", "post_retry=0", "reopen=0", "reset=0", "clear_halt=0",
        "persistent=0", "real_submit=76", "outstanding=0", "drained=1",
        "context_closed=1",
    ):
        require(token in epoch, f"epoch token missing: {token}")
    require((CAPTURE / "sudo-verify.log").stat().st_size == 0, "unexpected sudo log bytes")
    print("D286_01_FIRST_CYCLE_EVIDENCE_AUDIT=PASS_HASH_PINNED_WITH_SAME_BOOT_RECOVERY")


if __name__ == "__main__":
    main()

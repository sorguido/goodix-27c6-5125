#!/usr/bin/env python3
"""Fail-closed audit of the sanitized D289/01 real-lock live capture."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = (
    ROOT
    / "captures/live_probe/"
    "d289-real-locked-session_20260912T065056Z_74d8e5d8fc7e/sanitized"
)
BASELINE = "74d8e5d8fc7e0c91904c92725d3e5660def9ee72"
MANIFEST_SHA256 = "2130514674733dff6227e9aa23584c62baf0dfeda2d21e9bfdc96308e08de158"
PAYLOAD_PATH = "operator_kit/live_probe/experiments/d289-real-locked-session/payload.sh"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_env(name: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (CAPTURE / name).read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in values:
            raise ValueError(f"{name}: duplicate key {key}")
        values[key] = value
    return values


def require(values: dict[str, str], expected: dict[str, str], source: str) -> None:
    for key, value in expected.items():
        if values.get(key) != value:
            raise ValueError(
                f"{source}: {key} expected {value!r}, found {values.get(key)!r}"
            )


def require_exact_lines(name: str, expected: list[str]) -> None:
    actual = (CAPTURE / name).read_text(encoding="utf-8").splitlines()
    if actual != expected:
        raise ValueError(f"{name}: unexpected content {actual!r}")


def audit_manifest() -> dict[str, str]:
    manifest = CAPTURE / "capture.sha256"
    digest = sha256(manifest)
    if digest != MANIFEST_SHA256:
        raise ValueError(f"capture.sha256 digest mismatch: {digest}")
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  \./([^/]+)", line)
        if not match:
            raise ValueError(f"capture.sha256: malformed line {line!r}")
        expected_digest, name = match.groups()
        if name in entries:
            raise ValueError(f"capture.sha256: duplicate entry {name}")
        entries[name] = expected_digest
    actual_files = {path.name for path in CAPTURE.iterdir() if path.is_file()}
    if actual_files != set(entries) | {"capture.sha256"}:
        raise ValueError("capture file set differs from manifest")
    for name, expected_digest in entries.items():
        actual_digest = sha256(CAPTURE / name)
        if actual_digest != expected_digest:
            raise ValueError(f"{name}: digest mismatch {actual_digest}")
    return entries


def baseline_payload() -> str:
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{PAYLOAD_PATH}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"baseline payload unavailable: {result.stderr.strip()}")
    source = result.stdout
    ordered_fragments = [
        "org.freedesktop.ScreenSaver Lock",
        'wait_active true "$lock_deadline"',
        '[[ $greeter_ppid == "$kwin_pid" && $greeter_uid == "$(id -u)" ]]',
        "attempts=$((attempts + 1)); contacts=$((contacts + 1))",
        "if [[ $result == match ]]",
        'wait_active false "$unlock_deadline"',
        "outcome=REAL_LOCK_MATCH",
        "release_overlay",
        '[[ $matched -eq 0 ]] || break',
    ]
    cursor = 0
    for fragment in ordered_fragments:
        offset = source.find(fragment, cursor)
        if offset < 0:
            raise ValueError(
                f"baseline lock/match/unlock/cleanup fragment missing or unordered: {fragment}"
            )
        cursor = offset + len(fragment)
    if "unlock-session" in source:
        raise ValueError("baseline payload contains a forced unlock-session path")
    return source


def audit() -> dict[str, object]:
    manifest = audit_manifest()
    source = baseline_payload()

    context = parse_env("context.env")
    require(
        context,
        {
            "LIVE_PROBE_EXPERIMENT_ID": "d289-real-locked-session",
            "LIVE_PROBE_MODE": "operator-run",
            "LIVE_PROBE_BASELINE": BASELINE,
            "LIVE_PROBE_ACTION": "KDE_REAL_LOCKED_SESSION_VERIFY",
            "LIVE_PROBE_MAX_ACTIONS": "3",
            "LIVE_PROBE_MAX_CONTACTS": "3",
            "LIVE_PROBE_MAX_RETRIES": "0",
            "LIVE_PROBE_TIMEOUT_SECONDS": "900",
        },
        "context.env",
    )

    summary = parse_env("summary.env")
    require(
        summary,
        {
            "LIVE_PROBE_RESULT": "PASS",
            "LIVE_PROBE_EXPERIMENT_ID": "d289-real-locked-session",
            "LIVE_PROBE_BASELINE": BASELINE,
            "LIVE_PROBE_PRIMARY_FAILURE": "NONE",
            "LIVE_PROBE_PRE_AUDIT_RETURN_CODE": "0",
            "LIVE_PROBE_JOURNAL_CURSOR_RETURN_CODE": "0",
            "LIVE_PROBE_PAYLOAD_STARTED": "true",
            "LIVE_PROBE_PAYLOAD_RETURN_CODE": "0",
            "LIVE_PROBE_SANITIZER_RETURN_CODE": "0",
            "LIVE_PROBE_CAPTURE_TEE_RETURN_CODE": "0",
            "LIVE_PROBE_CLEANUP_RETURN_CODE": "0",
            "LIVE_PROBE_JOURNAL_RETURN_CODE": "0",
            "LIVE_PROBE_JOURNAL_COLLECTION": "COLLECTED",
            "LIVE_PROBE_POST_AUDIT_RETURN_CODE": "0",
            "LIVE_PROBE_COMMON_CLASSIFIER_RETURN_CODE": "0",
            "LIVE_PROBE_PAYLOAD_CLASSIFIER_RETURN_CODE": "0",
            "LIVE_PROBE_OPERATOR_INTERRUPTED": "false",
            "LIVE_PROBE_AUTOMATIC_RETRY_COUNT": "0",
            "LIVE_PROBE_INVOCATION_COUNT": "1",
        },
        "summary.env",
    )

    telemetry = parse_env("telemetry.env")
    require(
        telemetry,
        {
            "PAYLOAD_OUTCOME": "REAL_LOCK_MATCH",
            "ACTION_ATTEMPT_COUNT": "1",
            "CONTACT_COUNT": "1",
            "RETRY_COUNT": "0",
            "MAX_ACTIONS_ENFORCED": "3",
            "MAX_CONTACTS_ENFORCED": "3",
            "MAX_RETRIES_ENFORCED": "0",
            "PERSISTENT_WRITE_FAMILY_COUNT": "0",
            "OUTSTANDING_COUNT": "0",
            "DRAINED_COUNT": "1",
            "CONTEXT_CLOSED_COUNT": "1",
        },
        "telemetry.env",
    )

    details = parse_env("payload-details.env")
    require(
        details,
        {
            "D289_SERIES_OUTCOME": "REAL_LOCK_MATCH",
            "D289_ATTEMPTS_PERFORMED": "1",
            "D289_CONTACTS_CONSUMED": "1",
            "D289_MATCHED_ATTEMPT": "1",
            "D289_AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED": "false",
            "D289_REAL_LOCK_CYCLES": "1",
        },
        "payload-details.env",
    )

    lock_state = parse_env("attempt-1-lock-state.env")
    require(
        lock_state,
        {
            "D289_ATTEMPT": "1",
            "D289_LOCK_ACTIVE_BEFORE": "false",
            "D289_LOCK_ACTIVE_OBSERVED": "true",
            "D289_GREETER_PARENT_KWIN": "true",
            "D289_GREETER_CGROUP": (
                "/user.slice/user-1000.slice/user@1000.service/session.slice/"
                "plasma-kwin_wayland.service"
            ),
            "D289_FINGERPRINT_RESULT": "match",
            "D289_LOCK_ACTIVE_AFTER": "false",
            "D289_NON_FINGERPRINT_RECOVERY_AFTER_NO_MATCH": "false",
        },
        "attempt-1-lock-state.env",
    )
    if not lock_state.get("D289_GREETER_PID", "").isdigit():
        raise ValueError("attempt-1-lock-state.env: invalid greeter PID")

    require_exact_lines(
        "root-overlay.log",
        [
            "D289_ROOT_NAMESPACE_MATCH=true",
            "D289_ROOT_OVERLAY_READ_ONLY=true",
            "D289_ROOT_OVERLAY_READY=true",
            "D289_USER_OVERLAY_VISIBLE_AND_PASSWORD_SERVICE_UNCHANGED=true",
            "D289_ROOT_OVERLAY_UNMOUNTED=true",
            "D289_ROOT_HOST_PAM_RESTORED=true",
            "D289_ROOT_RUNTIME_REMOVED=true",
        ],
    )
    require_exact_lines(
        "cleanup.log",
        ["D289_ROOT_OVERLAY_RESIDUAL=false", "D289_CLEANUP=PASS"],
    )

    expected_audit_common = {
        "D289_TARGET_VERSIONS_AND_HASHES": "PASS",
        "D289_KWIN_IDENTITY_RESULT": "PASS",
        "D289_KWIN_IDENTITY_UID": "1000",
        "D289_KWIN_IDENTITY_COMM": "kwin_wayland",
        "D289_KWIN_IDENTITY_CMDLINE": "COHERENT",
        "D289_KWIN_IDENTITY_CGROUP": (
            "/user.slice/user-1000.slice/user@1000.service/session.slice/"
            "plasma-kwin_wayland.service"
        ),
        "D289_KWIN_IDENTITY_EXE": "UNREADABLE_ACCEPTED_WITH_COMPOSITE",
        "D289_LOGIND_SESSION": "2",
        "D289_LOGIND_SESSION_ACTIVE": "yes",
        "D289_LOGIND_SESSION_STATE": "active",
        "D289_LOGIND_SESSION_TYPE": "wayland",
        "D289_LOGIND_LOCKED_HINT": "no",
        "D289_SCREEN_LOCK_ACTIVE": "false",
        "D289_PAM_MODES": "root:root:644",
        "D289_EXISTING_GREETER_COUNT": "0",
        "D289_FINGERPRINT_PAM_MOUNTPOINT": "false",
        "D289_RUNTIME_PRESENT": "false",
        "D289_TARGET_SYSFS_CARDINALITY": "1",
        "D286_01_STATE_COHERENCE": "PASS_ROOT_ONLY",
        "D286_01_RUNTIME_INTEGRITY": "PASS",
        "D286_01_WRAPPER_PROVENANCE": "PASS",
        "D286_01_AUTHSELECT_SCOPE": "PASS_REDUCED",
        "D286_01_PASSWORD_FALLBACK": "PASS",
        "D286_01_TEMPLATE_OWNERSHIP": "PASS_PINNED_EXACTLY_ONE",
        "D286_01_SYSTEM_LIBFPRINT_UNCHANGED": "true",
        "D286_01_UNINSTALL_READINESS": "PASS_ALL_PREDELETE_GATES",
    }
    pre = parse_env("pre-audit.log")
    post = parse_env("post-audit.log")
    require(pre, expected_audit_common, "pre-audit.log")
    require(post, expected_audit_common, "post-audit.log")
    require(
        pre,
        {
            "D286_01_ROOT_AUDIT_PHASE": "D289_REAL_LOCK_PRE",
            "D286_01_D289_REAL_LOCK_PRE_ROOT_AUDIT_SENSOR_ACTION_COUNT": "0",
            "D289_PRE_AUDIT": "PASS",
            "D289_PRE_AUDIT_SENSOR_ACTION_COUNT": "0",
        },
        "pre-audit.log",
    )
    require(
        post,
        {
            "D286_01_ROOT_AUDIT_PHASE": "D289_REAL_LOCK_POST",
            "D286_01_D289_REAL_LOCK_POST_ROOT_AUDIT_SENSOR_ACTION_COUNT": "0",
            "D289_POST_AUDIT": "PASS",
            "D289_POST_AUDIT_SENSOR_ACTION_COUNT": "0",
        },
        "post-audit.log",
    )
    if pre["D286_01_BOOT_ID"] != post["D286_01_BOOT_ID"]:
        raise ValueError("pre/post audit boot IDs differ")

    attempt = (CAPTURE / "attempt-1-journal.log").read_text(encoding="utf-8")
    diagnostic = (CAPTURE / "diagnostic-journal.log").read_text(encoding="utf-8")
    epoch_lines = [line for line in attempt.splitlines() if "GOODIX_D282_EPOCH_AUDIT" in line]
    if len(epoch_lines) != 1:
        raise ValueError(f"attempt journal contains {len(epoch_lines)} VERIFY epochs")
    epoch = dict(re.findall(r"([a-z0-9_]+)=([^ ]+)", epoch_lines[0]))
    require(
        epoch,
        {
            "action": "FPI_DEVICE_ACTION_VERIFY",
            "attempts": "1",
            "rejected": "0",
            "consumed": "1",
            "tls": "1",
            "first_image": "1",
            "release_tail": "0",
            "single_terminal": "0",
            "rearm32": "0",
            "enroll_stages": "0",
            "enroll_rearm32": "0",
            "enroll_terminal": "0",
            "secure_retry": "0",
            "post_retry": "0",
            "reopen": "0",
            "reset": "0",
            "clear_halt": "0",
            "persistent": "0",
            "real_submit": "76",
            "outstanding": "0",
            "drained": "1",
            "context_closed": "1",
        },
        "attempt-1-journal.log epoch",
    )
    sigfm_expected = [
        "GOODIX_SIGFM_EXTRACT_AUDIT keypoints=129",
        "GOODIX_SIGFM_MATCH_AUDIT event=start template_samples=8 threshold=40",
        "GOODIX_SIGFM_MATCH_AUDIT event=comparison sample=1 score=9 threshold=40",
        "GOODIX_SIGFM_MATCH_AUDIT event=comparison sample=2 score=14 threshold=40",
        "GOODIX_SIGFM_MATCH_AUDIT event=comparison sample=3 score=376 threshold=40",
        "GOODIX_SIGFM_MATCH_AUDIT event=outcome result=match matched_sample=3 comparisons=3 threshold=40",
    ]
    for marker in sigfm_expected:
        if attempt.count(marker) != 1:
            raise ValueError(f"attempt journal does not contain exactly one {marker!r}")
    filtered_attempt = [line.split(": ", 1)[1] for line in attempt.splitlines() if "GOODIX_" in line]
    filtered_diagnostic = [line.split(": ", 1)[1] for line in diagnostic.splitlines()]
    if filtered_attempt != filtered_diagnostic:
        raise ValueError("diagnostic journal is not the same collected Goodix epoch")

    require(
        parse_env("common-classification.env"),
        {
            "LIVE_PROBE_COMMON_CLASSIFICATION": "PASS",
            "LIVE_PROBE_COMMON_CLASSIFICATION_REASON": "NONE",
            "LIVE_PROBE_PAYLOAD_OUTCOME": "REAL_LOCK_MATCH",
            "LIVE_PROBE_ACTION_ATTEMPT_COUNT": "1",
            "LIVE_PROBE_CONTACT_COUNT": "1",
            "LIVE_PROBE_RETRY_COUNT": "0",
            "LIVE_PROBE_PERSISTENT_WRITE_FAMILY_COUNT": "0",
            "LIVE_PROBE_OUTSTANDING_COUNT": "0",
            "LIVE_PROBE_DRAINED_COUNT": "1",
            "LIVE_PROBE_CONTEXT_CLOSED_COUNT": "1",
        },
        "common-classification.env",
    )
    require(
        parse_env("payload-classification.env"),
        {"D289_PAYLOAD_CLASSIFICATION": "PASS_LIVE_PENDING_INDEPENDENT_REVIEW"},
        "payload-classification.env",
    )

    payload_log = (CAPTURE / "payload.log").read_text(encoding="utf-8")
    cleanup_end = payload_log.index("D289_ROOT_RUNTIME_REMOVED=true")
    fd_noise = payload_log.index('"$root_out_fd": Descrittore di file errato')
    outcome = payload_log.index("D289_SERIES_OUTCOME=REAL_LOCK_MATCH")
    if not cleanup_end < fd_noise < outcome:
        raise ValueError("FD diagnostic is not isolated after successful cleanup")
    if source.count("coproc D289_ROOT_HELPER") != 1:
        raise ValueError("baseline does not contain exactly one overlay helper lifecycle")

    return {
        "schema": "D289_01_LIVE_EVIDENCE_AUDIT_V1",
        "capture": str(CAPTURE.relative_to(ROOT)),
        "baseline_sha": BASELINE,
        "manifest_sha256": MANIFEST_SHA256,
        "manifest_entry_count": len(manifest),
        "result": "PASS_MATCH",
        "real_kde_locked_session_unlock": "PROVEN",
        "lock_transition": "false_true_false",
        "kwin_kscreenlocker_identity": "PROVEN_BY_COMPOSITE",
        "action_attempt_count": 1,
        "contact_count": 1,
        "retry_count": 0,
        "sigfm": {
            "keypoints": 129,
            "matched_sample": 3,
            "score": 376,
            "threshold": 40,
        },
        "usb_real_submit_count": 76,
        "persistent_write_family_count": 0,
        "outstanding_count": 0,
        "drained_count": 1,
        "context_closed_count": 1,
        "overlay_unmounted": True,
        "host_pam_restored": True,
        "runtime_removed": True,
        "fd_teardown_noise": "OBSERVABILITY_ONLY_AFTER_CONFIRMED_CLEANUP",
        "password_or_pin_absence": "OPERATOR_PROCEDURE_CONSISTENT_NOT_MACHINE_TELEMETERED",
        "rerun_required": False,
        "sddm_login_with_fingerprint": "NOT_PROVEN",
        "decision": "ACCEPT_AND_CONTINUE",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))

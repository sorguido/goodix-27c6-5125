#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Static closure check for the D293/04 native-KDE operator gate."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
EXP = ROOT / "operator_kit/live_probe/experiments/d293-kde-new-user"
SCRIPTS = (
    "prepare.sh",
    "root-helper.sh",
    "recover.sh",
    "audit.sh",
    "payload.sh",
    "cleanup.sh",
    "sanitize.sh",
    "normalize-journal.sh",
    "classify.sh",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def text(name: str) -> str:
    return (EXP / name).read_text(encoding="utf-8")


def main() -> int:
    require(EXP.is_dir(), "experiment directory missing")
    combined = "\n".join(text(name) for name in SCRIPTS + ("experiment.conf", "README_IT.md"))
    for name in SCRIPTS:
        path = EXP / name
        require(path.is_file() and os.access(path, os.X_OK), f"{name} is not executable")
        subprocess.run(["bash", "-n", str(path)], check=True)
        require("SPDX-License-Identifier: GPL-2.0-or-later" in text(name), f"{name}: SPDX missing")

    config = text("experiment.conf")
    for marker in (
        "EXPERIMENT_ID=d293-kde-new-user",
        "MAX_ACTIONS=5",
        "MAX_CONTACTS=24",
        "MAX_RETRIES=0",
        "LIVE_CAPABLE=true",
        "COLLECT_JOURNAL=false",
        "GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL",
        "GUI_SESSION_HARD_CAP_REQUIRED=false",
        "PER_ACTION_TECHNICAL_FENCES=UNCHANGED",
        "VERIFY_SERIES_CONTROL=SCRIPT_BOUNDED",
        "RUN_TOTALS_CHECK=OBSERVED_PROTOCOL_BOUNDS",
        "EXTRA_MANUAL_UI_ACTION=PROTOCOL_DEVIATION_STOP",
    ):
        require(marker in config, f"config marker missing: {marker}")

    require(r"\${" not in combined, "literal escaped parameter expansion remains")
    require("GOODIX_D282_EPOCH_AUDIT" not in combined, "stale D282 epoch marker remains")
    require("GOODIX_PRODUCTION_EPOCH_AUDIT" in text("payload.sh"), "production epoch audit missing")

    payload = text("payload.sh")
    require('systemsettings_command=/usr/bin/systemsettings' in payload,
            "KCM Users is not the enrollment UI")
    executable_payload = re.sub(r"'.*?'", "", payload)
    require(not re.search(r"^\s*fprintd-enroll(?:\s|$)", executable_payload, re.MULTILINE),
            "payload invokes fprintd-enroll")
    require(not re.search(r"^\s*fprintd-delete(?:\s|$)", executable_payload, re.MULTILINE),
            "payload invokes fprintd-delete")
    require("for attempt in 1 2 3" in payload, "verify series is not statically bounded to three")
    require("action_field FPI_DEVICE_ACTION_ENROLL enroll_contacts" in payload,
            "enrollment contacts are not derived from the ENROLL audit")
    require('contacts_observed=$((contacts_observed + 1))' in payload,
            "contact telemetry does not derive IDENTIFY+ENROLL+VERIFY")
    require("'enroll_stages 8'" in payload, "eight production stages not enforced")
    require("D293_04_RUNTIME_AUDIT head=" in payload, "runtime provenance is not checked")
    require("D293_04_GUI_OPERATION_COUNT_CONTROL=OPERATOR_PROTOCOL" in payload and
            "D293_04_GUI_SESSION_HARD_CAP_REQUIRED=false" in payload and
            "MAX_ACTIONS_ENFORCEMENT_SCOPE=OBSERVED_PROTOCOL_ACCEPTANCE" in payload,
            "R7 operator-protocol telemetry semantics missing")
    require("D293_04_EXTRA_UI_PREACTION_FENCE=BLOCKED" not in payload,
            "superseded R7 pre-action blocker remains")
    require("D293_04_VERIFY_ACTION_BUDGET_PRECHECKED=true" in payload and
            "D293_04_ACTION_BUDGET_PRECHECKED=true" not in payload,
            "verify-only pre-action budget is overstated")

    prepare = text("prepare.sh")
    for marker in (
        "D293_04_PREPARE_MODE",
        "offline-script-test",
        "goodix_sysfs_cardinality_not_one",
        "critical_set_dirty",
        "--deploy",
        "run_id=d293-04-",
        "D293_04_PREPARE=PASS",
    ):
        require(marker in prepare, f"prepare path missing: {marker}")
    require("prior_capture_root_present" not in prepare and "run_capture_collision" in prepare,
            "prepare rejects historical capture base or misses per-run collision")

    helper = text("root-helper.sh")
    require("sha256sum \"$file\"" in helper and "CONTENT|%s|" in helper,
            "pre-existing principal digest does not cover file content")
    stop = helper.index("systemctl stop fprintd.service", helper.index("supervise()"))
    ready = helper.index("write_public READY_FOR_NEW_USER", helper.index("supervise()"))
    require(stop < ready and "fprintd_not_quiescent_before_ready" in helper,
            "READY can be published before fprintd is inactive")
    require("getent passwd \"$test_user\"" in helper and "test_account_exists_before_deploy" in helper,
            "post-deployment account creation boundary missing")
    require("mount -o remount,bind,ro,nodev,nosuid" in helper,
            "new-user repository mount is not read-only/nodev/nosuid")
    require("capture_base=/var/tmp/goodix-d293-04-captures" in helper and
            "RUN_ID=" in helper,
            "per-run capture root is missing")
    require('chown -R "$original:$original_gid" "$capture_root"' in helper and
            "capture_special_file" in helper and "capture_owner_drift" in helper,
            "recovery does not validate and transfer the retained capture")
    require("D293_04_CAPTURE_RETAINED=" in helper,
            "recovery does not report the retained capture path")
    require("trap supervisor_signal INT TERM" in helper and
            "trap - EXIT INT TERM" in helper and "exit 143" in helper,
            "supervisor signal path does not terminate after rollback")
    require('$(id -u "$original") == "$caller"' in helper,
            "deploy does not bind the original principal to the pkexec caller")
    require("recovery_caller_missing" in helper and "recovery_caller_invalid" in helper,
            "post-reboot recovery cannot recover the original caller identity")
    require("flock 9" in helper and "rollback_runtime || true" not in helper,
            "rollback is not serialized/propagated")
    require("D293_04_RUNTIME_RESTORED=" in helper and
            "D293_04_CLEANUP_REQUIRED=" in helper and
            "D293_04_INTEGRITY_FAILURE=" in helper and
            "rollback-history.log" in helper,
            "F3 rollback state/history is incomplete")
    require("rollback.integrity-failure" in helper and
            "recovery-integrity-failure.env" in helper,
            "integrity failures are not sticky")
    require("D293_04_ACCOUNT_REMOVAL_STATE=PENDING" in helper and
            "D293_04_ACCOUNT_REMOVAL_STATE=COMPLETE" in helper and
            "D293_04_FINAL_RECOVERY_IDEMPOTENT" in helper,
            "account recovery is not attributable/idempotent")
    require('--deploy) shift; deploy "$@"' in helper,
            "direct helper deployment was not restored")
    wrapper = helper[helper.index("write_runtime_wrapper()"):helper.index("publish_runtime_audit()")]
    require("goodix-d293-04-public" not in wrapper and
            "D293_04_RUNTIME_AUDIT head=" in wrapper,
            "F1 wrapper still writes public state or lacks runtime marker")
    publisher = helper[helper.index("publish_runtime_audit()"):helper.index("collect_epoch_journal()")]
    require("--property=MainPID --value fprintd.service" in publisher and
            'readlink -- "$proc_root/$pid/exe"' in publisher and
            '"$proc_root/$pid/maps"' in publisher and
            "mapped_libraries" in publisher and
            "DAEMON_PATH" in publisher,
            "F1 publication does not attest MainPID/executable/candidate mapping")
    require("capture_base_owner=0:0" in helper and
            "validate_capture_base()" in helper and
            "prepare_capture_base()" in helper and
            helper.index("prepare_capture_base || fail capture_base_integrity") <
            helper.index("fail deployment_collision") and
            helper.index("validate_capture_base || fail capture_base_integrity") <
            helper.index("fail run_capture_collision"),
            "capture base is not root-owned or revalidated before per-run use")
    collector = helper[helper.index("collect_epoch_journal()"):helper.index("append_rollback_history()")]
    require("--grep" not in collector and
            'awk \'index($0, "GOODIX_PRODUCTION_EPOCH_AUDIT ") { print }\'' in collector,
            "F2 journal reader does not separate reading from local filtering")
    recover = helper[helper.index("recover()"):helper.index("case ${1:-} in")]
    require("recovery_digest_missing" in recover and
            "recovery_digest_malformed" in recover and
            "recovery_original_gid_missing" in recover and
            "recovery_original_gid_mismatch" in recover,
            "recovery metadata integrity failures are not sticky/fail-closed")
    recovery_write = recover.rindex('atomic_from_stdin "$run_root/recovery.env"')
    require(recovery_write > recover.index('remove_tree "$public"') and
            recovery_write > recover.index('remove_tree "$private"'),
            "F4 final PASS can be published before final cleanup")

    diversity = (ROOT / "libfprint-driver/goodix_enrollment_diversity.h").read_text(
        encoding="utf-8"
    )
    require("#define GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS 20u" in diversity,
            "production enrollment contact ceiling is not statically enforced at twenty")

    readme = text("README_IT.md")
    require("/var/tmp/goodix-d293-04-captures/<run-id>/capture/" in readme,
            "per-run capture path is not documented")
    require("5 action" in readme and "24" in readme,
            "documented observed protocol bounds are stale")
    require("D293_04_OPERATOR_KIT=READY_OFFLINE_HUMAN_GATE_PENDING" in readme and
            "R7_METHOD_DECISION=USER_APPROVED_NATIVE_GUI_OPERATOR_PROTOCOL" in readme,
            "R7 method decision/readiness is not documented")

    behavior = ROOT / "analysis/D293/test_d293_04_operator_scripts.py"
    require(behavior.is_file(), "behavioral script regression missing")

    for rel in (
        "operator_kit/live_probe/run.sh",
        "operator_kit/live_probe/safety.sh",
        "operator_kit/live_probe/capture.sh",
        "operator_kit/live_probe/classify_common.sh",
    ):
        diff = subprocess.run(
            ["git", "diff", "--quiet", "--", rel], cwd=ROOT, check=False
        )
        require(diff.returncode == 0, f"common harness unexpectedly modified: {rel}")

    manual = (ROOT / "Goodix 27c6 5125 manuale tecnico.md").read_text(encoding="utf-8")
    plan = (ROOT / "analysis/PROJECT_NEXT_STEPS_PLAN.md").read_text(encoding="utf-8")
    index = (ROOT / "analysis/README.md").read_text(encoding="utf-8")
    for document, name in ((manual, "manual"), (plan, "plan"), (index, "analysis index")):
        require(
            "READY_OFFLINE_HUMAN_GATE_PENDING" in document,
            f"{name}: current D293/04 readiness missing",
        )
        require(
            "USER_APPROVED_NATIVE_GUI_OPERATOR_PROTOCOL" in document
            or "protocollo KDE nativo" in document,
            f"{name}: current R7 decision missing",
        )
    for document, name in ((manual, "manual"), (plan, "plan")):
        require("PHASE_B_CLOSED=false" in document, f"{name}: Phase B closure marker missing")
        require("PRODUCTION_READY=false" in document, f"{name}: readiness marker missing")
        require(
            "NEXT_BOUNDARY=D293_04_OPERATOR_HUMAN_GATE" in document,
            f"{name}: current Human Gate boundary missing",
        )

    print("D293_04_VALIDATOR=PASS_READY_OFFLINE")
    print("COMMON_HARNESS_MODIFIED=false")
    print("MAX_ACTIONS=5")
    print("MAX_CONTACTS=24")
    print("MAX_TRANSPORT_RETRIES=0")
    print("VERIFY_ATTEMPT_LIMIT=3")
    print("REAL_USB_EXECUTED=0")
    print("R7_METHOD_DECISION=USER_APPROVED_NATIVE_GUI_OPERATOR_PROTOCOL")
    print("LIVE_CAPABLE=true")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
        print(f"D293_04_VALIDATOR=FAIL reason={exc}", file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Static closure check for the blocked D293/04 corrective experiment."""

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
        "LIVE_CAPABLE=false",
        "COLLECT_JOURNAL=false",
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
    require("D293_04_EXTRA_UI_PREACTION_FENCE=BLOCKED" in payload,
            "R7 pre-action blocker is not explicit")
    require("D293_04_VERIFY_ACTION_BUDGET_PRECHECKED=true" in payload and
            "D293_04_ACTION_BUDGET_PRECHECKED=true" not in payload,
            "verify-only pre-action budget is overstated")

    prepare = text("prepare.sh")
    require("D293_04_PREPARE=BLOCKED" in prepare and "exit 3" in prepare,
            "prepare is not blocked")
    for forbidden in ("pkexec", "sysfs", "build.sh", "systemctl", "mount "):
        require(forbidden not in prepare, f"prepare retains dead live path: {forbidden}")

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
    require("account-removal.intent" in helper and
            "D293_04_FINAL_RECOVERY_IDEMPOTENT" in helper,
            "account recovery is not attributable/idempotent")
    require("--deploy) fail deployment_blocked_r7_gui_session_budget" in helper,
            "direct helper deployment is not blocked")

    diversity = (ROOT / "libfprint-driver/goodix_enrollment_diversity.h").read_text(
        encoding="utf-8"
    )
    require("#define GOODIX_ENROLLMENT_DIVERSITY_MAX_PHYSICAL_ATTEMPTS 20u" in diversity,
            "production enrollment contact ceiling is not statically enforced at twenty")

    readme = text("README_IT.md")
    require("/var/tmp/goodix-d293-04-captures/<run-id>/capture/" in readme,
            "per-run capture path is not documented")
    require("MAX_ACTIONS=5" in readme and "MAX_CONTACTS=24" in readme,
            "documented technical budgets are stale")
    require("D293_04_OPERATOR_KIT=BLOCKED_OFFLINE" in readme,
            "R7 blocker is not documented")

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
    for document, name in ((manual, "manual"), (plan, "plan")):
        require("D293_04_OPERATOR_KIT=BLOCKED_OFFLINE" in document, f"{name}: blocker marker missing")
        require("D293_04_LIVE_EXECUTION=BLOCKED_NOT_PERFORMED" in document,
                f"{name}: blocked-live marker missing")
        require("PHASE_B_CLOSED=false" in document, f"{name}: Phase B closure marker missing")
        require("PRODUCTION_READY=false" in document, f"{name}: readiness marker missing")

    print("D293_04_VALIDATOR=PASS_BLOCKED")
    print("COMMON_HARNESS_MODIFIED=false")
    print("MAX_ACTIONS=5")
    print("MAX_CONTACTS=24")
    print("MAX_TRANSPORT_RETRIES=0")
    print("VERIFY_ATTEMPT_LIMIT=3")
    print("REAL_USB_EXECUTED=0")
    print("LIVE_CAPABLE=false")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
        print(f"D293_04_VALIDATOR=FAIL reason={exc}", file=sys.stderr)
        raise SystemExit(1)

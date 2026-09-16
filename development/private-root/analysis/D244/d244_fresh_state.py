"""Read-only host-boot evidence for the D244 fresh-state causal control."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Mapping, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
BASELINE = REPOSITORY / "analysis/D244/D244_d243_boot_baseline.json"
BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
UPTIME_PATH = Path("/proc/uptime")


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def read_boot_id(path: Path = BOOT_ID_PATH) -> str | None:
    value = _read_text(path)
    if value is None:
        return None
    normalized = value.replace("-", "").lower()
    if len(normalized) != 32 or any(c not in "0123456789abcdef" for c in normalized):
        return None
    return normalized


def read_uptime(path: Path = UPTIME_PATH) -> float | None:
    value = _read_text(path)
    try:
        uptime = float(value.split()[0]) if value else None
    except (ValueError, IndexError):
        return None
    return uptime if uptime is not None and uptime >= 0 else None


def read_journal_boot_ids() -> tuple[str, ...]:
    try:
        completed = subprocess.run(
            ["journalctl", "--list-boots", "--no-pager"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if completed.returncode:
        return ()
    result: list[str] = []
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        candidate = fields[1].replace("-", "").lower()
        if len(candidate) == 32 and all(c in "0123456789abcdef" for c in candidate):
            result.append(candidate)
    return tuple(result)


def assess_fresh_state(
    *,
    baseline_boot_id: str | None,
    current_boot_id: str | None,
    uptime_seconds: float | None,
    journal_boot_ids: Sequence[str] = (),
    operator_confirmed: bool,
) -> dict[str, object]:
    baseline = baseline_boot_id.replace("-", "").lower() if baseline_boot_id else None
    current = current_boot_id.replace("-", "").lower() if current_boot_id else None
    boot_changed = bool(baseline and current and baseline != current)
    journal_consistent = bool(
        boot_changed
        and current in journal_boot_ids
        and baseline in journal_boot_ids
    )
    documented = boot_changed
    if current is not None and uptime_seconds is not None and journal_boot_ids:
        evidence = "combination"
    elif current is not None and uptime_seconds is not None:
        evidence = "combination"
    elif current is not None:
        evidence = "boot_id"
    elif uptime_seconds is not None:
        evidence = "uptime"
    else:
        evidence = "unavailable"
    valid = bool(operator_confirmed and documented)
    return {
        "schema": "d244-fresh-state-evidence-v1",
        "baseline_d243_boot_id": baseline or "unavailable",
        "current_boot_id": current or "unavailable",
        "system_uptime_seconds": uptime_seconds if uptime_seconds is not None else "unavailable",
        "journal_boot_list_accessible": bool(journal_boot_ids),
        "journal_baseline_and_current_consistent": journal_consistent,
        "operator_shutdown_power_on_confirmed": operator_confirmed,
        "D244_FRESH_BOOT_DOCUMENTED": documented,
        "D244_FRESH_BOOT_EVIDENCE": evidence,
        "D244_FRESH_STATE_CONTROL_VALID": valid,
        "D244_SENSOR_POWER_CYCLE_ELECTRICALLY_PROVEN": False,
        "interpretation": (
            "fresh_host_boot_documented_not_sensor_power_proven"
            if documented
            else "fresh_host_boot_not_documented"
        ),
    }


def collect(
    *, baseline_path: Path = BASELINE, operator_confirmed: bool
) -> dict[str, object]:
    try:
        baseline: Mapping[str, object] = json.loads(
            baseline_path.read_text(encoding="utf-8")
        )
        baseline_id = str(baseline["d243_boot_id"])
    except (OSError, ValueError, KeyError, TypeError):
        baseline_id = None
    return assess_fresh_state(
        baseline_boot_id=baseline_id,
        current_boot_id=read_boot_id(),
        uptime_seconds=read_uptime(),
        journal_boot_ids=read_journal_boot_ids(),
        operator_confirmed=operator_confirmed,
    )


def emit_shell_environment(report: Mapping[str, object]) -> str:
    values = {
        "D244_CURRENT_BOOT_ID": report["current_boot_id"],
        "D244_SYSTEM_UPTIME_SECONDS": report["system_uptime_seconds"],
        "D244_FRESH_BOOT_DOCUMENTED": str(report["D244_FRESH_BOOT_DOCUMENTED"]).lower(),
        "D244_FRESH_BOOT_EVIDENCE": report["D244_FRESH_BOOT_EVIDENCE"],
        "D244_FRESH_STATE_CONTROL_VALID": str(
            report["D244_FRESH_STATE_CONTROL_VALID"]
        ).lower(),
        "D244_SENSOR_POWER_CYCLE_ELECTRICALLY_PROVEN": "false",
        "D244_OPERATOR_SHUTDOWN_POWER_ON_CONFIRMED": str(
            report["operator_shutdown_power_on_confirmed"]
        ).lower(),
    }
    return "\n".join(
        f"export {key}={shlex.quote(str(value))}" for key, value in values.items()
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--operator-confirmed", action="store_true")
    parser.add_argument("--format", choices=("json", "env"), default="json")
    args = parser.parse_args(argv)
    report = collect(
        baseline_path=args.baseline.resolve(),
        operator_confirmed=args.operator_confirmed,
    )
    if args.format == "env":
        print(emit_shell_environment(report))
    else:
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

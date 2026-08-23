#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded D261 live-import closure and fresh-process import-safety evidence."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# This is deliberately the supported D261 path, not a general import analyzer.
LIVE_MODULES = (
    "core",
    "core.usb_runtime",
    "core.protected_runtime",
    "core.runtime_transport",
    "core.tls_b0",
    "core.persistent_runtime",
    "core.cold_start",
    "core.fdt_lifecycle",
    "core.fdt_seed",
    "core.post_d4",
    "poc.goodix5125.tools.binding_reference",
    "poc.goodix5125.tools.binding_reference.runtime",
    "tools.d261_live_fdt_arm_once",
)

CLOSURE_METADATA: dict[str, dict[str, str]] = {
    "core/__init__.py": {
        "reason": "Python executes the core package initializer before its first submodule",
        "imported_by": "tools/d261_live_fdt_arm_once.py via package import machinery",
        "execution_role": "package_initializer",
    },
    "core/cold_start.py": {
        "reason": "cold-start state machine and protected material types",
        "imported_by": "tools/d261_live_fdt_arm_once.py",
        "execution_role": "runtime_module",
    },
    "core/fdt_lifecycle.py": {
        "reason": "fresh-FDT lifecycle used by the persistent coordinator",
        "imported_by": "core/persistent_runtime.py",
        "execution_role": "runtime_module",
    },
    "core/fdt_seed.py": {
        "reason": "pre-USB cache hash/layout/CRC validation and live OTP binding",
        "imported_by": "tools/d261_live_fdt_arm_once.py",
        "execution_role": "runtime_module",
    },
    "core/persistent_runtime.py": {
        "reason": "single-session cold-start/TLS/FDT coordinator",
        "imported_by": "tools/d261_live_fdt_arm_once.py",
        "execution_role": "runtime_module",
    },
    "core/post_d4.py": {
        "reason": "A0/B0 framing and post-D4 parsers/builders",
        "imported_by": "core/cold_start.py and core/fdt_lifecycle.py",
        "execution_role": "runtime_module",
    },
    "core/protected_runtime.py": {
        "reason": "capabilities, protected content loaders and real secret boundary definition",
        "imported_by": "tools/d261_live_fdt_arm_once.py",
        "execution_role": "runtime_module",
    },
    "core/runtime_transport.py": {
        "reason": "logical/physical transport policy contracts",
        "imported_by": "core/cold_start.py and tools/d261_live_fdt_arm_once.py",
        "execution_role": "runtime_module",
    },
    "core/tls_b0.py": {
        "reason": "persistent TLS and B0 application record handling",
        "imported_by": "core/fdt_lifecycle.py and core/persistent_runtime.py",
        "execution_role": "runtime_module",
    },
    "core/usb_runtime.py": {
        "reason": "lazy real libusb backend and shared EP81 reader",
        "imported_by": "tools/d261_live_fdt_arm_once.py",
        "execution_role": "runtime_module",
    },
    "src/goodix5125_cleanroom.py": {
        "reason": "CRC and clean-room framing primitives",
        "imported_by": "core/post_d4.py and core/fdt_seed.py",
        "execution_role": "runtime_module",
    },
    "poc/goodix5125/tools/binding_reference/__init__.py": {
        "reason": "Python executes the binding_reference package initializer before runtime",
        "imported_by": "core/protected_runtime.py via package import machinery",
        "execution_role": "package_initializer",
    },
    "poc/goodix5125/tools/binding_reference/runtime.py": {
        "reason": "canonical PE-derived E4 validator API",
        "imported_by": "poc/goodix5125/tools/binding_reference/__init__.py",
        "execution_role": "runtime_module",
    },
    "poc/goodix5125/tools/binding_reference/crypto_reference.py": {
        "reason": "E4 binding cryptographic implementation",
        "imported_by": "poc/goodix5125/tools/binding_reference/runtime.py",
        "execution_role": "runtime_module",
    },
    "poc/goodix5125/tools/binding_reference/pe_parser.py": {
        "reason": "hash-gated seed extraction from the canonical PE",
        "imported_by": "poc/goodix5125/tools/binding_reference/runtime.py",
        "execution_role": "runtime_module",
    },
    "tools/d261_live_fdt_arm_once.py": {
        "reason": "supported Python entrypoint, baseline verifier and live transaction",
        "imported_by": "operator_kit/d261-live-fdt-arm-once.sh",
        "execution_role": "python_entrypoint",
    },
}


def _repo_python_files() -> set[str]:
    paths: set[str] = set()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(REPO) and path.suffix == ".py":
            paths.add(path.relative_to(REPO).as_posix())
    return paths


def _flatten_path_values(value: Any):
    if isinstance(value, (str, bytes, os.PathLike)):
        yield os.fsdecode(value)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _flatten_path_values(item)


def _child() -> int:
    before = _repo_python_files()
    counts = {
        "IMPORT_TIME_USB_ATTEMPT_COUNT": 0,
        "IMPORT_TIME_PROTECTED_FS_ACCESS_COUNT": 0,
        "IMPORT_TIME_SECRET_INSTANTIATION_COUNT": 0,
        "IMPORT_TIME_SECRET_MATERIALIZATION_COUNT": 0,
        "IMPORT_TIME_FPRINTD_MUTATION_COUNT": 0,
        "IMPORT_TIME_MARKER_CREATE_COUNT": 0,
        "IMPORT_TIME_SIGNAL_MUTATION_COUNT": 0,
    }

    def audit(event: str, args: tuple[Any, ...]) -> None:
        paths = tuple(_flatten_path_values(args))
        if any(path == "/var/lib/goodix-5125-poc" or path.startswith("/var/lib/goodix-5125-poc/") for path in paths):
            counts["IMPORT_TIME_PROTECTED_FS_ACCESS_COUNT"] += 1
        if event == "ctypes.dlopen" and any("usb" in path.lower() for path in paths):
            counts["IMPORT_TIME_USB_ATTEMPT_COUNT"] += 1
        if event == "subprocess.Popen" and any(
            token in {"stop", "start", "restart", "reload"}
            for path in paths for token in path.split()
        ):
            counts["IMPORT_TIME_FPRINTD_MUTATION_COUNT"] += 1
        if event in {"open", "os.mkdir"} and any("d261-live-single-use.marker" in path for path in paths):
            counts["IMPORT_TIME_MARKER_CREATE_COUNT"] += 1

    profile_targets = {
        ("core/protected_runtime.py", "__init__"): "IMPORT_TIME_SECRET_INSTANTIATION_COUNT",
        ("core/protected_runtime.py", "materialize"): "IMPORT_TIME_SECRET_MATERIALIZATION_COUNT",
        ("core/usb_runtime.py", "open_exact"): "IMPORT_TIME_USB_ATTEMPT_COUNT",
        ("tools/d261_live_fdt_arm_once.py", "claim_marker"): "IMPORT_TIME_MARKER_CREATE_COUNT",
    }

    def profile(frame, event: str, _arg):
        if event == "c_call":
            caller = Path(frame.f_code.co_filename).resolve()
            if (
                caller.is_relative_to(REPO)
                and frame.f_code.co_name == "<module>"
                and getattr(_arg, "__name__", "") == "pthread_sigmask"
            ):
                counts["IMPORT_TIME_SIGNAL_MUTATION_COUNT"] += 1
            return
        if event != "call":
            return
        path = Path(frame.f_code.co_filename).resolve()
        if path.name == "pathlib.py" and frame.f_code.co_name in {
            "stat", "lstat", "open", "read_bytes", "read_text", "write_bytes", "write_text",
        }:
            target = frame.f_locals.get("self")
            if target is not None:
                value = os.fspath(target)
                if value == "/var/lib/goodix-5125-poc" or value.startswith("/var/lib/goodix-5125-poc/"):
                    counts["IMPORT_TIME_PROTECTED_FS_ACCESS_COUNT"] += 1
            return
        if not path.is_relative_to(REPO):
            return
        relative = path.relative_to(REPO).as_posix()
        key = profile_targets.get((relative, frame.f_code.co_name))
        if key:
            # __init__ is counted only for the concrete real secret class.
            instance = frame.f_locals.get("self")
            if (
                key != "IMPORT_TIME_SECRET_INSTANTIATION_COUNT"
                or (instance is not None and instance.__class__.__name__ == "RealSecretBoundary")
            ):
                counts[key] += 1

    sys.addaudithook(audit)
    sys.setprofile(profile)
    try:
        for module in LIVE_MODULES:
            importlib.import_module(module)
    finally:
        sys.setprofile(None)

    loaded = sorted(_repo_python_files() - before)
    # The harness itself was already loaded before observation and is excluded.
    expected = sorted(CLOSURE_METADATA)
    missing_metadata = sorted(set(loaded) - set(expected))
    not_executed = sorted(set(expected) - set(loaded))
    passed = not missing_metadata and not not_executed and not any(counts.values())
    print("IMPORT_SAFETY_PASS" if passed else "IMPORT_SAFETY_FAIL")
    print(json.dumps({
        "loaded_repository_python_paths": loaded,
        "missing_metadata_paths": missing_metadata,
        "expected_but_not_executed_paths": not_executed,
        **counts,
    }, sort_keys=True))
    return 0 if passed else 1


def run_import_safety(repo: Path = REPO) -> dict[str, Any]:
    environment = dict(os.environ)
    environment.pop("D261_APPROVED_LIVE_BASELINE_SHA", None)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        (sys.executable, "-B", str(Path(__file__).resolve()), "--child"),
        cwd=repo,
        env=environment,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines = completed.stdout.splitlines()
    child = json.loads(lines[-1]) if lines else {}
    passed = completed.returncode == 0 and lines[:1] == ["IMPORT_SAFETY_PASS"]
    return {
        "schema": "D261_IMPORT_SAFETY_EVIDENCE_V1",
        "execution_mode": "OFFLINE_ONLY_FRESH_UNPRIVILEGED_SUBPROCESS",
        "command": "python3 -B analysis/D261/d261_import_safety.py --child",
        "IMPORT_SAFETY_TEST": "PASS" if passed else "FAIL",
        "IMPORT_SAFETY_EXIT_CODE": completed.returncode,
        "NO_IMPORT_TIME_SIDE_EFFECTS": passed and not any(
            child.get(key, -1) for key in (
                "IMPORT_TIME_USB_ATTEMPT_COUNT",
                "IMPORT_TIME_PROTECTED_FS_ACCESS_COUNT",
                "IMPORT_TIME_SECRET_INSTANTIATION_COUNT",
                "IMPORT_TIME_SECRET_MATERIALIZATION_COUNT",
                "IMPORT_TIME_FPRINTD_MUTATION_COUNT",
                "IMPORT_TIME_MARKER_CREATE_COUNT",
                "IMPORT_TIME_SIGNAL_MUTATION_COUNT",
            )
        ),
        "stdout_marker": lines[0] if lines else None,
        "stderr": completed.stderr,
        "live_flag_present": False,
        "sudo_used": False,
        **child,
    }


def build_closure(import_safety: dict[str, Any]) -> dict[str, Any]:
    from tools.d261_live_fdt_arm_once import CANONICAL_LIVE_CRITICAL_PATHS

    python_paths = import_safety["loaded_repository_python_paths"]
    canonical = set(CANONICAL_LIVE_CRITICAL_PATHS)
    rows = [
        {
            "path": path,
            **CLOSURE_METADATA[path],
            "in_canonical_live_critical_paths": path in canonical,
        }
        for path in python_paths
    ]
    missing = sorted(path for path in python_paths if path not in canonical)
    return {
        "schema": "D261_BOUNDED_LIVE_IMPORT_CLOSURE_V1",
        "supported_python_entrypoint": "tools/d261_live_fdt_arm_once.py",
        "operator_shell_launcher": "operator_kit/d261-live-fdt-arm-once.sh",
        "derivation": "fresh subprocess sys.modules delta for the bounded supported D261 import path plus reviewed import edges",
        "LIVE_IMPORT_CLOSURE_STATUS": "PASS" if not missing else "FAIL",
        "LIVE_IMPORT_CLOSURE_PATH_COUNT": len(rows),
        "LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT": len(missing),
        "PACKAGE_INITIALIZERS_EXECUTED_AND_BASELINE_GATED": all(
            path in canonical for path in (
                "core/__init__.py",
                "poc/goodix5125/tools/binding_reference/__init__.py",
            )
        ),
        "missing_paths": missing,
        "files": rows,
    }


def closure_markdown(closure: dict[str, Any]) -> str:
    lines = [
        "# D261 bounded live-import closure",
        "",
        "Derived from a fresh-process import of the supported D261 Python entrypoint and its bounded runtime modules. The operator shell is gated separately as `operator_kit/d261-live-fdt-arm-once.sh`.",
        "",
        f"`LIVE_IMPORT_CLOSURE_STATUS={closure['LIVE_IMPORT_CLOSURE_STATUS']}`  ",
        f"`LIVE_IMPORT_CLOSURE_PATH_COUNT={closure['LIVE_IMPORT_CLOSURE_PATH_COUNT']}`  ",
        f"`LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT={closure['LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT']}`",
        "",
        "| Path | Imported by | Execution role | Baseline gated |",
        "| --- | --- | --- | --- |",
    ]
    for row in closure["files"]:
        lines.append(
            f"| `{row['path']}` | {row['imported_by']} | {row['execution_role']} | "
            f"{'yes' if row['in_canonical_live_critical_paths'] else 'no'} |"
        )
    lines.extend(("", "All listed files execute repository-local Python code on the supported import path; namespace-package directories without `__init__.py` are intentionally absent.", ""))
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--child":
        return _child()
    evidence = run_import_safety()
    closure = build_closure(evidence)
    print(json.dumps({"import_safety": evidence, "closure": closure}, indent=2, sort_keys=True))
    return 0 if evidence["IMPORT_SAFETY_TEST"] == "PASS" and closure["LIVE_IMPORT_CLOSURE_STATUS"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

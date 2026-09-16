# SPDX-License-Identifier: GPL-2.0-or-later
"""D251 live-critical Git closure and index-independent baseline verifier."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
LIVE_CRITICAL_RATIONALES = {
    "operator_kit/d251-live-af-once.sh": "operator authorization, single-shot lifecycle, patching, cleanup, and reseal",
    "analysis/D245/D245_live_unseal.patch": "enables the reviewed A8-to-TLS predecessor path",
    "analysis/D246/D246_d4_continuation.patch": "adds the reviewed exactly-one D4 predecessor",
    "analysis/D250/D250_af_continuation.patch": "adds the reviewed exactly-one AF predecessor",
    "analysis/D251/D251_af_semantics_continuation.patch": "removes only the over-constrained byte0 gate and corrects AF observability",
    "analysis/D251/d251_preflight.py": "D251 pre-USB safety and baseline policy",
    "analysis/D251/d251_preflight_observability.py": "renders actionable redacted preflight failures",
    "analysis/D251/d251_live_critical.py": "defines and verifies this Git baseline closure",
    "core/post_d4.py": "AF serializer, structural response validator, opaque byte0 model, and terminal stop",
    "src/goodix5125_cleanroom.py": "transitive module imported by the AF protocol core",
    "src/goodix5125_d232_offline.py": "wire framing, protected material loading, replay policy, and durable reporting",
    "src/goodix5125_d233_backend.py": "real USB transport, PSK binding, TLS, D4, and AF backend path",
    "src/goodix5125_d235_entrypoint.py": "real entrypoint, runtime paths, authorization, and result mapping",
    "analysis/D230/work/GoodixExport/gfusb.dll": "hash-gated canonical PE input used by the E4 validator",
    "poc/goodix5125/tools/binding_reference/__init__.py": "binding package initializer executed on import",
    "poc/goodix5125/tools/binding_reference/runtime.py": "runtime PSK-to-E4 validator derivation and PE gate",
    "poc/goodix5125/tools/binding_reference/crypto_reference.py": "cryptographic PSK-to-E4 binding implementation",
    "poc/goodix5125/tools/binding_reference/pe_parser.py": "canonical gfusb PE validation and seed extraction",
}
LIVE_CRITICAL_FILES = tuple(LIVE_CRITICAL_RATIONALES)
FULL_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def _git(repository: Path, *arguments: str, text: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=text,
    )


def baseline_state(
    repository: Path,
    baseline_sha: str,
    files: Sequence[str] = LIVE_CRITICAL_FILES,
) -> str:
    """Compare working bytes with one commit without consulting the Git index."""
    repository = repository.resolve()
    if not FULL_SHA_RE.fullmatch(baseline_sha):
        return "UNAPPROVED"
    if _git(repository, "cat-file", "-e", f"{baseline_sha}^{{commit}}").returncode:
        return "UNAPPROVED"
    for relative in files:
        if _git(repository, "cat-file", "-e", f"{baseline_sha}:{relative}").returncode:
            return "STALE"
        path = repository / relative
        if not path.is_file() or path.is_symlink():
            return "STALE"
        committed = _git(repository, "show", f"{baseline_sha}:{relative}")
        if committed.returncode or path.read_bytes() != committed.stdout:
            return "STALE"
    return "APPROVED"


def manifest() -> list[dict[str, str]]:
    return [
        {"path": path, "rationale": LIVE_CRITICAL_RATIONALES[path]}
        for path in LIVE_CRITICAL_FILES
    ]


def offline_stale_detection_test() -> dict[str, object]:
    """Prove clean approval and stale detection for every critical file class."""
    with tempfile.TemporaryDirectory(prefix="d251-live-critical-") as directory:
        work = Path(directory)
        for relative in LIVE_CRITICAL_FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPOSITORY / relative, target)
        commands = (
            ("init", "-q"),
            ("add", "--", *LIVE_CRITICAL_FILES),
            (
                "-c",
                "user.name=D251 Offline Test",
                "-c",
                "user.email=d251-offline@example.invalid",
                "commit",
                "-q",
                "-m",
                "D251 offline baseline fixture",
            ),
        )
        for command in commands:
            result = _git(work, *command)
            if result.returncode:
                raise RuntimeError(f"temporary Git fixture failed: {' '.join(command)}")
        head_result = _git(work, "rev-parse", "HEAD", text=True)
        if head_result.returncode:
            raise RuntimeError("temporary Git fixture has no HEAD")
        head = head_result.stdout.strip()
        clean_state = baseline_state(work, head)
        invalid_states = {
            "missing": baseline_state(work, ""),
            "malformed": baseline_state(work, "0" * 39),
            "nonexistent": baseline_state(work, "0" * 40),
        }
        stale_paths = []
        for relative in LIVE_CRITICAL_FILES:
            target = work / relative
            original = target.read_bytes()
            target.write_bytes(original + b"\nD251_STALE_FIXTURE\n")
            state = baseline_state(work, head)
            target.write_bytes(original)
            if state != "STALE":
                raise AssertionError(f"stale detection failed:{relative}:{state}")
            stale_paths.append(relative)
    if clean_state != "APPROVED":
        raise AssertionError(f"clean baseline fixture not approved:{clean_state}")
    if set(invalid_states.values()) != {"UNAPPROVED"}:
        raise AssertionError(f"invalid SHA classification failed:{invalid_states}")
    return {
        "schema": "d251-live-critical-stale-test-v1",
        "status": "PASS",
        "clean_state": clean_state,
        "invalid_sha_states": invalid_states,
        "stale_state": "STALE",
        "stale_paths_checked": stale_paths,
        "stale_path_count": len(stale_paths),
        "canonical_tree_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--baseline-state", metavar="FULL_SHA")
    group.add_argument("--list-json", action="store_true")
    group.add_argument("--offline-stale-test", action="store_true")
    args = parser.parse_args()
    if args.baseline_state is not None:
        print(baseline_state(args.repository, args.baseline_state))
    elif args.list_json:
        print(json.dumps(manifest(), sort_keys=True))
    else:
        print(json.dumps(offline_stale_detection_test(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

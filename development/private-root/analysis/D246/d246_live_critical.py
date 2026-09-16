"""D246 live-critical Git closure and index-independent baseline verifier."""

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
    "operator_kit/d246-live-d4-once.sh": "operator authorization, single-shot lifecycle, patching, cleanup, and reseal",
    "analysis/D245/D245_live_unseal.patch": "enables the reviewed A8-to-TLS predecessor path used by D246",
    "analysis/D246/D246_d4_continuation.patch": "adds the only reachable D4 wire action and terminal stop",
    "analysis/D246/d246_preflight.py": "D246 authorization namespace and pre-USB safety policy",
    "analysis/D246/d246_preflight_observability.py": "renders actionable fail-closed D246 preflight status",
    "analysis/D246/d246_live_critical.py": "defines and verifies the complete Git baseline closure",
    "src/goodix5125_d232_offline.py": "wire framing, replay policy, protected material loading, and durable reporting",
    "src/goodix5125_d233_backend.py": "real USB transport, PSK binding, TLS engine, and D4 backend path",
    "src/goodix5125_d235_entrypoint.py": "real entrypoint, runtime paths, authorization, and result mapping",
    "analysis/D230/work/GoodixExport/gfusb.dll": "hash-gated canonical PE input used to derive the runtime E4 validator",
    "poc/goodix5125/tools/binding_reference/__init__.py": "package initializer executed before the binding runtime module",
    "poc/goodix5125/tools/binding_reference/runtime.py": "runtime PSK-to-E4 validator derivation and canonical PE gate",
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
    repository: Path, baseline_sha: str, files: Sequence[str] = LIVE_CRITICAL_FILES
) -> str:
    """Compare working files directly with a Git commit without consulting .git/index."""
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
    with tempfile.TemporaryDirectory(prefix="d246-live-critical-") as directory:
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
                "user.name=D246 Offline Test",
                "-c",
                "user.email=d246-offline@example.invalid",
                "commit",
                "-q",
                "-m",
                "D246 offline baseline fixture",
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
        before = baseline_state(work, head)
        stale_target = work / "poc/goodix5125/tools/binding_reference/runtime.py"
        with stale_target.open("ab") as stream:
            stream.write(b"\n# D246 temporary stale-detection fixture\n")
        after = baseline_state(work, head)
    if before != "APPROVED" or after != "STALE":
        raise AssertionError(f"stale detection failed: before={before}, after={after}")
    return {
        "schema": "d246-live-critical-stale-test-v1",
        "status": "PASS",
        "clean_state": before,
        "modified_binding_runtime_state": after,
        "modified_path": "poc/goodix5125/tools/binding_reference/runtime.py",
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

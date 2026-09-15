#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate the deterministic SPDX 2.3 JSON SBOM for a managed candidate."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess


SHIPPED_COMPONENTS = (
    {
        "SPDXID": "SPDXRef-Package-libfprint-goodix",
        "name": "libfprint-goodix-27c6-5125",
        "versionInfo": "1.94.100",
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "GPL-3.0-or-later",
        "licenseDeclared": "LGPL-2.1-or-later AND GPL-2.0-or-later",
        "copyrightText": "NOASSERTION",
        "sourceInfo": (
            "Fedora libfprint 1.94.100 plus the project Goodix delta; the "
            "combined binary is conveyed under GPL-3.0-or-later while every "
            "source file retains its own license."
        ),
    },
    {
        "SPDXID": "SPDXRef-Package-Rockytkg-R2",
        "name": "Rockytkg-R2-image-preprocessing-adaptation",
        "versionInfo": "227eba219fa9e3fbac5bd59aca79f624f67cd11b",
        "downloadLocation": "https://github.com/Rockytkg/goodix-linux-27c6-5125",
        "filesAnalyzed": False,
        "licenseConcluded": "GPL-2.0-or-later",
        "licenseDeclared": "GPL-2.0-or-later",
        "copyrightText": "Copyright (C) 2026 liushicong (Rockytkg)",
    },
    {
        "SPDXID": "SPDXRef-Package-SIGFM",
        "name": "SIGFM",
        "versionInfo": "7ebe0c809b4d1df3400e84299a4ec4acdea84590",
        "downloadLocation": "https://github.com/goodix-fp-linux-dev/libfprint.git",
        "filesAnalyzed": False,
        "licenseConcluded": "LGPL-2.1-or-later",
        "licenseDeclared": "LGPL-2.1-or-later",
        "copyrightText": (
            "Copyright (C) 2022 Matthieu Charette and other SIGFM contributors"
        ),
    },
    {
        "SPDXID": "SPDXRef-Package-libgusb-bundled",
        "name": "libgusb",
        "versionInfo": "0.4.9-5.fc44",
        "downloadLocation": "https://src.fedoraproject.org/rpms/libgusb",
        "filesAnalyzed": False,
        "licenseConcluded": "LGPL-2.1-or-later",
        "licenseDeclared": "LGPL-2.1-or-later",
        "copyrightText": "NOASSERTION",
    },
    {
        "SPDXID": "SPDXRef-Package-OpenCV-bundled",
        "name": "opencv-runtime-subset",
        "versionInfo": "4.13.0-1.fc44",
        "downloadLocation": "https://src.fedoraproject.org/rpms/opencv",
        "filesAnalyzed": False,
        "licenseConcluded": "BSD-3-Clause AND Apache-2.0 AND ISC",
        "licenseDeclared": "BSD-3-Clause AND Apache-2.0 AND ISC",
        "copyrightText": "NOASSERTION",
    },
)

INTEGRATION_PACKAGES = (
    "fprintd",
    "fprintd-pam",
    "pam",
    "plasma-login-manager",
    "systemd",
    "selinux-policy-targeted",
    "policycoreutils",
    "checkpolicy",
)


def run(*argv: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        argv,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    ).stdout


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha1(path: pathlib.Path) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def spdx_id(value: str) -> str:
    return "SPDXRef-" + re.sub(r"[^A-Za-z0-9.-]", "-", value).strip("-")


def package_for_path(path: pathlib.Path) -> dict[str, object]:
    query = "%{NAME}\t%{EVR}\t%{ARCH}\t%{LICENSE}"
    fields = run("rpm", "-qf", "--qf", query, str(path)).strip().split("\t", 3)
    if len(fields) != 4:
        raise RuntimeError(f"invalid rpm metadata for {path}")
    name, version, arch, license_expression = fields
    return {
        "SPDXID": spdx_id(f"Package-host-{name}-{arch}"),
        "name": name,
        "versionInfo": version,
        "downloadLocation": f"https://src.fedoraproject.org/rpms/{name}",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "copyrightText": "NOASSERTION",
        "comment": f"Fedora RPM License metadata: {license_expression}",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:rpm/fedora/{name}@{version}?arch={arch}",
            }
        ],
    }


def installed_package(name: str) -> dict[str, object]:
    path = run("rpm", "-ql", name).splitlines()[0]
    return package_for_path(pathlib.Path(path))


def dynamic_package_paths(candidate: pathlib.Path) -> set[pathlib.Path]:
    paths: set[pathlib.Path] = set()
    env = os.environ | {"LD_LIBRARY_PATH": str(candidate)}
    for binary in sorted(candidate.glob("lib*.so*")):
        for line in run("ldd", str(binary), env=env).splitlines():
            match = re.search(r"=>\s+(/\S+)\s+\(", line)
            if not match and line.lstrip().startswith("/"):
                match = re.match(r"\s*(/\S+)\s+\(", line)
            if match:
                resolved = pathlib.Path(match.group(1)).resolve()
                if candidate not in resolved.parents:
                    paths.add(resolved)
            elif "not found" in line:
                raise RuntimeError(f"unresolved dynamic dependency: {line.strip()}")
    return paths


def creation_time(root: pathlib.Path, commit: str) -> str:
    value = run("git", "-C", str(root), "show", "-s", "--format=%cI", commit).strip()
    stamp = dt.datetime.fromisoformat(value).astimezone(dt.timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=pathlib.Path)
    parser.add_argument("--repo", required=True, type=pathlib.Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    root = args.repo.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("invalid source commit")
    if args.output.parent.resolve() != candidate:
        raise SystemExit("SBOM output must be inside the candidate")

    files = []
    for path in sorted(candidate.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"non-regular candidate entry: {path.name}")
        if path.name in {args.output.name, "SHA256SUMS"}:
            continue
        files.append(
            {
                "SPDXID": spdx_id(f"File-{path.name}"),
                "fileName": f"./{path.name}",
                "checksums": [
                    {"algorithm": "SHA1", "checksumValue": sha1(path)},
                    {"algorithm": "SHA256", "checksumValue": sha256(path)}
                ],
                "licenseConcluded": "NOASSERTION",
                "licenseInfoInFiles": ["NOASSERTION"],
                "copyrightText": "NOASSERTION",
            }
        )

    host_packages: dict[str, dict[str, object]] = {}
    for path in dynamic_package_paths(candidate):
        package = package_for_path(path)
        host_packages[str(package["SPDXID"])] = package
    for name in INTEGRATION_PACKAGES:
        package = installed_package(name)
        host_packages[str(package["SPDXID"])] = package

    verification = hashlib.sha1(
        "".join(
            sorted(
                next(
                    checksum["checksumValue"]
                    for checksum in entry["checksums"]
                    if checksum["algorithm"] == "SHA1"
                )
                for entry in files
            )
        ).encode("ascii"),
        usedforsecurity=False,
    ).hexdigest()
    shipped_components = [dict(component) for component in SHIPPED_COMPONENTS]
    bundled_gusb = installed_package("libgusb")
    for component in shipped_components:
        if component["SPDXID"] == "SPDXRef-Package-libgusb-bundled":
            component["versionInfo"] = bundled_gusb["versionInfo"]
            component["comment"] = bundled_gusb["comment"]

    package_id = "SPDXRef-Package-Goodix-Managed-Candidate"
    packages = [
        {
            "SPDXID": package_id,
            "name": "goodix-27c6-5125-source-first-managed",
            "versionInfo": args.commit,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": True,
            "packageVerificationCode": {
                "packageVerificationCodeValue": verification
            },
            "licenseInfoFromFiles": ["NOASSERTION"],
            "licenseConcluded": "GPL-3.0-or-later",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "Goodix 27c6:5125 project contributors",
            "sourceInfo": "Complete corresponding source is the exact SOURCE_COMMIT in MANIFEST.",
        },
        *shipped_components,
        *sorted(host_packages.values(), key=lambda item: str(item["SPDXID"])),
    ]
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": package_id,
        }
    ]
    relationships.extend(
        {
            "spdxElementId": package_id,
            "relationshipType": "CONTAINS",
            "relatedSpdxElement": file_entry["SPDXID"],
        }
        for file_entry in files
    )
    relationships.extend(
        {
            "spdxElementId": package_id,
            "relationshipType": "DEPENDS_ON",
            "relatedSpdxElement": package["SPDXID"],
        }
        for package in packages[1:]
    )

    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"goodix-27c6-5125-{args.commit}",
        "documentNamespace": (
            "https://spdx.org/spdxdocs/goodix-27c6-5125-" + args.commit
        ),
        "creationInfo": {
            "created": creation_time(root, args.commit),
            "creators": ["Tool: goodix-generate-sbom-1"],
        },
        "documentDescribes": [package_id],
        "packages": packages,
        "files": files,
        "relationships": relationships,
    }
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

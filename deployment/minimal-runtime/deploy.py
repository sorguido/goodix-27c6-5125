#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""R3: private libraries, one environment drop-in and an owned material fcontext."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import stat
import subprocess
import sys
import tempfile

BUILD_COMMIT = "b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226"
RUNTIME = Path("/usr/local/lib64/goodix-27c6-5125")
DROPIN = Path("/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf")
UNIT = "fprintd.service"
LIBRARIES = ("libfprint-2.so.2.0.0",) + tuple(
    f"libopencv_{part}.so.413" for part in ("core", "features2d", "flann", "imgproc"))
LINKS = {"libfprint-2.so.2": "libfprint-2.so.2.0.0", "libfprint-2.so": "libfprint-2.so.2"}
CONFIG = f"[Service]\nEnvironment=LD_LIBRARY_PATH={RUNTIME}\n".encode()
STATE = "installation.json"
REPO = Path(__file__).resolve().parents[2]
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(*args):
    result = subprocess.run(args, env=ENV, text=True, capture_output=True)
    require(result.returncode == 0,
            f"{' '.join(args)}: {result.stderr.strip() or result.stdout.strip() or result.returncode}")
    return result.stdout.strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, limit=64 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        st = os.fstat(stream.fileno())
        require(stat.S_ISREG(st.st_mode) and st.st_size <= limit, f"invalid regular file: {path}")
        data = stream.read(limit + 1)
    require(len(data) <= limit, f"file too large: {path}")
    return data


def safe_directory(path):
    require(path.is_absolute(), f"non-absolute directory: {path}")
    for item in (path, *path.parents):
        st = item.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                and not st.st_mode & 0o022, f"unsafe directory: {item}")


def no_sensor():
    # Read sysfs identity only; no USB handle or sensor command is opened.
    for device in Path("/sys/bus/usb/devices").iterdir():
        if (device / "idVendor").exists():
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
            require((vendor, product) != ("27c6", "5125"), "disconnect the Goodix reader from the VM")


def machine_gate():
    run("systemd-detect-virt", "--vm", "--quiet")
    require(os.geteuid() == 0, "run manually with sudo inside the VM")
    no_sensor()


def property_value(name):
    return run("systemctl", "show", UNIT, "--property=" + name, "--value")


def install_preflight():
    os_info = Path("/etc/os-release").read_text()
    require(re.search(r'^ID="?fedora"?$', os_info, re.M) and
            re.search(r'^VERSION_ID="?44"?$', os_info, re.M), "Fedora 44 required for this candidate")
    require(os.uname().machine == "x86_64", "x86_64 required")
    run("rpm", "-V", "fprintd")
    require(property_value("FragmentPath") == "/usr/lib/systemd/system/fprintd.service",
            "vendor fprintd unit required")
    commands = re.findall(r"path=([^ ;]+)", property_value("ExecStart"))
    require(commands == ["/usr/libexec/fprintd"], "stock fprintd ExecStart required")
    for name in property_value("DropInPaths").split():
        if name == str(DROPIN):
            continue
        require(name.startswith("/usr/lib/systemd/system/"), f"foreign service override: {name}")
        run("rpm", "-qf", name)
    environment = shlex.split(property_value("Environment"))
    for variable in environment:
        require(not variable.startswith("LD_PRELOAD="), "foreign preload environment")
        if variable.startswith("LD_LIBRARY_PATH="):
            require(variable == f"LD_LIBRARY_PATH={RUNTIME}" and DROPIN.exists()
                    and CONFIG == read_regular(DROPIN), "foreign library environment")
    require("LD_LIBRARY_PATH" not in property_value("UnsetEnvironment"), "library environment is unset by another override")
    active = property_value("ActiveState")
    require(active in ("active", "inactive"), f"service state requires review: {active}")
    require(run("getenforce") == "Enforcing", "SELinux Enforcing required; do not change enforcement for this test")
    return active


def git(*args):
    return run("git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args)


def load_payload(build):
    require(build.is_absolute() and build.resolve() == build, "use a real absolute build directory")
    for directory in (build / "runtime", build / "runtime/licenses"):
        require(directory.is_dir() and directory.resolve() == directory, f"unexpected directory link: {directory}")
    require(git("branch", "--show-current") == "development", "development required")
    require(not git("status", "--porcelain"), "clean committed checkout required")
    install_commit = git("rev-parse", "HEAD")
    provenance = read_regular(build / "build-provenance.txt", 65536)
    require(provenance.startswith(f"SOURCE_COMMIT={BUILD_COMMIT}\nBUILD_MODE=normal\n".encode()),
            "expected the qualified normal R3 build from " + BUILD_COMMIT)
    critical = ["libfprint-driver", "reference/libfprint-fedora44-1.94.100",
                "Rockytkg/libfprint/libfprint/sigfm", "production/build-inner.sh",
                "production/build-support", "production/minimal-runtime/build.sh",
                "production/check-source.sh", "production/source-files.tsv",
                "production/source-files.sha256", "production/host-test-only-symbols.txt"]
    git("diff", "--exit-code", BUILD_COMMIT, "HEAD", "--", *critical)
    checksum_text = read_regular(build / "runtime/SHA256SUMS", 4096).decode()
    checksums = {}
    for line in checksum_text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([a-zA-Z0-9_.-]+)", line)
        require(match is not None and match[2] not in checksums, "invalid runtime checksum manifest")
        checksums[match[2]] = match[1]
    require(set(checksums) == set(LIBRARIES), "unexpected runtime library set")
    payload = {name: read_regular(build / "runtime" / name) for name in LIBRARIES}
    require(all(digest(payload[name]) == checksums[name] for name in LIBRARIES), "runtime digest mismatch")
    for name, target in LINKS.items():
        require((build / "runtime" / name).is_symlink() and
                os.readlink(build / "runtime" / name) == target, f"unexpected link: {name}")
    for name in ("OpenCV-LICENSES.txt", "source-files.tsv", "source-files.sha256"):
        payload[name] = read_regular(build / "runtime" / name)
    for name in ("GPL-2.0-or-later", "LGPL-2.1-or-later", "GPL-3.0-or-later", "Apache-2.0"):
        payload[f"licenses/{name}.txt"] = read_regular(build / "runtime/licenses" / f"{name}.txt")
    payload["LICENSING_AND_PROVENANCE.md"] = read_regular(REPO / "docs/LICENSING_AND_PROVENANCE.md")
    payload["build-provenance.txt"] = provenance
    payload["SHA256SUMS"] = checksum_text.encode()
    # Keep the exact inverse with the installed runtime, independent of later Git changes.
    payload["deploy.py"] = read_regular(Path(__file__).resolve())
    payload["uninstall.sh"] = read_regular(Path(__file__).with_name("uninstall.sh"))
    return payload, install_commit


# Secret/binary material contents never enter deployment code.  The manifest
# is explicitly non-secret and is parsed fail-closed because the production
# loader requires the runtime-v1 projection, not the historical D232 source.
MATERIAL = Path("/var/lib/goodix-5125-poc")
MATERIAL_NAMES = ("target-material-manifest.json", "transport-material.bin",
                  "target-config-90.bin", "gfusb.dll", "fdt-cache.bin")
MATERIAL_RULE = r"/var/lib/goodix-5125-poc(/.*)?"
MATERIAL_CONTEXT = "system_u:object_r:fprintd_var_lib_t:s0"
MATERIAL_MANIFEST_EXPECTED = {
    "schema": "goodix-5125-device-materials-v1",
    "vid": "27c6",
    "pid": "5125",
    "app": "GF_ST411SEC_APP_12509",
    "transport_sha256": "eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75",
    "config90_sha256": "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82",
    "fdt_cache_sha256": "9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2",
    "a2_response_sha256": "39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5",
    "chip82_response_sha256": "82537d2c108887baef128b47ad401fc888d54b184673b1fc23811d79ab6d5703",
    "otp_a6_response_sha256": "d7e81a415aa5e7b0168c9a632756d1dc8b7b47346cc0a44dc68796f854c2b92b",
}
LEGACY_MANIFEST_SIZE = 2305
LEGACY_INSTALL = "264cd7ff1ba77857e1985502f299e4375f9a0516"
LEGACY_INVERSE_DIGEST = "67cfd22b5a0df829233722c1cf16dda8dadf473f4acb20529465f6015cddf585"


def atomic_file(path, data, mode):
    fd, temporary = tempfile.mkstemp(prefix=".goodix-metadata-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_state(state):
    atomic_file(RUNTIME / STATE, (json.dumps(state, indent=2) + "\n").encode(), 0o600)


def material_paths():
    return (MATERIAL, *(MATERIAL / name for name in MATERIAL_NAMES))


def material_metadata():
    safe_directory(MATERIAL.parent)
    result = []
    for index, path in enumerate(material_paths()):
        st = path.lstat()
        expected = (stat.S_IFDIR | 0o700) if index == 0 else (stat.S_IFREG | 0o600)
        require(st.st_mode == expected and st.st_uid == st.st_gid == 0,
                f"material metadata mismatch: {path}; no provisioning performed")
        require(index == 0 or st.st_nlink == 1, f"material hard link: {path}")
        result.append([st.st_dev, st.st_ino, st.st_uid, st.st_gid, st.st_mode,
                       st.st_size, st.st_mtime_ns])
    require({p.name for p in MATERIAL.iterdir()} == set(MATERIAL_NAMES),
            "unexpected material directory entries; retain for review")
    return result


def runtime_manifest_preflight():
    path = MATERIAL / "target-material-manifest.json"
    data = read_regular(path, 4096)
    # goodix_target_material.c accepts unescaped strings and unique keys only.
    # Python's default JSON decoder would normalize escapes and discard duplicates.
    require(b"\\" not in data, "runtime material manifest string escapes are unsupported")

    def unique_fields(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "runtime material manifest duplicate field")
            value[key] = item
        return value

    try:
        value = json.loads(data.decode("ascii"), object_pairs_hook=unique_fields)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("runtime material manifest is not valid ASCII JSON") from error
    require(isinstance(value, dict), "runtime material manifest must be a JSON object")
    require(value.get("schema") != "d232-target-material-v1",
            "legacy D232 material manifest is incompatible with R3; convert to runtime v1 before deployment")
    require(value == MATERIAL_MANIFEST_EXPECTED,
            "runtime material manifest fields or acceptance pins mismatch")
    return digest(data)


def material_contexts():
    return [os.getxattr(p, "security.selinux", follow_symlinks=False)
            .rstrip(b"\0").decode("ascii") for p in material_paths()]


def valid_material_precontext(context):
    # SELinux user is distinct from the Unix UID. Preserve its full value in
    # before_contexts; this transition constrains object role, type and level.
    if not isinstance(context, str):
        return False
    fields = context.split(":", 3)
    if len(fields) != 4:
        return False
    user, role, label_type, level = fields
    return (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", user) is not None
            and role == "object_r" and level == "s0"
            and label_type in ("var_lib_t", "fprintd_var_lib_t"))


def selinux_tools():
    for name in ("semanage", "restorecon", "matchpathcon"):
        require(shutil.which(name, path=ENV["PATH"]) is not None,
                f"missing {name}; STOP for review, do not change enforcement")
    require(run("getenforce") == "Enforcing", "SELinux Enforcing required")


def may_cover_material(expression):
    # Conservative PCRE stem check, NOT a Python-regex approximation of SELinux.
    # Unknown constructs/alternation can cover this path: stop for human review.
    if "|" in expression:
        return True
    expression = expression.removeprefix("^")
    end = next((i for i, char in enumerate(expression)
                if char in r".\[]()*+?{}$"), len(expression))
    stem, remainder = expression[:end], expression[end:]
    if remainder.startswith(("*", "?", "{")):
        stem = stem[:-1]  # A quantifier can make the last literal optional.
    target = str(MATERIAL)
    return target.startswith(stem) or stem.startswith(target + "/") or stem == target


def local_material_rule():
    # -C queries the local customization store (including equivalences), not the
    # effective/default label. -n and LC_ALL=C give the Fedora CLI's stable rows.
    listing = run("semanage", "fcontext", "-l", "-C", "-n")
    found = False
    kinds = "all files|regular file|directory|character device|block device|socket|symbolic link|named pipe"
    for line in listing.splitlines():
        if not line.strip():
            continue
        row = re.fullmatch(r"(.+?)\s+(" + kinds + r")\s+(\S+)\s*", line)
        if row:
            expression, kind, context = row.groups()
            if expression == MATERIAL_RULE and kind == "all files" and context == MATERIAL_CONTEXT:
                require(not found, "duplicate project fcontext rule; retain for review")
                found = True
            else:
                require(not may_cover_material(expression),
                        f"conflicting/possibly covering local fcontext: {expression}; retain for review")
        else:
            equivalence = re.fullmatch(r"(\S+)\s+=\s+(\S+)", line)
            require(equivalence is not None, "unrecognized local fcontext output; retain for review")
            require(not may_cover_material(equivalence[1]),
                    "local fcontext equivalence covers material; retain for review")
    return found


def material_plan():
    selinux_tools()
    metadata = material_metadata()
    manifest_sha256 = runtime_manifest_preflight()
    contexts = material_contexts()
    present = local_material_rule()
    require(all(valid_material_precontext(c) for c in contexts),
            "unexpected material context; retain for review")
    return {"rule": MATERIAL_RULE, "context": MATERIAL_CONTEXT, "owned": False,
            "phase": "apply" if present else "creating", "preexisting": present,
            "metadata": metadata, "before_contexts": contexts,
            "manifest_sha256": manifest_sha256}


def check_material_record(record):
    require(isinstance(record, dict), "invalid material ownership record; retain for review")
    require(record.get("rule") == MATERIAL_RULE and record.get("context") == MATERIAL_CONTEXT
            and type(record.get("owned")) is bool and type(record.get("preexisting")) is bool
            and record.get("phase") in ("creating", "apply", "ready", "removing", "removed")
            and isinstance(record.get("before_contexts"), list)
            and len(record["before_contexts"]) == 6,
            "invalid material ownership metadata; retain for review")
    require(record["phase"] != "creating", "uncertain mapping creation; retain state for review")
    require(record["owned"] != record["preexisting"] and
            all(valid_material_precontext(c) for c in record["before_contexts"]),
            "inconsistent material ownership metadata; retain for review")
    require(material_metadata() == record["metadata"], "material metadata drift; retain for review")
    if record.get("manifest_sha256") is not None:
        require(re.fullmatch(r"[0-9a-f]{64}", record["manifest_sha256"]) is not None,
                "invalid saved material manifest digest; retain for review")
        require(runtime_manifest_preflight() == record["manifest_sha256"],
                "runtime material manifest drift; retain for review")
    present = local_material_rule()
    phase = record["phase"]
    if phase in ("apply", "ready") or not record["owned"]:
        require(present, "material local rule drift; retain for review")
    elif phase == "removed":
        require(not present, "removed material rule reappeared; retain for review")
    actual = material_contexts()
    defaults = None
    if record["owned"] and phase in ("removing", "removed") and not present:
        defaults = [run("matchpathcon", "-n", str(p)) for p in material_paths()]
    for i, context in enumerate(actual):
        allowed = {MATERIAL_CONTEXT}
        if phase == "apply" or phase == "removing":
            allowed.add(record["before_contexts"][i])
        if defaults is not None:
            allowed.add(defaults[i])
            if phase == "removed":
                allowed = {defaults[i]}
        require(context in allowed, "material SELinux context drift; retain for review")
    return present


def restore_material(record, expected):
    # No recursive traversal: exactly the directory and the five checked files.
    require(material_metadata() == record["metadata"], "material metadata drift before relabel")
    run("restorecon", "-F", "--", *(str(p) for p in material_paths()))
    require(material_metadata() == record["metadata"], "material metadata changed during relabel")
    require(material_contexts() == expected, "effective material SELinux context verification failed")


def apply_material(state, record):
    state["material_selinux"] = record
    save_state(state)  # Save inverse/intent before the first SELinux mutation.
    require(local_material_rule() == record["preexisting"], "local rule changed during deployment")
    require(material_metadata() == record["metadata"] and
            material_contexts() == record["before_contexts"],
            "material changed during deployment; retain for review")
    if not record["preexisting"]:
        run("semanage", "fcontext", "-a", "-f", "a", "-t", "fprintd_var_lib_t", "-r", "s0", MATERIAL_RULE)
        record["owned"] = True  # Ownership only after successful creation.
        record["phase"] = "apply"
        save_state(state)
    require(local_material_rule(), "project mapping missing after establishment")
    restore_material(record, [MATERIAL_CONTEXT] * 6)
    record["phase"] = "ready"
    save_state(state)


def remove_material(state):
    record = state.get("material_selinux")
    if record is None:
        return  # Legacy R3 install never owned a mapping.
    selinux_tools()
    present = check_material_record(record)
    if record["phase"] == "removed":
        return
    if record["owned"]:
        record["phase"] = "removing"
        save_state(state)
        if present:
            require(check_material_record(record), "local rule changed before deletion")
            run("semanage", "fcontext", "-d", "-f", "a", MATERIAL_RULE)
        require(not local_material_rule(), "owned material rule still present after deletion")
        defaults = [run("matchpathcon", "-n", str(p)) for p in material_paths()]
        restore_material(record, defaults)
    elif record["phase"] == "apply":
        restore_material(record, [MATERIAL_CONTEXT] * 6)
    # An unowned compatible rule and its labels stay in place.
    record["phase"] = "removed"
    save_state(state)


def require_stopped():
    no_sensor()
    require(property_value("ActiveState") == "inactive" and property_value("MainPID") == "0",
            "fprintd must already be inactive/MainPID 0; no service action performed")


def show_material():
    selinux_tools()
    material_metadata()
    manifest_sha256 = runtime_manifest_preflight()
    present = local_material_rule()
    print("R3_MATERIAL_MANIFEST=RUNTIME_V1")
    print(f"R3_MATERIAL_MANIFEST_SHA256={manifest_sha256}")
    print(f"R3_MATERIAL_LOCAL_RULE={'PRESENT_COMPATIBLE' if present else 'ABSENT'}")
    for i, (path, context) in enumerate(zip(material_paths(), material_contexts())):
        print(f"{path} root:root {'0700' if i == 0 else '0600'} {context}")


def label_existing():
    require_stopped()
    state = inspect_owned()
    require(DROPIN.exists(), "incomplete runtime install; retain for review")
    record = state.get("material_selinux")
    if record is not None:
        selinux_tools()
        check_material_record(record)
        require(record["phase"] in ("ready", "removed"), "incomplete material operation; use inverse/review")
        if record["phase"] == "ready":
            runtime_manifest_preflight()
            print(f"R3_MATERIAL_LABEL=ALREADY_APPLIED OWNED={str(record['owned']).lower()} "
                  f"LABEL_COMMIT={state['material_label_commit']}")
            return
    plan = material_plan()  # All collision/layout checks before changing the saved inverse.
    require(git("branch", "--show-current") == "development" and not git("status", "--porcelain"),
            "clean committed development required")
    commit = git("rev-parse", "HEAD")
    inverse = read_regular(Path(__file__).resolve())
    old_inverse = read_regular(RUNTIME / "deploy.py")
    require(old_inverse == inverse or (state["install_commit"] == LEGACY_INSTALL and
            digest(old_inverse) == LEGACY_INVERSE_DIGEST and record is None),
            "unknown saved inverse; no runtime upgrade performed")
    old_state = read_regular(RUNTIME / STATE)
    try:
        atomic_file(RUNTIME / "deploy.py", inverse, 0o644)
        state["files"]["deploy.py"] = digest(inverse)
        state["material_label_commit"] = commit
        save_state(state)
    except BaseException:
        atomic_file(RUNTIME / "deploy.py", old_inverse, 0o644)
        atomic_file(RUNTIME / STATE, old_state, 0o600)
        raise
    # On label failure keep this inverse, state and runtime for inspected rollback.
    apply_material(state, plan)
    require_stopped()
    inspect_owned()
    print(f"R3_MATERIAL_LABEL=PASS OWNED={str(plan['owned']).lower()} LABEL_COMMIT={commit}")
    show_material()


def reconcile_runtime_manifest():
    """Accept only the reviewed legacy-D232 -> runtime-v1 manifest replacement."""
    require_stopped()
    state = inspect_owned()
    require(DROPIN.exists(), "incomplete runtime install; retain for review")
    record = state.get("material_selinux")
    require(isinstance(record, dict) and record.get("phase") == "ready",
            "material labeling must already be ready before manifest reconciliation")
    selinux_tools()
    require(local_material_rule(), "material local rule missing; retain for review")
    require(material_contexts() == [MATERIAL_CONTEXT] * 6,
            "material SELinux contexts are not canonical; retain for review")
    manifest_sha256 = runtime_manifest_preflight()
    current = material_metadata()
    saved = record.get("metadata")
    require(isinstance(saved, list) and len(saved) == 6,
            "saved material metadata is invalid; retain for review")
    require(current[2:] == saved[2:],
            "non-manifest material metadata drift; retain for review")
    require(current[0][:5] == saved[0][:5],
            "material directory identity/ownership/mode drift; retain for review")
    require(saved[1][2:5] == current[1][2:5] and saved[1][5] == LEGACY_MANIFEST_SIZE,
            "saved manifest is not the reviewed legacy D232 prestate")
    record["metadata"] = current
    record["manifest_sha256"] = manifest_sha256
    state["material_manifest_reconciled"] = True
    save_state(state)
    check_material_record(record)
    print("R3_MATERIAL_MANIFEST_RECONCILE=PASS SCHEMA=goodix-5125-device-materials-v1")
    print(f"R3_MATERIAL_MANIFEST_SHA256={manifest_sha256}")


def inspect_owned():
    safe_directory(RUNTIME)
    state = json.loads(read_regular(RUNTIME / STATE, 65536))
    require(state.get("schema") == 1 and state.get("build_commit") == BUILD_COMMIT,
            "unknown installation metadata; retain files for review")
    require(state.get("previous_service") in ("active", "inactive") and
            type(state.get("created_dropin_directory")) is bool, "invalid previous state")
    expected = set(state["files"]) | set(LINKS) | {STATE, "licenses"}
    actual = {str(p.relative_to(RUNTIME)) for p in RUNTIME.rglob("*")}
    require(actual == expected, "runtime contains missing or unowned files; retain for review")
    for name, checksum in state["files"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "invalid owned path")
        st = (RUNTIME / name).lstat()
        require(st.st_uid == os.geteuid() and not st.st_mode & 0o022, f"installed metadata drift: {name}")
        require(digest(read_regular(RUNTIME / name)) == checksum, f"installed file drift: {name}")
    for name, target in LINKS.items():
        require(os.readlink(RUNTIME / name) == target, f"installed link drift: {name}")
    if DROPIN.exists() or DROPIN.is_symlink():
        require(read_regular(DROPIN) == CONFIG, "project drop-in has drifted; retain for review")
    return state


def remove_owned_files(state, own_dropin=True):
    require(own_dropin or not (DROPIN.exists() or DROPIN.is_symlink()),
            "concurrent foreign drop-in: service left stopped; retained runtime for review")
    remove_material(state)
    # Missing drop-in is allowed for recovery after an interrupted removal.
    if own_dropin and (DROPIN.exists() or DROPIN.is_symlink()):
        require(read_regular(DROPIN) == CONFIG, "drop-in collision during recovery; retained runtime")
        DROPIN.unlink()
    run("systemctl", "daemon-reload")
    restore_service(state)
    # Retain the inverse and previous state until the vendor service is restored.
    shutil.rmtree(RUNTIME)
    if state["created_dropin_directory"]:
        try:
            DROPIN.parent.rmdir()
        except OSError:
            # A new foreign file must be preserved, never recursively removed.
            if not DROPIN.parent.is_dir() or not any(DROPIN.parent.iterdir()):
                raise


def restore_service(state):
    if state["previous_service"] == "active":
        no_sensor()
        run("systemctl", "start", UNIT)


def install(payload, install_commit, previous_service):
    safe_directory(RUNTIME.parent)
    safe_directory(DROPIN.parent if DROPIN.parent.exists() else DROPIN.parent.parent)
    if RUNTIME.exists() or RUNTIME.is_symlink():
        state = inspect_owned()
        require(DROPIN.exists(), "incomplete install: use saved uninstall before reinstalling")
        require(all(state["files"].get(name) == digest(data) for name, data in payload.items()),
                "different payload: use saved uninstall first")
        require(state.get("material_selinux", {}).get("phase") == "ready",
                "material labeling incomplete; use reviewed labeling action")
        selinux_tools()
        check_material_record(state["material_selinux"])
        runtime_manifest_preflight()
        print("R3_INSTALL=ALREADY_INSTALLED")
        return
    require(not DROPIN.exists() and not DROPIN.is_symlink(), "project drop-in path already occupied")
    material = material_plan()
    state = {"schema": 1, "build_commit": BUILD_COMMIT, "install_commit": install_commit,
             "material_label_commit": install_commit,
             "previous_service": previous_service, "created_dropin_directory": not DROPIN.parent.exists(),
             "files": {name: digest(data) for name, data in payload.items()}}
    stage = Path(tempfile.mkdtemp(prefix=".goodix-5125-stage-", dir=RUNTIME.parent))
    published = False
    stopped = False
    own_dropin = False
    try:
        for name, data in payload.items():
            destination = stage / name
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            destination.write_bytes(data)
            destination.chmod(0o755 if name == "uninstall.sh" else 0o644)
        for name, target in LINKS.items():
            (stage / name).symlink_to(target)
        (stage / STATE).write_text(json.dumps(state, indent=2) + "\n")
        (stage / STATE).chmod(0o600)
        stage.chmod(0o755)
        no_sensor()
        stopped = True
        run("systemctl", "stop", UNIT)
        stage.rename(RUNTIME)
        published = True
        DROPIN.parent.mkdir(mode=0o755, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".goodix-5125-dropin-", dir=DROPIN.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(CONFIG)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            os.link(temporary, DROPIN)  # Atomic publication; never overwrite a collision.
            own_dropin = True
        finally:
            Path(temporary).unlink()
        run("restorecon", "-RF", str(RUNTIME), str(DROPIN))
        run("systemctl", "daemon-reload")
        apply_material(state, material)
        # Leave stopped: the user explicitly starts stock fprintd in the R3 load check.
        print(f"R3_INSTALL=PASS BUILD_SOURCE_COMMIT={BUILD_COMMIT} INSTALL_COMMIT={install_commit}")
        print("FPRINTD=STOPPED_READY_FOR_MANUAL_LOAD_CHECK FEDORA_COMPONENTS_REPLACED=NONE")
    except BaseException:
        if published:
            # Only this transaction's files exist here; restore before propagating failure.
            remove_owned_files(state, own_dropin=own_dropin)
        elif stopped:
            restore_service(state)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def uninstall():
    safe_directory(RUNTIME.parent)
    safe_directory(DROPIN.parent if DROPIN.parent.exists() else DROPIN.parent.parent)
    if not RUNTIME.exists() and not RUNTIME.is_symlink():
        require(not DROPIN.exists() and not DROPIN.is_symlink(), "orphan drop-in: retain for review")
        print("R3_UNINSTALL=ALREADY_ABSENT")
        return
    state = inspect_owned()
    if state.get("material_selinux") is not None:
        selinux_tools()
        check_material_record(state["material_selinux"])
    run("systemctl", "stop", UNIT)
    remove_owned_files(state)
    print("R3_UNINSTALL=PASS FEDORA_VENDOR_FILES_UNCHANGED=true MATERIALS_TEMPLATES_PRESERVED=true")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall", "material-status", "label-material",
                                           "reconcile-material-manifest", "unlabel-material"))
    parser.add_argument("build_output", nargs="?", type=Path)
    args = parser.parse_args()
    require((args.action == "install") == (args.build_output is not None), "only install takes a build directory")
    machine_gate()
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt("deployment interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    safe_directory(RUNTIME.parent)
    # Advisory lock on the existing directory: serialize our transactions without a new host file.
    fd = os.open(RUNTIME.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "install":
            active = install_preflight()
            payload, commit = load_payload(args.build_output)
            install(payload, commit, active)
        elif args.action == "material-status":
            require_stopped()
            show_material()
        elif args.action == "label-material":
            install_preflight()
            label_existing()
        elif args.action == "reconcile-material-manifest":
            reconcile_runtime_manifest()
        elif args.action == "unlabel-material":
            require_stopped()
            state = inspect_owned()
            remove_material(state)
            require_stopped()
            print("R3_MATERIAL_ROLLBACK=PASS RUNTIME_PRESERVED=true")
            show_material()
        else:
            uninstall()  # No Fedora version/RPM/build-source check: inverse works after an update.
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("R3_DEPLOY=INTERRUPTED inspect the reported recovery result before continuing", file=sys.stderr)
        sys.exit(130)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"R3_DEPLOY=FAIL {error}", file=sys.stderr)
        sys.exit(1)

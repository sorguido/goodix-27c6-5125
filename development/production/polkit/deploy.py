#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Closed-set Polkit deployment, shared by the local patch and managed installer.

No authentication, bus access or service restart. Run only by the operator.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import importlib.util
from contextlib import contextmanager
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location("sudo_rules", Path(__file__).resolve().parents[1] / "sudo/rules.py")
sudo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sudo)

ROOT = Path(os.environ.get("GOODIX_MANAGED_TEST_ROOT", "/"))
TEST = ROOT != Path("/")
STATE = "/var/lib/goodix-polkit"
GUARD = "/run/polkit/goodix-fingerprint"
LOCAL = "/usr/local/lib64/goodix-27c6-5125/polkit/pam_goodix_polkit.so"
MANAGED = "/usr/lib64/goodix-27c6-5125/current/pam_goodix_polkit.so"
VENDOR = "/usr/lib/pam.d/polkit-1"
VENDOR_BYTES = (b"#%PAM-1.0\n\nauth       include      system-auth\n"
                b"account    include      system-auth\npassword   include      system-auth\n"
                b"session    include      system-auth\n")
PAM = "/etc/pam.d/polkit-1"
LEAF = "/etc/pam.d/goodix-polkit-fingerprint"
TMPFILES = "/etc/tmpfiles.d/goodix-polkit.conf"
DROPIN = "/etc/systemd/system/polkit-agent-helper@.service.d/50-goodix-polkit.conf"
FILES = (LEAF, TMPFILES, DROPIN, PAM)  # enable the public PAM service last
# Exact PAM binary delivered at d7de50585d555b1ca676e4fcf6c9ed77cc20d601.
# Compatibility applies only to its authentic local-user counter, never to a
# new module or to an arbitrary GID. The outer managed verifier pins its tree.
HISTORICAL_MODULE = "9de3aba169b78298e539df1320f9bb10d64d418b6dd3ece196dcc401f1b7e3c2"


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def p(name):
    return ROOT / name.lstrip("/")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(name, mode=0o644):
    path = p(name)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == mode and info.st_nlink == 1,
            f"file type/mode drift: {name}")
    require(TEST or (info.st_uid, info.st_gid) == (0, 0), f"file ownership drift: {name}")
    if not TEST:
        require(set(os.listxattr(path)) <= {"security.selinux"}, f"custom file attributes: {name}")
    return path.read_bytes()


def run(*args):
    if not TEST:
        subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def parents(name, created=None, missing_ok=False):
    for path in reversed(list(p(name).parents)[:-1]):
        if not path.is_relative_to(ROOT):
            continue
        if not path.exists() and not path.is_symlink():
            if missing_ok: continue
            require(created is not None, f"missing directory: {path}")
            path.mkdir(mode=0o755)
            path.chmod(0o755)
            created.append("/" + str(path.relative_to(ROOT)))
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o022,
                f"unsafe parent: {path}")
        require(TEST or info.st_uid == 0, f"parent ownership: {path}")


def atomic(name, data, mode=0o644):
    temporary = p(name + ".goodix-next")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, p(name))
        run("restorecon", "-F", str(p(name)))
    finally:
        if temporary.exists(): temporary.unlink()


def no_helpers(kind="local"):
    ancestors = set()
    pid = os.getpid()
    while pid > 1:
        ancestors.add(str(pid))
        try: pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except FileNotFoundError: break
    if TEST: return
    for proc in Path("/proc").glob("[0-9]*/exe"):
        try:
            executable = os.readlink(proc)
        except FileNotFoundError:
            continue
        require(executable != "/usr/lib/polkit-1/polkit-agent-helper-1" and
                not (kind == "managed" and executable == "/usr/bin/sudo" and proc.parent.name not in ancestors),
                "close authentication dialogs before install/uninstall")


def baseline(kind="local"):
    parents(VENDOR)
    require(regular(VENDOR) == VENDOR_BYTES, "unsupported/drifted vendor polkit PAM")
    for directory in ("/etc/pam.d", "/usr/lib/pam.d"):
        for suffix in (".rpmnew", ".rpmsave"):
            path = p(directory + "/polkit-1" + suffix)
            require(not path.exists() and not path.is_symlink(), "resolve polkit PAM rpmnew/rpmsave first")
    # This boundary supports the Fedora local password stack audited here.
    # Reject richer auth stacks rather than bypassing their required factors.
    system = p("/etc/pam.d/system-auth")
    info = system.stat()
    require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022 and
            (TEST or (info.st_uid, info.st_gid) == (0, 0)), "unsafe system-auth metadata")
    rows = [line.split() for line in system.read_text().splitlines()
            if line.split() and line.split()[0] == "auth"]
    require(rows == [
        ["auth", "required", "pam_env.so"],
        ["auth", "required", "pam_faildelay.so", "delay=2000000"],
        ["auth", "sufficient", "pam_unix.so", "nullok"],
        ["auth", "required", "pam_deny.so"],
    ], "unsupported system-auth: local password stack without global fingerprint required")
    if not TEST:
        for package, version in (("polkit", "127-2.fc44.2"), ("polkit-kde", "6.7.5-1.fc44"),
                                 ("fprintd-pam", "1.94.5-5.fc44"), ("pam", "1.7.2-2.fc44")):
            value = subprocess.check_output(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", package], text=True)
            require(value == version, f"unsupported {package} version")
        for name, expected in (
            ("/usr/lib64/security/pam_fprintd.so", "96e47e1514a7c6c4fc722fa086bc25bb1c4d44774421c3d2970c7fc2b4385ebd"),
            ("/usr/lib/polkit-1/polkit-agent-helper-1", "026972c2853aa610480cdf5957dacdf28d7b07059977282cfee0a5d8deb0605a"),
        ):
            mode = 0o4755 if "helper" in name else 0o755
            require(digest(regular(name, mode)) == expected, f"stock component drift: {name}")
        # The existing policy labels permit the narrow runtime counter, without
        # adding SELinux grants. Socket mode additionally needs ReadWritePaths.
        label = subprocess.check_output(["matchpathcon", "-n", GUARD], text=True)
        require(":policykit_var_run_t:" in label, "unsupported SELinux runtime label")
    extra = sudo.baseline(SimpleNamespace(p=p, regular=regular, require=require, digest=digest, TEST=TEST)) if kind == "managed" else ""
    return digest(system.read_bytes() + extra.encode())


def payload(kind):
    module = LOCAL if kind == "local" else MANAGED
    prefix = ("auth required pam_env.so\nauth required pam_faildelay.so delay=2000000\n"
              f"auth [success=done ignore=ignore open_err=ignore symbol_err=ignore module_unknown=ignore default=die] {module}\n").encode()
    result = {
        PAM: VENDOR_BYTES.replace(b"auth       include", prefix + b"auth       include", 1),
        LEAF: b"#%PAM-1.0\nauth required /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=45\n",
        TMPFILES: f"d {GUARD} 0700 root root -\n".encode(),
        DROPIN: f"[Service]\nReadWritePaths={GUARD}\n".encode(),
    }

    if kind == "managed": result.update(sudo.payload())
    return result

def preflight(kind):
    require(kind in ("local", "managed"), "invalid deployment kind")
    system_auth = baseline(kind)
    no_helpers(kind)
    if p(PAM).exists() or p(PAM).is_symlink():
        require(regular(PAM) == VENDOR_BYTES, "custom Polkit override: preserve and review")
        run("matchpathcon", "-V", str(p(PAM)))
    if kind == "managed":
        require(regular(sudo.PAM) == sudo.VENDOR, "custom sudo PAM: original owner rollback required")
        run("matchpathcon", "-V", str(p(sudo.PAM)))
    for name in set(payload(kind)) - {PAM, sudo.PAM} | {GUARD, STATE} | ({LOCAL} if kind == "local" else set()):
        require(not p(name).exists() and not p(name).is_symlink(), f"Polkit path collision: {name}")
    return system_auth


def load():
    parents(STATE + "/state.json")
    info = p(STATE).lstat()
    require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and
            (TEST or (info.st_uid, info.st_gid) == (0, 0)),
            "Polkit state directory drift")
    data = json.loads(regular(STATE + "/state.json", 0o600))
    require(data["kind"] in ("local", "managed") and data["schema"] == (2 if data["kind"] == "managed" else 1), "unsupported Polkit state")
    require(set(data["hashes"]) == set(payload(data["kind"])) | ({LOCAL} if data["kind"] == "local" else set()),
            "Polkit state file set drift")
    return data


def verify(kind, recovery=False):
    data = load()
    require(data["kind"] == kind, "local/managed Polkit deployment collision")
    if not recovery:
        no_helpers(kind)
        require(data["system_auth"] == baseline(kind), "system-auth changed since Polkit installation")
        require(all(data["hashes"][name] == digest(contents) for name, contents in payload(kind).items()),
                "Polkit host rules changed: original uninstall then fresh install required")
        info = p(GUARD).lstat()
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700 and
                (TEST or (info.st_uid, info.st_gid) == (0, 0)), "Polkit runtime directory drift")
        run("matchpathcon", "-V", str(p(GUARD)))
        # A historical noncanonical counter can be removed with its pinned
        # module, but must not be carried into an update to the new contract.
        with qualified_guard(kind, historical=False): pass
    for name, expected in data["hashes"].items():
        path = p(name)
        parents(name, missing_ok=recovery)
        if recovery and not path.exists() and not path.is_symlink(): continue
        contents = regular(name)
        if recovery and name == PAM and data["pam_existed"] and contents == VENDOR_BYTES: continue
        if recovery and name == sudo.PAM and contents == sudo.VENDOR: continue
        require(digest(contents) == expected, f"owned Polkit file drift: {name}")
    return data


def local_counter_users():
    # Same local non-root identity set as runtime local_uid(); no NSS/network.
    # A numeric filename alone is not a trusted identity.
    users = {}
    for line in p("/etc/passwd").read_text().splitlines():
        row = line.split(":")
        require(len(row) == 7, "local passwd drift")
        require(row[2].isdecimal() and row[3].isdecimal(), "local passwd identity drift")
        if int(row[2]) != 0: users[str(int(row[2]))] = row[0], int(row[3])
    return users


def historical_runtime(kind):
    path = p(MANAGED if kind == "managed" else LOCAL)
    return path.is_file() and not path.is_symlink() and digest(path.read_bytes()) == HISTORICAL_MODULE


def guard_owners():
    return (os.geteuid(), os.getegid()) if TEST else (0, 0)


@contextmanager
def qualified_guard(kind, historical=True):
    """Read-only qualification of the COMPLETE directory before any removal.

    Keep exclusive counter locks until uninstall finishes. O_NOFOLLOW and
    O_NONBLOCK reject links and special files without waiting on a FIFO.
    """
    handles = []
    directory = None
    try:
        if not os.path.lexists(p(GUARD)):
            yield []
            return
        parents(GUARD)
        directory = os.open(p(GUARD), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(directory)
        owner, group = guard_owners()
        require(stat.S_IMODE(info.st_mode) == 0o700 and
                (info.st_uid, info.st_gid) == (owner, group), "guard directory drift")
        require(set(os.listxattr(directory)) <= {"security.selinux"}, "guard directory attributes drift")
        entries = os.listdir(directory)
        users = local_counter_users() if entries else {}
        require(set(entries) <= set(users), "unexpected guard entry; preserve for review")
        for name in entries:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and
                    info.st_nlink == 1 and info.st_size == 1 and info.st_uid == owner,
                    "counter type/mode/owner/link/size drift")
            require(info.st_gid == group or
                    (historical and name == '1000' and users[name] == ('guido',1000) and
                     info.st_gid == 1000 and historical_runtime(kind)),
                    "counter group drift")
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
            handles.append(fd)
            require(os.fstat(fd) == info, "counter changed during qualification")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require(os.read(fd, 2) in (b"0", b"1", b"2", b"3"), "counter content drift")
            require(set(os.listxattr(fd)) <= {"security.selinux"}, "counter attributes drift")
        yield entries
    finally:
        for fd in handles: os.close(fd)
        if directory is not None: os.close(directory)


@contextmanager
def removal_rollback(data, entries):
    """Small in-memory antidote for handled I/O failures after qualification.

    Public PAM/module bytes and bounded counters only; no protected material.
    Crash/power-loss recovery is outside this local antidote.
    """
    names=set(data['hashes']) | {STATE+'/state.json'} | {GUARD+'/'+n for n in entries}
    directories=set(data['directories']) | {STATE, GUARD}
    def metadata(path):
        info=path.lstat()
        return (info, {key:os.getxattr(path,key) for key in os.listxattr(path)})
    files={name:(p(name).read_bytes(),metadata(p(name))) if p(name).exists() else None for name in names}
    dirs={name:metadata(p(name)) for name in directories if p(name).exists()}
    for name in names:
        require(not os.path.lexists(p(name+'.goodix-next')), "uninstall temporary collision")
    def restore_metadata(path, saved):
        info,attrs=saved
        if not TEST: os.chown(path,info.st_uid,info.st_gid)
        path.chmod(stat.S_IMODE(info.st_mode))
        for key in os.listxattr(path):
            if key not in attrs: os.removexattr(path,key)
        for key,value in attrs.items(): os.setxattr(path,key,value)
        os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
    try:
        yield
    except BaseException:
        # Runtime directory stays private before counter bytes are restored.
        for name in sorted(dirs,key=lambda n:len(Path(n).parts)):
            p(name).mkdir(mode=stat.S_IMODE(dirs[name][0].st_mode),exist_ok=True)
        for name in sorted(files, key=lambda n:(n in (PAM,sudo.PAM),n)):
            saved=files[name]
            if saved is None:
                if p(name).exists(): p(name).unlink()
                continue
            contents,meta=saved
            temporary=p(name+'.goodix-next')
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as file:
                file.write(contents);file.flush();os.fsync(file.fileno())
            restore_metadata(temporary,meta)
            os.replace(temporary,p(name))
        for name,meta in dirs.items(): restore_metadata(p(name),meta)
        run('systemctl','daemon-reload')
        print('POLKIT_UNINSTALL=ROLLED_BACK previous_candidate_files=RESTORED',file=sys.stderr)
        raise


def uninstall(kind):
    if not p(STATE).exists() and not p(STATE).is_symlink():
        print("POLKIT_UNINSTALL=ALREADY_ABSENT")
        return
    no_helpers(kind)
    data = verify(kind, recovery=True)
    require(set(os.listdir(p(STATE))) == {"state.json"}, "unexpected Polkit state entry")
    for name in (PAM, sudo.PAM) if kind == "managed" else (PAM,):
        require(not os.path.lexists(p(name + ".goodix-next")), "PAM temporary collision")
    require(isinstance(data["directories"], list) and all(
        name in {"/" + str(parent.relative_to(ROOT)) for path in (*payload(kind), LOCAL, GUARD)
                 for parent in p(path).parents if parent.is_relative_to(ROOT) and parent != ROOT}
        for name in data["directories"]), "Polkit directory ledger drift")
    # All drift checks precede the FIRST mutation, including the complete
    # runtime set. Handled later I/O failures restore the original file set.
    with qualified_guard(kind) as entries, removal_rollback(data, entries):
        if kind == "managed": atomic(sudo.PAM, sudo.VENDOR)
        if data["pam_existed"]:
            atomic(PAM, VENDOR_BYTES)
        elif p(PAM).exists(): p(PAM).unlink()
        for name in data["hashes"]:
            if name not in (PAM, sudo.PAM) and p(name).exists(): p(name).unlink()
        run("systemctl", "daemon-reload")
        for name in entries: p(GUARD + "/" + name).unlink()
        if p(GUARD).exists(): p(GUARD).rmdir()
        for name in reversed(data["directories"]):
            try: p(name).rmdir()
            except OSError: pass  # preserve directories acquired by other software
        p(STATE + "/state.json").unlink()
        p(STATE).rmdir()
    print("POLKIT_UNINSTALL=PASS previous_PAM=RESTORED")


def install(kind, module=None):
    require(kind in ("local", "managed"), "invalid deployment kind")
    if p(STATE).exists() or p(STATE).is_symlink():
        data = verify(kind)
        if kind == "local":
            require(module is not None and digest(Path(module).read_bytes()) == data["hashes"][LOCAL],
                    "different local patch: uninstall the previous patch first")
        print("POLKIT_INSTALL=ALREADY_ACTIVE")
        return
    system_auth = preflight(kind)
    files = payload(kind)
    source_commit = None  # managed provenance is owned by the outer transaction
    if kind == "local":
        require(not p("/var/lib/goodix-27c6-5125-managed/state").exists(), "managed host needs managed lifecycle")
        source = Path(module)
        require(source.is_file() and not source.is_symlink(), "invalid local PAM payload")
        files[LOCAL] = source.read_bytes()  # freeze before the first host mutation
        require(files[LOCAL][:4] == b"\x7fELF", "local PAM payload is not ELF")
        provenance = (source.parent / "PROVENANCE").read_text()
        match = re.fullmatch(r"SOURCE_COMMIT=([0-9a-f]{40})\nPURPOSE=POLKIT_INTERRUPTIBLE_SERVICE_LOCAL_V1\n", provenance)
        require(match is not None, "invalid local source provenance")
        source_commit = match.group(1)
    existed = p(PAM).exists() or p(PAM).is_symlink()
    if existed: require(regular(PAM) == VENDOR_BYTES, "custom Polkit override: preserve and review")
    for name in set(files) - {PAM, sudo.PAM} | {GUARD, STATE}:
        require(not p(name).exists() and not p(name).is_symlink(), f"Polkit path collision: {name}")
    # Every missing directory is recorded before installing any PAM content.
    directories = []
    try:
        for name in (*files, GUARD, STATE + "/state.json"):
            parents(name, directories)
        p(STATE).chmod(0o700)
        data = dict(schema=2 if kind == "managed" else 1, kind=kind, source_commit=source_commit, system_auth=system_auth, pam_existed=existed,
                    hashes={name: digest(contents) for name, contents in files.items()},
                    directories=[name for name in directories if name != STATE])
        atomic(STATE + "/state.json", json.dumps(data, sort_keys=True).encode(), 0o600)
    except Exception:
        for name in reversed(directories):
            try: p(name).rmdir()
            except OSError: pass
        raise
    try:
        # Library precedes leaf; public service is enabled only after tmpfiles.
        for name in (*([LOCAL] if kind == "local" else []), LEAF, TMPFILES, DROPIN):
            atomic(name, files[name])
        if kind == "managed": atomic(sudo.LEAF, files[sudo.LEAF])
        p(GUARD).mkdir(mode=0o700)
        run("restorecon", "-RF", str(p("/run/polkit")))
        run("systemctl", "daemon-reload")
        if kind == "managed": atomic(sudo.PAM, files[sudo.PAM])
        atomic(PAM, files[PAM])
        verify(kind)
    except Exception:
        uninstall(kind)
        raise
    print("POLKIT_INSTALL=PASS live_validation=HUMAN_REQUIRED")


if __name__ == "__main__":
    try:
        require(not TEST or (str(ROOT).startswith("/tmp/goodix-managed-test.") and ROOT.is_dir()
                            and ROOT.stat().st_uid == os.geteuid()), "unsafe offline test root")
        require(TEST or os.geteuid() == 0, "operator root transaction required")
        require(len(sys.argv) in (3, 4), "usage: install|verify|preflight|uninstall local|managed [PAM_MODULE]")
        action, kind = sys.argv[1:3]
        # Serialize with the existing parent directory, without a persistent lock file.
        lock = os.open(p("/var/lib"), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action == "install": install(kind, sys.argv[3] if len(sys.argv) == 4 else None)
        elif action == "verify": verify(kind)
        elif action == "preflight": preflight(kind)
        elif action == "uninstall": uninstall(kind)
        else: raise RuntimeError("unknown action")
        os.close(lock)
    except Exception as error:
        print(f"POLKIT_DEPLOY=FAIL reason={error}", file=sys.stderr)
        sys.exit(1)

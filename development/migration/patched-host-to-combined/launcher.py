#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Human-only KDE launcher. One password-only elevation, explicit phases.

No biometric workflow, retries, daemon start or arbitrary root command API.
Tests inject calls into pure functions; the CLI has no test-root override.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
CANDIDATE=Path('/tmp/goodix-combined-migration-ready/candidate')
POLICY=Path('/tmp/goodix-migration-ready-policy/goodix_fprint_account_delete.pp')
RECEIPT=Path('/tmp/goodix-migration-ready.SHA256SUMS')
FOLDERS=('development/migration/patched-host-to-combined','deployment/managed-install',
         'production/polkit','production/sudo')
ENV={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1',
     'SUDO_USER':'guido','SUDO_UID':'1000','SUDO_GID':'1000'}


def require(value,reason):
    if not value: raise RuntimeError(reason)


def sha(data): return hashlib.sha256(data).hexdigest()


def git(repo,*args):
    return subprocess.check_output(['/usr/bin/git','-C',str(repo),*args],env=ENV,text=True).strip()


def delivery(repo=REPO,candidate=CANDIDATE,policy=POLICY,receipt=RECEIPT):
    require(git(repo,'branch','--show-current')=='development','branch_not_development')
    head=git(repo,'rev-parse','HEAD')
    require(not git(repo,'status','--porcelain','--untracked-files=all'),'worktree_dirty')
    require(candidate.is_dir() and not candidate.is_symlink(),'candidate_missing_or_symlink')
    paths=set(candidate.iterdir())
    require(len(paths)==36,'candidate_file_set')
    paths.add(policy)
    for folder in FOLDERS:
        paths.update(repo/name for name in git(repo,'ls-files','--',folder).splitlines())
    require(receipt.is_file() and not receipt.is_symlink(),'delivery_receipt_missing')
    recorded={}
    for line in receipt.read_text().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (/[^\n]+)',line)
        require(match is not None,'receipt_grammar')
        path=Path(match[2]); require(path not in recorded,'duplicate_receipt_path')
        recorded[path]=match[1]
    require(set(recorded)==paths,'receipt_path_set')
    for path in paths:
        require(path.is_file() and not path.is_symlink(),'delivery_file_missing_or_symlink')
        require(sha(path.read_bytes())==recorded[path],'delivery_digest_drift')
    manifest=dict(line.split('=',1) for line in (candidate/'MANIFEST').read_text().splitlines())
    require(manifest['SOURCE_COMMIT']==head,'candidate_head_mismatch')
    require(manifest['SUDO_INTEGRATION']=='PASSWORD_FIRST_SERVICE_LOCAL_V1' and
            manifest['POLKIT_INTEGRATION']=='INTERRUPTIBLE_SERVICE_LOCAL_V1' and
            manifest['PROTECTED_MATERIAL_INCLUDED']=='false','candidate_contract')
    return head


def password_only(root=Path('/')):
    def p(name): return root/name.lstrip('/')
    require(not os.path.lexists(p('/etc/pam.d/polkit-1')),'polkit_not_password_only_baseline')
    require(sha(p('/usr/lib/pam.d/polkit-1').read_bytes())==
            'a4454c54582a86fd4560321b22ffb7639485968438a07d5412fadc102d62cf49','polkit_vendor_drift')
    require(p('/etc/pam.d/system-auth').resolve()==p('/etc/authselect/system-auth').resolve(),
            'system_auth_selection_drift')
    require(sha(p('/etc/authselect/system-auth').read_bytes())==
            '2e53f704372b6c7fb69cdc4dfd6c27456d642c83feff8b1588fa1f9cb1126cd0',
            'system_auth_not_qualified_password_baseline')


def elevate(action,invoke):
    # Called only AFTER the password-only PAM check. No fallback authentication.
    command=['/usr/bin/pkexec','--disable-internal-agent','--user','root',
             '/usr/bin/python3','-I','-B',str(HERE/'launcher.py'),'--root-'+action]
    try: invoke(command)
    except subprocess.CalledProcessError as error:
        raise RuntimeError('privileged_phase_failed_rc_'+str(error.returncode)) from error


def console_ready(host):
    require(host.run('/usr/bin/systemctl','show','goodix-migration-recovery.service',
                     '-p','ActiveState','--value')=='active','recovery_console_not_active')
    command=host.run('/usr/bin/systemctl','show','goodix-migration-recovery.service',
                     '-p','ExecStart','--value')
    require('argv[]=/usr/bin/openvt -s -w -- /usr/bin/bash --noprofile --norc ;' in command,
            'recovery_console_command_drift')


def run_flow(tx,invoke,ask,check_delivery):
    # preflight stays read-only; negative preflight never reaches apply.
    tx.before(armed=True); console_ready(tx.host)
    print('PREFLIGHT=PASS. Console di emergenza mantenuta; nessuna attività biometrica automatica.',flush=True)
    ask('Invio: applica la migrazione; Ctrl+C: esci senza modifiche. ')
    check_delivery()
    attempted=False
    try:
        attempted=True
        print('MIGRATION='+tx.apply(POLICY),flush=True)
        print('PASSWORD: verifica sudo come guido; inserisci la password, senza contatto sul lettore.',flush=True)
        # Privilege is dropped for the normal password workflow, while fprintd
        # remains masked and the standard password-only PAM is restored.
        invoke(['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--',
                '/usr/bin/sudo','-k','/usr/bin/true'])
        ask('PASSWORD=PASS. Invio: release e installazione candidate; Ctrl+C: ripristina. ')
        check_delivery()
        print('MIGRATION='+tx.release(),flush=True)
        manager=str(REPO/'deployment/managed-install/root-transaction.sh')
        invoke(['/usr/bin/bash',manager,'--root-install','guido',str(CANDIDATE)])
        invoke(['/usr/bin/bash',manager,'--status'])
        print('OPERATOR=PASS_INSTALL_AND_STATUS. Esegui ora i workflow manuali del README; '
              'TTY solo emergenza: /run/gx. La console root resta aperta.',flush=True)
    except BaseException:
        if attempted and tx.fs.info('/var/lib/goodix-27c6-5125-migration') is not None:
            try:
                print('RECOVERY='+tx.recovery_restore(invoke),flush=True)
            except BaseException:
                print('RECOVERY=STOP usare /run/gx dalla TTY; preservare tutti i file.',file=sys.stderr)
        raise


def main():
    args=sys.argv[1:]
    if args in ([],['--help']):
        print('Uso da KDE/Konsole: operator.sh check | preflight | rearm | console | run\n'
              'check: solo consegna offline; preflight: root read-only; rearm: prepara nuovo tentativo dopo rollback; console: solo recovery; '
              'run: fasi esplicite, poi stop prima delle prove biometriche.'); return 0
    require(len(args)==1,'usage')
    action=args[0]
    if action.startswith('--root-'):
        require(os.geteuid()==0 and os.environ.get('PKEXEC_UID')=='1000','operator_root_boundary')
        require(action in ('--root-preflight','--root-rearm','--root-console','--root-run'),'root_action')
        delivery(); password_only()
        spec=importlib.util.spec_from_file_location('migration',HERE/'migration.py')
        m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        fs=m.Files(); tx=m.Migration(fs,m.Host())
        tx.recovery_restore=lambda invoke: m.recovery.restore(tx,invoke)
        lock=os.open('/run',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            def invoke(command): subprocess.run(command,check=True,env=ENV)
            if action=='--root-preflight':
                print('OPERATOR='+tx.preflight())
            elif action=='--root-rearm':
                console_ready(tx.host)
                print('OPERATOR='+tx.rearm(POLICY))
            elif action=='--root-console':
                tx.before()
                units=tx.host.run('/usr/bin/systemctl','list-units','--all','--plain','--no-legend',
                                 'goodix-migration-recovery.service')
                if units: console_ready(tx.host); print('RECOVERY_CONSOLE=ALREADY_ACTIVE')
                else:
                    invoke(['/usr/bin/systemd-run','--unit=goodix-migration-recovery','--collect','--',
                            '/usr/bin/openvt','-s','-w','--','/usr/bin/bash','--noprofile','--norc'])
            else:
                require(sys.stdin.isatty(),'konsole_interactive_terminal_required')
                run_flow(tx,invoke,input,delivery)
        finally: os.close(lock); fs.close()
    else:
        require(os.geteuid()==1000,'operator_must_be_guido')
        require(action in ('check','preflight','rearm','console','run'),'usage')
        head=delivery(); print('DELIVERY=PASS SOURCE_COMMIT='+head,flush=True)
        if action=='check': return 0
        password_only()
        require(sys.stdin.isatty(),'konsole_interactive_terminal_required')
        elevate(action,lambda command: subprocess.run(command,check=True))
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except KeyboardInterrupt:
        print('OPERATOR=STOP interrupted_no_retry',file=sys.stderr); sys.exit(130)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,RuntimeError,subprocess.SubprocessError) as error:
        reason=str(error) if isinstance(error,RuntimeError) else 'io_or_subprocess_failure'
        if not re.fullmatch('[A-Za-z0-9_]+',reason): reason='validation_failure'
        print('OPERATOR=STOP reason='+reason+' keep_recovery_console',file=sys.stderr); sys.exit(1)

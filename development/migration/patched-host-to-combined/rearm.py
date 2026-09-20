# SPDX-License-Identifier: GPL-2.0-or-later
"""Qualified snapshot rotation. No cleanup or execution of unpinned saved code."""
import importlib.util
import json
import re


def saved(tx, directory):
    m=tx.module_api
    data,_=tx.fs.read(directory+'/state.json',0o600,65536)
    state=json.loads(data)
    m.require(isinstance(state,dict),'invalid_recovery_state_shape')
    pins=json.loads((m.HERE/'legacy-recovery.json').read_bytes())
    current=state.get('source') == tx.source()
    expected=tx.source() if current else pins['source']
    m.require(state.get('source') == expected,'unknown_recovery_provenance')
    for name, sha in expected.items():
        content,_=tx.fs.read(directory+'/'+name,0o600)
        m.require(m.digest(content)==sha,'saved_recovery_source_drift')
    if not current:
        m.require(state.get('recovery')==pins['recovery'],'unknown_saved_manager')
    # All imports have now been authenticated against current or pinned f97de44 sources.
    if current:
        restored=tx.at(directory)
    else:
        spec=importlib.util.spec_from_file_location('qualified_previous_migration',
                                                  tx.fs.root/(directory+'/migration.py').lstrip('/'))
        previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
        previous.BACKUP=directory
        restored=previous.Migration(tx.fs,tx.host,plan=tx.plan if tx.fs.test else None)
    checked=restored.state()
    m.require(checked['status']=='RESTORED' or
              (current and checked['status']=='PREPARED' and 'rearmed_from' in checked),
              'recovery_not_restored')
    restored.validate(checked,'before')
    # Exact tree: no arbitrary extra files may be hidden inside an archived backup.
    files=set(expected)|{'state.json','recovery-policy.pp'}|{r['backup'] for r in checked['files'].values()}
    files|={'recovery/'+p for p in m.recovery.PATHS}
    directories={'','recovery'}|{'recovery'+p for p in m.recovery.DIRECTORIES if p}
    for sub in directories:
        path=directory+('/'+sub if sub else '')
        info=tx.fs.info(path)
        m.require(info and info['mode']==0o700 and info['uid']==tx.fs.uid and
                  info['gid']==tx.fs.gid,'unsafe_recovery_directory')
        fd,_=tx.fs.parent(path+'/entry')
        try:
            prefix=sub+'/' if sub else ''
            wanted={p[len(prefix):].split('/')[0] for p in files|directories
                    if p.startswith(prefix) and p!=sub}
            m.require(set(m.os.listdir(fd))==wanted,'unexpected_recovery_entry')
        finally: m.os.close(fd)
    return checked, m.digest(data)


def rotate(tx, policy):
    m=tx.module_api
    draft,_=tx.before()
    m.require(tx.fs.info(m.BACKUP) is not None,'no_restored_attempt_to_rearm')
    state,sha=saved(tx,m.BACKUP)
    if state['status']=='PREPARED':
        finish(tx,state)
        return 'ALREADY_REARMED'
    archive=m.BACKUP+'.restored-'+sha
    m.require(tx.fs.info(archive) is None,'rearm_archive_collision')
    m.require(tx.fs.info(m.BACKUP+'.pending') is None,'rearm_pending_before_exchange_keep_recovery')
    draft['rearmed_from']=archive
    draft['previous_state_sha256']=sha
    tx.snapshot(draft,policy,publish=False)
    tx.checkpoint('rearm_prepared')
    # Atomic exchange keeps /run/gx's canonical backup present throughout.
    tx.fs.exchange(m.BACKUP,m.BACKUP+'.pending')
    tx.checkpoint('rearm_exchanged')
    finish(tx,draft)
    return 'REARMED_BASELINE_UNCHANGED_PREVIOUS_BACKUP_ARCHIVED'


def finish(tx,state):
    m=tx.module_api
    archive=state['rearmed_from']
    m.require(re.fullmatch('[0-9a-f]{64}',state['previous_state_sha256']) is not None and
              archive==m.BACKUP+'.restored-'+state['previous_state_sha256'],
              'invalid_rearm_archive')
    pending=m.BACKUP+'.pending'
    if tx.fs.info(pending) is not None:
        _,sha=saved(tx,pending)
        m.require(sha==state['previous_state_sha256'],'previous_snapshot_drift')
        m.require(tx.fs.info(archive) is None,'rearm_archive_collision')
        tx.fs.rename(pending,archive)
    _,sha=saved(tx,archive)
    m.require(sha==state['previous_state_sha256'],'rearm_archive_drift')

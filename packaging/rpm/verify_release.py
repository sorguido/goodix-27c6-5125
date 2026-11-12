#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline publication gate for saved GitHub Release metadata and local RPMs.

This checks a candidate, not GitHub reachability or publication. No downloads,
installation, user keyring changes or commands supplied by metadata are allowed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REPOSITORY = 'https://github.com/sorguido/goodix-27c6-5125'
APPROVED_FINGERPRINT = '5FB20F583C831729D5FF073FE99ADAE5B7EA4918'
PUBLIC_KEY = HERE / 'keys/Guido-Soraru.asc'
VERSION = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'
ENV = dict(os.environ, LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
spec = importlib.util.spec_from_file_location('goodix_payload_builder', HERE.parents[1] / 'production/build-public.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def require(value, message):
    if not value:
        raise ValueError(message)


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, env=ENV,
                          capture_output=True, text=True, timeout=60, **kwargs).stdout


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON field')
        result[key] = value
    return result


def release_assets(data, mode):
    """Draft readiness and published metadata have intentionally distinct gates."""
    require(mode in ('draft', 'public'), 'invalid validation mode')
    require(isinstance(data, dict), 'release must be an object')
    require(data.get('draft') is (mode == 'draft'), 'draft/public mode mismatch')
    require(data.get('prerelease') is False, 'prerelease cannot pass this gate')
    tag = data.get('tag_name')
    require(isinstance(tag, str) and len(tag) <= 49
            and re.fullmatch('v' + VERSION, tag), 'missing or invalid stable version tag')
    version = tag[1:]
    # GitHub drafts can retain a temporary URL even when their product tag
    # already exists. Only that exact official-repository token may be reused
    # by the assets; the published-release URL contract remains unchanged.
    download_ref = tag
    if mode == 'draft':
        require(data.get('published_at') is None, 'draft has a publication time')
        url = data.get('html_url')
        temporary = (re.fullmatch(re.escape(REPOSITORY + '/releases/tag/')
                                  + r'(untagged-[0-9a-f]{20})', url)
                     if isinstance(url, str) else None)
        if temporary:
            download_ref = temporary[1]
    require(data.get('html_url') == REPOSITORY + '/releases/tag/' + download_ref,
            'untrusted release URL')
    assets = data.get('assets')
    require(isinstance(assets, list) and len(assets) <= 128, 'invalid asset list')
    names = []
    binaries = []
    for asset in assets:
        require(isinstance(asset, dict) and isinstance(asset.get('name'), str),
                'malformed asset')
        name = asset['name']
        require(name not in names, 'duplicate asset name')
        names.append(name)
        if re.fullmatch(r'goodix-manager-' + re.escape(version)
                        + r'-([1-9][0-9]{0,5})\.fc44\.x86_64\.rpm', name):
            binaries.append(asset)
    require(len(binaries) == 1, 'expected one compatible binary RPM')
    binary = binaries[0]
    source_name = binary['name'].replace('.x86_64.rpm', '.src.rpm')
    sources = [asset for asset in assets if asset['name'] == source_name]
    require(len(sources) == 1, 'missing corresponding SRPM')
    source = sources[0]
    # The gate covers the exact pair being published, not unrelated RPMs.
    require({name for name in names if name.endswith('.rpm')}
            == {binary['name'], source_name}, 'unexpected or inconsistent RPM asset')
    for asset in (binary, source):
        require(asset.get('state') == 'uploaded', 'asset upload incomplete')
        require(type(asset.get('size')) is int and asset['size'] > 0, 'invalid asset size')
        require(isinstance(asset.get('digest'), str)
                and re.fullmatch(r'sha256:[0-9a-f]{64}', asset['digest']),
                'missing or invalid asset SHA-256 digest')
        require(asset.get('browser_download_url') == REPOSITORY + '/releases/download/'
                + download_ref + '/' + asset['name'], 'untrusted download URL')
    revision = binary['name'].removeprefix('goodix-manager-' + version + '-').split('.')[0]
    return version, revision, binary, source


def primary_fingerprint(public_key, gnupghome):
    output = run('gpg', '--homedir', gnupghome, '--batch', '--with-colons',
                 '--show-keys', public_key)
    primary = []
    want = False
    for line in output.splitlines():
        fields = line.split(':')
        if fields[0] == 'pub':
            want = True
        elif fields[0] == 'fpr' and want:
            primary.append(fields[9].upper())
            want = False
    require(primary == [APPROVED_FINGERPRINT], 'certificate is not the approved signing identity')


def verify_header(path, version, revision, source=False):
    fields = ('NAME', 'EPOCHNUM', 'VERSION', 'RELEASE', 'ARCH', 'SOURCERPM', 'SOURCEPACKAGE')
    output = run('rpm', '-qp', '--queryformat', ''.join('%{' + field + '}\n' for field in fields), path)
    expected = ['goodix-manager', '0', version, revision + '.fc44', 'x86_64',
                '(none)' if source else f'goodix-manager-{version}-{revision}.fc44.src.rpm',
                '1' if source else '(none)']
    require(output.splitlines() == expected, 'RPM header does not match release asset identity')


def check_payload_metadata(package, manifest, provenance_bytes, version, revision):
    provenance = json.loads(provenance_bytes, object_pairs_hook=unique_object)
    require(isinstance(package, dict) and type(package.get('schema')) is int and package['schema'] == 1
            and package.get('version') == version
            and type(package.get('release')) is int and package['release'] == int(revision)
            and package.get('fedora') == 44 and package.get('arch') == 'x86_64',
            'package metadata differs from RPM version/release/target')
    source_id = package.get('source_id')
    require(isinstance(source_id, str) and re.fullmatch('[0-9a-f]{64}', source_id),
            'invalid package source identity')
    require(isinstance(provenance, dict) and provenance.get('version') == version
            and provenance.get('source_id') == source_id
            and provenance.get('matcher') == 'chicago-type24', 'payload provenance mismatch')
    require(isinstance(manifest, dict) and type(manifest.get('schema')) is int and manifest['schema'] == 1
            and manifest.get('source_id') == source_id and isinstance(manifest.get('files'), dict)
            and manifest['files'].get('runtime/build-provenance.json')
            == hashlib.sha256(provenance_bytes).hexdigest(), 'payload manifest mismatch')


def verify_payload_metadata(path, version, revision):
    # A fixed extraction boundary; the canonical builder remains the authority
    # for file inventory, hashes, permissions and link targets. Nothing runs.
    files = {'payload.json', 'runtime/libfprint-2.so.2.0.0', 'runtime/ChicagoHS-NOTICES.txt',
             'runtime/LICENSING_AND_PROVENANCE.md', 'runtime/source-files.sha256',
             'runtime/build-provenance.json', 'login/pam_goodix_login_gate.so',
             'login/plasmalogin.pam', 'check-material',
             *(f'runtime/licenses/{name}.txt' for name in builder.LICENSES)}
    links = {'runtime/libfprint-2.so', 'runtime/libfprint-2.so.2'}
    directories = {'', 'runtime', 'runtime/licenses', 'login'}
    base = '/usr/lib/goodix-manager/'
    entries = {}
    output = run('rpm', '-qp', '--queryformat', '[%{FILENAMES}\t%{FILEMODES}\t%{FILELINKTOS}\n]', path)
    for line in output.splitlines():
        fields = line.split('\t')
        require(len(fields) == 3, 'malformed RPM file inventory')
        name, mode, target = fields
        if name == base + 'package.json' or name.startswith(base + 'payload/') or name == base + 'payload':
            require(name not in entries, 'duplicate RPM payload path')
            entries[name] = (int(mode), target)
    require(set(entries) == {base + 'package.json', base + 'payload'}
            | {base + 'payload/' + name for name in files | links | (directories - {''})},
            'incomplete or unexpected RPM payload paths')
    archive = subprocess.run(['rpm2cpio', str(path)], check=True, env=ENV,
                             capture_output=True, timeout=60).stdout
    def read_member(name):
        # Fixed paths, stdout only: no extraction or execution of archive content.
        return subprocess.run(['cpio', '--extract', '--to-stdout', '--quiet',
                               './usr/lib/goodix-manager/' + name], input=archive,
                              check=True, env=ENV, capture_output=True, timeout=60).stdout
    mode, target = entries[base + 'package.json']
    require(stat.S_ISREG(mode) and not target and stat.S_IMODE(mode) == 0o644,
            'invalid package metadata file type/mode')
    package = json.loads(read_member('package.json'), object_pairs_hook=unique_object)
    with tempfile.TemporaryDirectory(prefix='goodix-release-payload-') as temporary:
        payload = Path(temporary).resolve()
        for name in sorted(directories):
            mode, target = entries[base + 'payload' + ('/' + name if name else '')]
            require(stat.S_ISDIR(mode) and not target and stat.S_IMODE(mode) == 0o755,
                    'invalid payload directory type/mode')
            (payload / name).mkdir(exist_ok=True)
        for name in files:
            mode, target = entries[base + 'payload/' + name]
            require(stat.S_ISREG(mode) and not target, 'nonregular payload file')
            destination = payload / name
            destination.write_bytes(read_member('payload/' + name))
            destination.chmod(stat.S_IMODE(mode))
        for name in links:
            mode, target = entries[base + 'payload/' + name]
            require(stat.S_ISLNK(mode) and re.fullmatch('[A-Za-z0-9.-]+', target),
                    'invalid payload symlink')
            (payload / name).symlink_to(target)
        manifest = builder.validate_payload(payload)
        require(hashlib.sha256((payload / 'runtime/source-files.sha256').read_bytes()).hexdigest()
                == manifest['source_id'], 'source inventory does not match source identity')
        check_payload_metadata(package, manifest, (payload / 'runtime/build-provenance.json').read_bytes(),
                               version, revision)


def verify(data, binary, source, mode):
    version, revision, binary_asset, source_asset = release_assets(data, mode)
    with tempfile.TemporaryDirectory(prefix='goodix-release-verify-') as temporary:
        root = Path(temporary)
        snapshot = []
        for path, asset in ((Path(binary), binary_asset), (Path(source), source_asset)):
            require(path.name == asset['name'] and path.is_file() and not path.is_symlink(),
                    'local artifact is not the named regular file')
            # All subsequent checks refer to the same private snapshot bytes.
            target = root / path.name
            shutil.copyfile(path, target)
            require(target.stat().st_size == asset['size'], 'asset size mismatch')
            require('sha256:' + hashlib.sha256(target.read_bytes()).hexdigest() == asset['digest'],
                    'asset SHA-256 mismatch')
            snapshot.append(target)
        gnupghome, database = root / 'gnupg', root / 'rpmdb'
        gnupghome.mkdir(mode=0o700)
        database.mkdir(mode=0o700)
        primary_fingerprint(PUBLIC_KEY, gnupghome)
        options = ('--dbpath', database, '--define', '_keyring rpmdb',
                   '--define', '_pkgverify_level all', '--define', '_pkgverify_flags 0')
        run('rpmkeys', *options, '--import', PUBLIC_KEY)
        require(APPROVED_FINGERPRINT.lower() in run('rpmkeys', *options, '--list').lower(),
                'isolated keyring fingerprint mismatch')
        for path in snapshot:
            run('rpmkeys', *options, '--checksig', '--verbose', path)
        verify_header(snapshot[0], version, revision)
        verify_header(snapshot[1], version, revision, source=True)
        verify_payload_metadata(snapshot[0], version, revision)
    return dict(result='PASS_LOCAL_CONTRACT', mode=mode, version=version,
                release=revision, fingerprint=APPROVED_FINGERPRINT,
                sha256={asset['name']: asset['digest'][7:] for asset in (binary_asset, source_asset)},
                publication='NOT_CHECKED')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True, help='saved GitHub Release JSON')
    parser.add_argument('--binary', type=Path, required=True, help='exact local binary RPM')
    parser.add_argument('--source', type=Path, required=True, help='corresponding local signed SRPM')
    parser.add_argument('--mode', choices=('draft', 'public'), required=True,
                        help='draft readiness or already-public metadata; neither contacts GitHub')
    args = parser.parse_args()
    data = json.loads(args.metadata.read_text(), object_pairs_hook=unique_object)
    print(json.dumps(verify(data, args.binary, args.source, args.mode), indent=2, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f'GOODIX_RELEASE=STOP {error}')

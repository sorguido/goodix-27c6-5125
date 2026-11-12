#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Publication-contract regressions; generated packages/keys are TEST ONLY.

The tiny signed fixture verifies RPM cryptography, not the production payload.
The normal synthetic 3.0.1 build is a separate packaging qualification step.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('release_verifier', HERE / 'verify_release.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
FIXTURE = json.loads((HERE / 'fixtures/release-v3.0.1.json').read_text())


def fixture():
    return copy.deepcopy(FIXTURE)


def payload_metadata():
    identity = hashlib.sha256(b'TEST ONLY source inventory\n').hexdigest()
    package = dict(schema=1, version='3.0.1', release=1, fedora=44, arch='x86_64', source_id=identity)
    provenance = json.dumps(dict(version='3.0.1', matcher='chicago-type24', source_id=identity)).encode()
    manifest = dict(schema=1, source_id=identity,
                    files={name: hashlib.sha256(data).hexdigest() for name, data in payload_contents(provenance).items()},
                    links={'runtime/libfprint-2.so': 'libfprint-2.so.2',
                           'runtime/libfprint-2.so.2': 'libfprint-2.so.2.0.0'})
    return package, manifest, provenance


def payload_contents(provenance):
    names = {'runtime/libfprint-2.so.2.0.0', 'runtime/ChicagoHS-NOTICES.txt',
             'runtime/LICENSING_AND_PROVENANCE.md', 'login/pam_goodix_login_gate.so',
             'login/plasmalogin.pam', 'check-material',
             *(f'runtime/licenses/{name}.txt' for name in v.builder.LICENSES)}
    return {**{name: b'TEST ONLY NEVER PUBLISH inert fixture\n' for name in names},
            'runtime/source-files.sha256': b'TEST ONLY source inventory\n',
            'runtime/build-provenance.json': provenance}


def artifact_metadata(binary, source):
    data = fixture()
    for asset, path in zip(data['assets'], (binary, source)):
        asset['name'] = path.name
        asset['size'] = path.stat().st_size
        asset['digest'] = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        asset['browser_download_url'] = v.REPOSITORY + '/releases/download/v3.0.1/' + path.name
    return data


class Metadata(unittest.TestCase):
    def test_realistic_temporary_draft_urls_are_consistent_and_never_public(self):
        data = fixture()
        data.update(draft=True, published_at=None)
        temporary = 'untagged-9e008443590cf1a75c55'
        data['html_url'] = v.REPOSITORY + '/releases/tag/' + temporary
        for asset in data['assets']:
            asset['browser_download_url'] = v.REPOSITORY + '/releases/download/' + temporary + '/' + asset['name']
        self.assertEqual(v.release_assets(data, 'draft')[:2], ('3.0.1', '1'))
        public = copy.deepcopy(data)
        public['draft'] = False
        with self.assertRaisesRegex(ValueError, 'untrusted release URL'):
            v.release_assets(public, 'public')
        public['html_url'] = FIXTURE['html_url']
        with self.assertRaisesRegex(ValueError, 'untrusted download URL'):
            v.release_assets(public, 'public')
        for field, value in (('published_at', '2026-11-12T12:00:00Z'),
                             ('html_url', None),
                             ('html_url', data['html_url'] + '?redirect=1'),
                             ('html_url', data['html_url'] + '#fragment'),
                             ('html_url', data['html_url'].replace('github.com/', 'github.com.evil.invalid/')),
                             ('html_url', data['html_url'].replace('/sorguido/', '/foreign/')),
                             ('html_url', data['html_url'].replace(temporary, 'untagged-../v3.0.1')),
                             ('html_url', data['html_url'].replace(temporary, 'untagged-%2f' + '0' * 20)),
                             ('html_url', data['html_url'].replace(temporary, 'untagged-' + '0' * 19))):
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(data)
                bad[field] = value
                with self.assertRaises(ValueError):
                    v.release_assets(bad, 'draft')
        for index in (0, 1):
            for url in (data['assets'][index]['browser_download_url'].replace(temporary, 'untagged-' + '0' * 20),
                        data['assets'][index]['browser_download_url'].replace(temporary, 'v3.0.1'),
                        data['assets'][index]['browser_download_url'] + '?redirect=1',
                        data['assets'][index]['browser_download_url'] + '#fragment',
                        data['assets'][index]['browser_download_url'].replace('/download/', '/download/%2f'),
                        data['assets'][index]['browser_download_url'].replace('github.com/', 'evil.invalid/'),
                        data['assets'][index]['browser_download_url'].replace('/sorguido/', '/foreign/')):
                with self.subTest(index=index, url=url):
                    bad = copy.deepcopy(data)
                    bad['assets'][index]['browser_download_url'] = url
                    with self.assertRaises(ValueError):
                        v.release_assets(bad, 'draft')

    def test_draft_readiness_distinct_from_public(self):
        data = fixture()
        self.assertEqual(v.release_assets(data, 'public')[:2], ('3.0.1', '1'))
        with self.assertRaisesRegex(ValueError, 'mode mismatch'):
            v.release_assets(data, 'draft')
        data['draft'] = True
        self.assertEqual(v.release_assets(data, 'draft')[:2], ('3.0.1', '1'))
        with self.assertRaisesRegex(ValueError, 'mode mismatch'):
            v.release_assets(data, 'public')

    def test_invalid_release_metadata(self):
        for field, value in (('draft', 0), ('prerelease', True), ('prerelease', None),
                             ('tag_name', None), ('tag_name', 'main'), ('tag_name', 'v3.0.1-rc1'),
                             ('tag_name', 'v03.0.1'), ('tag_name', 'v3.0.2'),
                             ('html_url', 'https://evil.invalid/releases/tag/v3.0.1')):
            with self.subTest(field=field, value=value):
                data = fixture()
                data[field] = value
                with self.assertRaises(ValueError):
                    v.release_assets(data, 'public')

    def test_missing_binary_source_duplicate_and_incompatible(self):
        for kind in ('src-only', 'no-src', 'duplicate', 'fc45', 'aarch64', 'wrong-version', 'extra-rpm'):
            with self.subTest(kind=kind):
                data = fixture()
                if kind == 'src-only':
                    data['assets'].pop(0)
                elif kind == 'no-src':
                    data['assets'].pop()
                elif kind == 'duplicate':
                    data['assets'].append(copy.deepcopy(data['assets'][0]))
                elif kind == 'fc45':
                    data['assets'][0]['name'] = data['assets'][0]['name'].replace('fc44', 'fc45')
                elif kind == 'aarch64':
                    data['assets'][0]['name'] = data['assets'][0]['name'].replace('x86_64', 'aarch64')
                elif kind == 'wrong-version':
                    data['assets'][0]['name'] = data['assets'][0]['name'].replace('3.0.1', '3.0.2')
                else:
                    data['assets'].append(dict(name='extra.rpm'))
                with self.assertRaises(ValueError):
                    v.release_assets(data, 'public')

    def test_both_assets_require_complete_hash_size_and_official_url(self):
        for index in (0, 1):
            for field, value in (('state', 'new'), ('size', 0), ('size', True),
                                 ('digest', None), ('digest', 'sha1:' + '0' * 40),
                                 ('browser_download_url', 'https://evil.invalid/package.rpm'),
                                 ('browser_download_url', FIXTURE['assets'][index]['browser_download_url'] + '?redirect=1')):
                with self.subTest(index=index, field=field, value=value):
                    data = fixture()
                    data['assets'][index][field] = value
                    with self.assertRaises(ValueError):
                        v.release_assets(data, 'public')

    def test_duplicate_json_fields_refused(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            json.loads('{"draft":true,"draft":false}', object_pairs_hook=v.unique_object)


class PayloadMetadata(unittest.TestCase):
    def test_version_release_and_provenance_consistent(self):
        v.check_payload_metadata(*payload_metadata(), '3.0.1', '1')

    def test_missing_version_or_mismatched_payload_identity_refused(self):
        for target, field, value in (('package', 'schema', True), ('manifest', 'schema', True),
                                      ('package', 'version', None), ('package', 'release', 2),
                                      ('package', 'source_id', '2' * 64), ('package', 'arch', 'aarch64'),
                                      ('provenance', 'version', None), ('provenance', 'version', '3.0.0'),
                                      ('provenance', 'source_id', '2' * 64), ('manifest', 'source_id', '2' * 64),
                                      ('manifest', 'files', {})):
            with self.subTest(target=target, field=field):
                package, manifest, provenance = payload_metadata()
                if target == 'package':
                    package[field] = value
                elif target == 'manifest':
                    manifest[field] = value
                else:
                    document = json.loads(provenance)
                    document[field] = value
                    provenance = json.dumps(document).encode()
                with self.assertRaises(ValueError):
                    v.check_payload_metadata(package, manifest, provenance, '3.0.1', '1')


@unittest.skipUnless(all(shutil.which(tool) for tool in ('rpmbuild', 'rpmsign', 'rpmkeys', 'rpm2cpio', 'cpio', 'gpg')),
                     'RPM build/sign tools and GnuPG are required for signature integration')
class Signatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generated private test keys never leave the repository's ignored area.
        private = ROOT / 'development/rpm'
        subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', str(private / 'fixture-key')], check=True)
        private.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='TEST-ONLY-release-contract-', dir=private)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.home = cls.root / 'gnupg'
        cls.home.mkdir(mode=0o700)
        cls.env = dict(os.environ, LC_ALL='C', GNUPGHOME=str(cls.home))
        cls.command('gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '',
                '--quick-generate-key', 'Goodix TEST ONLY NEVER PUBLISH', 'rsa2048', 'sign', '1d')
        cls.addClassCleanup(cls.command, 'gpgconf', '--kill', 'gpg-agent')
        output = cls.command('gpg', '--batch', '--with-colons', '--list-keys')
        cls.fingerprint = next(line.split(':')[9] for line in output.splitlines() if line.startswith('fpr:'))
        cls.public = cls.root / 'fixture-public.asc'
        cls.public.write_text(cls.command('gpg', '--batch', '--armor', '--export', cls.fingerprint))
        cls.binary, cls.source = cls.build_fixture()
        cls.unsigned = cls.root / 'unsigned'
        cls.unsigned.mkdir()
        for path in (cls.binary, cls.source):
            shutil.copyfile(path, cls.unsigned / path.name)
            cls.command('rpmsign', '--define', '_openpgp_sign gpg', '--key-id', cls.fingerprint, '--addsign', path)

    @classmethod
    def build_fixture(cls, revision=1, variant=None):
        top = cls.root / f'rpmbuild-{revision}'
        for name in ('BUILD', 'BUILDROOT', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS'):
            (top / name).mkdir(parents=True)
        package, manifest, provenance = payload_metadata()
        package['release'] = revision
        payload = top / 'fixture-payload'
        payload.mkdir(mode=0o755)
        for name, data in payload_contents(provenance).items():
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o755 if name in v.builder.EXECUTABLES else 0o644)
        for name, target in manifest['links'].items():
            (payload / name).symlink_to(target)
        if variant == 'missing-driver':
            (payload / 'runtime/libfprint-2.so.2.0.0').unlink()
        elif variant == 'wrong-hash':
            (payload / 'login/pam_goodix_login_gate.so').write_bytes(b'changed bytes')
        elif variant == 'schema-bool':
            manifest['schema'] = True
        elif variant == 'wrong-source-id':
            package['source_id'] = manifest['source_id'] = '9' * 64
        (payload / 'payload.json').write_text(json.dumps(manifest))
        with tarfile.open(top / 'SOURCES/payload.tar', 'w') as archive:
            archive.add(payload, arcname='payload')
        (top / 'SOURCES/package.json').write_text(json.dumps(package))
        specification = top / 'SPECS/fixture.spec'
        specification.write_text('''%global __os_install_post %{nil}
%global debug_package %{nil}
Name: goodix-manager
Version: 3.0.1
Release: @REVISION@.fc44
Summary: TEST ONLY NEVER PUBLISH signature fixture
License: GPL-2.0-or-later
Source0: payload.tar
Source1: package.json
%description
TEST ONLY NEVER PUBLISH: not the Goodix driver or Manager.
%install
mkdir -p %{buildroot}/usr/share/goodix-contract-fixture
printf 'TEST ONLY NEVER PUBLISH\\n' > %{buildroot}/usr/share/goodix-contract-fixture/marker
mkdir -p %{buildroot}/usr/lib/goodix-manager
tar -xf %{SOURCE0} -C %{buildroot}/usr/lib/goodix-manager
cp %{SOURCE1} %{buildroot}/usr/lib/goodix-manager/package.json
%files
/usr/share/goodix-contract-fixture/marker
/usr/lib/goodix-manager/
'''.replace('@REVISION@', str(revision)))
        cls.command('rpmbuild', '-ba', '--define', f'_topdir {top}', specification)
        return next((top / 'RPMS').rglob('*.rpm')), next((top / 'SRPMS').glob('*.rpm'))

    @classmethod
    def command(cls, *args):
        return subprocess.run([str(arg) for arg in args], env=cls.env, check=True,
                              text=True, capture_output=True, timeout=90).stdout

    def trusted(self):
        # Test-only injection at the trust boundary; no production CLI override.
        return patch.multiple(v, APPROVED_FINGERPRINT=self.fingerprint, PUBLIC_KEY=self.public)

    def test_signed_pair_passes_and_does_not_attest_publication(self):
        with self.trusted():
            result = v.verify(artifact_metadata(self.binary, self.source), self.binary, self.source, 'public')
        self.assertEqual(result['result'], 'PASS_LOCAL_CONTRACT')
        self.assertEqual(result['publication'], 'NOT_CHECKED')
        self.assertEqual(result['fingerprint'], self.fingerprint)

    def test_signed_incomplete_corrupt_or_bad_schema_payload_refused(self):
        for revision, variant in enumerate(('missing-driver', 'wrong-hash', 'schema-bool', 'wrong-source-id'), 2):
            with self.subTest(variant=variant):
                binary, source = self.build_fixture(revision, variant)
                for path in (binary, source):
                    self.command('rpmsign', '--define', '_openpgp_sign gpg', '--key-id', self.fingerprint, '--addsign', path)
                with self.trusted(), self.assertRaises((RuntimeError, ValueError)):
                    v.verify(artifact_metadata(binary, source), binary, source, 'public')

    def test_unsigned_binary_or_source_refused(self):
        for binary, source in ((self.unsigned / self.binary.name, self.source),
                               (self.binary, self.unsigned / self.source.name)):
            with self.subTest(unsigned=binary.parent == self.unsigned), self.trusted():
                with self.assertRaises(subprocess.CalledProcessError):
                    v.verify(artifact_metadata(binary, source), binary, source, 'public')

    def test_fixture_signature_not_accepted_by_production_trust(self):
        with self.assertRaises(subprocess.CalledProcessError):
            v.verify(artifact_metadata(self.binary, self.source), self.binary, self.source, 'public')

    def test_wrong_certificate_refused_before_rpm_verification(self):
        with patch.object(v, 'PUBLIC_KEY', self.public):
            with self.assertRaisesRegex(ValueError, 'approved signing identity'):
                v.verify(artifact_metadata(self.binary, self.source), self.binary, self.source, 'public')

    def test_hash_and_size_mismatch(self):
        for index in (0, 1):
            for field, value in (('digest', 'sha256:' + '0' * 64), ('size', 1)):
                with self.subTest(index=index, field=field):
                    data = artifact_metadata(self.binary, self.source)
                    data['assets'][index][field] = value
                    with self.assertRaisesRegex(ValueError, 'mismatch'):
                        v.verify(data, self.binary, self.source, 'public')

    def test_signed_rpm_cannot_be_renamed_as_another_version(self):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            paths = []
            data = artifact_metadata(self.binary, self.source)
            data['tag_name'] = 'v3.0.2'
            data['html_url'] = data['html_url'].replace('v3.0.1', 'v3.0.2')
            for asset, original in zip(data['assets'], (self.binary, self.source)):
                asset['name'] = asset['name'].replace('3.0.1', '3.0.2')
                asset['browser_download_url'] = asset['browser_download_url'].replace('3.0.1', '3.0.2')
                target = Path(temporary) / asset['name']
                shutil.copyfile(original, target)
                paths.append(target)
            with self.trusted(), self.assertRaisesRegex(ValueError, 'RPM header'):
                v.verify(data, *paths, 'public')


if __name__ == '__main__':
    unittest.main()

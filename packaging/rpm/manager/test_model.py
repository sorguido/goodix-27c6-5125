"""Offline tests: no GUI, network, device access or privilege escalation."""
import copy
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from model import REPOSITORY, LocalPackage, NoCompatibleRelease, Release, Status, version_tuple


def status(**changes):
    data = {'schema': 1, 'state': 'installed', 'runtime_version': '3.0.0',
            'payload_version': '3.1.0', 'package_version': '3.1.0-1.fc44',
            'sensor_present': False, 'message_code': 'ready'}
    data.update(changes)
    if 'payload_version' in changes and 'package_version' not in changes:
        data['package_version'] = changes['payload_version'] + '-1.fc44'
    return Status.parse(data)


def release(version='3.2.0', revision=1):
    tag = 'v' + version
    name = f'goodix-manager-{version}-{revision}.fc44.x86_64.rpm'
    return {'draft': False, 'prerelease': False, 'tag_name': tag,
            'html_url': REPOSITORY + '/releases/tag/' + tag,
            'assets': [{'name': name, 'state': 'uploaded', 'size': 123456,
                        'browser_download_url': REPOSITORY + '/releases/download/' + tag + '/' + name}]}


class StateTests(unittest.TestCase):
    def test_semver_numeric_not_lexical(self):
        self.assertGreater(version_tuple('3.10.0'), version_tuple('3.9.0'))
        for item in ['v3.0.0', '3.0', '03.0.0', '3.0.0-rc1', None, '3.0.0\n']:
            with self.assertRaises(ValueError):
                version_tuple(item)

    def test_install_update_current_and_downgrade(self):
        self.assertEqual(status(state='absent', runtime_version=None).action, 'install')
        self.assertEqual(status().action, 'update')
        self.assertEqual(status(runtime_version='3.1.0').action, '')
        self.assertEqual(status(runtime_version='3.2.0').action, '')
        self.assertEqual(status(state='blocked').action, '')
        self.assertEqual(status(state='legacy', runtime_version='2.0.0').action, '')

    def test_recognized_legacy_upgrade_requires_explicit_backend_code(self):
        legacy = status(state='legacy', runtime_version=None,
                        message_code='legacy_upgrade_available', enrollment_required=True)
        self.assertEqual(legacy.action, 'update')
        self.assertIsNone(legacy.runtime_version)
        self.assertEqual(status(state='legacy', runtime_version=None,
                                message_code='legacy_upgrade_available').action, '')

    def test_inconsistent_status_fails_closed(self):
        for change in [{'state': 'absent'}, {'state': 'installed', 'runtime_version': None},
                       {'schema': 2}, {'runtime_version': '3.0.0-rc1'}, {'sensor_present': 'yes'},
                       {'enrollment_required': 'no'}, {'package_version': '../../x'}]:
            with self.assertRaises(ValueError):
                status(**change)

    def test_packaging_revision_does_not_offer_driver_update(self):
        for revision in (5, 6):
            current = status(runtime_version='3.0.0', payload_version='3.0.0',
                             package_version=f'3.0.0-{revision}.fc44')
            self.assertEqual(current.action, '')
            self.assertEqual(current.title, 'Up to date')

    def test_unknown_legacy_version_is_not_invented(self):
        legacy = status(state='legacy', runtime_version=None, message_code='legacy_unqualified')
        self.assertEqual(legacy.action, '')
        self.assertIsNone(legacy.runtime_version)

    def test_untrusted_package_can_only_report_blocked(self):
        item = status(state='blocked', runtime_version=None, payload_version='', package_version='', result='blocked')
        self.assertEqual(item.action, '')
        with self.assertRaises(ValueError):
            status(state='absent', runtime_version=None, payload_version='', package_version='', result='success')

    def test_diagnostics_allowlist(self):
        clean = status(psk='do-not-export', stdout='secret', message_code='unexpected secret')
        self.assertNotIn('secret', clean.diagnostic())
        self.assertNotIn('psk', clean.diagnostic())
        self.assertEqual(clean.message_code, 'ready')


class ReleaseTests(unittest.TestCase):
    def test_300_discovers_portable_301_and_301_discovers_next_release(self):
        old = LocalPackage('3.0.0', 13)
        candidate = Release.parse(release('3.0.1'))
        self.assertTrue(candidate.newer_than(old))
        current = LocalPackage('3.0.1', 1)
        self.assertFalse(candidate.newer_than(current))
        self.assertTrue(Release.parse(release('3.0.2')).newer_than(current))
        # Updating the RPM does not implicitly update the installed runtime.
        pending = status(payload_version='3.0.1', runtime_version='3.0.0')
        self.assertEqual(pending.action, 'update')
        self.assertEqual(LocalPackage.from_status(pending), current)

    def test_compatible_download_and_numeric_ordering(self):
        parsed = Release.parse(release())
        self.assertTrue(parsed.newer_than(LocalPackage.from_status(status())))
        self.assertTrue(parsed.newer_than(LocalPackage.from_status(status(runtime_version='3.3.0'))))
        self.assertFalse(parsed.newer_than(LocalPackage.from_status(status(payload_version='3.10.0'))))
        self.assertTrue(Release.parse(release('3.1.0', 2)).newer_than(LocalPackage.from_status(status())))
        self.assertFalse(Release.parse(release('3.1.0', 1)).newer_than(LocalPackage.from_status(status())))

    def test_discovery_independent_of_runtime_identity(self):
        candidate = Release.parse(release())
        for change in ({'state': 'absent', 'runtime_version': None},
                       {'state': 'legacy', 'runtime_version': None},
                       {'state': 'blocked', 'runtime_version': None, 'message_code': 'version_unknown'},
                       {'state': 'blocked', 'message_code': 'source_mismatch'}):
            self.assertTrue(candidate.newer_than(LocalPackage.from_status(status(**change))))

    def test_no_compatible_distinct_from_invalid_response(self):
        for change in ({'draft': True}, {'prerelease': True}, {'assets': []}):
            item = release()
            item.update(change)
            with self.assertRaises(NoCompatibleRelease):
                Release.parse(item)
        with self.assertRaises(ValueError) as error:
            Release.parse({'draft': 'false'})
        self.assertNotIsInstance(error.exception, NoCompatibleRelease)

    def test_only_stable_releases(self):
        for change in [{'draft': True}, {'prerelease': True}, {'draft': None},
                       {'tag_name': 'v3.2.0-rc1'}, {'html_url': 'https://evil.test/release'},
                       {'assets': []}, {'message': 'API rate limit exceeded', 'tag_name': None}]:
            item = release()
            item.update(change)
            with self.assertRaises(ValueError):
                Release.parse(item)

    def test_download_rejects_wrong_platform_and_untrusted_urls(self):
        for change in [{'name': 'goodix-manager-3.2.0-1.fc45.x86_64.rpm'},
                       {'name': 'goodix-manager-3.2.0-1.fc44.aarch64.rpm'},
                       {'state': 'new'}, {'size': 0}, {'size': True},
                       {'browser_download_url': 'https://evil.test/payload.rpm'},
                       {'browser_download_url': REPOSITORY + '/releases/download/v3.2.0/../payload.rpm'}]:
            item = release()
            item['assets'][0].update(change)
            with self.assertRaises(ValueError):
                Release.parse(item)

    def test_ambiguous_asset_rejected(self):
        item = release()
        item['assets'].append(copy.deepcopy(item['assets'][0]))
        with self.assertRaises(ValueError):
            Release.parse(item)

    def test_highest_packaging_revision_selected(self):
        item = release()
        item['assets'] += release(revision=2)['assets']
        self.assertEqual(Release.parse(item).packaging_release, 2)


if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact D293 development-reader manifest conversion. Pure bytes, no file I/O."""
import hashlib
import json

LEGACY_SHA256 = '1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15'
LEGACY_SIZE = 2305
LOADER_COMMIT = 'e61fce313794922a2dab156a1b38a8ddc5837f19'
# Not present in D232 JSON. These are the existing acceptance pins in the
# above commit's target_material.c / runtime_inputs.c, not newly sampled data.
TRANSPORT_SHA256 = 'eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75'
FDT_SHA256 = '9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2'


def convert(original):
    if (len(original) != LEGACY_SIZE or
            hashlib.sha256(original).hexdigest() != LEGACY_SHA256):
        raise ValueError('legacy_manifest_drift')
    old = json.loads(original)
    result = {
        'schema': 'goodix-5125-device-materials-v1',
        'vid': old['target']['vid'].removeprefix('0x'),
        'pid': old['target']['pid'].removeprefix('0x'),
        'app': old['target']['app'],
        'transport_sha256': TRANSPORT_SHA256,
        'config90_sha256': old['config90']['body_sha256'],
        'fdt_cache_sha256': FDT_SHA256,
        'a2_response_sha256': old['a2']['response_body_sha256'],
        'chip82_response_sha256': old['chip82']['response_body_sha256'],
        'otp_a6_response_sha256': old['otp_a6']['response_body_sha256'],
    }
    return (json.dumps(result, sort_keys=True, indent=2) + '\n').encode('ascii')

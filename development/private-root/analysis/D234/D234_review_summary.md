# D234 review summary

`D234_DECISION=D234_BLOCKED_BY_UNSEAL_SCOPE_EXPANSION`

The D234 operator risk acceptance was present, but the source gate did not pass.
`d233_offline_entrypoint()` is capability-only and rejects every attempted live
selection. `run_production_candidate_offline()` is not a live entrypoint: it
requires injected preflight, material/secret loaders, backend factory and two
publishers, and it hard-codes the D233 offline schema and authorization state.

Changing `_d233_usb_source_seal()` alone would only expose low-level libusb
methods to an ad-hoc caller. A correct live path would require substantive new
orchestration, operational path resolution and D234 report mapping. That exceeds
the sole minimal unseal patch authorized by D234 section 4.

No source unseal was applied. No root session, protected secret/config load,
libusb initialization, USB open, command, E4, TLS handshake, fprintd mutation or
recovery occurred. Offline regression ran 40 tests successfully. The canonical
`gfusb.dll` and D232 target-material manifest hashes matched their pinned values.
The udev rule remained absent.

Although the live run never started, the final D234 rule consumes the
single-shot authorization on any terminal result. D234 authorizes no attempt
after this decision. Any future live execution requires a separately reviewed
expanded implementation and a new explicit human authorization.

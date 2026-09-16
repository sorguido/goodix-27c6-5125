# D235 independent production-entrypoint review

## Verdict

`INDEPENDENT_REVIEW=pass`

The D235 layer is composition, not a second implementation. It imports the
D232 protected loaders and exact core and the D233 preflight, binder, transport,
TLS/B0 stack and orchestrator. The D232 core SHA-256 remains
`f2ace73461cb9f7d4499ed21cc724cd2331c933ff49a25f22b14b8d91faf8ef1`.
The only D233 behavioral additions are report observability and stricter file
metadata: attempted phase, failure domain, canonical-PE non-symlink enforcement,
and root-owned mode-0700 report-directory enforcement.

## Adversarial findings closed

- Production paths are fixed, absolute and independent of `HOME`; no fallback
  or generic secret-store scan exists.
- The future selector reads exact sysfs metadata and rejects zero or multiple
  targets before any device open. Bus, address and nonempty port path are bound
  to the exact `/dev/bus/usb` character node and later revalidated by transport.
- Root protected loaders retain lstat/open/fstat TOCTOU protection, exact owner,
  mode and length gates. Providers enforce one material load and one PSK load.
- Canonical `gfusb.dll` is regular, non-symlink, hash/pattern-gated and parsed as
  data only. The D190 binder derives at E4 and the same `SecretBuffer` object is
  passed to the one-shot TLS engine.
- The mapper uses the D233 abort class plus attempted phase and backend failure
  domain. USB, E4, both A2 calls, chip ID, OTP, 0x70, DAC, config90, D1, TLS,
  preflight, protected input and internal failures have deterministic families.
- Cleanup and zeroization precede the durable checkpoint; fprintd and signals
  restore afterward; the final report follows. Checkpoint, restore, final
  publication and signal failures were falsified independently.
- No retry loop, alternate PSK, replacement path, D4/E0/A4/F0/F4 builder,
  application-data phase or automatic invasive recovery is present.

## Hard-disable assessment

`main()` reaches `_d235_source_seal()` before sysfs, protected stores, fprintd,
libusb construction or reports. Arguments/config/backend selectors cannot pass
the seal and environment is not consulted for enablement. The D233 seal remains
in every real libusb ABI method. Normal, direct-import and `python -m` calls,
`--live`, `--force`, unexpected argv, environment/config/backend attempts all
report USB init/open zero.

The injected offline review function is not a runtime unseal: it requires all
sensitive/report paths under a caller-supplied temporary root and rejects the
shipped `SystemOsFacade`, `LibusbSystemApi` and root protected provider. Its USB
traffic is an in-memory fake. The provided real libusb class remains sealed even
under direct import.

## Residual D236 boundary

D235 does not verify that future root-provisioned files currently exist or have
the contract metadata, and does not enumerate the actual target. Those are D236
preflight facts, deliberately untouched here. D236 requires a small reviewed
source patch spanning the D235 and D233 seals plus compile-time authorization,
then a fresh human risk acceptance. Runtime flags are not an alternative.

No hardware, sudo, udev, real protected input, real fprintd operation or live TLS
was used in this review.

# D232 independent implementation review

## Review posture and scope

This second pass treated the D232 implementation as unsafe until each reachable
path was falsified. It reviewed the sealed-candidate source, tests, synthetic
fixture, exact replay contract and target manifest; it did not execute hardware,
USB, libusb, sudo, fprintd operations or the real secret loader.

## Findings

1. **Live reachability — pass.** `D232_LIVE_CAPABILITY` is the literal zero.
   There is no USB/live backend, import, device path or live entrypoint. CLI and
   environment attempts unconditionally fail before constructing a backend.
   The state machine accepts only the exact synthetic class (not subclasses).
2. **Wire allowlist — pass.** The only state-machine requests are
   E4/A2/82/A6/A2/70/80/80/80/80/90/D1. A2, 70 and the pre-OR D1 checksum have
   golden vectors. D4 is rejected; E0/A4/F0/F4/IAP/ClearApp do not appear as
   reachable operations.
3. **Order/retry — pass.** One tuple defines the phase order. Every response is
   checked before the next exchange. Timeout, ambiguity, extra, reordered and
   duplicate/retry attempts terminate; no loop repeats a phase and the
   application retry count is zero.
4. **Target material — pass.** The published manifest pins only non-secret
   hashes/metadata obtained from the provenance-valid local target capture.
   Protected consumption rejects symlink/owner/mode/schema/manifest hash/config
   length/hash/finalizer/DAC order/correlation failures. Raw target 0x90 bytes
   are absent from source and bundle.
5. **PSK boundary — pass.** Root loader checks regular file, exact owner/mode,
   inode stability, no-follow and exact 32-byte length. There is no fallback or
   provisioning. The owned buffer is wiped on pass/failure; reports omit it.
6. **TLS gate — pass offline.** A B0 record is accepted only after D1 and every
   pre-D1 phase. The parser pins TLS 1.2 ClientHello and sole suite 0x00a8; the
   synthetic backend pins `Client_identity`. Bad Record MAC, alert and timeout
   are terminal. No real TLS claim is made.
7. **Report/cleanup — pass.** Accepted-backend success and every tested failure
   enter one `finally`, call cleanup once, zeroize the secret and atomically
   publish one mode-0600 redacted JSON result. Protected-input failures also
   publish before commands. A rejected foreign backend is never invoked and
   therefore has no acquired resource to clean.
8. **Race/signal — pass for D232 scope.** The code is synchronous and starts no
   thread/process. Future live gates are pure validation of a supplied snapshot;
   D232 performs no system scan. The snapshot requires signal blocking, report
   readiness and restore plan before transport could be authorized.
9. **Provenance/clean-room — pass.** No external GPL code was copied. Rockytkg
   is not used as material. The first capture is explicitly recorded as
   definitively lost; packet-level coverage is one recovered capture.

## Recovery review

The implementation stops new commands, preserves the report and performs only
accepted-backend cleanup. It contains no reboot, power-cycle, Windows check,
SWD/JTAG or automatic invasive recovery. R4–R7 remain human/out-of-workflow
steps. `automatic_reset=forbidden` in every phase.

## Residual limits (not defects in D232)

- D232 proves behavior only against synthetic oracles and performs no live TLS.
- Python in-place overwrite is testable but is not a compiler-level guarantee
  against every historical memory copy.
- OS integration for USB ownership, fprintd, signals and restore remains work
  for a separately reviewed D233 patch; D232 only validates the evidence model.
- Device-resident no-NVM side effect remains unproven and packet coverage is
  corpus-bounded because the first capture is lost.

No blocking implementation defect or hidden live-enablement path was found.
Independent review result: **PASS** for offline readiness only. Human risk
acceptance remains `not_granted`; live authorization remains `no`.


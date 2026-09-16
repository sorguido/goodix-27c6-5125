# D235 production entrypoint gap inventory

D234 correctly found that neutralizing the D233 libusb seal alone would expose
methods but would not construct a production run. D235 closes only that
composition gap. No protocol, KDF, TLS, B0, serializer, response validator or
state-machine behavior is reimplemented.

| Dependency | Current injection source in D233 | Future production source | Validation gate | Cleanup owner | Failure behavior |
| --- | --- | --- | --- | --- | --- |
| Runtime paths | Test temporary directory | `ProductionRuntimePaths.system_default()` | Absolute, unique, fixed parent relationships, no `HOME` | Entrypoint | Preflight/internal terminal before USB |
| Operator identity | `FakeOsFacade` values | EUID plus `SUDO_UID` from `SystemOsFacade` | EUID 0 and decimal SUDO UID equality | Preflight transaction | `D236_BLOCKED_BY_PREFLIGHT` |
| USB target | Injected `UsbIdentity` | Exact sysfs selector for one `27c6:5125` | Unique VID/PID, bus/address, nonempty port path, exact character node | Transport after future open | `D236_BLOCKED_BY_PREFLIGHT` before open |
| Holder path | Temporary injected path | `/dev/bus/usb/BBB/DDD` from the exact selector | Identity/path correlation | Preflight transaction | Preflight terminal; no input load/open |
| fprintd state | `FakeOsFacade` | `systemctl is-active/stop/start` via `SystemOsFacade` | Initial state captured and exactly restored | `ProductionOsPreflight` | Internal terminal; restore still attempted |
| Signal mask | Fake token | `pthread_sigmask` | Blocked before backend; saved mask required | `ProductionOsPreflight` | Internal terminal; restore still attempted |
| Single-use marker | Temporary fixture | `/var/lib/goodix-5125-poc/d236-live-single-use.marker` | Absolute, O_EXCL, mode 0600 | Preflight/governance; never removed for reuse | Preflight terminal |
| PSK | Synthetic mode-0600 fixture | `/var/lib/goodix-5125-poc/transport-material.bin` | Regular, root-owned, 0600, non-symlink, exactly 32 bytes, one load | `SecretBuffer` and TLS engine | Protected-input terminal; zeroize if loaded |
| Target manifest | Synthetic protected JSON | `/var/lib/goodix-5125-poc/target-material-manifest.json` | Regular, root-owned, 0600, non-symlink, pinned D232 hash/schema | Immutable `TargetMaterial` | Protected-input terminal |
| Config 0x90 | Synthetic 224-byte fixture | `/var/lib/goodix-5125-poc/target-config-90.bin` | Regular, root-owned, 0600, non-symlink, length/hash/finalizer/DAC | Immutable `TargetMaterial` | Protected-input terminal |
| Canonical PE | Injected canonical path | Repository-fixed D230 `gfusb.dll` | Regular non-symlink, canonical SHA-256 and unique patterns | Binder zeroizes extracted seeds | Protected-input terminal |
| D190 binder | Injected factory | `RuntimePskE4Binder.from_canonical_pe()` | Same-run derivation and constant-time E4 comparison | Binder/secret owners | E4 terminal before A2 |
| USB API | `FakeUsbApi` | `LibusbSystemApi` | D233 source seal; exact target/interface/endpoints | `ProductionUsbTransport.cleanup()` | USB terminal; exactly-once cleanup |
| TLS/B0 | Immediate or negative fake engine | `Tls12PskServer` plus existing `B0TlsBridge` | TLS 1.2, 0x00a8, identity, one handshake | TLS engine then backend | TLS terminal; no application data |
| Exact replay | D232 shared core | Same `_run_exact_oem_core` through D233 orchestrator | Immutable phase order and forbidden-control gates | D233 orchestrator | First error stops; no retry |
| Reports | Temporary delegates | Fixed checkpoint/final paths under root-owned 0700 directory | Atomic 0600, non-symlink final path, mapper is total | D232 publisher/D233 orchestrator | Checkpoint survives restore failure |
| Result mapping | Absent in D233 entrypoint | `map_future_live_decision()` | Attempted phase plus backend failure domain and abort class | D235 mapped publisher | One D236 terminal family |

The remaining D236 change is not runtime configuration. It must be a small,
reviewed source patch covering both source seals and compile-time authorization
declarations after a new human risk decision.

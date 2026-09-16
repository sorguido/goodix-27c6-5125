# D238 operator-kit review

Reviewed script: `operator_kit/d238-live-pre-d1-tls-once.sh`.

The script was syntax-checked and its unseal patch was dry-run against the
sealed D238 sources. It was not executed. No command in this review initialized
libusb, selected or opened `/dev/bus/usb`, read the root transport store, ran a
TLS handshake with the sensor, stopped fprintd or used sudo.

## Gates and lifecycle

1. Requires the exact repository cwd, EUID 0 from a manual `sudo` launch,
   non-root `SUDO_UID` and the literal authorization argument.
2. Verifies hashes of both sealed source files and the reviewed unseal patch.
3. Verifies both source seals are active.
4. Runs `analysis/D236/d236_preflight.py` before unseal; checks its durable JSON
   reports no libusb init/open and confirms the 88-byte store contract.
5. Refuses an existing D238 operator-consumption marker.
6. Backs up both sealed sources with ownership/mode preserved and installs only
   `analysis/D238/D238_live_unseal.patch`.
7. Claims a second, never-automatically-removed authorization marker before the
   single Python entrypoint invocation. This consumes authorization even if the
   process crashes before the application marker is claimed.
8. Invokes the live entrypoint exactly once. It never loops or retries.
9. Reseals source explicitly after the invocation and again through an
   idempotent exit/signal trap; restored hashes must match.
10. Preserves the redacted stdout result, returns the live exit status, and uses
    dedicated nonzero codes for argument, preflight, hash, marker, patch and
    reseal failures.

Production paths now use `/var/lib/goodix-5125-poc/d238-results/` and
`d238-live-single-use.marker`. The root preflight requires those report paths
to be ready and the final path absent before any USB operation. The Python
orchestrator publishes a pre-restore checkpoint, restores the prior fprintd and
signal state, zeroizes the secret, then publishes the final report.

The operator marker and application single-use marker are deliberately not
removed. A second invocation requires a new risk review/authorization and a
manual, separately reviewed reset of those gates; the script never performs
that reset.

Offline review result: **PASS**.

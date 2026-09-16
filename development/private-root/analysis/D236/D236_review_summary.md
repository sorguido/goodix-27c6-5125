# D236 review summary

`D236_DECISION=D236_BLOCKED_BY_PREFLIGHT`

The renewed operator risk acceptance was present. The D236 source diff passed
review: it temporarily activated the two compile-time seals and D236 policy,
normalized the production schema/mode, and changed exit status to depend on the
terminal decision. It added no protocol, builder, backend, state-machine,
runtime enablement, retry or recovery logic. Fourteen focused offline tests
passed before the root gate.

The authorized root preflight command used `sudo -n` so credentials could never
be requested, captured or exposed. Local sudo had no cached authentication and
returned `a password is required`; Python did not start. Therefore protected
stores, sysfs target selection, fprintd, signal masks and libusb were never
reached. Target enumeration, USB init/open/claim, commands, E4 and TLS are zero.

Because no live run started, the live authorization was not consumed. The
terminal result nevertheless closes D236 and authorizes no retry. Both D233 and
D235 source seals and their non-authorized compile-time declarations were
restored immediately; the safe decision-based exit-code correction remains.

Any future live attempt requires a new step, review, explicit authorization and
a separately established authenticated root session. D236 must not be rerun.

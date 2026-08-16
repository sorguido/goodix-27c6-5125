# D190 local binding reference

Recovered from the local D190 Codex session transcript and hardened with the
bounded parser changes recorded in D191. The API accepts a 32-byte secret and a
local canonical, SHA-256-gated `gfusb.dll`. It parses the PE strictly as data,
requires the unique target instruction pattern, derives OEM material only in
memory, returns only validator[32], and overwrites mutable intermediates on the
ordinary and exceptional paths.

There is no PE execution, loader, cache, DPAPI, USB, TLS, device, persistence,
fallback, alternate family, or real-export mode. The canonical PE and its raw
seeds are deliberately not part of this directory or the closure bundle.

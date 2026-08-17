# D233 binding-reference material policy

Policy: `LOCAL_VOLATILE_DERIVATION_HASH_ONLY`.

- Only a local PE with exact SHA-256
  `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
  is accepted.
- The DLL is read as bytes. No entrypoint, Wine, `rundll32`, Windows loader or
  executable mapping is used.
- The exact PE identity pins the target loader-zero mode and branch-B producer;
  there is no alternate mode/family branch in the API.
- The parser accepts bounded PE headers/sections, fixed target RVAs and one
  unique producer instruction pattern; missing, ambiguous or out-of-range data
  is terminal.
- The two seed values are returned only as mutable process-local buffers and are
  overwritten after preflight or derivation.
- Producer halves, producer key, SP800-108 out48 and envelope are mutable where
  practical and overwritten on ordinary and exceptional exit.
- No seed, producer key, derived48 or raw envelope is logged or persisted. No
  raw OEM static material or PE is included in source or bundle.
- The API returns only mutable validator[32]; the binder overwrites it after
  constant-time comparison.
- There is no cache, DPAPI, USB, device, TLS, export, fallback, random or
  alternate-device mode in the reference.

Python and crypto-library internals can create transient immutable copies, so
this is an honest volatile best-effort policy, not a claim of guaranteed
cryptographic erasure of every runtime copy.

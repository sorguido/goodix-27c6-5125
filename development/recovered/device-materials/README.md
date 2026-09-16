# Recovered device-material utilities

This directory is a private archival recovery. It is intentionally below the
ignored `red_tag/` boundary and is not part of the publishable source surface.
None of the files contains the target secret or protected OEM payload bytes.

## Origin

The sources were reconstructed by replaying, in order, the file patches
recorded in the local Codex session transcript:

```text
/home/guido/.codex/sessions/2026/07/29/
rollout-2026-07-29T07-43-40-019fac66-698c-7362-9b50-96b4bc1bb1a6.jsonl
```

Original workspace paths:

```text
poc/goodix5125/windows/Export-Goodix5125TransportMaterial.ps1
poc/goodix5125/tools/transfer_record.py
poc/goodix5125/tools/finalize_transfer.py
```

Recovered SHA-256 digests:

```text
677fde5622df4a2446a07e7103ad14ce1be98b011274618807edf5c682da0936  Export-Goodix5125TransportMaterial.ps1
81602216891602f6a9a8d722f36937ea4bf0007786ff0d9eecf3102119f2d8d3  transfer_record.py
df562fe6b2bb26a99c35343908f65e154beb14880397389c49adba2037461bc0  finalize_transfer.py
```

The two Python digests are also present in the historical session evidence.
The PowerShell digest represents the deterministic result of replaying the
complete final hardening patch sequence from that transcript.

## Status and dependency boundary

The PowerShell exporter is the recovered final Windows implementation. The
record module and finalizer are the recovered Linux implementation used by the
historical transfer procedure.

Do not copy the finalizer into the current public tree and assume it is
standalone. It imports the historical `bind` API and the historical importer
binary. The current retained binding reference exposes a later API shape, and
the current managed importer accepts the complete five-file material set
rather than this staging record. A future distribution of these tools needs a
focused compatibility and licensing review; it must not silently alter the
recovered semantics.

No live export was performed during this recovery review. Any new DPAPI
unprotect operation, Windows/USB interaction, or handling of the real transfer
record remains an explicit operator-controlled action.


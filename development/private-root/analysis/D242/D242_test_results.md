# D242 — test and executable closure results

## Results

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
Ran 104 tests in 1.724s
OK

./operator_kit/d242-live-tls-once.sh --offline-dry-run
D242_PHASE=EXECUTABLE_CLOSURE
D242_RESULT=PASS
D242_FAILURE_CLASS=none
```

Both commands ran without root, secret access, sensor access or real USB/TLS.
The closure uses only synthetic peers and temporary directories.

## Mandatory coverage map

| Requirement | Dynamic coverage |
| --- | --- |
| operator-visible preflight failure | `test_launcher_renders_specific_redacted_preflight_failure_before_live`; same launcher prints `OPERATOR_IDENTITY`, failures, marker and zero/not-started counters |
| missing/invalid preflight report | `test_launcher_classifies_missing_and_invalid_preflight_reports`; distinct `PREFLIGHT_REPORT_MISSING` and `PREFLIGHT_REPORT_INVALID` |
| no generic-only preflight terminal | observability test rejects `D242_FAILURE_CLASS=PREFLIGHT_FAILED` and requires the concrete class/list |
| failure path before live | fixture proves sealed source bytes unchanged, marker absent, USB/command/secret/fprintd/live-marker counters zero |
| historical D241 artifact immutability | `test_historical_d241_dependencies_are_byte_exact_and_fully_pinned`; operator hash `0bf09214…944f` |
| D241 preflight dependency integrity | same test and launcher pre-import gate; preflight hash `6cc7ddd6…cf7` |
| closure dependency completeness | closure `d241_dependency_integrity`: behavior-relevant 2, pinned 2, unpinned 0 |
| D242-local fixed64 fixture compatibility | closure success uses `D242LoopbackTlsUsbApi` with canonical unchanged D241 fixture |
| common A0 fixed64 scope | `test_a0_declared_frame_checksum_and_response_semantics_survive_fixed64` and 48-frame D175 A0 census |
| D241 first B0 exactly once | `test_t1_direct_b0_is_handed_to_bridge_once_with_exact_payload`, `test_t3_first_record_is_not_read_again_or_fed_twice` |
| 47-byte ClientHello fixture | `test_primary_capture_metadata_fixture_is_stable_and_redacted`, `test_d239_52_is_the_complete_tls_record_and_d241_47_its_payload` |
| canonical historical server flight | `test_primary_capture_metadata_fixture_is_stable_and_redacted` |
| historical B0 grouping | `test_server_flight_keeps_one_tls_record_per_b0_and_paces_each` plus closure two-B0 assertion |
| historical USB segmentation | `test_transport_zero_pads_every_final_out_to_oem_packet_size` plus closure `64:3` assertion |
| partial USB completion | `test_partial_padded_out_is_ambiguous_and_fails_closed` |
| malformed B0 fail-closed | `test_t4_malformed_b0_and_tls_record_remain_terminal` |
| timeout after server flight | `test_t12_timeout_is_bounded_classified_and_trace_is_redacted` plus closure timeout fixture |
| OpenSSL fatal classification | `test_alert_and_malformed_record_are_terminal`, `test_corrupted_encrypted_finished_is_bad_record_mac` |
| no D4 | `test_d4_and_reordering_are_not_representable`, closure `d4_count=0` |
| no application data | `test_t7_t8_forbidden_counts_cleanup_and_zeroization_remain_invariant`, closure count 0 |
| no persistent write | same invariant test and closure count 0 |
| retry zero | bounded timeout test and closure `retry_count=0` |
| cleanup/zeroization exactly once | invariant test and both closure fixtures |
| D242 marker namespace | `test_marker_namespace_is_new_and_historical_markers_are_benign` |
| seal/unseal coherence | `test_seal_unseal_round_trip_is_coherent` and closure patch round trip |
| result-directory lifecycle | `test_result_directory_lifecycle_is_strict_and_preflight_is_offline` |
| redaction schema | primary fixture, D241 timeout trace and D242 closure redaction assertions |
| executable closure end to end | `test_executable_closure_end_to_end_is_redacted_and_has_no_live_io` and the real launcher dry-run |

```text
D242_D241_HISTORICAL_ARTIFACT_RESTORED=true
D242_D241_BEHAVIOR_RELEVANT_DEPENDENCY_COUNT=2
D242_D241_PINNED_DEPENDENCY_COUNT=2
D242_UNPINNED_CLOSURE_DEPENDENCY_COUNT=0
D242_FIXED64_SCOPE=OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED
D242_OPERATOR_FAILURE_OBSERVABILITY=PASS
D242_GENERIC_PREFLIGHT_FAILURE_ONLY=FORBIDDEN
D242_REAL_USB_ACCESS_DURING_CODEX=0
D242_REAL_TLS_HANDSHAKE_DURING_CODEX=0
```

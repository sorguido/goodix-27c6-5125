# D272/01 — Corrective: exact ACK status, fail-closed

`OFFLINE_ONLY`. Nessun USB reale, nessun secret, nessun fprintd, nessuna
acquisizione biometrica, nessun `sudo`, nessuna installazione di dipendenze.

## 1. Baseline

| Campo | Valore |
| --- | --- |
| `GIT_ROOT` | `/home/guido/Repository/goodix-27c6-5125_private` |
| Branch | `development` |
| `STARTING_HEAD` | `8d016e2de476d910b358249e0cd1c255121d5ad2` |
| D272 parent | `fdc52d04995d65d1e2a895a373e1fe7e24e6fa9f` |
| `D272_BASELINE_ANCESTOR_CHECK` | `PASS` (`git merge-base --is-ancestor` verso HEAD) |
| Worktree iniziale | `CLEAN` |
| Bundle storico D272/01 | SHA-256 verificato invariato `4397d00e…87a7b5` |

Il bundle storico e il suo sidecar **non** sono stati modificati né rigenerati.

## 2. Difetto corretto

`core/multiframe_validation.py`, metodo condiviso `_command_ack()`:

```python
# prima (permissivo, non allineato all'evidenza)
if ack.control != control or ack.status not in (0x01, 0x07):

# dopo (esatto, fail-closed)
if ack.control != control or ack.status != EXPECTED_ACK_STATUS:
```

con la costante esplicita:

```python
EXPECTED_ACK_STATUS = 0x01
```

Il contratto D272 dichiarava già in
`analysis/D272/D272_01_multiframe_contract.json`:
`mandatory exact ACK; no optional/permissive fallback`. L'implementazione era
quindi più permissiva del proprio contratto e dell'evidenza target.

Risultato ora garantito:

```text
ACK_ECHO must equal expected control
ACK_STATUS must equal 0x01 exactly
otherwise -> fail closed, nessun comando successivo emesso
```

Nessuna tabella di status multiple, nessun fallback, nessun retry, nessun
recovery introdotti.

## 3. Verifica evidence-to-code

Fonte: `analysis/D263/D263_01_post_arm_order.json`.

Classificazione: **target-specific primary evidence**. La capture primaria
`analysis/D230/work/GoodixExport/rilevamento.pcapng` è hash-gated
(`50071c0f…c184b`, `hash_gate: PASS`) sul firmware `GF_ST411SEC_APP_12509`.
Indici packet zero-based.

| Control | Target ACK observed | Packet | Corrective policy |
| --- | --- | --- | --- |
| `0x34` | `0x01` | 235 (`ctl 0xb0`, body `3401`) | exact `0x01` |
| `0x20` | `0x01` | 241 (`ctl 0xb0`, body `2001`) | exact `0x01` |
| `0x50` | `0x01` | 247 (`ctl 0xb0`, body `5001`) | exact `0x01` |
| `0x32` | `0x01` | 253 (`3201`); pre-first-image 223 `ack_status 0x01` | exact `0x01` |
| `0x22` | `0x01` | 229 (`ack_status 0x01`) | exact `0x01` |

Nessun comportamento non osservato è stato promosso. `0x07` non appare in alcun
ACK del ciclo post-arm.

## 4. Perché i parser globali non sono stati toccati

La differenza rispetto al resto del codice è **intenzionale**, non un difetto
residuo:

- `core/cold_start.py` → `ALLOWED_ACK_STATUSES = frozenset((0x01, 0x07))`
- `core/post_d4.py` → `parse_ack()` accetta `(0x01, 0x07)`

`0x07` è realmente **target-osservato live** nelle fasi di bring-up pre-TLS:
`analysis/D241/D241_operator_live_stdout.json` riporta `ack_status 0x07` per
`E4`, `A2_1`, `CHIP_82`, `OTP_A6`, `A2_2`, `MODE_70`, `DAC_*` e `CONFIG_90`.
Restringere quei parser a `0x01` sarebbe una regressione contro evidenza live.

Il difetto era la **propagazione** di quel set permissivo nel nuovo seam D272,
dove `0x07` non è mai stato osservato. Il corrective è quindi strettamente
locale al seam D272, come richiesto.

## 5. Test

`tests/test_d272_multiframe_validation.py`, 11 test, `OK`.

Copertura parametrizzata/strutturale aggiunta:

| Test | Verifica |
| --- | --- |
| `test_expected_ack_status_is_exactly_0x01` | la costante di policy è `0x01` |
| `test_every_cycle_ack_accepts_only_status_0x01` | 5 control × 7 status (`0x00,0x02,0x03,0x07,0x10,0x81,0xFF`) = 35 casi fail-closed, con asserzione che **nessun comando** è emesso dopo l'ACK rifiutato |
| `test_every_cycle_ack_passes_on_status_0x01` | i 5 stessi stage continuano ad accettare `0x01` |
| `test_wrong_echo_is_rejected_even_with_status_0x01` | echo control errato resta rifiutato |
| `test_ack_policy_has_no_permissive_membership_test` | guardia strutturale: `_command_ack` usa `EXPECTED_ACK_STATUS`, non contiene `0x07` né test di appartenenza |

Il happy path completo D272 (`test_exact_bounded_order_and_terminal_last_image`)
continua a passare con l'ordine invariato `0x34, 0x20, 0x50, 0x32, 0x22` × 2.

### Mutation check

La policy permissiva è stata reintrodotta **solo in memoria** (nessun file
modificato) per provare la sensibilità del test:
`test_every_cycle_ack_accepts_only_status_0x01` fallisce con 5 failure, una per
ciascuno stage ACK (`0x34, 0x20, 0x50, 0x32, 0x22`) con `status=0x07`.
`MUTATION_DETECTED = True`. La copertura dimostra quindi inequivocabilmente che
nessun ACK D272 può accettare `0x07`.

## 6. Executable closure correttiva

| Verifica | Esito |
| --- | --- |
| `tests.test_d272_multiframe_validation` da Git root | `PASS` (11) |
| Regressione pertinente D260/D263/D266/D267/D268/D272 da Git root | `PASS` (121) |
| Suite D272 (multiframe + privacy + operator kit) da cwd esterno `/tmp/kilo/d272_ext` con `PYTHONPATH` | `PASS` (17) |
| `tools/d272_sigfm_validation.py --dry-run` da Git root e da cwd esterno | `PASS`, exit 0, contatori zero |
| `tools/d272_sigfm_validation.py --future-live` | fail-closed, exit 1, `D272_OPERATOR_DRY_RUN=NOT_RUN` |
| `git diff --check` | clean |

Nota di igiene: la suite `test_d260_persistent_runtime` riscrive come effetto
collaterale preesistente tre artefatti storici in `analysis/D260/`
(`D260_architecture_critical_fileset.json`, `D260_bundle_manifest.json`,
`D260_end_to_end_rehearsal.json`), per drift di schema dovuto a step successivi.
Il drift non è correlato a questo corrective ed è stato **ripristinato a HEAD**;
la worktree finale contiene solo i file in scope. Comportamento segnalato, non
modificato qui.

Le sole anomalie residue della suite completa sono preesistenti e ambientali,
non correlate a questo corrective:

- `test_d264_03_prelive_operator`, `test_d265_live_first_image_once`:
  `ModuleNotFoundError: No module named 'pytest'`;
- `test_d261_operational_readiness`: `known_live_io_capability_required`
  (capability live-IO assente in contesto offline).

Nessuna di esse importa `core/multiframe_validation`.

## 7. Stato D272 che NON cambia

Il corrective non maschera alcun blocker primario:

```text
OUTCOME_D272_PRIMARY=BLOCKED_POST_FIRST_IMAGE_UP_TABLE_SECOND_CYCLE_AND_OPENCV4_DEV
D272_PRIMARY_EXECUTABLE_CLOSURE=FAIL
POST_FIRST_IMAGE_0X34_STATUS=OBSERVED_PAYLOAD_UP_TABLE_PROVENANCE_AND_FRESHNESS_UNKNOWN
FINGER_UP_IRQ_0200_STATUS=OBSERVED_AFTER_0X34_ACK_TARGET_TIMEOUT_UNKNOWN
POST_FINGER_UP_0X20_STATUS=OBSERVED_WITH_ACK_AND_B0_SEMANTICS_NOT_QUALITY_PROVEN
REARM_0X32_STATUS=OBSERVED_WITH_ACK_SECOND_CYCLE_COMPLETION_NOT_OBSERVED
REAL_SIGFM_BUILD=BLOCKED_OPENCV4_DEV_UNAVAILABLE
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
```

Invariati: ordine `0x34 → IRQ0200 → 0x20 → image → 0x50 → response → 0x32`,
mapping D269, SIGFM metric seam, privacy contract, timeout candidate, semantica
tabelle up/down, dipendenza OpenCV, live flags, stato live-disabled
dell'Operator Kit.

## 8. Closure del corrective

```text
ACK_POLICY_CORRECTIVE=PASS
ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
ACK_0X07_ACCEPTED=false
CORRECTIVE_EXECUTABLE_CLOSURE=PASS
```

`CORRECTIVE_EXECUTABLE_CLOSURE=PASS` vale esclusivamente per la policy ACK e
**non** promuove `D272_PRIMARY_EXECUTABLE_CLOSURE`, che resta `FAIL`.

Il prossimo boundary resta invariato:

```text
NEXT_PRIMARY_BOUNDARY=POST_FIRST_IMAGE_MULTIFRAME_CONTRACT_CLOSURE_AND_REAL_SIGFM_BUILD
NEXT_BOUNDARY_PREREQUISITE=TARGET_CLOSE_0X34_UP_TABLE_AND_SECOND_CYCLE_PLUS_EXISTING_OPENCV4_DEV_ENVIRONMENT
```

## 9. Documentazione canonica

`Goodix 27c6 5125 manuale tecnico.md` è stato aggiornato organicamente, non in
append: sintesi di stato corrente, blocco canonico alto, riga roadmap D272/01,
tabella lifecycle post-first-image (riga ACK `B0/34/01`), nuova sottosezione
"Policy ACK esatta del ciclo multi-frame (corrective post-review AI-PM)" e
blocco canonico della sezione D272/01, con
`D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01` e la nota esplicita che il
precedente `0x01|0x07` è stato corretto dopo review AI-PM.

## 10. Git

Nessun commit, push, merge, rebase, reset, amend, creazione o switch di branch,
nessun history rewrite. Worktree lasciata pronta per review Utente/AI-PM con le
sole modifiche in scope.

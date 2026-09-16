# D279/39 — quality-map NBIS correct-role e operator boundary

## Obiettivo

D279/39 prepara il più piccolo esperimento ancora discriminante dopo il
corrective D279/38. Sulle stesse nove varianti D279/37 misura se le minutiae
sono sostenute dai tier nativi della quality-map NBIS e separabili dai falsi
positivi della baseline. Non introduce matching, fusion primary/auxiliary,
accumulo multi-frame o modifica production.

I ruoli applicativi sono ora fissati dal metadata audit:

```text
baseline,(primary,auxiliary)*21
```

## Metriche e limite di interpretazione

Il helper C test-only chiama l'esatto `get_minutiae()` Fedora 44/libfprint
1.94.100 dopo il resize pixman bilineare pinned. Per ogni frame mantiene in
memoria e restituisce alla pipe:

- numero totale di minutiae;
- numero con reliability almeno 0,25 e almeno 0,50;
- istogramma dei cinque livelli della quality-map;
- dimensioni della mappa.

L'evaluator deriva conteggi e proporzioni intere A/B e conserva soltanto
`frames_nonzero`, minimo, mediana e massimo per ciascun ruolo e variante. Non
persiste valori per-frame, quality-map, raster o template.

Il path resta esattamente a `ppmm=0`, come la produzione corrente. In NBIS ciò
riduce la componente grayscale della reliability a zero: le soglie 0,25/0,50
riflettono quindi rispettivamente i tier B/A e A della quality-map, non una
reliability fisicamente calibrata. D279/39 non assegna un `ppmm` inventato e
non usa la reliability come prova autonoma di matchabilità.

## Implementazione e closure offline

`test-goodix-nbis-resize-quality-pipe` è `install:false`, accetta soltanto
frame 80×64/64×80 via stdin e fattori 1..3. Non contiene path capture/secret,
entry point driver o API USB. I buffer immagine C e Python owned vengono
azzerati; le copie interne del runtime restano fuori dal claim.

Il build isolato usa la stessa SDK Flatpak 25.08, libfprint 1.94.100 e pixman
0.46.4 pinned di D279/37. Build normale e ASan/UBSan passano; l'integrazione
Python→pipe verifica dimensioni, somma dell'istogramma, ordinamento delle
soglie e zero-frame. Il preflight completo del kit passa 27 test Python e
ricostruisce con successo il helper da snapshot, senza rete.

## Review live-critical

- nessun file del driver Goodix production è modificato;
- il nuovo target è test-only e non installato;
- nessuna seam/iniezione host-only del test è referenziata dal percorso USB
  production e la scansione sorgente/binario esclude open/enumerate/claim;
- i timeout della pipe sono solo safety bound del processo host offline e non
  implicano timeout o quiescenza device-side;
- sender e allowlist delle famiglie persistenti restano invariati; la loro
  assenza è un guardrail e non prova assenza di altra persistenza sensor-side;
- il kit non avvia fprintd e non enumera, apre o raggiunge USB.

## Operator boundary e Human Gate

Il kit è in:

```text
operator_kit/d279-39-offline-protected-nbis-quality/
```

Preflight e costruzione da snapshot sono offline. La sola modalità
`--run-approved-analysis` richiede un nuovo grant single-use distinto da
D279/35 e D279/37, lo consuma prima di leggere il transport e permette una
sola decrittazione in-memory dei raster ATTEMPT02. Il solo output ammesso è
`summary.json` aggregate-only validato fail-closed.

L'eventuale autorizzazione deve nominare il full SHA pubblicato e precisamente:

```text
D279_39_ONE_OFFLINE_PROTECTED_NBIS_QUALITY_EVALUATION
```

Esclude USB/live, sensore, retry, seconda lettura, modifica/copia del transport,
persistenza di raster/quality-map/template, matching e modifica production.

## Closure

```text
OUTCOME=READY_FOR_HUMAN_GATE_ONE_OFFLINE_PROTECTED_NBIS_QUALITY_EVALUATION
ADVANCEMENT=NEW_BIOMETRIC_DISCRIMINATOR_AND_OPERATOR_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=PASS_OFFLINE_ONLY
D279_39_PYTHON_PREFLIGHT_TESTS=27/27_PASS
D279_39_EXACT_TARGET_LIBFPRINT=1.94.100
D279_39_PINNED_PIXMAN=0.46.4
D279_39_NORMAL_AND_ASAN_UBSAN=PASS
D279_39_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
TARGET_ROLE_ORDER=baseline,(primary,auxiliary)*21
TARGET_PSK_ACCESSED_BY_AI=false
REAL_RASTER_EVALUATED_COUNT=0
LIVE_OR_USB_ACTION_COUNT_BY_AI=0
D279_35_AUTHORIZATION_CONSUMED=true
D279_37_AUTHORIZATION_CONSUMED=true
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
RESIDUAL_BLOCKER_OR_RISK=EXPLICIT_FULL_SHA_HUMAN_APPROVAL_FOR_ONE_PROTECTED_OFFLINE_READ
CANONICAL_DOCUMENTATION=GOODIX_MANUAL_D279_39
REVIEW_SET=GIT_NATIVE
```

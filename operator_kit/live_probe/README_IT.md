# Live Probe Harness riutilizzabile

Questo è il percorso predefinito per nuovi probe live factory-preserving che
rientrano nella stessa threat model. Centralizza orchestrazione e safety; ogni
esperimento conserva soltanto il delta tecnico. Non sostituisce il Human Gate:
Codex verifica tutto offline e si ferma, mentre l'operatore avvia manualmente
un payload live già chiuso.

```text
COMMON_HARNESS stabile + SMALL_EXPERIMENT_PAYLOAD = NUOVO_TEST_LIVE
```

## Interfaccia minima

Ogni directory `experiments/<id>/` contiene `experiment.conf`, un payload
eseguibile e, solo se necessari, sanitizer, pre/post audit, cleanup e
classificatore locali. Il config dichiara obbligatoriamente obiettivo, action,
budget, timeout, requisiti di privilegio/sessione, telemetria attesa e stop
conditions. È un file di assegnazioni shell versionato e sottoposto a review,
non una DSL o un plugin system.

Il common harness:

- per `--operator-run` impone branch `development`, HEAD uguale a
  `origin/development` e critical set pulito;
- rifiuta un esperimento non esplicitamente `LIVE_CAPABLE=true`;
- presenta scopo, budget e stop conditions e richiede la conferma dichiarata;
- invoca il payload una sola volta, passandogli esplicitamente max action,
  contatti, retry zero e timeout;
- non effettua retry e usa un timeout bounded con propagazione dei segnali;
- conserva stdout/stderr di payload e audit solo dopo il sanitizer, oppure richiede la
  dichiarazione esplicita che l'output è già sanitizzato;
- esegue sempre cleanup e post-audit, poi valida telemetria, classificatori,
  summary e `capture.sha256`;
- può delimitare e raccogliere journal per cursor/units/grep senza
  materializzare un journal globale raw.

Se il pre-audit fallisce, il payload non parte e il summary conserva sia il
return code sia `LIVE_PROBE_PRIMARY_FAILURE=PRE_AUDIT`. Se il cursor journal
non è disponibile, la raccolta non viene invocata con un cursor vuoto: il
capture registra `JOURNAL_COLLECTION=NOT_APPLICABLE_NO_CURSOR`. Un fallimento
di acquisizione cursor successivo a un pre-audit valido è distinto come
`FAIL_JOURNAL_CURSOR`. Questi percorsi sono sicuri anche con `set -u`.

Il payload deve imporre tecnicamente i budget ricevuti prima di qualsiasi
azione sensor-reaching e deve gestire nel proprio failure/signal path gli
obblighi device-specific di release/reseal. Il common classifier richiede
budget handoff coerente, zero famiglie persistenti note, outstanding zero,
drained e context closed. Questi controlli non rendono sicuro un payload non
revisionato: payload, hook e classifier fanno parte del live-critical set.

## Comandi

Fixture offline, eseguibile anche da cwd diverso:

```bash
operator_kit/live_probe/run.sh offline-reference --offline-test
```

Un futuro esperimento live viene provato offline solo se dichiara e implementa
`OFFLINE_TEST_CAPABLE=true`, quindi viene avviato live esclusivamente
dall'operatore:

```bash
operator_kit/live_probe/run.sh <experiment-id> --operator-run
```

La fixture `offline-reference` è `LIVE_CAPABLE=false`: il secondo comando
viene rifiutato. Non usarla come pretesto per una live di validazione del
refactoring.

## Test policy

- `PAYLOAD_ONLY_CHANGE`: test locali del payload + compatibility test del
  common harness;
- `COMMON_HARNESS_CHANGE`: intera suite `tests/test_live_probe_harness.py`;
- milestone o pre-live ad alto rischio: regressione completa pertinente,
  inclusi i safety-critical test del percorso riusato.

Un nuovo esperimento non modifica normalmente `run.sh`, `safety.sh`,
`capture.sh` o `classify_common.sh`. Se il boundary non è compatibile con
questo contratto o richiede un profilo di rischio diverso, si documenta il
motivo e si prepara un kit autonomo. `NEW_EXPERIMENT != NEW_OPERATOR_FRAMEWORK`.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — prima invocazione operatore fermata dal pre-audit e correttivo

## Evidenza autentica

L'operatore ha invocato manualmente il common harness sulla baseline completa
`1a8c5528a0b9f9d12c395f1a9804ee82fd076b94`. La capture sanitizzata è:

```text
captures/live_probe/d290-plasmalogin_20260912T142615Z_1a8c5528a0b9/sanitized/
```

`sha256sum -c capture.sha256` verifica tutti i sette file elencati; il digest
del manifest è
`c3d9491f74ceddba1c7a4d3fc2d8c8364dd9578bbca811b4820ce8dd8cd42715`.
I marker primari sono:

```text
D290_TARGET_VERSIONS_AND_HASHES=PASS
D290_PRE_AUDIT=FAIL
D290_AUDIT_FAILURE=INITIAL_GRAPHICAL_SESSION_CARDINALITY_NOT_ONE
LIVE_PROBE_RESULT=FAIL_PRE_AUDIT
LIVE_PROBE_PRIMARY_FAILURE=PRE_AUDIT
LIVE_PROBE_PAYLOAD_STARTED=false
LIVE_PROBE_PAYLOAD_RETURN_CODE=125
LIVE_PROBE_JOURNAL_COLLECTION=NOT_APPLICABLE_NO_CURSOR
LIVE_PROBE_POST_AUDIT_RETURN_CODE=0
D290_POST_AUDIT=PASS
D290_POST_AUDIT_SENSOR_ACTION_COUNT=0
D290_PLASMALOGIN_PAM_MOUNTPOINT=false
D290_RUNTIME_PRESENT=false
D290_TARGET_SYSFS_CARDINALITY=1
D290_CLEANUP=PASS
D290_ROOT_OVERLAY_RESIDUAL=false
```

Il classifier payload della baseline restituiva `2` e lasciava il proprio file
vuoto perché cercava artefatti che non possono esistere quando il payload non è
partito. È un difetto diagnostico secondario; il common harness ha preservato
correttamente `PRE_AUDIT` come causa primaria.

Il control-flow e gli artefatti provano che non sono stati acquisiti cursor,
conferma operatore o payload: logout, overlay PAM, `pam_fprintd`, VERIFY e
azioni sensor-reaching non sono iniziati. Non esistono telemetria, payload log,
journal diagnostico o nuova evidenza device-side.

```text
D290_01_FIRST_OPERATOR_RUN=ABORTED_PRE_AUDIT
D290_01_FIRST_OPERATOR_BASELINE=1a8c5528a0b9f9d12c395f1a9804ee82fd076b94
D290_01_LOGOUT_STARTED=false
D290_01_PAM_OVERLAY_STARTED=false
D290_01_PAM_FPRINTD_STARTED=false
D290_01_VERIFY_STARTED=false
D290_01_SENSOR_ACTION_COUNT=0
D290_01_PHYSICAL_CONTACTS_CONSUMED=0
D290_01_NEW_DEVICE_SIDE_EVIDENCE=false
```

## Root cause

Dalla stessa TTY 3 la fotografia logind mostrava tre record: sessione `2`
dell'utente su `tty2`, class `user`; sessione `3`, class `manager`; sessione
`4` dello stesso utente su `tty3`, class `user`. Il pre-audit richiedeva però
che la sessione Wayland iniziale fosse anche `State=active`. Dopo il passaggio
alla TTY 3, lo stato foreground può migrare dalla sessione grafica alla TTY
senza che il desktop su tty2 cessi di esistere o di essere loggato. Una lettura
read-only successiva ha osservato il duale (`tty2=active`, `tty3=online`),
confermando che `State` non è un'identità stabile della sessione.

La sessione grafica iniziale è ora definita univocamente da UID operatore,
ID diverso dalla TTY 3, `Class=user`, `Type=wayland`,
`Service=plasmalogin`, `TTY=tty2` e stato loggato `active|online`. La sessione
`manager` è esclusa. La nuova sessione post-MATCH usa un predicato distinto:
stessa identità Plasma/Wayland utente, TTY grafica, stato loggato e ID diverso
sia dalla TTY operatore sia dall'ID iniziale già osservato scomparire al logout.

## Correttivo e verifica

`session-model.sh`, locale al payload D290, è condiviso da audit e payload ma
espone funzioni separate per sessione iniziale e nuova sessione. Il pre-audit
stampa sempre count, ID, TTY, service, type, class e state prima del gate di
cardinalità. Il classifier riconosce esplicitamente
`D290_PRE_AUDIT=FAIL` quando payload log e telemetria sono assenti, emette
`NOT_APPLICABLE_PRE_AUDIT_FAILURE` e non tenta di leggere artefatti live.

La matrice comprende il caso osservato, assenza tty2, doppio candidato,
manager+TTY3, ogni proprietà identitaria errata, creazione di un nuovo ID dopo
MATCH, assenza di sessione dopo NO_MATCH e un run common-harness sintetico con
pre-audit fallito. Quest'ultimo chiude con causa primaria pulita
`FAIL_PRE_AUDIT`, payload non avviato, classifier rc 0 e nessun errore file.

```text
D290_TESTS=23/23_PASS
D290_COMMON_HARNESS_CHANGED=false
D290_TARGET_SESSION_MODEL_READ_ONLY=PASS
LIVE_OR_PRIVILEGED_ACTION_EXECUTED_BY_AI=false
USB_OR_SENSOR_ACTION_EXECUTED_BY_AI=false
OUTCOME=READY_FOR_HUMAN_GATE_AFTER_LOCAL_CORRECTIVE
```

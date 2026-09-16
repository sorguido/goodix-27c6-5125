<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D288/01 — review AI PM del payload KScreenLocker

```text
PM_DECISION=HUMAN_REQUIRED
OUTCOME=READY_FOR_ONE_MANUAL_BOUNDED_KSCREENLOCKER_SERIES
EXECUTABLE_CLOSURE=PASS_OFFLINE
LIVE_EXECUTION_PERFORMED=false
```

La review ha riesaminato direttamente common harness, config, shim C/version
script, smoke runner, payload, sanitizer, audit, cleanup, classifier,
istruzioni, manuale e test. Il payload non duplica il framework storico D287:
riusa gate, capture, timeout, segnali, journal finale, summary/hash e
classificazione comune e conserva localmente soltanto lifecycle del greeter e
classificazione per-attempt.

Finding chiusi durante la review:

1. il primo payload live richiedeva offline compatibility test e cleanup
   multi-context; il common harness è stato esteso minimalmente e sottoposto a
   full regression;
2. i critical path con spazi erano inizialmente espressi come stringa; ora sono
   un array Bash preservato come pathspec singolo e una fixture Git ne prova il
   rifiuto dirty;
3. il primo smoke runner restituiva `PAM_CONV_ERR`; una conversation bounded
   con risposte vuote chiude il percorso reale a `0/0/0` senza credenziali;
4. preflight live ora rifiuta un greeter preesistente e cardinalità sysfs target
   diversa da uno prima del root audit o della conferma del contatto.

Non restano difetti offline noti. La verifica residua è intrinsecamente live:
UI KScreenLocker, chiamata PAM reale, una eventuale serie di massimo tre
VERIFY/contatti e propagazione del MATCH. È il Human Gate concreto; l'AI non
esegue `--operator-run`, `pkexec`, greeter, pam_fprintd, fprintd, USB o sensore.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Provenance D282/01 privileged staging probe

- baseline: `3d42daec016d1a2c3292ac35374ae117ef8d1611`;
- operation: `D282_01_PRIVILEGED_SYSTEMD_SELINUX_STAGING_PROBE`;
- result originale: `/var/tmp/goodix-d282-01-staging-probe-results/20260910T143838Z-3d42daec016d`;
- run: privileged host, Fedora 44, SELinux Enforcing, autorizzata ed eseguita
  dall'operatore il 10 settembre 2026;
- import: blocco `summary.env` sanitizzato fornito integralmente
  dall'operatore nel prompt di handoff, preservato come transcript verbatim;
- SHA-256 del file importato:
  `988f992039b6cee1d0dcc64aef4bc53775f6fb5617ec1ec6ce7a93ac558e49ef`.

Il raw originale e `operator.log` sono `0600` sotto una directory non leggibile
senza privilegi. Non sono stati letti o copiati e non viene dichiarata
byte-identità tra il transcript importato e il raw root-only. Nessun contenuto
di `private/`, dato biometrico o materiale protetto è stato importato.

La directory `/run/goodix-d282-01` osservata dopo la run è una directory padre
vuota: è classificata come residuo di housekeeping non bloccante. La lettura
manuale successiva `inactive/dead` non invalida il rollback `active → active`
registrato dal cleanup: il sorgente Fedora canonico arma un timeout quando il
daemon non è occupato e termina con status zero; `--no-timeout` disabilita
esplicitamente questo comportamento.

<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D296/01 — qualificazione release Phase E

Data: 15 settembre 2026

## Esito

La release candidate source-first identificata dal commit
`3feabcfb7918375ce0e04def0605c2389f95d932` supera la qualificazione Phase E
per il solo target iniziale dichiarato: Fedora 44 KDE x86_64 con Goodix USB
`27c6:5125` / APP12509. Il digest dell'indice `SHA256SUMS` della candidate è
`151e0092ddbc1e4751628c1e338efbf29259f3ce9fd79d093f1630f30f5f0584`.

Questo documento conserva la provenance tecnica della review; il manuale
tecnico resta la fonte narrativa canonica dello stato e dei claim.

## Matrice e criteri verificati

| Confine | Evidenza | Esito |
|---|---|---|
| source-of-truth | rigenerazione patch, digest source/build-support, 30 TU, 32 header, 15 path downstream | PASS |
| build | due build pulite, non privilegiate e senza rete condivisa | PASS |
| riproducibilità | candidate byte-identiche; stesso digest `SHA256SUMS` | PASS |
| runtime binary | SHA-256 `115db4450272435c80ecb61e3540577b99c8355fb02a0f1648175104a7c3dd20` in entrambe le build | PASS |
| ABI e leakage | ABI libfprint 2.0.0, nessun RPATH/RUNPATH, nessun simbolo host/test-only o path `/home`/`/tmp` | PASS |
| installer | 12 test offline: install/update/rollback/uninstall, drift/tamper/collision fail-closed, metadata release e material separation | PASS |
| lifecycle reale | evidenze D293–D295 e Phase D già chiuse, senza riaprire boundary live | PASS nello scope osservato |
| integrità candidate | allowlist esatta di 22 file e verifica completa di `SHA256SUMS` | PASS |
| SBOM | SPDX 2.3 JSON deterministico: 38 package, 20 file, 58 relazioni | PASS |

La baseline di compatibilità qualificata è Fedora Linux 44 KDE x86_64 con
libfprint `1.94.100-1.fc44`, fprintd/fprintd-pam `1.94.5-5.fc44`, libgusb
`0.4.9-5.fc44`, OpenSSL `1:3.5.8-1.fc44`, GLib `2.88.3-1.fc44`, OpenCV
`4.13.0-1.fc44`, Plasma Login Manager `6.7.5-1.fc44`, PAM `1.7.2-2.fc44`,
systemd `259.8-1.fc44` e SELinux policy `44.8-1.fc44`. La build usa
Freedesktop SDK 25.08.16, commit
`b90ed309cc1d505dea48b6a2121c5dcfac22868120eee643b0596d31f96b9bb8`.
Altre versioni Fedora, distribuzioni, desktop, architetture, sensori e firmware
sono `NOT_YET_CLAIMED`, non dichiarati incompatibili.

## Threat/privacy review

Gli asset rilevanti sono materiali protetti per-device, template biometrici
gestiti da fprintd, autenticazione host e stato factory del sensore. I boundary
sono build non privilegiata, import amministrativo separato, transazione root,
runtime fprintd/sensore ed eventuale futuro export pubblico.

La candidate contiene solo l'allowlist verificata e nessun secret, PSK,
template, immagine o capture. I materiali restano fuori da Git/candidate e
sono importati separatamente con directory `0700`, file `0600`, controlli su
ownership/tipo/symlink e senza log di contenuto o digest. Candidate e stato
installato sono hash-pinned; PAM vendor resta immutato; SELinux, systemd,
rollback e uninstall limitano e rendono reversibili le modifiche host. Il
runtime conserva i guardrail factory-preserving e bounded già qualificati.

Il repository e la sua history privata non sono pubblicabili automaticamente:
content/history audit, isolamento in `red_tag/` ed export sanitizzato restano
obblighi Phase F. Non è provata l'assenza assoluta di mutazioni NVM interne, né
la compatibilità universale con Windows dopo ogni esecuzione.

## Licenze, attribution e SBOM

L'audit per file e provenance resta nel ledger
`docs/LICENSING_AND_PROVENANCE.md`. R2 conserva GPL-2.0-or-later, SIGFM e il
delta locale conservano le licenze per-file applicabili, libgusb è
LGPL-2.1-or-later e il subset OpenCV Fedora dichiara
`BSD-3-Clause AND Apache-2.0 AND ISC`. OpenSSL 3 è Apache-2.0.

Poiché il combined binary incorpora espressione GPL-2.0-or-later e collega
componenti Apache-2.0, la candidate lo distribuisce sotto
GPL-3.0-or-later, scelta consentita dal suffisso “or later” e compatibile con
Apache-2.0. Le licenze sorgente per-file non vengono riscritte. Candidate,
notice, corpus licenze OpenCV e testi GPL/LGPL/Apache sono coerenti; non è
stato cambiato il licensing boundary approvato.

`SBOM.spdx.json` è generato in modo deterministico dal commit, dall'allowlist
della candidate, dalle dipendenze dinamiche risolte e dai pacchetti di
integrazione Fedora. Un difetto iniziale nella query dei pacchetti installati
è stato corretto e coperto da regressione: libgusb risulta correttamente
`0.4.9-5.fc44`.

## Decisioni di qualificazione

- FAR/FRR: nessun claim. Le evidenze live sono funzionali e non costituiscono
  una popolazione o un protocollo statistico definito in anticipo.
- Windows: nuova prova non necessaria. Il delta D296 riguarda esclusivamente
  SBOM, notice, licenze e packaging; il binario libfprint è byte-identico alla
  baseline precedente e nessun codice sensor-reaching o stato factory è
  cambiato. Non viene fatto alcun claim di supporto Windows.
- Firmabilità: PASS. Commit completo, manifest, allowlist e checksum
  content-addressed consentono una firma esterna non ambigua; nessuna firma è
  stata generata o rivendicata in Phase E.
- Release qualification: PASS per il target e le versioni dichiarate, con i
  limiti sopra esposti.

```text
RELEASE_CANDIDATE=3feabcfb7918375ce0e04def0605c2389f95d932
RELEASE_CANDIDATE_SHA256=151e0092ddbc1e4751628c1e338efbf29259f3ce9fd79d093f1630f30f5f0584
SUPPORTED=FEDORA_44_KDE_X86_64_PLUS_GOODIX_27C6_5125_APP12509
NOT_YET_CLAIMED=OTHER_OS_DESKTOP_ARCH_SENSOR_FIRMWARE_OR_FEDORA_VERSION
TEST_MATRIX=PASS
THREAT_PRIVACY_REVIEW=PASS_SCOPED_TO_CANDIDATE
LICENSING_REVIEW=PASS_GPL_3_0_OR_LATER_COMBINED_BINARY
SBOM=PASS_SPDX_2_3_JSON
WINDOWS_REGRESSION=NOT_REQUIRED_FOR_D296_METADATA_ONLY_DELTA
FAR_FRR_CLAIM=NOT_MADE
REPRODUCIBLE_RC=PASS
SIGNABLE_RC=PASS_UNSIGNED
RELEASE_QUALIFICATION=PASS
EXECUTABLE_CLOSURE=PASS_OFFLINE_MAXIMUM
REAL_USB_ACCESS=0
LIVE_EXECUTION_PERFORMED=false
```

# Sviluppo privato e documentazione interna

Questa è l'unica directory non pubblica. La decisione Utente corrente definisce
l'albero pubblico come tutti i file del repository eccetto `development/`.
Nessun import, build, test o installazione pubblico può dipendere da questa
area o dalla storia Git privata.

La ripartenza autonoma legge [START_PROMPT.md](START_PROMPT.md),
[AGENTS.md](AGENTS.md), [roadmap](ROADMAP_DISTRO_DECOUPLED_RELEASE.md) e lo stato
corrente nel [manuale tecnico](<Goodix 27c6 5125 manuale tecnico.md>).
La root pubblica contiene il manuale tecnico inglese del prodotto.

Gli archivi mantengono evidenza utile. Le istruzioni di esecuzione nei documenti
storici descrivono checkout e ambienti del loro tempo: non sono la procedura
corrente di installazione. Per l'utente finale esiste solo
[la guida pubblica](../docs/INSTALLATION.md).

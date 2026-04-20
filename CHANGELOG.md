# Changelog

Tutte le release di `DocMolder` sono tracciate qui.

Il changelog segue un flusso orientato a GitHub:

- le versioni sono gestite con Semantic Versioning
- le release sono preparate da `release-please`
- il contenuto deriva dai merge su `main` con titolo/commit in formato Conventional Commits

## [Unreleased]

## [0.3.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.2.0...docmolder-v0.3.0) (2026-04-20)

### Features

- parser testuale piu robusto per richieste naturali su PDF e immagini, con sinonimi aggiuntivi e tolleranza leggera ai refusi comuni
- estrazione diretta da testo di selezione pagine, gradi di rotazione, watermark e livello di compressione
- chiarimenti guidati e passaggi a input pending quando la richiesta e ambigua o incompleta
- brand system DocMolder con asset dedicati e sincronizzazione di nome, descrizione, comandi e menu del profilo Telegram

### Fixes

- affinata la chiarezza del logo e la qualita di export degli asset brand
- corretto l'avatar Telegram con varianti a fondo pieno per evitare aloni chiari dovuti alla trasparenza
- riallineata l'operativita VPS per deploy e gestione delle variabili ambiente del bot

### Docs

- roadmap, contesto, README e linee guida brand riallineati al completamento della Fase 3

## [0.2.0](https://github.com/max23468/DocMolder/compare/docmolder-v0.1.0...docmolder-v0.2.0) (2026-04-18)


### Features

* aggiunge layout guidato e auto-orientamento PDF ([25c3eb2](https://github.com/max23468/DocMolder/commit/25c3eb29d9508b3a628d2e74a2bee302ba1e1b07))
* completa la fase 1 su affidabilità e fallback PDF ([c98bd82](https://github.com/max23468/DocMolder/commit/c98bd82ba7f81ca49196c57c11b91c2600be2fcf))
* completa la fase 2 su osservabilita e operativita admin ([1913ce1](https://github.com/max23468/DocMolder/commit/1913ce135bdb077ad8c598db8a29b3891aee8b5f))
* completa la fase 3 con funzioni pdf avanzate ([b0f6c9c](https://github.com/max23468/DocMolder/commit/b0f6c9c15feb622190953288d9881826a0a618b6))
* **release:** automate versioning and changelog ([#12](https://github.com/max23468/DocMolder/issues/12)) ([0208942](https://github.com/max23468/DocMolder/commit/020894204d629d63d06bdc52250c937fe04d00f0))


### Fixes

* evita riepiloghi admin periodici vuoti ([b9777fa](https://github.com/max23468/DocMolder/commit/b9777fa237a359fc6dbe8b6a25577b0963a0b6d8))
* redact telegram token from logs ([01b6880](https://github.com/max23468/DocMolder/commit/01b6880a42a0f25743a991d6081347a92653513d))


### Docs

* add minimal root AGENTS pointer to docs ([4a3adaa](https://github.com/max23468/DocMolder/commit/4a3adaa79d18d7a231a97a6e7ecfadf5f54e1c56))
* add root AGENTS guidelines for Codex workflow ([a5494c9](https://github.com/max23468/DocMolder/commit/a5494c917524604b026a8af1adbaa597d4f06faa))
* AGENTS.md root minimal pointer to docs/AGENTS.md ([663a34b](https://github.com/max23468/DocMolder/commit/663a34bc1a331f23268ed1a538a96c16de4256b2))
* aggiorna context del flusso PDF ([a69e750](https://github.com/max23468/DocMolder/commit/a69e7505bf864765055a590401a00087794e8609))
* aggiorna la roadmap dopo i test manuali ([0ddfde3](https://github.com/max23468/DocMolder/commit/0ddfde34ce702c1311c578e9569877589e00db06))
* aggiorna roadmap e README ([72ec030](https://github.com/max23468/DocMolder/commit/72ec030712fb2656359420c9153d602025ddb838))
* amplia e uniforma la documentazione ([53db63b](https://github.com/max23468/DocMolder/commit/53db63be49feeef7c2a9b757b86aeca2a5509809))
* amplia la roadmap con ottimizzazioni operative ([147d1fd](https://github.com/max23468/DocMolder/commit/147d1fd0c1d0cd5e2e5e9e91749dfc1d184a3f52))
* chiarisce il flusso corretto di release ([8fff46e](https://github.com/max23468/DocMolder/commit/8fff46eae23f71b95cb868fb658dc29af1431a0e))
* consolidate runbooks and remove unused tmp assets ([5ca2dca](https://github.com/max23468/DocMolder/commit/5ca2dca942dfd9b14dd067e390b98beaa992e069))
* definisce perimetro prodotto e nuova roadmap ([2409de1](https://github.com/max23468/DocMolder/commit/2409de11c4f9169f6c820e0644e390d066b4c1d6))
* rifinisce la roadmap finale ([846f870](https://github.com/max23468/DocMolder/commit/846f870305a020351334eb4cf19ac72e5712868d))

## [0.1.0] - 2026-04-18

Release baseline che consolida lo stato attuale del progetto prima dell'automazione delle release.

### Added

- bot Telegram funzionante per trasformazioni documentali guidate su PDF e immagini
- creazione PDF da immagini con scelta tra formato originale e impaginazione A4
- unione PDF, estrazione pagine, riordino pagine, eliminazione pagine, rotazione manuale e watermark testuale
- conversione PDF in scala di grigi, compressione su richiesta e correzione automatica dell'orientamento nei flussi compatibili
- storico degli ultimi job con dettaglio essenziale e possibilita di rilancio
- report admin e storage meta persistente per stato operativo e riepiloghi periodici
- workflow GitHub di CI, template issue/PR e documentazione operativa per il mantenimento del repository
- strategia di smoke test post-deploy e script `scripts/smoke_telegram_desktop.py` per automatizzare i controlli principali via Telegram Desktop

### Changed

- flussi utente, recap sessione, prompt guidati e messaggi di stato resi piu espliciti e coerenti
- pipeline PDF resa piu conservativa con fallback piu robusti e gestione errori/cleanup piu solida
- naming degli output, catalogo azioni e storico lavori resi piu leggibili e consistenti
- README e documentazione interna riallineati alle funzionalita realmente disponibili

### Technical

- ampliata la copertura test su pipeline PDF, job flow, storico, timeout, cleanup e smoke test automatizzati
- formalizzata la base per processi GitHub piu strutturati in vista di release versionate

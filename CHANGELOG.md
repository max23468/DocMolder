# Changelog

Tutte le release di `DocMolder` sono tracciate qui.

Il changelog segue un flusso orientato a GitHub:

- le versioni sono gestite con Semantic Versioning
- le release sono preparate da `release-please`
- il contenuto deriva dai merge su `main` con titolo/commit in formato Conventional Commits

## [Unreleased]

Nessuna modifica ancora rilasciata dopo la baseline `0.1.0`.

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

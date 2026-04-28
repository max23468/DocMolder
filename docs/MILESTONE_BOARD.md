# Board Milestone Minima

Board locale per mantenere visibili priorità, dipendenze e deliverable finché la roadmap resta leggera.

## Milestone attive

### M0 - Baseline prodotto e documentazione

Obiettivo:

- rendere chiaro perimetro, architettura, dati trattati e flusso release

Dipendenze:

- nessuna

Deliverable minimi:

- documentazione architettura
- governance servizio
- sicurezza operativa
- modello dati
- decisioni aperte

Stato:

- in consolidamento

### M1 - Affidabilità VPS e recovery

Obiettivo:

- rendere il servizio recuperabile da incidenti semplici senza ambiguità operative

Dipendenze:

- M0 abbastanza stabile

Deliverable principali:

- backup SQLite giornaliero verificato
- restore documentato
- health post-deploy più forte del solo `active`
- verifica spazio disco e runtime dir
- criteri minimi per job stuck e coda anomala

Stato:

- completata per il perimetro attuale: backup, restore, health/smoke, spazio disco, runtime dir e job stale sono coperti da CLI, timer e runbook

### M2 - Osservabilità e alert

Obiettivo:

- rendere leggibili failure mode principali senza ispezionare manualmente SQLite

Dipendenze:

- M1 parzialmente stabile

Deliverable principali:

- standard eventi log
- correlation id minimi
- soglie salute servizio
- metriche admin stabili
- alert Telegram admin governati da cooldown

Stato:

- stabile per il perimetro attuale: console `/admin`, alert admin e healthcheck CLI includono soglie operative principali

### M3 - Cleanup e lifecycle dati

Obiettivo:

- rendere esplicita e automatica la gestione di temporanei, storico e backup

Dipendenze:

- M0 e M1

Deliverable principali:

- cleanup runtime più rigoroso
- pruning job se deciso
- retention backup confermata
- policy cancellazione utente chiarita

Stato:

- completata per il perimetro 1.x iniziale: retention job live, pruning automatico, backup con retention breve e cancellazione dati live self-service sono documentati e implementati

### M4 - Raddrizzamento foto documento

Obiettivo:

- introdurre una trasformazione automatica per foto di documenti senza spostare il prodotto verso editor generalista

Dipendenze:

- pipeline per PDF e immagini stabile

Deliverable principali:

- rilevamento bordo foglio
- correzione prospettica
- controlli qualità input
- fallback chiari
- messaggi utente coerenti sui limiti

Stato:

- implementata come azione "Raddrizza foto documento"

### M5 - Performance e job pesanti

Obiettivo:

- evitare saturazione VPS su input grandi o batch costosi

Dipendenze:

- M2 per osservare i colli di bottiglia

Deliverable principali:

- limiti batch più intelligenti
- downscale preventivo immagini enormi
- profiling flussi costosi
- test locali ripetibili di carico leggero
- regolazione parallelismo job

Stato:

- completata per il perimetro VPS corrente: worker seriale, limiti per utente, downscale preventivo immagini enormi e profiler locale dei flussi pesanti

## Priorità correnti

Priorità raccomandate:

- chiudere M0 documentale
- rafforzare M1 con health post-deploy e backup/restore verificabili
- rendere M2 abbastanza stabile da supportare alert e diagnosi
- affrontare M3 prima di aumentare retention o numero utenti

Per la lista task operativa vedere [ROADMAP.md](./ROADMAP.md).

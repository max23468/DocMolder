# Hardening tecnico-operativo (2026-05-27)

## Rischio iniziale

- Livello: **medio-alto**.
- Stato in questa ondata: **P0/P1 prioritario** su superficie pipeline+runtime.
- Rotazione segreti: **non inclusa** in questa fase (espressamente esclusa).

## Contesto operativo rilevante

- Perimetro Telegram-first con bot operativo e pipeline VPS.
- Servizi runtime: bot Telegram, job di deploy, storage temporanei e backup locale.
- Ambiente deploy: VPS con release automatizzabili.

## Piano tecnico (P0/P1/P2)

### P0

- Hardening pipeline VPS + bot Telegram:
  - confermare che segreti e identificatori operativi risiedono solo in env dedicati o secret store e non in repo;
  - separare runtime/path bot, job deploy e backup con permessi stretti;
  - bloccare commit accidentali di secret pattern e file `.env` nel pre-deploy.
- Eseguire `dry-run` obbligatorio prima di ogni deploy pubblico/produzione.
- Definire artefatto di rilascio stabile e tracciabile (`immutable` dove praticabile), così da poter ricostruire il pacchetto da deploy in modo verificabile.

### P1

- Controllo idempotenza degli script:
  - isolamento percorso di esecuzione;
  - lock/guard per run concorrenti e doppie partite;
  - zero side-effect in riavvio parziale.
- Audit backup/restore con verifica di ripristino periodica e procedure di rollback.
- Rafforzare isolamento percorsi di output e cleanup dei file temporanei.

### P2

- Policy log e anti-leak su allegati:
  - filtrare identificativi sensibili e contenuti documento nei log condivisi;
  - registrare solo metadati operativi minimi;
  - anti-leak su allegati/preview pubblicati.
- Formalizzare soglie di retention e verifica mensile.

## Piano operativo e di governo

### P0/P1

- Ridurre la superficie esposta dai workflow/script locali verso ambienti condivisi.
- Inventario esecuzioni in ogni run con owner, ora, comando e artefatto di rilascio
- Aggiornare `docs/OPERATIONS_SECURITY.md` con runbook “deploy + rollback + guard”.
- Prima di rimettere online una funzionalità nuova, chiudere checklist Telegram/VPS e verificare runbook.

### P2

- Inserire controllo ricorrente (runbook) su lock di deployment, retention e separazione output.
- Allineare eventuali nuove dipendenze runtime nel `docs/VPS_RUNBOOK.md` e `README.md` operativi.

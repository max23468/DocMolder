# Contesto Persistente Progetto: DocMolder

Questo file e un handoff rapido: descrive il minimo contesto utile e punta alla documentazione specialistica.

Ultimo aggiornamento del contesto:
- data di riferimento: `2026-04-15`

## Cos'e DocMolder

`DocMolder` e un bot Telegram-first per trasformazioni documentali guidate (PDF e immagini), con coda asincrona e retention breve dei temporanei.

## Componenti principali

- `src/docmolder/main.py`: entrypoint applicazione.
- `src/docmolder/bot.py`: handler Telegram, orchestrazione flussi utente.
- `src/docmolder/processing.py`: pipeline documentale.
- `src/docmolder/session_store.py`: persistenza sessioni/job su SQLite.
- `src/docmolder/services.py`: regole azioni supportate e naming output.

## Dove trovare le informazioni

- Setup locale e test: [LOCAL_DEV.md](./LOCAL_DEV.md)
- Deploy e operations VPS: [VPS_RUNBOOK.md](./VPS_RUNBOOK.md)
- Processo rilascio: [RELEASE_PROCESS.md](./RELEASE_PROCESS.md)
- Strategia pipeline PDF: [PDF_PIPELINE.md](./PDF_PIPELINE.md)
- Decisioni tecniche: [DECISIONS.md](./DECISIONS.md)
- Roadmap: [ROADMAP.md](./ROADMAP.md)
- Changelog: [CHANGELOG.md](./CHANGELOG.md)
- Indice documentazione: [INDEX.md](./INDEX.md)

## Regole operative sintetiche

- mantenere modifiche piccole e verificabili
- non introdurre dipendenze senza motivazione
- aggiornare docs e changelog quando cambia comportamento utente/operativo
- validare con test rilevanti prima del deploy

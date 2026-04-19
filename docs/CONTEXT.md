# Contesto Persistente Progetto: DocMolder

Questo file e un handoff rapido: descrive il minimo contesto utile e punta alla documentazione specialistica.

Ultimo aggiornamento del contesto:
- data di riferimento: `2026-04-18`

## Cos'e DocMolder

`DocMolder` e un bot Telegram-first per trasformazioni documentali guidate (PDF e immagini), con coda asincrona e retention breve dei temporanei.

## Componenti principali

- `src/docmolder/main.py`: entrypoint applicazione.
- `src/docmolder/bot.py`: handler Telegram, orchestrazione flussi utente.
- `src/docmolder/processing.py`: pipeline documentale.
- `src/docmolder/session_store.py`: persistenza sessioni/job su SQLite.
- `src/docmolder/sqlite_backup.py`: backup e restore verificati del database SQLite.
- `src/docmolder/services.py`: regole azioni supportate e naming output.

## Dove trovare le informazioni

- Setup locale e test: [LOCAL_DEV.md](./LOCAL_DEV.md)
- Deploy e operations VPS: [VPS_RUNBOOK.md](./VPS_RUNBOOK.md)
- Processo rilascio: [RELEASE_PROCESS.md](./RELEASE_PROCESS.md)
- Policy versioni e changelog: [VERSIONING.md](./VERSIONING.md)
- Strategia pipeline PDF: [PDF_PIPELINE.md](./PDF_PIPELINE.md)
- Decisioni tecniche: [DECISIONS.md](./DECISIONS.md)
- Roadmap: [ROADMAP.md](./ROADMAP.md)
- Changelog: [../CHANGELOG.md](../CHANGELOG.md)
- Indice documentazione: [INDEX.md](./INDEX.md)

## Regole operative sintetiche

- mantenere modifiche piccole e verificabili
- non introdurre dipendenze senza motivazione
- aggiornare docs e usare il changelog versionato quando cambia comportamento utente/operativo
- validare con test rilevanti prima del deploy

## Ultime note rilevanti

- il bot espone ora un recap sessione piu strutturato, con azioni consigliate e suggerimento sul prossimo passo
- gli input pagina sono piu tolleranti e accettano anche sequenze separate da spazi nei flussi guidati
- il risultato di un PDF puo diventare subito il punto di partenza per una nuova operazione tramite pulsanti contestuali sul file restituito
- il bot conserva in modo leggero alcune ultime scelte frequenti per proporle come scorciatoie, ma le cancella con `/reset`
- lo storico distingue ora anche i job rilanciati come entita separate, mantenendo il riferimento al job di origine
- la Fase 2 ha introdotto alert admin anti-spam per failure rate anomali o errori ripetuti nelle ultime finestre operative
- la VPS ha ora backup SQLite giornaliero con timer systemd, script manuali di backup/restore e retention corta verificabile
- la copertura pseudo end-to-end include ora anche flussi piu realistici di upload Telegram, wizard immagini->PDF e follow-up sul PDF risultato
- la comprensione testuale e ora piu tollerante su richieste naturali, sinonimi e piccoli refusi, con estrazione diretta di pagine, rotazioni, watermark e livello di compressione
- quando un comando testuale e ambiguo o incompleto, il bot prova a chiarire l'azione o chiede il dettaglio mancante invece di fermarsi su una lettura fragile

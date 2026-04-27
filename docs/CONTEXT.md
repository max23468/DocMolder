# Contesto Persistente Progetto: DocMolder

Questo file e un handoff rapido: descrive il minimo contesto utile e punta alla documentazione specialistica.

Ultimo aggiornamento del contesto:
- data di riferimento: `2026-04-23`

## Cos'e DocMolder

`DocMolder` e un bot Telegram-first per trasformazioni documentali guidate (PDF e immagini), con coda asincrona e retention breve dei temporanei.

## Componenti principali

- `src/docmolder/main.py`: entrypoint applicazione.
- `src/docmolder/bot.py`: handler Telegram, orchestrazione flussi utente.
- `src/docmolder/processing.py`: pipeline documentale.
- `src/docmolder/session_store.py`: facciata store sessioni/job.
- `src/docmolder/sqlite_session_store.py`: persistenza sessioni/job su SQLite.
- `src/docmolder/sqlite_backup.py`: backup e restore verificati del database SQLite.
- `src/docmolder/action_catalog.py`: regole azioni supportate e naming output.

## Dove trovare le informazioni

- Setup locale e test: [LOCAL_DEV.md](./LOCAL_DEV.md)
- Architettura: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Modello dati: [DATA_MODEL.md](./DATA_MODEL.md)
- Coordinamento tra agenti e chat parallele: [AGENT_COORDINATION.md](./AGENT_COORDINATION.md)
- Task packet e prompt Codex: [CODEX_TASK_PACKET.md](./CODEX_TASK_PACKET.md), [CODEX_TASK_PROMPTS.md](./CODEX_TASK_PROMPTS.md)
- Integrazioni Codex, GitHub e operations: [CODEX_INTEGRATIONS.md](./CODEX_INTEGRATIONS.md)
- Tooling Codex/GitHub/operations: `scripts/codex_dev_report.py`, `scripts/github_maintenance_report.py`, `scripts/ops_report.py`
- Deploy e operations VPS: [VPS_RUNBOOK.md](./VPS_RUNBOOK.md)
- Governance servizio: [SERVICE_GOVERNANCE.md](./SERVICE_GOVERNANCE.md)
- Sicurezza operativa: [OPERATIONS_SECURITY.md](./OPERATIONS_SECURITY.md)
- Processo rilascio: [RELEASE_PROCESS.md](./RELEASE_PROCESS.md)
- Policy versioni e changelog: [VERSIONING.md](./VERSIONING.md)
- Strategia pipeline PDF: [PDF_PIPELINE.md](./PDF_PIPELINE.md)
- Decisioni tecniche: [DECISIONS.md](./DECISIONS.md)
- Decisioni aperte: [DECISIONS_PENDING.md](./DECISIONS_PENDING.md)
- Milestone: [MILESTONE_BOARD.md](./MILESTONE_BOARD.md)
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
- il flusso senza GitHub Actions usa hook Git locali installabili e un listener webhook GitHub privato sulla VPS per deploy su `main`; se `/etc/docmolder/release.env` abilita la release automatica, la VPS crea anche bump, changelog, tag e GitHub Release dopo un deploy riuscito
- la copertura pseudo end-to-end include ora anche flussi piu realistici di upload Telegram, wizard immagini->PDF e follow-up sul PDF risultato
- la comprensione testuale e ora piu tollerante su richieste naturali, sinonimi e piccoli refusi, con estrazione diretta di pagine, rotazioni, watermark e livello di compressione
- quando un comando testuale e ambiguo o incompleto, il bot prova a chiarire l'azione o chiede il dettaglio mancante invece di fermarsi su una lettura fragile
- la Fase 4 ha aggiunto lo split PDF in un file per pagina, con scelta tra archivio ZIP e PDF separati
- la Fase 5 ha rafforzato i riferimenti contestuali in chat: pronomi come "questo PDF"/"quello", frasi come "giralo" o "alleggeriscilo" e "ripeti l'ultimo job" sono gestiti in modo piu esplicito
- la Fase 6 ha aggiunto "Raddrizza foto documento": una trasformazione automatica per foto di fogli, con rilevamento contorno, correzione prospettica, normalizzazione leggibilita e fallback conservativi
- l'allineamento operativo ha introdotto healthcheck/reconcile CLI, timer alert/reconcile, audit admin, access request in chat, `/policy`, helper retry/logging/messaging e tool git-safe locale
- la Fase 7 ha chiuso il rafforzamento VPS/performance: healthcheck con soglie su servizio, SQLite, backup, runtime, disco, load e RAM; backup/reconcile/alert timer; retention journald; downscale preventivo delle immagini enormi; profiler locale dei flussi pesanti

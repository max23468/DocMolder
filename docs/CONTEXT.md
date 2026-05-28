# Contesto Persistente Progetto: DocMolder

Questo file è un handoff rapido: descrive il minimo contesto utile e punta alla documentazione specialistica.

Ultimo aggiornamento del contesto:
- data di riferimento: `2026-05-26`

## Stato progetto

- Fase: linea stabile `1.x`, sviluppo feature in pausa salvo bugfix, priorità
  prodotto o decisioni esplicite.
- Versione/release: `Release Please`, tag `docmolder-v*`, GitHub Release e
  documenti `VERSIONING.md` / `RELEASE_PROCESS.md`.
- Deploy corrente: VPS DocMolder via webhook privato GitHub -> VPS; deploy
  manuale solo fallback documentato in `VPS_RUNBOOK.md`.
- Eccezione `OK equivalente`: PR title e publish docs-only sono governati da
  policy/script locali invece di copiare un template Atlas identico.
- Pubblicazione proporzionata: docs-only/governance-only richiede review
  documentale, preflight mirato e `git diff --check`, senza release o deploy se
  il diff non è rilasciabile.

## Cos'è DocMolder

`DocMolder` è un bot Telegram-first per trasformazioni documentali guidate (PDF, immagini e interventi Excel mirati), con coda asincrona e retention breve dei temporanei.

## Componenti principali

- `src/docmolder/main.py`: entrypoint applicazione.
- `src/docmolder/bot.py`: handler Telegram, orchestrazione flussi utente.
- `src/docmolder/processing.py`: pipeline documentale.
- `src/docmolder/excel_unlock.py`: sblocco modifica Excel e integrazione LibreOffice per `.xls`.
- `src/docmolder/session_store.py`: facciata store sessioni/job.
- `src/docmolder/sqlite_session_store.py`: persistenza sessioni/job su SQLite.
- `src/docmolder/sqlite_backup.py`: backup e restore verificati del database SQLite.
- `src/docmolder/action_catalog.py`: regole azioni supportate e naming output.

## Fonti primarie e handoff

- Setup locale e test: [LOCAL_DEV.md](./LOCAL_DEV.md)
- Architettura: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Modello dati: [DATA_MODEL.md](./DATA_MODEL.md)
- Istruzioni operative per agenti e chat parallele: [AGENTS.md](../AGENTS.md)
- Task packet e prompt Codex: [CODEX_TASK_PACKET.md](./CODEX_TASK_PACKET.md), [CODEX_TASK_PROMPTS.md](./CODEX_TASK_PROMPTS.md)
- Integrazioni Codex, GitHub e operations: [CODEX_INTEGRATIONS.md](./CODEX_INTEGRATIONS.md)
- Tooling Codex/GitHub/operations: `scripts/codex_dev_report.py`, `scripts/github_maintenance_report.py`, `scripts/ops_report.py`
- Deploy e operations VPS: [VPS_RUNBOOK.md](./VPS_RUNBOOK.md)
- Governance servizio: [SERVICE_GOVERNANCE.md](./SERVICE_GOVERNANCE.md)
- Sicurezza operativa: [OPERATIONS_SECURITY.md](./OPERATIONS_SECURITY.md)
- Processo rilascio: [RELEASE_PROCESS.md](./RELEASE_PROCESS.md)
- Policy versioni e changelog: [VERSIONING.md](./VERSIONING.md)
- Toolchain e guardrail runtime: [TOOLCHAIN.md](./TOOLCHAIN.md)
- Strategia pipeline PDF: [PDF_PIPELINE.md](./PDF_PIPELINE.md)
- Strategia pipeline Excel: [EXCEL_PIPELINE.md](./EXCEL_PIPELINE.md)
- Decisioni tecniche: [DECISIONS.md](./DECISIONS.md)
- Decisioni aperte: [DECISIONS_PENDING.md](./DECISIONS_PENDING.md)
- ADR leggere: [decisions/](./decisions/)
- Milestone: [MILESTONE_BOARD.md](./MILESTONE_BOARD.md)
- Roadmap: [ROADMAP.md](./ROADMAP.md)
- Backlog: [BACKLOG.md](./BACKLOG.md)
- Changelog: [../CHANGELOG.md](../CHANGELOG.md)
- Indice documentazione: [INDEX.md](./INDEX.md)

## Regole operative sintetiche

- mantenere modifiche piccole e verificabili
- non introdurre dipendenze senza motivazione
- aggiornare docs e usare il changelog versionato quando cambia comportamento utente/operativo
- validare con test rilevanti prima del deploy
- mantenere `docs/DECISIONS.md`, `docs/DECISIONS_PENDING.md` e ADR in
  `docs/decisions/` come modello decisionale pieno

## Ultime note rilevanti

- il bot espone ora un recap sessione più strutturato, con azioni consigliate e suggerimento sul prossimo passo
- gli input pagina sono più tolleranti e accettano anche sequenze separate da spazi nei flussi guidati
- il risultato di un PDF può diventare subito il punto di partenza per una nuova operazione tramite pulsanti contestuali sul file restituito
- il bot conserva in modo leggero alcune ultime scelte frequenti per proporle come scorciatoie, ma le cancella con `/reset`
- lo storico distingue ora anche i job rilanciati come entità separate, mantenendo il riferimento al job di origine
- la Fase 2 ha introdotto alert admin anti-spam per failure rate anomali o errori ripetuti nelle ultime finestre operative
- la VPS ha ora backup SQLite giornaliero con timer systemd, script manuali di backup/restore e retention corta verificabile
- il flusso GitHub Actions prudente usa CI automatica sulle PR non draft verso `main`; il rilascio ufficiale parte poi con `Release Please` dopo il merge, e il listener webhook GitHub privato sulla VPS resta responsabile del deploy, mentre lo script legacy di release automatico locale non è più in uso.
- la copertura pseudo end-to-end include ora anche flussi più realistici di upload Telegram, wizard immagini->PDF e follow-up sul PDF risultato
- la comprensione testuale è ora più tollerante su richieste naturali, sinonimi e piccoli refusi, con estrazione diretta di pagine, rotazioni, watermark e livello di compressione
- quando un comando testuale è ambiguo o incompleto, il bot prova a chiarire l'azione o chiede il dettaglio mancante invece di fermarsi su una lettura fragile
- la Fase 4 ha aggiunto lo split PDF in un file per pagina, con scelta tra archivio ZIP e PDF separati
- la Fase 5 ha rafforzato i riferimenti contestuali in chat: pronomi come "questo PDF"/"quello", frasi come "giralo" o "alleggeriscilo" e "ripeti l'ultimo job" sono gestiti in modo più esplicito
- la Fase 6 ha aggiunto "Raddrizza foto documento": una trasformazione automatica per foto di fogli, con rilevamento contorno, correzione prospettica, normalizzazione leggibilità e fallback conservativi
- l'allineamento operativo ha introdotto healthcheck/reconcile CLI, timer alert/reconcile, audit admin, access request in chat, helper retry/logging/messaging e tool git-safe locale
- la gerarchia comandi Telegram è stata semplificata: utenti su `/start`, `/help`, `/history`, `/status`, `/reset`; admin su `/admin` nascosto e dashboard inline
- le tastiere inline sono contestuali: azioni consigliate in vista breve, azioni avanzate dietro `Altre azioni`, scorciatoie admin job mostrate solo per stati disponibili
- la Fase 7 ha chiuso il rafforzamento VPS/performance: healthcheck con soglie su servizio, SQLite, backup, runtime, disco, load e RAM; backup/reconcile/alert timer; retention journald; downscale preventivo delle immagini enormi; profiler locale dei flussi pesanti
- la Fase 8 ha introdotto un'analisi strutturata della sessione riusata da recap, tastiere e job flow: conteggi, preview file, azioni supportate/esposte/consigliate, azioni avanzate, warning e prossimo passo
- il processor usa ora una mappa azione -> handler invece di un dispatch lineare, rendendo più chiara l'aggiunta o modifica delle trasformazioni
- il flusso immagini verso PDF scrive PDF intermedi per pagina e li unisce, riducendo il picco di memoria sui batch; le foto documento chiudono prima le immagini trasformate dopo l'impaginazione
- il limite anti-burst degli upload conserva in `app_meta` solo le timestamp recenti della finestra operativa, così sopravvive a un riavvio senza diventare storico permanente
- lo storico job mostra anche riepilogo file sorgente e nome output base derivato dal catalogo, allineando file restituiti e dettaglio utente
- `DocMolder` è stato promosso alla linea stabile `1.x`: `docmolder-v1.0.0` ha dichiarato stabile il perimetro corrente e `docmolder-v1.0.1` è il follow-up live verificato sulla VPS
- l'uso pubblico previsto per la 1.x è un soft launch Telegram-first: bot raggiungibile pubblicamente, best-effort, basso volume atteso, retention breve, nessuno storage documentale permanente e possibilità di restringere accesso o mettere in manutenzione se carico o abuso lo richiedono
- le decisioni roadmap 1.x sono confermate: Fase 9 prima di nuove feature, cancellazione completa dentro `/reset`, retention job live predefinita a 30 giorni configurabile, backup non riscritti retroattivamente, italiano-first, preset automatici leggeri dopo UX/trust, OCR fuori dal perimetro pubblico iniziale
- la Fase 9 è implementata: `docmolder-reconcile` pruna i job conclusi oltre `DOCMOLDER_JOB_HISTORY_RETENTION_DAYS`, `/reset` espone cancellazione completa dei dati live con conferma inline, e i backup storici restano gestiti dalla loro retention breve
- la Fase 10 è implementata: `/start` e `/help` chiariscono uso pubblico, limiti e assenza di archivio permanente; `/start privacy`, `/status` e il sito statico portano a dati/retention/cancellazione; i messaggi di errore principali indicano un prossimo passo pratico
- la Fase 11 è implementata: compressione, split e immagini verso PDF conservano preferenze operative leggere, promuovono preset dopo scelte ripetute e li propongono come scorciatoie inline senza salvare contenuti o nomi file
- la Fase 12 è implementata: "Raddrizza foto documento" propone profili leggeri per leggibilità, colore o bianco/nero pulito, segnala input scuri/sfocati/col bordo incerto e la compressione PDF indica quando la riduzione è minima
- la Fase 13 è implementata: `/admin`, healthcheck e runbook espongono soglie prudenziali su job/giorno, utenti attivi, database, failure rate e coda, con alert più azionabili e criteri per fermare crescita o rivalutare SQLite/VPS
- dopo `docmolder-v1.5.0` non c’è una nuova fase attiva: lo sviluppo feature è in pausa finché non emergono bugfix, priorità prodotto, segnali operativi o decisioni esplicite; il focus corrente è stabilizzazione, smoke mirati e osservazione del soft launch
- il runtime applicativo preferito per sviluppo, CI operativa e VPS è Python 3.13 in virtualenv isolata; sulla VPS non va sostituito `/usr/bin/python3`, ma usato un interprete 3.13 side-by-side per `/opt/docmolder/venv`

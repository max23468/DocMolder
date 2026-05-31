# Contesto Persistente Progetto: DocMolder

Questo file è un handoff rapido: descrive il minimo contesto utile e punta alla
documentazione specialistica. Cronologie, fasi completate e dettagli operativi
estesi vivono in `CHANGELOG.md`, `docs/ROADMAP_HISTORY.md`,
`docs/VPS_RUNBOOK.md` e nei documenti di area.

## Stato progetto

- Fase: linea stabile `1.x`, sviluppo feature in pausa salvo bugfix, priorità
  prodotto o decisioni esplicite.
- Versione/release: procedura release manuale documentata; tag
  `v*`, GitHub Release e documenti `VERSIONING.md` /
  `RELEASE_PROCESS.md`.
- Deploy corrente: VPS DocMolder via webhook privato GitHub -> VPS; deploy
  manuale solo fallback documentato in `VPS_RUNBOOK.md`.
- Runtime preferito: Python `3.13` in virtualenv isolata, sia per sviluppo sia
  per VPS; non sostituire il Python di sistema della VPS.
- Eccezione repo-specifica: PR title e publish docs-only sono governati da
  policy/script locali invece di copiare template Atlas identici.
- Pubblicazione proporzionata: docs-only/governance-only richiede review
  documentale, preflight mirato e `git diff --check`, senza release o deploy se
  il diff non è rilasciabile.

## Cos'è DocMolder

DocMolder è un bot Telegram-first per trasformazioni documentali guidate su PDF,
immagini e interventi Excel mirati. Usa coda asincrona, SQLite e retention breve
dei temporanei.

Perimetro da rispettare:

- utility documentale semplice, guidata e affidabile;
- soft launch pubblico best-effort, basso volume atteso e retention breve;
- nessuno storage documentale permanente;
- possibilità di restringere accesso o mettere in manutenzione se emergono
  carico o abuso.

Fuori perimetro senza decisione esplicita:

- gestionale documentale completo;
- storage permanente di file utente;
- editor collaborativo;
- dashboard web-first.

## Componenti principali

- `src/docmolder/main.py`: entrypoint applicazione.
- `src/docmolder/bot.py`: handler Telegram e orchestrazione flussi utente.
- `src/docmolder/processing.py`: pipeline documentale.
- `src/docmolder/excel_unlock.py`: sblocco modifica Excel e integrazione
  LibreOffice per `.xls`.
- `src/docmolder/session_store.py` e
  `src/docmolder/sqlite_session_store.py`: persistenza sessioni/job.
- `src/docmolder/sqlite_backup.py`: backup e restore verificati del database
  SQLite.
- `src/docmolder/action_catalog.py`: regole azioni supportate e naming output.

## Fonti primarie e handoff

- Regole operative: [AGENTS.md](../AGENTS.md).
- Indice documentazione: [INDEX.md](./INDEX.md).
- Setup locale e test: [LOCAL_DEV.md](./LOCAL_DEV.md).
- Architettura: [ARCHITECTURE.md](./ARCHITECTURE.md).
- Modello dati: [DATA_MODEL.md](./DATA_MODEL.md).
- Deploy e operations VPS: [VPS_RUNBOOK.md](./VPS_RUNBOOK.md).
- Governance servizio: [SERVICE_GOVERNANCE.md](./SERVICE_GOVERNANCE.md).
- Sicurezza operativa: [OPERATIONS_SECURITY.md](./OPERATIONS_SECURITY.md).
- Processo rilascio: [RELEASE_PROCESS.md](./RELEASE_PROCESS.md).
- Versioning e changelog: [VERSIONING.md](./VERSIONING.md) e
  [CHANGELOG.md](../CHANGELOG.md).
- Toolchain: [TOOLCHAIN.md](./TOOLCHAIN.md).
- Pipeline PDF/Excel: [PDF_PIPELINE.md](./PDF_PIPELINE.md),
  [EXCEL_PIPELINE.md](./EXCEL_PIPELINE.md).
- Decisioni: [DECISIONS.md](./DECISIONS.md),
  [DECISIONS_PENDING.md](./DECISIONS_PENDING.md), [decisions/](./decisions/).
- Roadmap e backlog: [ROADMAP.md](./ROADMAP.md), [BACKLOG.md](./BACKLOG.md).
- Storico roadmap 1.x: [ROADMAP_HISTORY.md](./ROADMAP_HISTORY.md).

## Stato operativo da ricordare

- La roadmap operativa iniziale `1.x` è completata fino a `docmolder-v1.5.x`.
- Il focus corrente è stabilizzazione prudente, smoke mirati e osservazione del
  soft launch.
- Le decisioni roadmap 1.x restano in `docs/DECISIONS.md`; le fasi completate
  sono storicizzate in `docs/ROADMAP_HISTORY.md` e nel changelog.
- OCR resta fuori dal perimetro pubblico iniziale.
- Le soglie prudenziali su job/giorno, utenti attivi, database, failure rate e
  coda guidano eventuali decisioni di crescita oltre VPS singola e SQLite.

## Handoff per nuova chat

Prima di procedere:

1. leggere `AGENTS.md`;
2. controllare `git status --short --branch`;
3. leggere `docs/INDEX.md`, `docs/CONTEXT.md`, `docs/ROADMAP.md`,
   `docs/BACKLOG.md`, `docs/TOOLCHAIN.md` e i documenti vicini al task;
4. per release o deploy leggere `docs/VERSIONING.md`,
   `docs/RELEASE_PROCESS.md` e `docs/VPS_RUNBOOK.md`;
5. controllare Codex feedback inbox prima di PR ready, merge, publish, deploy o
   release;
6. scegliere verifiche proporzionate: docs-only di solito `git diff --check` e
   preflight mirato; runtime/VPS richiede gate locali e controlli da runbook.

## Rischi aperti

- Far ricrescere `docs/CONTEXT.md` come changelog parallelo.
- Confondere soft launch pubblico con promozione ampia.
- Introdurre feature o automazioni che aumentano volume, storage o supporto
  senza osservare prima le soglie operative.
- Aggiornare runtime, release o deploy senza seguire la procedura manuale
  documentata.
- Perdere dati utente o temporanei violando retention e cleanup.

## Prossimo passo

Continuare a usare `docs/ROADMAP.md` per priorità vive, `docs/BACKLOG.md` per
debiti non promossi e `docs/ROADMAP_HISTORY.md`/`CHANGELOG.md` per storico. Il
context va aggiornato solo quando cambia stato operativo, handoff, deploy,
release, runtime o rischio rilevante.

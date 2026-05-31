# Documentazione DocMolder

Indice unico della documentazione operativa.

La root resta per ingresso ed esecuzione: `README.md`, `AGENTS.md`,
`CHANGELOG.md`, `SECURITY.md`, manifest, configurazioni, script e codice.
`docs/` contiene runbook, guide, pipeline, contesto, roadmap, backlog,
decisioni, governance operativa e approfondimenti.

## Per iniziare

- [README](../README.md): panoramica prodotto e funzionalità principali.
- [LOCAL_DEV.md](./LOCAL_DEV.md): setup locale, flusso quotidiano e testing.
- [AGENTS.md](../AGENTS.md): istruzioni operative persistenti per agenti, scope, coordinamento, test, PR e deploy.
- [CODEX_TASK_PACKET.md](./CODEX_TASK_PACKET.md): template per assegnare sotto-task a istanze parallele o filoni di lavoro separati.
- [CODEX_TASK_PROMPTS.md](./CODEX_TASK_PROMPTS.md): prompt operativi riutilizzabili per Codex.
- [CODEX_INTEGRATIONS.md](./CODEX_INTEGRATIONS.md): integrazioni scelte per sviluppo Codex, GitHub release e operations.
- Tool locali: `make codex-dev-report`, `make github-maintenance`, `make ops-report` per sviluppo Codex, release GitHub e osservabilità.

## Esercizio e deploy

- [VPS_RUNBOOK.md](./VPS_RUNBOOK.md): setup Oracle VPS + operations day-2.
- [CODEX_CLOUD_DEPLOY.md](./CODEX_CLOUD_DEPLOY.md): flusso consigliato per lavorare da Codex web/cloud, con CI prudente, release manuale e webhook GitHub privato come deploy standard.
- [RELEASE_PROCESS.md](./RELEASE_PROCESS.md): checklist di rilascio e deploy.
- [VERSIONING.md](./VERSIONING.md): policy ufficiale per versioni, changelog e release.
- [TOOLCHAIN.md](./TOOLCHAIN.md): runtime, comandi, tool esterni e guardrail di versione.
- [doppler-setup.md](./doppler-setup.md): integrazione Doppler, variabili GitHub e verifica segreti CI.
- [ONE_DOT_ZERO_READINESS.md](./ONE_DOT_ZERO_READINESS.md): criteri, checklist e record della promozione DocMolder a `1.0.0`.
- [OPERATIONS_SECURITY.md](./OPERATIONS_SECURITY.md): sicurezza operativa, segreti, log, backup e incident response.
- [SERVICE_GOVERNANCE.md](./SERVICE_GOVERNANCE.md): dati trattati, retention, cancellazione e limiti del servizio.
- [SMOKE_TESTS.md](./SMOKE_TESTS.md): strategia post-deploy per smoke test rapidi via Telegram Desktop scriptato e verifica UI mirata.
- [GITHUB_ALIGNMENT.md](./GITHUB_ALIGNMENT.md): setup GitHub e best practice per maintainer singolo.
- [GITHUB_MAINTENANCE.md](./GITHUB_MAINTENANCE.md): checklist periodica GitHub, security e fallback git-safe.

## Prodotto e decisioni

- [BRAND.md](./BRAND.md): identità del prodotto, asset e linee guida di tono/UI.
- [ARCHITECTURE.md](./ARCHITECTURE.md): mappa di moduli, flussi, runtime e limiti architetturali.
- [DATA_MODEL.md](./DATA_MODEL.md): modelli applicativi, tabelle SQLite e stati persistenti.
- [PDF_PIPELINE.md](./PDF_PIPELINE.md): strategia pipeline PDF e fallback.
- [EXCEL_PIPELINE.md](./EXCEL_PIPELINE.md): strategia sblocco modifica Excel e dipendenze LibreOffice.
- [TELEGRAM_OPERATIONS.md](./TELEGRAM_OPERATIONS.md): comandi, deep link, console admin, metriche e hardening del bot Telegram.
- [DECISIONS.md](./DECISIONS.md): decisioni tecniche persistenti.
- [DECISIONS_PENDING.md](./DECISIONS_PENDING.md): decisioni aperte distinte dai task di roadmap.
- [decisions/](./decisions/): ADR leggere per nuove decisioni strutturali o migrazioni progressive; l'indice decisionale resta [DECISIONS.md](./DECISIONS.md).
- [MILESTONE_BOARD.md](./MILESTONE_BOARD.md): milestone locali, dipendenze e deliverable principali.
- [ROADMAP.md](./ROADMAP.md): direzione, priorità e prossimi passi correnti.
- [ROADMAP_HISTORY.md](./ROADMAP_HISTORY.md): archivio storico della vecchia roadmap estesa.
- [BACKLOG.md](./BACKLOG.md): idee, debiti e decisioni non ancora promosse in roadmap.
- [../CHANGELOG.md](../CHANGELOG.md): changelog versionato delle release.

## Contesto persistente

- [CONTEXT.md](./CONTEXT.md): handoff rapido e mappa dei documenti.

## Manutenzione catalogo

Non creare documenti paralleli con lo stesso titolo, scopo o ruolo canonico.
Se un documento viene migrato, rinominato o assorbito, aggiorna questo indice,
preserva contenuti utili e lascia un rinvio temporaneo quando serve
tracciabilità.

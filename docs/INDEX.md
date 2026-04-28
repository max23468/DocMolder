# Documentazione DocMolder

Indice unico della documentazione operativa.

## Per iniziare

- [README](../README.md): panoramica prodotto e funzionalita principali.
- [LOCAL_DEV.md](./LOCAL_DEV.md): setup locale, flusso quotidiano e testing.
- [AGENT_COORDINATION.md](./AGENT_COORDINATION.md): registro e protocollo per coordinare chat, agenti e branch parallele.
- [CODEX_TASK_PACKET.md](./CODEX_TASK_PACKET.md): template per deleghe a sub-agenti o istanze parallele.
- [CODEX_TASK_PROMPTS.md](./CODEX_TASK_PROMPTS.md): prompt operativi riutilizzabili per Codex.
- [CODEX_INTEGRATIONS.md](./CODEX_INTEGRATIONS.md): integrazioni scelte per sviluppo Codex, GitHub release e operations.
- Tool locali: `make codex-dev-report`, `make github-maintenance`, `make ops-report` per sviluppo Codex, release GitHub e osservabilita.

## Esercizio e deploy

- [VPS_RUNBOOK.md](./VPS_RUNBOOK.md): setup Oracle VPS + operations day-2.
- [CODEX_CLOUD_DEPLOY.md](./CODEX_CLOUD_DEPLOY.md): flusso consigliato per lavorare da Codex web/cloud, con webhook GitHub privato come deploy standard senza Actions e deploy manuale come fallback.
- [RELEASE_PROCESS.md](./RELEASE_PROCESS.md): checklist di rilascio e deploy.
- [VERSIONING.md](./VERSIONING.md): policy ufficiale per versioni, changelog e release.
- [ONE_DOT_ZERO_READINESS.md](./ONE_DOT_ZERO_READINESS.md): criteri, checklist e record della promozione DocMolder a `1.0.0`.
- [OPERATIONS_SECURITY.md](./OPERATIONS_SECURITY.md): sicurezza operativa, segreti, log, backup e incident response.
- [SERVICE_GOVERNANCE.md](./SERVICE_GOVERNANCE.md): dati trattati, retention, cancellazione e limiti del servizio.
- [SMOKE_TESTS.md](./SMOKE_TESTS.md): strategia post-deploy per smoke test rapidi via Telegram Desktop scriptato e verifica UI mirata.
- [GITHUB_ALIGNMENT.md](./GITHUB_ALIGNMENT.md): setup GitHub e best practice per maintainer singolo.
- [GITHUB_MAINTENANCE.md](./GITHUB_MAINTENANCE.md): checklist periodica GitHub, security e fallback git-safe.

## Prodotto e decisioni

- [BRAND.md](./BRAND.md): identita del prodotto, asset e linee guida di tono/UI.
- [ARCHITECTURE.md](./ARCHITECTURE.md): mappa di moduli, flussi, runtime e limiti architetturali.
- [DATA_MODEL.md](./DATA_MODEL.md): modelli applicativi, tabelle SQLite e stati persistenti.
- [PDF_PIPELINE.md](./PDF_PIPELINE.md): strategia pipeline PDF e fallback.
- [TELEGRAM_OPERATIONS.md](./TELEGRAM_OPERATIONS.md): comandi, deep link, console admin, metriche e hardening del bot Telegram.
- [DECISIONS.md](./DECISIONS.md): decisioni tecniche persistenti.
- [DECISIONS_PENDING.md](./DECISIONS_PENDING.md): decisioni aperte distinte dai task di roadmap.
- [MILESTONE_BOARD.md](./MILESTONE_BOARD.md): milestone locali, dipendenze e deliverable principali.
- [ROADMAP.md](./ROADMAP.md): prossimi blocchi evolutivi.
- [../CHANGELOG.md](../CHANGELOG.md): changelog versionato delle release.

## Contesto persistente

- [CONTEXT.md](./CONTEXT.md): handoff rapido e mappa dei documenti.

# Integrazioni Codex, GitHub e Operations

Questa guida raccoglie le integrazioni operative scelte per sfruttare meglio Codex/GPT nel progetto, senza allargare il perimetro prodotto di DocMolder.

Scope corrente:

- sviluppo Codex e PR workflow;
- GitHub per manutenzione e release;
- osservabilità e operations.

Fuori scope per questa fase:

- AI generativa dentro il bot;
- OCR/API esterne;
- dashboard web;
- storage permanente dei documenti utente.

## 1) Sviluppo Codex

Usa `make codex-dev-report` prima di aprire PR, delegare sub-task o pubblicare.

Il report:

- classifica il diff;
- segnala file release-owned, deploy relevance e dipendenze;
- suggerisce check locali coerenti con il cambio;
- rimanda agli strumenti di handoff e PR.

Per lavori paralleli continua a usare:

- `python3 scripts/agent_start.py --area "<area>" --owner "<owner>"`
- `python3 scripts/agent_parallel_safe.py --owner "<owner>"`
- `python3 scripts/agent_handoff.py ...`

## 2) GitHub manutenzione e release

Usa `make github-maintenance` per il giro periodico o prima di riprendere una PR lunga.

Il report controlla:

- PR aperte;
- Release PR aperte;
- PR Dependabot;
- alert Dependabot leggibili via GitHub API;
- run GitHub Actions fallite recenti.

Regola pratica:

- run failed del branch corrente: investigare prima con `scripts/current_failed_runs.py` e `gh run view`;
- Release PR aperta: verificare versione, changelog e manifest prima del merge;
- PR Dependabot/security: priorità alta se tocca runtime o CVE rilevanti.

## 3) Observability e operations

Usa `make ops-report` in locale o `scripts/ops_report.py --check-service` su VPS.

Il report raccoglie:

- healthcheck applicativo;
- stato systemd quando disponibile;
- warning e alert su runtime, backup e job;
- comandi VPS utili per diagnosi.

Non eseguire restart, deploy, restore o modifiche VPS solo perché il report li suggerisce: per azioni operative serve consenso esplicito e runbook VPS.

## Cadence consigliata

- Prima di PR: `make codex-dev-report`
- Settimanalmente o prima di release: `make github-maintenance`
- Dopo deploy o quando qualcosa sembra degradare: `make ops-report`
- Prima di merge/deploy: `make publish-doctor`

# GitHub Maintenance

Questa guida raccoglie i controlli periodici GitHub che completano i workflow versionati.

## Asset versionati

- CI: `.github/workflows/ci.yml`
- Release Please: `.github/workflows/release-please.yml`
- PR title guard: `.github/workflows/pr-title.yml`
- Release file guard: `.github/workflows/release-policy.yml`
- Main commit guard: `.github/workflows/main-commit-policy.yml`
- Deploy VPS: `.github/workflows/deploy-vps.yml`
- VPS Check: `.github/workflows/vps-check.yml`
- Rollback VPS: `.github/workflows/rollback-vps.yml`
- Dependabot: `.github/dependabot.yml`
- Template PR e issue: `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`
- Ownership: `.github/CODEOWNERS`

`Deploy VPS` non parte per ogni push su `main`: il trigger automatico usa una allowlist di path deploy-relevant (`src/**`, `deploy/**`, packaging e lock/requirements). Per cambi solo docs, test, release note, istruzioni agent, template o workflow GitHub, usare `workflow_dispatch` solo se serve davvero aggiornare la VPS.

## Pubblicazione più fluida

Strumenti locali:

- `scripts/classify_changes.py`: classifica il diff in docs/test/CI/code/ops/deploy e segnala file riservati a `release-please`.
- `scripts/preflight_publish.sh` o `make preflight-publish`: blocca branch sbagliati e version bump/changelog manuali prima del push.
- `scripts/current_failed_runs.py`: mostra solo run failed del branch e SHA correnti, evitando di inseguire failure vecchie o non correlate.
- `scripts/generate_pr_body.py`: genera un body PR coerente con impatto deploy/release e lista file.
- `scripts/publish_change.sh "<titolo conventional>"`: preflight, commit se serve, push, PR draft, check, ready e auto-merge.
- `scripts/cleanup_merged_branches.sh` o `make cleanup-branches`: elimina branch locali `codex/*` già mergiati.

La CI usa lo stesso classificatore: per cambi senza impatto runtime mantiene i check richiesti ma salta install, test Python e package build pesanti.

`Deploy VPS` ha concurrency con `cancel-in-progress: true`, quindi un deploy obsoleto viene cancellato quando arriva un nuovo deploy sullo stesso target. `VPS Check` consente verifiche manuali senza copiare file sulla macchina; `Rollback VPS` redeploya una revisione precedente scelta esplicitamente.

## Configurazione consigliata nella UI GitHub

### Branch protection per `main`

Richiedere almeno:

- pull request prima del merge;
- status check CI verdi;
- titolo PR convenzionale;
- linear history;
- disabilitazione force push e branch deletion.

Se il piano GitHub non permette branch protection completa, trattare i workflow come guardrail e mantenere comunque il flusso branch dedicato, PR e squash merge.

### Security

Abilitare:

- Dependabot alerts;
- Dependabot security updates;
- secret scanning;
- push protection per secret scanning, se disponibile.

### Merge options

Configurazione consigliata:

- abilitare squash merge;
- usare il titolo PR come subject dello squash;
- valutare di disabilitare merge commit e rebase merge.

## Revisione periodica

Frequenza minima mensile:

1. controllare workflow falliti o flakey;
2. verificare PR Dependabot aperte;
3. verificare alert Security e Dependabot;
4. controllare che i ruleset di `main` siano coerenti con il flusso reale;
5. controllare che `release-please` non abbia Release PR bloccate;
6. verificare che i secret VPS e release siano ancora presenti e non scaduti.

## Fallback operativo

Se Git resta bloccato da un `index.lock` stale durante manutenzione locale:

```bash
docmolder-fix-git-lock .
docmolder-git-safe -- status --short
```

Il tool rimuove il lock solo se non risulta detenuto da un processo attivo.

# GitHub Maintenance

Questa guida raccoglie i controlli periodici GitHub che completano i workflow versionati.

## Asset versionati

- CI: `.github/workflows/ci.yml`
- Release Please: `.github/workflows/release-please.yml`
- PR title guard: `.github/workflows/pr-title.yml`
- Release file guard: `.github/workflows/release-policy.yml`
- Main commit guard: `.github/workflows/main-commit-policy.yml`
- Deploy VPS: `.github/workflows/deploy-vps.yml`
- Dependabot: `.github/dependabot.yml`
- Template PR e issue: `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`
- Ownership: `.github/CODEOWNERS`

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

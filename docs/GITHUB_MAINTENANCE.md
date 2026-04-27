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
- VPS Backup: `.github/workflows/vps-backup.yml`
- Rollback VPS: `.github/workflows/rollback-vps.yml`
- Dependabot: `.github/dependabot.yml`
- Template PR e issue: `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`
- Ownership: `.github/CODEOWNERS`

`Deploy VPS` non parte per ogni push su `main`: il trigger automatico usa una allowlist di path deploy-relevant (`src/**`, `deploy/**`, packaging e lock/requirements). Per cambi solo docs, test, release note, istruzioni agent, template o workflow GitHub, il default resta l'aggiornamento manuale della VPS; usa `workflow_dispatch` solo se mi chiedi esplicitamente di passare da GitHub Actions o se il canale manuale non e disponibile.

## Pubblicazione più fluida

Canale GitHub preferito:

- usa dove possibile il tool/plugin GitHub come canale primario per repository, PR, issue, commenti, review, metadata e creazione PR;
- usa `gh` e `git` locali solo per operazioni non coperte bene dal plugin, come branch/commit/push locali, stato auth, log GitHub Actions e inspect di run CI;
- usa `gh pr ready <numero>` per rimuovere lo stato draft: il tool connector `mark_pull_request_ready_for_review` al momento richiede il campo GraphQL `PullRequest.htmlUrl`, che non esiste nello schema GitHub; il campo valido sarebbe `url`;
- quando passi da plugin a CLI, mantieni allineati branch locale, PR corrente e SHA monitorato.

Strumenti locali:

- `scripts/codex_dev_report.py` o `make codex-dev-report`: riepiloga impatto del diff, rischi e check consigliati prima di delegare, aprire PR o pubblicare.
- `scripts/github_maintenance_report.py` o `make github-maintenance`: riepiloga PR aperte, Release PR, PR Dependabot, alert Dependabot leggibili e run Actions fallite recenti.
- `scripts/ops_report.py` o `make ops-report`: produce un report operativo locale/VPS con healthcheck, stato systemd quando disponibile e prossime azioni.
- `scripts/classify_changes.py`: classifica il diff in docs/test/CI/code/ops/deploy e segnala file riservati a `release-please`.
- `scripts/preflight_publish.sh` o `make preflight-publish`: blocca branch sbagliati e version bump/changelog manuali prima del push.
- `scripts/current_failed_runs.py`: mostra solo run failed del branch e SHA correnti, evitando di inseguire failure vecchie o non correlate.
- `scripts/check_codex_bot_comments.py`: blocca ready/merge quando il Codex connector bot ha lasciato commenti aperti sulla PR.
- `scripts/publish_doctor.py` o `make publish-doctor`: verifica in un unico punto branch/base, detached HEAD, divergenza da `origin/main`, file riservati a `release-please`, run failed correnti e commenti bot aperti.
- `scripts/generate_pr_body.py`: genera un body PR coerente con impatto deploy/release e lista file.
- `scripts/publish_change.sh "<titolo conventional>"`: publish doctor, preflight, commit se serve, push, PR draft, check, ready e auto-merge.
- `scripts/cleanup_merged_branches.sh` o `make cleanup-branches`: elimina branch locali `codex/*` già mergiati.

La CI usa lo stesso classificatore, ma non parte automaticamente su push o PR: va avviata manualmente con `workflow_dispatch` solo quando serve un gate remoto. Per cambi senza impatto runtime mantiene i check richiesti ma salta install, test Python e package build pesanti.

`Deploy VPS` ha concurrency con `cancel-in-progress: true`, quindi un deploy obsoleto viene cancellato quando arriva un nuovo deploy sullo stesso target. `VPS Check` consente verifiche manuali senza copiare file sulla macchina; `VPS Backup` crea un backup SQLite verificato senza deployare file; `Rollback VPS` redeploya una revisione precedente scelta esplicitamente.

### Corsie di pubblicazione

Prima di qualunque publish da Codex:

```bash
git fetch origin main
git switch -c codex/<scope> origin/main
make publish-doctor
```

Usa poi una sola corsia, dichiarandola nella risposta finale:

- **Docs minuscoli diretti**: solo `AGENTS.md`, `README.md` o `docs/**`, titolo `chore(docs): ...`, nessun deploy/release atteso. Da `main` aggiornato usa `make publish-docs TITLE="chore(docs): <descrizione>"`: lo script esegue publish doctor, preflight, commit e push diretto senza PR. Evita questa corsia se il cambio tocca workflow, script, codice runtime, configurazione, release-owned files o istruzioni operative ambigue.
- **PR standard**: default per codice, CI, script, test, configurazione e docs operative non banali. Usa `scripts/publish_change.sh "<titolo conventional>"`.
- **PR + deploy/release follow-through**: solo quando il classificatore indica `deploy_relevant` o il titolo produce release. Tratta PR funzionale, Release PR e Deploy VPS come fasi separate da monitorare, non come un unico errore indistinto.

Se `publish_doctor` segnala branch indietro/divergente, detached HEAD, run failed correnti o commenti bot aperti, correggi quello prima di creare o aggiornare la PR.

## CI manuale a consumo ridotto

Il workflow `CI` resta disponibile solo manualmente per contenere il consumo di minuti Actions. Prima di aprire o mergiare una PR, esegui di norma i gate locali rilevanti (`make ci`, `make test` o suite mirate); avvia la CI remota solo per cambi rischiosi, release candidate o quando serve una verifica su runner GitHub. L'input manuale `full_tests` e attivo di default e forza quality gate, matrix test e package build anche quando il diff non li richiederebbe.

Il workflow è diviso in gate indipendenti:

- `Classify change impact`: decide se servono test completi, package build, coverage e deploy.
- `Fast gate`: controlli statici rapidi su workflow, shell script, script Python e whitespace.
- `Quality gate`: compile e lint una sola volta su Python 3.12, solo per cambi runtime/test.
- `Python 3.11/3.12/3.13`: test completi solo per cambi runtime/test; coverage solo su Python 3.12.
- `package-build`: build del pacchetto solo per cambi a `src/**`, packaging o dipendenze.

`CodeQL` mantiene il check su PR/main, ma l'analisi pesante parte solo per cambi a codice o dipendenze, oltre a schedule settimanale e manuale. `Dependency Review` mantiene il check su PR, ma l'action parte solo quando la PR tocca file di dipendenze (`pyproject.toml`, lock/requirements).

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

1. eseguire `make github-maintenance`;
2. controllare workflow falliti o flakey;
3. verificare PR Dependabot aperte;
4. verificare alert Security e Dependabot;
5. controllare che i ruleset di `main` siano coerenti con il flusso reale;
6. controllare che `release-please` non abbia Release PR bloccate;
7. verificare che i secret VPS e release siano ancora presenti e non scaduti.

## Fallback operativo

Se Git resta bloccato da un `index.lock` stale durante manutenzione locale:

```bash
docmolder-fix-git-lock .
docmolder-git-safe -- status --short
```

Il tool rimuove il lock solo se non risulta detenuto da un processo attivo.

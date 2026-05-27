# GitHub Maintenance

Questa guida raccoglie i controlli periodici GitHub che completano i workflow versionati.

## Asset versionati

- CI: `.github/workflows/ci.yml`
- CodeQL: `.github/workflows/codeql.yml`
- Dependabot Auto Merge: `.github/workflows/dependabot-auto-merge.yml`
- GitHub Maintenance: `.github/workflows/github-maintenance.yml`
- Release Please: `.github/workflows/release-please.yml`
- Release Sanity: `.github/workflows/release-sanity.yml`
- Deploy VPS: `.github/workflows/deploy-vps.yml`
- VPS Check: `.github/workflows/vps-check.yml`
- VPS Backup: `.github/workflows/vps-backup.yml`
- Rollback VPS: `.github/workflows/rollback-vps.yml`
- Update VPS Env: `.github/workflows/update-vps-env.yml`
- Codex PR comments: `.github/workflows/codex-pr-comments.yml`
- Dependabot: `.github/dependabot.yml`
- Codex feedback handler: `.github/scripts/handle-codex-pr-comments.mjs`
- Template PR e issue: `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`
- Ownership: `.github/CODEOWNERS`

L'automazione ordinaria resta prudente: `CI` parte sulle PR non draft verso `main`, `Release Please` parte sui push a `main`, `Codex PR comments` sincronizza la issue `Codex feedback inbox`, `VPS Check` gira una volta a settimana e `GitHub Maintenance` una volta al mese. `Deploy VPS`, `VPS Backup`, `Rollback VPS`, `Update VPS Env`, `Release Sanity` e `CodeQL` restano manuali; i guardrail locali (`make publish-doctor`, `make preflight-publish`, `bash scripts/ci_verify.sh`) restano il primo filtro prima del push.

Il deploy automatico resta affidato al servizio `docmolder-github-webhook` sulla VPS. Dopo il deploy, il listener può ancora lanciare `deploy/auto-release.sh`, ma nel flusso standard deve restare disabilitato con `DOCMOLDER_AUTO_RELEASE_ENABLED=false`: versioni, changelog, tag e GitHub Release spettano a `Release Please`.

## Pubblicazione più fluida

Canale GitHub preferito:

- usa dove possibile il tool/plugin GitHub come canale primario per repository, PR, issue, commenti, review, metadata e creazione PR;
- usa `gh` e `git` locali solo per operazioni non coperte bene dal plugin, come branch/commit/push locali, stato auth, log GitHub Actions e inspect di run CI;
- usa `gh pr ready <numero>` solo per PR create esplicitamente come draft; il percorso standard crea PR già pronte;
- quando passi da plugin a CLI, mantieni allineati branch locale, PR corrente e SHA monitorato.

Strumenti locali:

- `scripts/codex_dev_report.py` o `make codex-dev-report`: riepiloga impatto del diff, rischi e check consigliati prima di delegare, aprire PR o pubblicare.
- `scripts/github_maintenance_report.py` o `make github-maintenance`: riepiloga PR aperte, Release PR, PR Dependabot, alert Dependabot leggibili, run Actions fallite recenti e issue `Codex feedback inbox`.
- `scripts/ops_report.py` o `make ops-report`: produce un report operativo locale/VPS con healthcheck, stato systemd quando disponibile e prossime azioni.
- `scripts/classify_changes.py`: classifica il diff in docs/test/CI/code/ops/deploy e segnala file riservati a `release-please`.
- `scripts/preflight_publish.sh` o `make preflight-publish`: blocca branch sbagliati e version bump/changelog manuali prima del push.
- `scripts/current_failed_runs.py`: mostra solo run failed del branch e SHA correnti, evitando di inseguire failure vecchie o non correlate.
- `scripts/check_codex_bot_comments.py`: blocca ready/merge quando il Codex connector bot ha lasciato commenti aperti sulla PR.
- `scripts/publish_doctor.py` o `make publish-doctor`: verifica in un unico punto branch/base, detached HEAD, divergenza da `origin/main`, file riservati a `release-please`, run failed correnti e commenti bot aperti.
- `scripts/generate_pr_body.py`: genera un body PR coerente con impatto deploy/release e lista file.
- `scripts/publish_change.sh "<titolo conventional>"`: publish doctor, preflight, commit se serve, push e PR pronta; con `DOCMOLDER_PUBLISH_DRAFT=1` apri una draft esplicita, con `DOCMOLDER_PUBLISH_MERGE=1` chiedi merge assistito local-first, con `DOCMOLDER_USE_GH_ACTIONS=1` riattivi il fallback legacy watch/check/ready/auto-merge.
- `scripts/auto_release.py`: fallback spento di default per creare release senza Actions da una checkout pulita, aggiornando changelog, manifest, versioni, tag e GitHub Release.
- `scripts/release_sanity.py` o `make release-sanity`: controlla allineamento tra manifest Release Please, versione pacchetto, `__version__`, changelog e ultimo tag locale.
- `make install-hooks`: installa i hook Git locali che eseguono i controlli prima del push.
- `docmolder-github-webhook.service`: listener systemd sulla VPS che riceve il webhook GitHub privato e lancia il deploy.
- `scripts/cleanup_merged_branches.sh` o `make cleanup-branches`: elimina branch locali `codex/*` già mergiati.

La CI usa lo stesso classificatore e parte automaticamente sulle PR non draft verso `main`. Per cambi senza impatto runtime mantiene i check richiesti ma salta install, test Python e package build pesanti. L'esecuzione manuale con `workflow_dispatch` resta disponibile per un gate remoto esplicito; l'input `full_tests` forza quality gate, matrix test e package build.

`Deploy VPS` ha concurrency con `cancel-in-progress: true`, quindi un deploy obsoleto viene cancellato quando arriva un nuovo deploy sullo stesso target. `VPS Check` consente verifiche manuali senza copiare file sulla macchina; `VPS Backup` crea un backup SQLite verificato senza deployare file; `Rollback VPS` redeploya una revisione precedente scelta esplicitamente. `Update VPS Env` resta un fallback manuale Actions per piccoli cambi di configurazione quando non è pratico entrare sulla VPS; il percorso normale resta modifica controllata via SSH/runbook, senza consumare Actions.

### Corsie di pubblicazione

Prima di qualunque publish da Codex:

```bash
git fetch origin main
git switch -c codex/<scope> origin/main
make publish-doctor
```

Usa poi una sola corsia, dichiarandola nella risposta finale:

- **Docs minuscoli diretti**: solo `AGENTS.md`, `README.md` o `docs/**`, titolo `chore(docs): ...`, nessun deploy/release atteso. Da `main` aggiornato usa `make publish-docs TITLE="chore(docs): <descrizione>"`: lo script esegue publish doctor, preflight, commit e push diretto senza PR. Evita questa corsia se il cambio tocca workflow, script, codice runtime, configurazione, release-owned files o istruzioni operative ambigue.
- **PR standard**: default per codice, CI, script, test, configurazione e docs operative non banali. Usa `scripts/publish_change.sh "<titolo conventional>"`, poi review/merge e verifica webhook VPS.
- **PR draft esplicita**: usa `DOCMOLDER_PUBLISH_DRAFT=1 scripts/publish_change.sh "<titolo conventional>"` solo quando vuoi aprire review anticipata senza dichiarare il cambio pronto.
- **PR + deploy/release follow-through**: solo quando il classificatore indica `deploy_relevant` o il titolo produce release. Dopo il merge controlla webhook VPS, servizio, log recenti e la Release PR aggiornata da `Release Please`.

Se `publish_doctor` segnala branch indietro/divergente, detached HEAD, run failed correnti o commenti bot aperti, correggi quello prima di creare o aggiornare la PR.

### Codex feedback inbox

La gestione globale dei commenti Codex vive in GitHub, non in file di stato del repository.

Il workflow `Codex PR comments`:

- parte su eventi PR trusted, commenti issue, `workflow_dispatch` e scansione programmata ogni 6 ore;
- esegue lo script dalla default branch trusted;
- aggiorna o crea la issue unica `Codex feedback inbox`;
- chiude eventuali inbox duplicate;
- separa thread actionable e storico compatto;
- pubblica `@codex address that feedback` sulle PR con thread actionable.

Per la PR corrente resta valido il guardrail locale:

```bash
python3 scripts/check_codex_bot_comments.py --pr <numero> --fail
```

Quando la inbox segnala feedback actionable, il prossimo passo in chat deve essere esplicito: risolvere nella PR corrente se coerente, aprire una PR correttiva mirata se la PR originale e chiusa/mergiata, oppure dichiarare il falso positivo/non azionabile.

## CI automatica a consumo ridotto

Il workflow `CI` parte sulle PR non draft verso `main`, con job condizionali per contenere il consumo di minuti Actions. Prima di aprire o aggiornare una PR, esegui comunque i gate locali rilevanti (`make ci`, `make test` o suite mirate); l'input manuale `full_tests` è disattivo di default e forza quality gate, matrix test e package build solo quando viene selezionato.

Il workflow è diviso in gate indipendenti:

- `Classify change impact`: decide se servono test completi, package build, coverage e deploy.
- `PR policy`: valida titolo Conventional Commit e blocca file release-owned nelle PR normali, lasciandoli passare nelle Release PR di `Release Please`; non duplicarlo con un workflow `pr-title.yml` separato.
- `Dependency review`: parte solo su PR con cambi a dipendenze; sui repository privati richiede GitHub Code Security/GHAS, quindi resta disattivata salvo repository variable `DOCMOLDER_ENABLE_DEPENDENCY_REVIEW=true`.
- `Fast gate`: controlli statici rapidi su workflow, shell script, script Python e whitespace.
- `Quality gate`: compile e lint una sola volta su Python 3.13, solo per cambi runtime/test.
- `Python 3.11/3.12/3.13`: test completi solo per cambi runtime/test; coverage solo su Python 3.13.
- `package-build`: build del pacchetto solo per cambi a `src/**`, packaging o dipendenze.
- `CI result`: job finale unico da usare come status check required in branch protection.

`Dependabot Auto Merge` marca come candidate solo le PR Dependabot non draft verso `main` con aggiornamenti non-major e non `direct:production`, salvo `github-actions`. Il merge avviene solo dopo una run `CI` riuscita e solo se lo SHA verificato coincide con la testa corrente della PR.

`CodeQL` resta disponibile solo su avvio esplicito con `workflow_dispatch`, scegliendo una ragione come `security-window`, `release-candidate`, `security-sensitive-change` o `manual-investigation`. `Main Commit Policy` e `Release Policy` restano assorbiti dai controlli locali e dal gate `PR policy`.

## Release Please primario

`Release Please` parte su ogni push a `main`: apre o aggiorna la Release PR quando trova commit rilasciabili e crea tag/GitHub Release quando la Release PR viene mergiata. La Release PR è l'unico percorso ordinario per aggiornare `CHANGELOG.md`, `.release-please-manifest.json`, `pyproject.toml` e `src/docmolder/__init__.py`.

`deploy/auto-release.sh` resta nel repository come fallback operativo, ma deve restare disabilitato sulla VPS con `DOCMOLDER_AUTO_RELEASE_ENABLED=false`. Se lo si riabilita per emergenza, farlo solo dopo aver sospeso o escluso il flusso Release Please per evitare doppi bump, tag o release.

`Release Sanity` è un dispatch manuale leggero prima o dopo una Release PR: verifica che manifest, changelog, `pyproject.toml`, `src/docmolder/__init__.py` e tag locale siano coerenti.

## Configurazione consigliata nella UI GitHub

### Branch protection per `main`

Richiedere almeno:

- pull request prima del merge;
- `CI result` come unico status check Actions obbligatorio sulle PR non draft, se branch protection e disponibile sul piano/account;
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

1. eseguire `make github-maintenance` o leggere il workflow mensile `GitHub Maintenance`;
2. controllare workflow falliti o flakey su `CI` e `Release Please`;
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

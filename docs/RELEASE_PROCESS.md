# Release Process

Questa guida descrive il processo standard per portare una modifica da PR a release e deploy.

## Indice

- [Prima della PR](#prima-della-pr)
- [PR e merge](#pr-e-merge)
- [Release](#release)
- [Verifica locale](#verifica-locale)
- [Deploy](#deploy)

## Prima della PR

Verifica almeno:

- branch di lavoro creata da `origin/main`, non `HEAD detached`
- `make publish-doctor` senza blocker per intercettare base vecchia, run failed correnti, commenti bot aperti e file riservati a `release-please`
- codice coerente con il comportamento voluto
- test rilevanti verdi
- classificazione del diff con `scripts/classify_changes.py` o `make preflight-publish`
- documentazione aggiornata se cambia il flusso utente o operativo
- se cambia il catalogo azioni o la struttura dei job, aggiorna anche contesto, testing e decisioni tecniche correlate
- roadmap aggiornata solo se cambia il piano futuro
- nessun aggiornamento manuale di `CHANGELOG.md`, `.release-please-manifest.json`, campo `version` di `pyproject.toml` o `src/docmolder/__init__.py`, salvo commit di release automatico o correzioni eccezionali del flusso

## PR e merge

Regole operative essenziali:

- branch focalizzati su una singola modifica logica
- nessun push diretto su `main`
- PR con titolo in formato Conventional Commits
- squash merge su `main`
- eccezione: modifiche minuscole solo documentali (`chore(docs):`, limitate a `AGENTS.md`, `README.md` o `docs/**`) si pubblicano direttamente da `main` con `make publish-docs TITLE="chore(docs): <descrizione>"`, che esegue preflight/check mirati e salta branch/PR
- niente bump manuali di versione o changelog nelle PR normali
- per il flusso completo "carica", usare `scripts/publish_change.sh "<titolo conventional>"` quando possibile; in modalita senza GitHub Actions il comando si ferma dopo la creazione della PR e lascia il merge finale al maintainer. Dopo il merge su `main`, il webhook VPS gestisce deploy e release automatica se abilitata. Se vuoi riattivare il vecchio auto-follow-up via Actions, esporta `DOCMOLDER_USE_GH_ACTIONS=1`
- prima di aprire o aggiornare la PR, usare `scripts/publish_doctor.py --fail` o affidarsi a `scripts/publish_change.sh`, che lo esegue automaticamente
- prima di inseguire una run failed, controllare solo branch e SHA correnti con `scripts/current_failed_runs.py`
- i dettagli della policy vivono in [VERSIONING.md](./VERSIONING.md)

Formato atteso:

```text
<type>(optional-scope)!: breve descrizione
```

Esempi di titolo:

- `feat(history): improve result follow-up actions`
- `fix(pdf): preserve clearer error for protected files`
- `docs(release): explain release bootstrap`

I workflow GitHub fanno da guardrail solo quando li avvii esplicitamente. `CI` resta manuale-only per ridurre il consumo Actions; la fonte primaria della policy resta [VERSIONING.md](./VERSIONING.md).

## Release

Il flusso ufficiale senza GitHub Actions e:

1. merge della PR su `main`
2. il webhook privato GitHub -> VPS esegue il deploy
3. dopo un deploy riuscito, `deploy/auto-release.sh` esegue `scripts/auto_release.py` se `/etc/docmolder/release.env` abilita la release automatica
4. se ci sono commit rilasciabili dal tag precedente, la VPS crea commit di release, tag `docmolder-vX.Y.Z` e GitHub Release
5. il push del commit di release riattiva il webhook e redeploya la versione con bump/changelog, senza generare una nuova release

Il changelog ufficiale e [../CHANGELOG.md](../CHANGELOG.md).

Non usare piu il vecchio flusso di aggiornamento manuale del changelog per ogni modifica ordinaria.
Non fare bump versione manuali nelle PR normali.

`Release Please` non parte automaticamente. Resta eseguibile manualmente con `workflow_dispatch` solo come fallback esplicito se vuoi consumare Actions; il percorso automatico normale e quello VPS senza Actions.

## Verifica locale

Per cambi rilevanti:

```bash
.venv/bin/python -m unittest discover -s tests
```

Per cambi mirati, puoi eseguire solo le suite toccate.

Per riprodurre localmente i gate GitHub separati:

```bash
make ci-static
make ci-quality
make ci-test
make build
```

`make ci` resta il gate locale completo e include anche il package build. Su GitHub, invece, test, coverage e build vengono eseguiti solo quando il classificatore li considera necessari.

## Deploy

La procedura operativa completa e in [docs/VPS_RUNBOOK.md](./VPS_RUNBOOK.md).
La strategia di smoke test post-deploy e in [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
Il flusso GitHub/Codex per lavorare senza Mac locale e in [docs/CODEX_CLOUD_DEPLOY.md](./CODEX_CLOUD_DEPLOY.md).

In breve:

1. per deploy standard da remoto, lasciare che il webhook privato GitHub -> VPS aggiorni la VPS su push a `main`
2. in alternativa, aggiornare manualmente la VPS con `sudo /opt/docmolder/app/deploy/update-vps.sh`
3. verificare che, quando ci sono commit rilasciabili, la release automatica crei tag e GitHub Release coerenti
4. per controlli senza deploy, usare `VPS Check` solo come fallback esplicito
5. per ripristino esplicito, usare `Rollback VPS` con tag o SHA precedente
6. controllare stato servizio, timer backup SQLite, log recenti e revisione live
7. verificare che i backup SQLite siano attivi o lanciare almeno un backup manuale se hai toccato persistenza o runbook
8. eseguire almeno uno smoke test coerente con il tipo di modifica:
   - Livello 1 per fix tecnici
   - Livello 1 + 2 per cambi funzionali
   - Livello 1 + 2 + una verifica UI per cambi UX sensibili

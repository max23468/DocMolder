# Release Process

Questa guida descrive il processo standard per portare una modifica da PR a release e deploy.
Il percorso ordinario e local-first: controlli locali, PR pronta, merge su
`main`, webhook VPS.

## Indice

- [Prima della PR](#prima-della-pr)
- [PR e merge](#pr-e-merge)
- [Release](#release)
- [Verifica locale](#verifica-locale)
- [Deploy](#deploy)

## Prima della PR

Percorso standard:

1. lavora su branch dedicata da `origin/main`, non in `HEAD detached`
2. esegui i test locali rilevanti per il cambio
3. pubblica con `scripts/publish_change.sh "<titolo conventional>"`
4. fai review/merge della PR pronta
5. dopo il merge, verifica webhook VPS, deploy e auto-release

`publish_change.sh` esegue gia `publish_doctor`, `preflight_publish`, commit
se necessario, push, generazione body PR e controllo commenti Codex connector.
Non aspettare GitHub Actions nel flusso ordinario.

Prima del merge resta valido il divieto di modificare manualmente
`CHANGELOG.md`, `.release-please-manifest.json`, il campo `version` di
`pyproject.toml` o `src/docmolder/__init__.py`, salvo commit di release
automatico o manutenzione esplicita del flusso.

## PR e merge

Regole operative essenziali:

- branch focalizzati su una singola modifica logica
- nessun push diretto su `main`
- PR con titolo in formato Conventional Commits
- squash merge su `main`
- eccezione: modifiche minuscole solo documentali (`chore(docs):`, limitate a `AGENTS.md`, `README.md` o `docs/**`) si pubblicano direttamente da `main` con `make publish-docs TITLE="chore(docs): <descrizione>"`, che esegue preflight/check mirati e salta branch/PR
- niente bump manuali di versione o changelog nelle PR normali
- per il flusso completo "carica", usare `scripts/publish_change.sh "<titolo conventional>"`: di default crea una PR pronta, non draft, e si ferma con il prossimo passo operativo
- usa `DOCMOLDER_PUBLISH_DRAFT=1` solo quando vuoi aprire una PR draft esplicita
- usa `DOCMOLDER_PUBLISH_MERGE=1` solo quando vuoi un merge assistito dopo gate locali e controllo commenti bot
- usa `DOCMOLDER_USE_GH_ACTIONS=1` solo come fallback legacy raro per watch/check/ready/auto-merge basato su Actions
- prima di aprire o aggiornare una PR puoi usare `scripts/publish_doctor.py --fail`, ma il comando di publish lo esegue gia automaticamente
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

I workflow GitHub fanno da guardrail solo quando li avvii esplicitamente.
`CI` resta manuale-only per ridurre il consumo Actions; la fonte primaria della
policy resta [VERSIONING.md](./VERSIONING.md).

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

`Release Please` non parte automaticamente. Resta eseguibile manualmente con
`workflow_dispatch` solo come fallback esplicito se vuoi consumare Actions; il
percorso automatico normale e quello VPS senza Actions.

## Verifica locale

Per cambi rilevanti:

```bash
.venv/bin/python -m unittest discover -s tests
```

Per cambi mirati, puoi eseguire solo le suite toccate.

Per riprodurre localmente i gate GitHub separati, solo quando serve:

```bash
make ci-static
make ci-quality
make ci-test
make build
```

`make ci` resta il gate locale completo e include anche il package build. Su
GitHub, invece, i workflow sono fallback manuali e non fanno parte del percorso
quotidiano.

## Deploy

La procedura operativa completa e in [docs/VPS_RUNBOOK.md](./VPS_RUNBOOK.md).
La strategia di smoke test post-deploy e in [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
Il flusso GitHub/Codex per lavorare senza Mac locale e in [docs/CODEX_CLOUD_DEPLOY.md](./CODEX_CLOUD_DEPLOY.md).

In breve:

1. per deploy standard da remoto, lasciare che il webhook privato GitHub -> VPS aggiorni la VPS su push a `main`
2. controllare servizio, log recenti e revisione live
3. verificare che, quando ci sono commit rilasciabili, la release automatica crei tag e GitHub Release coerenti
4. eseguire lo smoke test coerente con il tipo di modifica
5. usare deploy manuale, `VPS Check` o `Rollback VPS` solo come fallback espliciti

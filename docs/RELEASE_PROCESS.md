# Release Process

Questa guida descrive il processo standard per portare una modifica da PR a release e deploy.
Il percorso ordinario resta local-first per lo sviluppo, con guardrail GitHub
prudente: controlli locali, PR pronta, `CI result`, merge su `main` e webhook VPS.

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
4. fai self-review e merge della PR pronta (in contesto maintainer singolo non richiedere approvazione esterna)
5. dopo il merge, verifica webhook VPS e deploy del commit funzionale
6. se la modifica richiede release, esegui `Release Please`, verifica tag, GitHub Release, deploy del commit di release e smoke/health VPS

`publish_change.sh` esegue già `publish_doctor`, `preflight_publish`, commit
se necessario, push, generazione body PR e controllo commenti Codex connector.
Non aspettare workflow operativi GitHub nel flusso ordinario; sulle PR non draft
verso `main` deve però passare `CI result`.

Prima del merge resta valido il divieto di modificare manualmente
`CHANGELOG.md`, il campo `version` di
`pyproject.toml` o `src/docmolder/__init__.py`, salvo commit di release
manuale (`Release Please`) o manutenzione esplicita del flusso.

## PR e merge

Regole operative essenziali:

- branch focalizzati su una singola modifica logica
- nessun push diretto su `main` (salvo eccezioni esplicitamente documentate)
- PR con titolo in formato Conventional Commits
- squash merge su `main`
- la review esterna non è requisito formale nel contesto maintainer singolo: si richiedono self-review, CI locale e `CI result` secondo il flusso.
- eccezione: modifiche minuscole solo documentali (`chore(docs):`, limitate a `AGENTS.md`, `README.md` o `docs/**`) si pubblicano direttamente da `main` con `make publish-docs TITLE="chore(docs): <descrizione>"`, che esegue preflight/check mirati e salta branch/PR
- niente bump manuali di versione o changelog nelle PR normali
- per il flusso completo "carica", usare `scripts/publish_change.sh "<titolo conventional>"`: di default crea una PR pronta, non draft, e si ferma con il prossimo passo operativo
- usa `DOCMOLDER_PUBLISH_DRAFT=1` solo quando vuoi aprire una PR draft esplicita
- usa `DOCMOLDER_PUBLISH_MERGE=1` solo quando vuoi un merge assistito dopo gate locali e controllo commenti bot
- usa `DOCMOLDER_USE_GH_ACTIONS=1` solo se vuoi il fallback legacy locale di watch/check/ready/auto-merge basato su Actions
- prima di aprire o aggiornare una PR puoi usare `scripts/publish_doctor.py --fail`, ma il comando di publish lo esegue già automaticamente
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

`CI` parte automaticamente sulle PR non draft verso `main`, ma resta prudente:
i job pesanti scattano solo quando il classificatore vede impatto runtime/test o
quando `workflow_dispatch` forza `full_tests`.

## Release

Il flusso ufficiale con `Release Please` è:

1. merge della PR su `main`
2. il webhook privato GitHub -> VPS esegue il deploy del commit funzionale
3. avvia il comando `Release Please` dal `main` aggiornato
4. lo script aggiorna `CHANGELOG.md`, versioni e tag `docmolder-vX.Y.Z`, crea la GitHub Release
5. il webhook VPS deploya anche il commit di release con bump/changelog

Quando una richiesta dell'utente implica pubblicare una modifica rilasciabile,
il lavoro non è concluso al solo merge della PR funzionale. L'agente deve
proseguire fino alla fase di release con `Release Please` e alla verifica della
release ufficiale (tag, GitHub Release, deploy, smoke/health), salvo istruzione
esplicita di fermarsi prima o blocco reale da riportare.

Il changelog ufficiale e [../CHANGELOG.md](../CHANGELOG.md).

Non usare più il vecchio flusso di aggiornamento manuale del changelog per ogni modifica ordinaria.
Non fare bump versione manuali nelle PR normali.
Il rilascio legacy con script esterni non fa parte del percorso operativo corrente.

### Release major `X.0.0`

Prima di pianificare una release `X.0.0`, applica il criterio in
[VERSIONING.md](./VERSIONING.md#criterio-per-release-major-x00).

In pratica:

1. apri o usa una PR dedicata alla preparazione della major;
2. aggiungi nel corpo PR una sezione `Major release rationale`;
3. chiarisci quali contratti cambiano o vengono dichiarati stabili: UX utente,
   dati/sicurezza, operatività, deploy/release o perimetro prodotto;
4. completa smoke e rollback coerenti con il rischio della major;
5. se serve una major intenzionale, definisci il target in `Release Please`
   prima del merge della PR finale;
6. verifica che esistano tag `X.0.0`, GitHub Release e che il commit di release
   sia stato deployato.

Se la motivazione è solo "abbiamo accumulato abbastanza feature", resta una
minor release. Se il cambio è solo interno e compatibile, resta patch/minor
secondo il tipo Conventional Commit.

### Promozione 1.0

DocMolder è già nella linea stabile `1.x`. Le note storiche e la checklist
restano in [ONE_DOT_ZERO_READINESS.md](./ONE_DOT_ZERO_READINESS.md); nuove major
 seguono la regola `X.0.0` sopra e il flusso manuale con `Release Please`.

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
GitHub, `CI result` è il gate remoto prudente per le PR non draft verso `main`.

## Deploy

La procedura operativa completa è in [docs/VPS_RUNBOOK.md](./VPS_RUNBOOK.md).
La strategia di smoke test post-deploy è in [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
Il flusso GitHub/Codex per lavorare senza Mac locale è in [docs/CODEX_CLOUD_DEPLOY.md](./CODEX_CLOUD_DEPLOY.md).

In breve:

1. per deploy standard da remoto, lasciare che il webhook privato GitHub -> VPS aggiorni la VPS su push a `main`
2. controllare servizio, log recenti e revisione live
3. verificare che, quando ci sono commit rilasciabili, `Release Please` crei tag e GitHub Release coerenti
4. eseguire lo smoke test coerente con il tipo di modifica
5. usare deploy manuale, `VPS Check` o `Rollback VPS` solo come fallback espliciti

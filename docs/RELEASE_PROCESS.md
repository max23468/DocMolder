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

- codice coerente con il comportamento voluto
- test rilevanti verdi
- documentazione aggiornata se cambia il flusso utente o operativo
- se cambia il catalogo azioni o la struttura dei job, aggiorna anche contesto, testing e decisioni tecniche correlate
- roadmap aggiornata solo se cambia il piano futuro
- nessun aggiornamento manuale del changelog di release, salvo bootstrap o correzioni eccezionali

## PR e merge

Preferenze:

- branch focalizzati su una singola modifica logica
- nessun push diretto su `main`
- PR con titolo in formato Conventional Commits
- squash merge su `main`
- evitare merge commit o rebase merge per le PR normali, cosi il titolo della PR resta la singola fonte di verita per la release

Formato atteso:

```text
<type>(optional-scope)!: breve descrizione
```

Esempi:

- `feat(history): improve result follow-up actions`
- `fix(pdf): preserve clearer error for protected files`
- `docs(release): explain release bootstrap`

La policy completa di bump versione e in [VERSIONING.md](./VERSIONING.md).

## Release

Il flusso ufficiale e:

1. merge della PR su `main`
2. esecuzione del workflow `Release Please`
3. apertura o aggiornamento automatico della Release PR
4. revisione finale della Release PR con versione e changelog generati
5. merge della Release PR
6. creazione automatica di tag Git e GitHub Release

Il changelog ufficiale e [../CHANGELOG.md](../CHANGELOG.md).

Non usare piu il vecchio flusso di aggiornamento manuale del changelog per ogni modifica ordinaria.

## Verifica locale

Per cambi rilevanti:

```bash
.venv/bin/python -m unittest discover -s tests
```

Per cambi mirati, puoi eseguire solo le suite toccate.

## Deploy

La procedura operativa completa e in [docs/VPS_RUNBOOK.md](./VPS_RUNBOOK.md).
La strategia di smoke test post-deploy e in [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).

In breve:

1. verificare che la release da deployare esista su GitHub con tag coerente
2. aggiornare la VPS con `sudo /opt/docmolder/app/deploy/update-vps.sh`
3. controllare stato servizio, timer backup SQLite, log recenti e revisione live
4. verificare che i backup SQLite siano attivi o lanciare almeno un backup manuale se hai toccato persistenza o runbook
5. eseguire almeno uno smoke test coerente con il tipo di modifica:
   - Livello 1 per fix tecnici
   - Livello 1 + 2 per cambi funzionali
   - Livello 1 + 2 + una verifica UI per cambi UX sensibili

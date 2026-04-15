# Release Process

Questa guida descrive un processo semplice per chiudere una modifica rilevante e portarla in deploy.

## Indice

- [Prima del commit finale](#prima-del-commit-finale)
- [Commit](#commit)
- [Changelog](#changelog)
- [Verifica locale](#verifica-locale)
- [Deploy](#deploy)

## Prima del commit finale

Verifica almeno:

- codice coerente con il comportamento voluto
- test rilevanti verdi
- documentazione aggiornata se cambia il flusso utente o operativo
- se cambia il catalogo azioni o la struttura dei job, aggiorna anche contesto, testing e decisioni tecniche correlate
- roadmap aggiornata solo se cambia il piano futuro
- changelog aggiornato solo per modifiche gia effettive e rilevanti

## Commit

Preferenze:

- commit piccoli e descrivibili con una frase chiara
- documentazione separata dal codice quando ha senso
- evitare commit che mischiano fix, refactor e WIP non collegati
- eseguire `commit` e `push` in sequenza, mai in parallelo
- dopo il `commit`, verificare che `git status` sia pulito prima del `push`
- dopo il `push`, verificare che il remote abbia ricevuto davvero l'ultimo commit locale

## Changelog

Aggiorna [docs/CHANGELOG.md](./CHANGELOG.md) quando:

- cambia il comportamento percepito dall'utente
- cambia un flusso operativo importante
- viene introdotto un miglioramento tecnico rilevante

Non usarlo per:

- idee future
- backlog o desiderata
- elementi ancora solo in roadmap

## Verifica locale

Per cambi rilevanti:

```bash
.venv/bin/python -m unittest discover -s tests
```

Per cambi mirati, puoi eseguire solo le suite toccate.

## Deploy

La procedura operativa completa e in [docs/VPS_RUNBOOK.md](./VPS_RUNBOOK.md).

In breve:

1. eseguire il `push` dell'ultimo commit locale e verificare che sia andato a buon fine
2. aggiornare la VPS con `sudo /opt/docmolder/app/deploy/update-vps.sh`
3. controllare stato servizio, log recenti e revisione live
4. testare il bot da Telegram quando il cambiamento tocca l'esperienza utente o i flussi reali

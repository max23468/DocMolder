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
- roadmap aggiornata solo se cambia il piano futuro
- changelog aggiornato solo per modifiche gia effettive e rilevanti

## Commit

Preferenze:

- commit piccoli e descrivibili con una frase chiara
- documentazione separata dal codice quando ha senso
- evitare commit che mischiano fix, refactor e WIP non collegati

## Changelog

Aggiorna [docs/CHANGELOG.md](/Users/Matteo/Documents/DocMolder/docs/CHANGELOG.md) quando:

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

La procedura operativa completa e in [docs/DEPLOY_ORACLE.md](/Users/Matteo/Documents/DocMolder/docs/DEPLOY_ORACLE.md).

In breve:

1. aggiornare la VPS con `sudo /opt/docmolder/app/deploy/update-vps.sh`
2. reinstallare il progetto nel virtualenv se serve
3. riavviare il servizio
4. controllare i log
5. testare il bot da Telegram

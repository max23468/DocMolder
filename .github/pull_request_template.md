## Contesto
<!-- Problema o esigenza che questa PR risolve. -->

## Soluzione adottata
<!-- Scelte principali implementate. -->

## Titolo PR
<!-- Usa un titolo in formato Conventional Commits, ad esempio: feat(bot): add restart action -->
<!-- Il titolo entra nel changelog: descrivi il cambiamento rilasciabile, non il lavoro interno. -->

## Release note
<!-- Se questa PR deve produrre una release, scrivi 1-3 frasi leggibili da utenti/admin/maintainer. -->
<!-- Se non deve produrre changelog release-please, usa un tipo non rilasciabile. -->
<!-- La label skip-changelog vale per le release note generate da GitHub. -->

## Release policy
<!-- Salvo Release PR automatica, non modificare CHANGELOG.md, .release-please-manifest.json, il campo version di pyproject.toml o src/docmolder/__init__.py -->

## Classificazione cambio
- [ ] Docs/istruzioni only
- [ ] Test/CI only
- [ ] Codice runtime o packaging
- [ ] Operativo/deploy-relevant
- [ ] File release-owned toccati solo da Release PR

## Deploy VPS
- [ ] Deploy VPS automatico atteso al merge su `main`
- [ ] Deploy VPS non necessario
- [ ] Serve solo `VPS Check` manuale, senza deploy
- [ ] Serve `Rollback VPS` o deploy manuale mirato

## Impatti e rischi
- [ ] Nessun impatto operativo rilevante
- [ ] Impatto su configurazione/deploy (descrivere)
- [ ] Possibile regressione da monitorare (descrivere)

## Checklist
- [ ] Ho mantenuto la modifica focalizzata e minima
- [ ] Ho aggiornato la documentazione necessaria
- [ ] Ho eseguito i test/check rilevanti in locale
- [ ] Non ho introdotto segreti o dati sensibili
- [ ] Non ho fatto bump manuali di versione o changelog fuori dalla Release PR

## Evidenze test
<!-- Comandi e output sintetico. -->

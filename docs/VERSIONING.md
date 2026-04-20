# Versioning e Changelog

Questa guida definisce la policy ufficiale di versionamento di `DocMolder`.

## Obiettivi

- avere una sola storia di release chiara e verificabile
- allineare changelog, tag Git e GitHub Releases
- rendere prevedibile il tipo di bump versione a partire dal titolo della PR

## Fonte di verita

La fonte di verita della release e composta da:

- tag Git `vX.Y.Z`
- [CHANGELOG.md](../CHANGELOG.md) in root
- `.release-please-manifest.json` come stato corrente della versione gestita

`pyproject.toml` e `src/docmolder/__init__.py` sono file derivati e vengono aggiornati automaticamente dal flusso di release.

## Regola operativa

Il branch `main` deve ricevere modifiche tramite PR con **squash merge**.

Policy del progetto:

- niente push diretti su `main`
- ogni modifica destinata a release passa da PR
- il titolo della PR e parte del processo di versioning, non solo descrizione editoriale
- ogni commit che entra su `main` deve provenire da una PR squashata
- il workflow `Main Commit Policy` e un guardrail di verifica, non un'alternativa al flusso PR

Il titolo della PR squashata diventa il commit che `release-please` usera per:

- decidere se aprire una Release PR
- determinare il bump di versione
- generare il changelog della release

Formato richiesto:

```text
<type>(optional-scope)!: breve descrizione
```

Esempi validi:

- `feat(bot): add history relaunch shortcuts`
- `fix(pdf): handle encrypted files more clearly`
- `docs(release): clarify smoke test levels`
- `feat(api)!: rename admin report payload`

## Policy di bump versione

DocMolder segue Semantic Versioning con una regola pre-`1.0.0` esplicita:

- `feat:` produce un **minor bump**
- `fix:` produce un **patch bump**
- `deps:` produce un **patch bump**
- `docs:` produce un **patch bump** solo quando la modifica documenta un comportamento operativo o utente gia effettivo
- qualunque tipo con `!` o footer `BREAKING CHANGE:` produce:
  - **minor bump** finche il progetto e in `0.x`
  - **major bump** da `1.0.0` in poi

Tipi che non devono generare una release autonoma:

- `refactor:`
- `test:`
- `chore:`
- `build:`
- `ci:`

Usali quando la modifica non cambia il comportamento rilasciabile del prodotto o dell'operativita.

## Quando usare ogni tipo

Usa `feat:` per:

- nuove azioni disponibili all'utente
- nuovi flussi end-to-end
- nuove capacita operative o admin percepibili

Usa `fix:` per:

- regressioni
- bug funzionali
- correzioni di comportamento atteso gia esistente

Usa `docs:` per:

- runbook, release process o istruzioni operative che cambiano davvero il modo corretto di usare o mantenere il progetto

Usa `chore:` o `ci:` per:

- manutenzione interna
- housekeeping
- workflow e tooling che non meritano una release annotata per gli utilizzatori del progetto

## Flusso release

1. si apre una PR con titolo convenzionale
2. la PR viene squash-mergeata su `main`
3. `release-please` aggiorna o crea una Release PR
4. la Release PR contiene:
   - nuova versione
   - aggiornamento di `CHANGELOG.md`
   - bump dei file versione
5. al merge della Release PR GitHub crea tag e Release

Non usare `main` per commit manuali o push diretti. Se una modifica e urgente, si apre comunque una PR piccola e la si squash-mergea appena la CI e verde.

## Baseline attuale

La baseline iniziale del flusso automatico e `0.1.0`, bootstrappata sul commit `cfd7271`.

Le modifiche precedenti restano consolidate nella release baseline presente in [CHANGELOG.md](../CHANGELOG.md).

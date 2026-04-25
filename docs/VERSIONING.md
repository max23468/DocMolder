# Versioning e Changelog

Questa guida definisce la policy ufficiale di versionamento di `DocMolder`.

## Obiettivi

- avere una sola storia di release chiara e verificabile
- allineare changelog, tag Git e GitHub Releases
- rendere prevedibile il tipo di bump versione a partire dal titolo della PR
- produrre changelog leggibili per chi usa o gestisce il bot, non solo per chi ha letto la PR

## Fonte di verita

La fonte di verita della release e composta da:

- tag Git `vX.Y.Z`
- [CHANGELOG.md](../CHANGELOG.md) in root
- `.release-please-manifest.json` come stato corrente della versione gestita

Il campo `version` di `pyproject.toml` e `src/docmolder/__init__.py` sono derivati e vengono aggiornati automaticamente dal flusso di release.

I seguenti file sono quindi **riservati alla Release PR** generata da `release-please`:

- `CHANGELOG.md`
- `.release-please-manifest.json`
- campo `version` di `pyproject.toml`
- `src/docmolder/__init__.py`

Le PR ordinarie non devono modificarli.

## Regola operativa

Il branch `main` deve ricevere modifiche tramite PR con **squash merge**.

Policy del progetto:

- niente push diretti su `main`
- ogni modifica destinata a release passa da PR
- il titolo della PR e parte del processo di versioning, non solo descrizione editoriale
- ogni commit che entra su `main` deve provenire da una PR squashata
- eccezione stretta: commit diretti `chore(docs):` sono ammessi solo per modifiche minuscole e solo documentali a `AGENTS.md`, `README.md` o `docs/**`, dopo preflight/check mirati e senza release/deploy attesi
- il workflow `Main Commit Policy` e un guardrail di verifica, non un'alternativa al flusso PR
- il workflow `Release Policy` blocca le PR normali che provano a fare bump versione o changelog manuali

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
- `fix(release): require explicit release PR follow-through`
- `fix(security): harden release-owned file guardrails`
- `docs(smoke): clarify post-deploy smoke levels`
- `feat(api)!: rename admin report payload`

Il titolo PR è anche la frase che finirà nel changelog: deve descrivere il cambiamento rilasciabile, non l'attività interna. Evita titoli come `fix: address review comments`; preferisci `fix(bot): keep retry_latest scoped to the current user`.

Quando una PR produce una release, aggiungi nel corpo PR una sezione `Release note` con 1-3 frasi in linguaggio naturale. Deve spiegare cosa cambia per utenti, admin o manutentori, senza ripetere la lista file.

## Policy di bump versione

DocMolder segue Semantic Versioning con una regola pre-`1.0.0` esplicita:

- `feat:` produce un **minor bump**
- `fix:` produce un **patch bump**
- usa `fix:` per correzioni operative o di sicurezza che devono produrre un **patch bump**
- `ops:` e `security:` non sono tipi ammessi nel flusso di merge: restano concetti utili per label o testo release, ma non vanno usati come prefisso Conventional Commit in questa repository
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

Usa `fix(ops):` o un altro scope `fix(...)` esplicito per:

- cambi operativi percepibili da admin o maintainer
- flussi di release, deploy, monitoraggio o manutenzione che meritano nota pubblica
- automazioni operative che cambiano il modo corretto di gestire il progetto

Usa `fix(security):` per:

- hardening di guardrail, policy, controlli o gestione accessi
- riduzione di rischi su dati utente, segreti, workflow o infrastruttura
- correzioni che chiudono bypass o comportamenti spoofabili

Usa `docs:` per:

- runbook, release process o istruzioni operative che cambiano davvero il modo corretto di usare o mantenere il progetto
- documentazione che vuoi far comparire nella prossima release

Usa `chore:` o `ci:` per:

- manutenzione interna
- housekeeping
- workflow e tooling che non meritano una release annotata per gli utilizzatori del progetto
- aggiornamenti documentali rapidi e non rilasciabili, in particolare con `chore(docs):`

Usa un tipo non rilasciabile (`chore:`, `ci:`, `test:`, `refactor:`, `build:`) per modifiche interne che non devono produrre una release autonoma, per esempio aggiornamenti alle sole istruzioni agent senza impatto sul prodotto o sull'operativita del maintainer. La label `skip-changelog` resta utile per le release note generate da GitHub, ma il flusso principale `release-please` dipende dal tipo del commit/PR.

## Sezioni del changelog

Il changelog generato da `release-please` raggruppa le PR rilasciabili in sezioni orientate al lettore:

- `feat:` → `Funzionalità`
- `fix:` → `Correzioni`
- `fix(ops):` e altri `fix(...)` → `Correzioni`
- `fix(security):` → `Correzioni`; per evidenziare la natura di sicurezza usa titolo e release note della PR
- `deps:` → `Dipendenze`
- `docs:` → `Documentazione`

I tipi interni `chore:`, `ci:`, `test:`, `refactor:` e `build:` sono configurati come nascosti nel changelog release-please: usali quando vuoi mantenere il commit tracciabile senza aggiungere rumore alla release.

Se una modifica potrebbe stare in più sezioni, scegli quella più utile per chi deve capire l'impatto della release usando uno scope chiaro. Per esempio una correzione al workflow che impedisce bypass sui file di release è `fix(release): ...`, non un generico `fix:`.

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

## Regola pratica per gli agenti e per il maintainer

Per evitare i disallineamenti visti nei tentativi precedenti:

- non fare mai bump manuali "gia dentro" una feature PR;
- non aggiornare il changelog di release dentro una feature PR;
- non riallineare a mano manifest o version file salvo manutenzione eccezionale del flusso release;
- se serve una release, si mergea la PR funzionale e si lascia lavorare `release-please`.

Se una PR normale contiene sia codice funzionale sia modifiche ai file riservati della release, la PR e da considerare sbagliata e va corretta prima del merge.

## Baseline attuale

La baseline iniziale del flusso automatico e `0.1.0`, bootstrappata sul commit `cfd7271`.

Le modifiche precedenti restano consolidate nella release baseline presente in [CHANGELOG.md](../CHANGELOG.md).

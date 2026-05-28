# Versioning e Changelog

Questa guida definisce la policy ufficiale di versionamento di `DocMolder`.

## Obiettivi

- avere una sola storia di release chiara e verificabile
- allineare changelog, tag Git e GitHub Releases
- rendere prevedibile il tipo di bump versione a partire dal titolo della PR
- produrre changelog leggibili per chi usa o gestisce il bot, non solo per chi ha letto la PR

## Fonte di verità

La fonte di verità della release è composta da:

- tag Git `docmolder-vX.Y.Z`
- [CHANGELOG.md](../CHANGELOG.md) in root

I campi version in `pyproject.toml` e `src/docmolder/__init__.py` sono allineati dal flusso manuale (`scripts/auto_release.py`) dopo il merge della PR funzionale.

I seguenti file sono quindi **riservati al flusso di release**:

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
- il titolo della PR è parte del processo di versioning, non solo descrizione editoriale
- ogni commit che entra su `main` deve provenire da una PR squashata
- eccezione stretta: commit diretti `chore(docs):` sono ammessi solo per modifiche minuscole e solo documentali a `AGENTS.md`, `README.md` o `docs/**`, dopo preflight/check mirati e senza release/deploy attesi
- `CI result` è il guardrail GitHub Actions richiesto sulle PR non draft verso `main`
- i controlli locali (`publish_doctor`, `preflight`, test mirati o `ci_verify`) restano la verifica primaria ed economica prima del push
- `scripts/publish_change.sh` è il percorso standard per commit, push e PR pronta; draft, merge assistito e follow-up Actions richiedono variabili esplicite

Il titolo della PR squashata diventa il commit che il flusso di release usera per:

- determinare il bump di versione
- generare il changelog della release

Formato richiesto:

```text
<type>(optional-scope)!: breve descrizione
```

Esempi validi:

- `feat(bot): add history relaunch shortcuts`
- `fix(pdf): handle encrypted files more clearly`
- `fix(release): require explicit manual release follow-through`
- `fix(security): harden release-owned file guardrails`
- `docs(smoke): clarify post-deploy smoke levels`
- `feat(api)!: rename admin report payload`

Il titolo PR è anche la frase che finirà nel changelog: deve descrivere il cambiamento rilasciabile, non l'attività interna. Evita titoli come `fix: address review comments`; preferisci `fix(bot): keep history retry scoped to the current user`.

Quando una PR produce una release, aggiungi nel corpo PR una sezione `Release note` con 1-3 frasi in linguaggio naturale. Deve spiegare cosa cambia per utenti, admin o manutentori, senza ripetere la lista file.

## Policy di bump versione

DocMolder segue Semantic Versioning con una regola pre-`1.0.0` esplicita:

- `feat:` produce un **minor bump**
- `fix:` produce un **patch bump**
- usa `fix:` per correzioni operative o di sicurezza che devono produrre un **patch bump**
- `ops:` e `security:` non sono tipi ammessi nel flusso di merge: restano concetti utili per label o testo release, ma non vanno usati come prefisso Conventional Commit in questa repository
- `deps:` produce un **patch bump**
- `docs:` produce un **patch bump** solo quando la modifica documenta un comportamento operativo o utente già effettivo
- qualunque tipo con `!` o footer `BREAKING CHANGE:` produce:
  - **minor bump** finché il progetto è in `0.x`
  - **major bump** da `1.0.0` in poi

Tipi che non devono generare una release autonoma:

- `refactor:`
- `test:`
- `chore:`
- `build:`
- `ci:`

Usali quando la modifica non cambia il comportamento rilasciabile del prodotto o dell'operatività.

## Criterio per release major `X.0.0`

Una release `X.0.0` non è una release "più grande" in senso generico. È una
soglia di contratto: dichiara che il modo corretto di usare, mantenere o
integrare DocMolder cambia in modo sostanziale oppure diventa stabile per una
nuova fase del progetto.

Una major release è appropriata quando almeno una di queste condizioni è vera:

- cambia il contratto utente principale: comandi pubblici, flussi Telegram,
  significato delle azioni o aspettative sui risultati dei documenti;
- cambia il contratto operativo: deploy, release, rollback, backup, retention,
  restore o runbook richiedono un comportamento diverso da parte del maintainer;
- cambia il contratto dati/sicurezza: retention, cancellazione, persistenza,
  log, accessi admin o gestione dei file utente assumono garanzie diverse;
- cambia il perimetro prodotto deciso in [DECISIONS.md](./DECISIONS.md), ad
  esempio da utility Telegram-first verso una superficie web/API o verso uno
  storage documentale più ampio;
- una o più breaking change non sono solo dettagli tecnici interni, ma
  richiedono migrazione, comunicazione esplicita o aggiornamento dei runbook.

Una major release non è appropriata solo per:

- accumulo di molte patch o feature compatibili;
- refactor interni, pulizia codice o miglioramenti di performance senza cambio
  di contratto;
- aggiornamenti documentali che chiariscono ciò che è già vero;
- desiderio di avere un numero versione più ordinato.

Ogni PR che prepara una major deve includere nel corpo PR una sezione
`Major release rationale` con:

1. perché il cambio merita `X.0.0`;
2. quali contratti cambiano o vengono dichiarati stabili;
3. quali smoke, rollback e note operative sono richiesti;
4. quali limiti o migrazioni restano dichiarati.

La major deve essere coordinata nel flusso manuale prima del merge della
PR finale. Non basta cambiare un numero versione: serve una decisione esplicita
e tracciabile nel corpo PR.

## Quando usare ogni tipo

Usa `feat:` per:

- nuove azioni disponibili all'utente
- nuovi flussi end-to-end
- nuove capacità operative o admin percepibili

Usa `fix:` per:

- regressioni
- bug funzionali
- correzioni di comportamento atteso già esistente

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

Usa un tipo non rilasciabile (`chore:`, `ci:`, `test:`, `refactor:`, `build:`) per modifiche interne che non devono produrre una release autonoma, per esempio aggiornamenti alle sole istruzioni agent senza impatto sul prodotto o sull'operatività del maintainer. La label `skip-changelog` resta utile per le release note generate da GitHub, ma il flusso principale dipende dal tipo del commit/PR.

## Sezioni del changelog

Il changelog generato dal flusso di release raggruppa le PR rilasciabili in sezioni orientate al lettore:

- `feat:` → `Funzionalità`
- `fix:` → `Correzioni`
- `fix(ops):` e altri `fix(...)` → `Correzioni`
- `fix(security):` → `Correzioni`; per evidenziare la natura di sicurezza usa titolo e release note della PR
- `deps:` → `Dipendenze`
- `docs:` → `Documentazione`

I tipi interni `chore:`, `ci:`, `test:`, `refactor:` e `build:` sono esclusi dal changelog automatico: usali quando vuoi mantenere il commit tracciabile senza aggiungere rumore alla release.

Se una modifica potrebbe stare in più sezioni, scegli quella più utile per chi deve capire l'impatto della release usando uno scope chiaro. Per esempio una correzione al workflow che impedisce bypass sui file di release è `fix(release): ...`, non un generico `fix:`.

## Flusso release

1. `scripts/publish_change.sh "<titolo conventional>"` apre una PR pronta con titolo convenzionale
2. la PR viene squash-mergeata su `main`
3. `CI result` passa sulla PR non draft
4. il webhook VPS deploya il merge su `main`
5. se la PR merita rilascio, esegui `scripts/auto_release.py` dalla copia pulita di `main`
6. lo script aggiorna `CHANGELOG.md`, `pyproject.toml`, `src/docmolder/__init__.py`, tag `docmolder-vX.Y.Z` e GitHub Release
7. il commit di release viene deployato dal webhook VPS

Se l'utente ha chiesto di pubblicare o procedere con una modifica rilasciabile,
il flusso operativo standard include anche il passaggio manuale `scripts/auto_release.py` e la verifica di tag, GitHub Release, deploy del commit di release e smoke/health VPS.

Non usare `main` per commit manuali o push diretti. Se una modifica è urgente,
si apre comunque una PR piccola e la si squash-mergea dopo i gate locali
rilevanti e `CI result`.

## Promozione esplicita a 1.0

DocMolder è già nella linea stabile `1.x`. La checklist storica resta in
[ONE_DOT_ZERO_READINESS.md](./ONE_DOT_ZERO_READINESS.md); nuove major seguono il
criterio `X.0.0` sopra e il flusso manuale con `scripts/auto_release.py`.

## Regola pratica per gli agenti e per il maintainer

Per evitare i disallineamenti visti nei tentativi precedenti:

- non fare mai bump manuali "già dentro" una feature PR;
- non aggiornare il changelog di release dentro una feature PR;
- non riallineare a mano manifest o version file salvo manutenzione eccezionale del flusso release;
- se serve una release, si mergea la PR funzionale, si completa il passaggio manuale con `scripts/auto_release.py` e si verifica il commit di release in VPS e changelog.
- `deploy/auto-release.sh` resta solo come fallback esplicito e spento di default sulla VPS.

Se una PR normale contiene sia codice funzionale sia modifiche ai file riservati della release, la PR è da considerare sbagliata e va corretta prima del merge.

## Baseline attuale

La baseline iniziale del flusso di release e `0.1.0`, bootstrappata sul commit `cfd7271`.

Le modifiche precedenti restano consolidate nella release baseline presente in [CHANGELOG.md](../CHANGELOG.md).

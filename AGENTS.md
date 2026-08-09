# AGENTS.md — Istruzioni operative per DocMolder

Queste istruzioni valgono per l’intera repository. Un `AGENTS.md` più vicino
alla cartella toccata può specializzarle per quel sottoalbero.

## Prodotto e fonti

DocMolder è una utility documentale Telegram-first, semplice, guidata e
affidabile. Non trasformarla senza decisione esplicita in gestionale
documentale, storage permanente, editor collaborativo, API pubblica o
dashboard web-first.

Prima di modifiche non banali leggi solo le fonti pertinenti:

- orientamento e stato: `README.md`, `docs/INDEX.md`, `docs/CONTEXT.md`;
- perimetro e priorità: `docs/DECISIONS.md`, `docs/ROADMAP.md`,
  `docs/BACKLOG.md`;
- sviluppo e test: `docs/LOCAL_DEV.md`, `docs/TOOLCHAIN.md`;
- brand o microcopy: `docs/BRAND.md`;
- GitHub, release e deploy: `docs/GITHUB_MAINTENANCE.md`,
  `docs/VERSIONING.md`, `docs/RELEASE_PROCESS.md`, `docs/VPS_RUNBOOK.md`.

La linea stabile corrente è `2.x`, in manutenzione e stabilizzazione. Nuove
feature richiedono una priorità o decisione esplicita.

## Autonomia e scope

- Per review, diagnosi o piano, ispeziona e riferisci senza modificare.
- Per fix o implementazioni richieste, modifica direttamente lo scope locale ed
  esegui verifiche non distruttive proporzionate.
- Decidi autonomamente dettagli di routine come naming, formattazione e default
  coerenti con il codice esistente.
- Chiedi conferma prima di azioni distruttive o difficili da annullare, deploy,
  release, nuove dipendenze o ampliamenti materiali dello scope, salvo che una
  richiesta esplicita di pubblicazione includa già release/deploy secondo il
  processo documentato. Non estendere comunque il perimetro prodotto.
- Se l’ambiguità cambia materialmente il risultato, fermati e chiedi; per
  dettagli marginali scegli un’assunzione prudente e dichiarala.
- Non introdurre compatibilità legacy o scaffolding speculativo: non ci sono
  consumatori esterni da preservare.

## Worktree e ownership

- All’avvio controlla `git status --short --branch`, branch/PR rilevanti e run
  fallite per il branch o SHA corrente.
- Non sovrascrivere, normalizzare o includere modifiche non tue.
- Se il worktree contiene un diff non collegato, usa una branch e un worktree
  puliti `codex/<tema>`; un semplice `git switch -c` non separa modifiche non
  committate.
- Per lavoro non minuscolo usa
  `python3 scripts/agent_start.py --area <area> --owner <owner>` e, prima di
  toccare aree condivise,
  `python3 scripts/agent_parallel_safe.py --owner <owner>`.
- Delega solo filoni indipendenti con ownership disgiunta. Usa
  `docs/AGENT_TASK_PACKET.md` e, se utile, `docs/AGENT_TASK_PROMPTS.md`; il
  coordinatore integra e decide merge, release, deploy e prodotto.
- Se una run GitHub Actions rilevante per branch/SHA corrente è fallita,
  ispezionala prima di proseguire. Correggi solo cause chiare e in scope;
  segnala subito blocchi dovuti a segreti, infrastruttura o decisioni prodotto.

## Codice, errori e dati

- Segui struttura, naming, idiomi e densità di commenti del codice circostante.
- Preferisci funzioni piccole e verificabili; non aggiungere `try/except`
  attorno agli import.
- Gestisci gli errori con messaggi operativi e fallback sicuri quando possibili.
- Mantieni messaggi Telegram in italiano chiaro, includendo stati intermedi,
  retry e prossima azione utile.
- Non committare segreti, `.env`, `.DS_Store`, documenti utente, output
  temporanei o backup.
- Non loggare contenuti dei documenti. Tratta upload, output e metadati job come
  dati utente: persisti solo quanto serve al runtime e rispetta cleanup e
  retention documentati.
- Per cambi a cleanup, backup, restore, runtime dir o VPS verifica anche il
  percorso di rimozione o recupero in `docs/VPS_RUNBOOK.md`.

## Verifica

Scegli la corsia minima che copre il rischio:

- `veloce`: analisi o docs/governance a basso rischio; usa `git diff --check` e
  preflight mirato;
- `standard`: test-only, runtime piccolo, helper condivisi o config ordinaria;
  esegui test mirati e `bash scripts/ci_verify.sh` quando il rischio supera la
  patch locale;
- `completa`: workflow, release, security, dati utente, bot, pipeline
  documentale, VPS o provider esterni; esegui `bash scripts/ci_verify.sh`, CI
  GitHub e smoke/runbook pertinenti.

Comandi canonici:

- gate locale: `bash scripts/ci_verify.sh`;
- suite: `make test`;
- compilazione/import: `make compile`;
- test mirati: `.venv/bin/python -m unittest tests.<modulo>`;
- smoke Telegram, solo quando pertinente e disponibile: `make smoke-ui`.

`CI result` e `codex-review` sono i gate remoti autorevoli per PR non draft verso `main`. Se un
check fallisce o non è eseguibile, indica comando, sintomo, impatto e prossimo
passo; non nascondere il limite dietro un riepilogo positivo.

## Documentazione

- `docs/INDEX.md` è il catalogo canonico. Non creare documenti paralleli con lo
  stesso scopo.
- Aggiorna documenti, link e roadmap solo quando cambia comportamento, stato o
  processo; non usare `docs/CONTEXT.md` o `docs/ROADMAP.md` come changelog.
- Non modificare `CHANGELOG.md`, la versione in `pyproject.toml` o
  `src/docmolder/__init__.py` nelle PR ordinarie: sono release-owned.
- Mantieni procedure specialistiche nei documenti o script canonici e in
  `AGENTS.md` solo vincoli durevoli e gotcha non ricavabili dal repository.

## Significato di `Pubblica`

Quando il proprietario dice `Pubblica` o chiede in modo affermativo e
inequivocabile di pubblicare, autorizza l'intero ciclo tecnico applicabile alla
repository. Domande, ipotesi, pianificazioni e negazioni non costituiscono
autorizzazione. L'agente non si ferma a stati intermedi e completa, nell'ordine
previsto dalla policy della repository, preparazione e verifiche, branch e
commit, versione e changelog quando richiesti, push, PR, soli gate bloccanti,
merge, tag e GitHub Release quando previsti, deploy o promozione tecnica,
verifica live e pulizia finale di branch, worktree, stash e altri residui.

Se un passaggio non è applicabile, lo dichiara e prosegue con gli altri. La
richiesta affermativa di pubblicazione vale come autorizzazione a PR, merge,
deploy tecnico
e release previsti dal ciclo, senza una seconda conferma. Non autorizza
pubblicazione di temi Shopify live, submission Shopify App Store, billing o
nuove attivazioni produttive, TestFlight o App Store, invii Aruba, email o
scansioni reali, né aggiornamenti Notion: queste azioni richiedono una richiesta
esplicita separata. Non dichiarare `pubblicato` finché il ciclo applicabile e la
rilettura finale di PR, check, deploy, release e stato Git non sono completi.

## GitHub, release e deploy

- Il flusso standard è branch dedicato, commit coeso, PR pronta verso `main`,
  gate pertinenti e squash merge. Il titolo PR deve essere un Conventional
  Commit orientato al cambiamento, non il nome del branch.
- Prima di aprire o mergiare una PR esegui `make preflight-publish`, rivedi il
  diff e controlla lo status `codex-review` sull'HEAD corrente come descritto in
  `docs/GITHUB_MAINTENANCE.md`, inclusi i ricontrolli prima e dopo il merge.
- Usa `scripts/publish_change.sh "<titolo conventional>"` per il flusso
  standard. Per togliere una PR da draft usa `gh pr ready <numero>`.
- Anche le modifiche minuscole a `AGENTS.md`, `README.md` o `docs/**` seguono
  branch e PR quando il proprietario parla di pubblicare; non usare la corsia
  diretta `make publish-docs` nel ciclo completo.
- Per cambi interni non rilasciabili usa `chore:`, `ci:`, `test:`, `refactor:`
  o `build:`. Non creare tag, GitHub Release o deploy per docs agentiche senza
  impatto runtime.
- Il deploy ordinario passa dal webhook privato GitHub alla VPS
  `docmolder.duckdns.org`; il fallback manuale e i controlli post-deploy sono in
  `docs/VPS_RUNBOOK.md`. Non avviare deploy se il diff non è deploy-relevant.
- Dopo un flusso mergiato elimina branch locale/remota di lavoro e verifica il
  cleanup con `git fetch --prune`.

## Chiusura

Una modifica è conclusa quando risolve la richiesta, preserva dati e scope,
supera i gate pertinenti, aggiorna solo la documentazione necessaria e lascia
publish/release/deploy completati o dichiarati non applicabili.

Chiudi partendo dall’esito. Riporta file principali, fallimenti o limiti,
rischi residui e prossimo passo solo quando ancora utile.

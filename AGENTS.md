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

Interpreta le richieste operative come incarichi da completare, usando intento
e contesto della sessione. Risolvi autonomamente naming, formattazione, default
e dettagli ordinari con assunzioni ragionevoli. Prima di chiedere un chiarimento,
verifica le fonti disponibili; chiedi solo se resta una decisione che cambia
materialmente il risultato.

Prima di una conferma necessaria, completa il lavoro indipendente già autorizzato
e prepara un risultato concreto da valutare. Sospendi soltanto il passaggio che
dipende dalla decisione mancante. Non richiedere consensi già concessi per la
stessa azione e lo stesso perimetro, salvo un checkpoint esplicito del progetto.
Conserva i confini di pubblicazione, dati e operazioni esterne definiti qui;
un ordine esplicito di attesa o arresto interrompe il lavoro interessato.
Il tempo trascorso non costituisce una risposta o un'autorizzazione.

Integra correzioni e nuovi vincoli durante il lavoro; rispondi alle domande
laterali senza perdere l'obiettivo, salvo annullamento o cambio di scope esplicito.

- Per review, diagnosi o piano, ispeziona e riferisci senza modificare.
- Per fix o implementazioni richieste, modifica direttamente lo scope locale ed
  esegui verifiche non distruttive proporzionate.
- Chiedi conferma prima di azioni distruttive o difficili da annullare, deploy,
  release, nuove dipendenze o ampliamenti materiali dello scope, salvo che una
  richiesta esplicita di pubblicazione includa già release/deploy secondo il
  processo documentato. Non estendere comunque il perimetro prodotto.
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
- Se una run GitHub Actions rilevante per branch/SHA corrente è fallita,
  ispezionala prima di proseguire. Correggi solo cause chiare e in scope;
  segnala subito blocchi dovuti a segreti, infrastruttura o decisioni prodotto.

## Codice, errori e dati

Evita di creare un numero eccessivo di file di test. Crea un nuovo file di test
solo se richiesto dalle convenzioni della repository o se nessun file esistente
è una collocazione adatta. Evita pulizie non pertinenti e complessità non
necessaria. Riusa le utility esistenti adatte allo scopo. Leggi le istruzioni
pertinenti della repository ed esamina codice, test, documentazione e CI vicini
all'area interessata. Segui le convenzioni consolidate. L'obiettivo è ottenere
codice pulito e pronto per essere integrato.

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

Calibra la verifica sul rischio del diff e completa i gate applicabili. Riusa
i test esistenti; aggiungine solo per un comportamento o rischio concreto, non
per replicare modifiche banali. Dopo un esito verde ripeti o amplia i controlli
solo per nuove modifiche, errori o dubbi irrisolti. Verifica il diff effettivo,
senza trattare il messaggio di successo di uno strumento come prova sufficiente.

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

`CI result` è il gate remoto autorevole per PR non draft verso `main`. Se un
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

Quando il proprietario, riferendosi alla repository o alla modifica corrente,
dice `Pubblica` o chiede in modo affermativo e inequivocabile di pubblicare,
autorizza l'intero ciclo tecnico applicabile. Domande, ipotesi, pianificazioni e
negazioni non costituiscono autorizzazione. L'agente non si ferma a stati
intermedi e completa tutti i passaggi applicabili: preparazione e verifiche,
branch e commit, versione e changelog quando richiesti, push, PR, soli gate
bloccanti, merge, tag e GitHub Release quando previsti, deploy o promozione
tecnica e verifica live. La sequenza concreta, in particolare tra versionamento,
merge, deploy e release, è quella definita dalla policy della repository.

La pulizia finale rimuove soltanto branch e worktree temporanei creati nel ciclo
corrente e già assorbiti; controlla stash e altri residui senza alterare elementi
preesistenti o estranei alla pubblicazione. Se un passaggio non è applicabile, lo
dichiara e prosegue con gli altri. La richiesta affermativa di pubblicazione
vale come autorizzazione a PR, merge, deploy tecnico e release previsti dal
ciclo, senza una seconda conferma. Non autorizza pubblicazione di temi Shopify
live, submission Shopify App Store, billing o nuove attivazioni produttive,
TestFlight o App Store, invii Aruba, email o scansioni reali, né aggiornamenti
Notion: queste azioni richiedono una richiesta esplicita separata. Una richiesta
riferita soltanto a una di queste azioni non avvia la pubblicazione della
repository. Non dichiarare `pubblicato` finché il ciclo applicabile e la
rilettura finale di PR, check, deploy, release e stato Git non sono completi.

## GitHub, release e deploy

- Il flusso standard è branch dedicato, commit coeso, PR pronta verso `main`,
  gate pertinenti e squash merge. Il titolo PR deve essere un Conventional
  Commit orientato al cambiamento, non il nome del branch.
- Prima di aprire o mergiare una PR esegui `make preflight-publish`, rivedi il
  diff e applica i ricontrolli descritti in `docs/GITHUB_MAINTENANCE.md` prima e dopo il merge.
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

Scrivi in italiano semplice, con esito per primo e paragrafi brevi. Usa elenchi
solo quando aiutano; evita formule ricorrenti, gergo superfluo e aggiornamenti
che ripetono lo stesso stato. Riporta prove, limiti e prossima azione reale.

Completa l'esito richiesto: analisi, modifica locale o pubblicazione. Distingui
passaggi completati, non richiesti, non applicabili e bloccati; non dichiarare
completo ciò che resta bloccato o non verificato. Applica i requisiti di commit
previsti per l'implementazione e pulisci soltanto risorse proprie e assorbite,
preservando modifiche e worktree altrui.

Riporta file principali e fallimenti; aggiorna soltanto la documentazione
necessaria, preservando dati e scope.

## Skill e delega

Le istruzioni esplicite dell'utente prevalgono sulle linee guida delle Skill,
nel rispetto delle istruzioni di sistema e sviluppatore. Verifica pertinenza,
gerarchia e conflitti di AGENTS, override e Skill prima di dedurne un blocco;
non trasformare raccomandazioni generiche in nuovi gate.

Se una Skill causa una pausa, una richiesta di permesso o lavoro incompleto,
cita e collega il preciso `SKILL.md`, riporta l'istruzione rilevante e distingui
il requisito esplicito dalla tua interpretazione.

Quando la sessione e le regole del progetto consentono subagent, delega solo
filoni consistenti e indipendenti, con ownership disgiunta, risultato atteso e
verifiche espliciti. Il coordinatore integra; niente delega per microtask o
semplice ricontrollo. Scrivi messaggi leggibili anche tra agenti.

Per la delega usa `docs/AGENT_TASK_PACKET.md` e, se utile,
`docs/AGENT_TASK_PROMPTS.md`; il coordinatore decide merge, release, deploy e
prodotto entro le autorizzazioni del progetto.

Esempio e fonti: [preparare un incarico](docs/AGENT_TASK_PROMPTS.md#preparare-un-incarico).

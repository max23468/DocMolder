# AGENTS.md — Istruzioni operative per Codex (DocMolder)

Questo file definisce linee guida persistenti per gli agenti che lavorano in questa repository.
Scope: intera repository, salvo override in `AGENTS.md` più specifici in sottocartelle.

## 1) Contesto da leggere prima

Prima di modifiche non banali, orientati con i documenti rilevanti per la task:
- `docs/CONTEXT.md` per lo stato sintetico del progetto;
- `docs/DECISIONS.md` per il perimetro prodotto;
- `docs/ROADMAP.md` per le priorità correnti;
- `docs/AGENT_COORDINATION.md` quando lavori in parallelo, riprendi una chat precedente o trovi modifiche non tue nel worktree;
- `docs/LOCAL_DEV.md` per setup e comandi di verifica;
- `docs/VERSIONING.md` e `docs/RELEASE_PROCESS.md` quando la task riguarda commit, PR, release o deploy.

## 2) Obiettivo di lavoro

- Preferire modifiche chiare, coese e verificabili.
- Le modifiche importanti sono accettabili quando servono, ma vanno prima esplicitate come piano e poi spezzate in passaggi comprensibili, testabili e, quando possibile, accompagnati da rollback o mitigazione chiari.
- Preferire robustezza, leggibilità e semplicità operativa.
- Evitare side-effect non richiesti rispetto alla task dell'utente.
- Tenere DocMolder nel suo perimetro: utility documentale Telegram-first, semplice, guidata e affidabile.
- DocMolder non è un gestionale documentale completo, non è uno storage permanente di file utente, non è un editor collaborativo e non deve diventare una dashboard web-first senza una decisione esplicita.

## 3) Prima di intervenire

- Controlla lo stato del worktree con `git status --short`.
- Se una nuova chat implica modifiche ai file e `git status --short` mostra modifiche non tue o non collegate alla richiesta, non aggiungere altri edit nello stesso worktree: considera quel diff gia posseduto da un altro filone, apri automaticamente una branch/worktree dedicata `codex/<tema>` da una base pulita e continua li.
- Comprendi il flusso toccato prima di editare: handler Telegram, pipeline documentale, session store, servizi, config o deploy.
- Non revertire modifiche già presenti se non richiesto esplicitamente.
- Se la richiesta è ambigua, fermati e fai domande mirate all'utente prima di scegliere approccio, scope o comportamento.
- Procedi con un'assunzione dichiarata solo per dettagli marginali che non cambiano il risultato sostanziale.

## 4) Stile e qualità del codice

- Segui le convenzioni già presenti nel progetto.
- Usa nomi espliciti e coerenti con il dominio del progetto.
- Evita blocchi troppo grandi: favorisci funzioni piccole e testabili.
- Non aggiungere commenti ridondanti; commenta solo decisioni non ovvie.
- Non inserire `try/except` attorno agli import.
- Non introdurre nuove dipendenze senza avvisare prima l'utente e spiegare motivazione, impatto e alternative.
- I file `.DS_Store` non fanno parte della repository: ignorali sempre e rimuovi quelli creati localmente quando li incontri.

## 4.1) Lavoro parallelo tra agenti

Quando piu chat, agenti o istanze Codex lavorano sul progetto nello stesso periodo, il coordinamento deve essere esplicito e leggibile dal repository.

- Usa una chat principale come coordinatore quando il lavoro e ampio: definisce scope, assegna sotto-task, integra i risultati e prende decisioni finali su merge, PR, deploy o prodotto.
- Usa sub-agenti o istanze parallele solo per sotto-task separabili e circoscritti: esplorazione di una zona del codice, patch su un modulo specifico, test mirati, review del diff o controllo documentale/deploy impact.
- Assegna ownership chiara prima di iniziare: ogni agente deve sapere quali file, moduli o responsabilita puo toccare; evita che due agenti modifichino lo stesso flusso senza coordinamento esplicito.
- Non usare sub-agenti per task piccoli, decisioni prodotto ambigue, refactor trasversali o modifiche dove il coordinatore dipende subito dal risultato per il passo successivo.
- Quando deleghi, prepara un task packet con `docs/CODEX_TASK_PACKET.md` e, se utile, usa i prompt di `docs/CODEX_TASK_PROMPTS.md`.
- Preferisci branch o worktree dedicati per filone di lavoro, con nomi `codex/<tema>` quando crei nuove branch operative.
- All'avvio di una nuova chat che deve modificare file, se la branch/worktree corrente e gia sporca per altre modifiche, separa automaticamente il nuovo lavoro: non riusare la stessa working tree, crea una branch/worktree dedicata da una base pulita e mantieni i due filoni distinti fino a PR/merge.
- Se modifiche non tue sono gia presenti nel worktree corrente, non basta fare `git switch -c`: gli uncommitted changes seguirebbero la nuova branch. Usa invece un worktree separato o una base pulita equivalente, poi annota la separazione in `docs/AGENT_COORDINATION.md` quando il lavoro non e minuscolo.
- Aggiorna `docs/AGENT_COORDINATION.md` all'avvio e alla chiusura di lavori non banali, indicando task, branch/worktree, area posseduta, stato, file toccati, verifiche e rischi residui.
- All'avvio di una nuova chat o quando riprendi lavoro, leggi `docs/AGENT_COORDINATION.md`, controlla `git status --short` e verifica branch/PR aperte rilevanti prima di editare.
- Per un briefing iniziale standard usa `python3 scripts/agent_start.py --area <area> --owner <owner>`.
- Prima di toccare aree potenzialmente condivise usa `python3 scripts/agent_parallel_safe.py --owner <owner>`.
- Se trovi un'altra istanza attiva sulla stessa area, non sovrascrivere ne normalizzare le sue modifiche: integra, ribasa o segnala il conflitto in modo esplicito.
- Per lavori non minuscoli, apri una branch o una draft PR appena possibile: la PR diventa la fonte di verita per diff, check, review e handoff.
- A fine lavoro lascia un handoff sintetico nel registro o nella PR: cosa e stato fatto, cosa resta aperto, quali check sono stati eseguiti e quali aree non vanno toccate senza rilettura. Per generarlo puoi usare `python3 scripts/agent_handoff.py`.

## 5) Logging, errori e UX operativa

- Gestisci errori in modo esplicito e con messaggi utili.
- Evita leak di dati sensibili in log, trace, messaggi Telegram ed error message.
- Se il fallback è possibile, preferiscilo al crash.
- Mantieni output e messaggi coerenti con il tono del progetto: italiano chiaro, operativo, senza rumore inutile.
- Per flussi utente Telegram, cura anche stati intermedi, retry, messaggi di errore e azioni successive suggerite.

## 6) Sicurezza, dati e file temporanei

- Minimizza la persistenza di file utente e temporanei.
- Non committare segreti, token, credenziali o file `.env` reali.
- Rispetta i limiti operativi già presenti: dimensioni, concorrenza, retention e cleanup.
- Non loggare contenuti dei documenti caricati dagli utenti.
- Tratta documenti caricati, output generati e metadati di job come dati utente: conservali solo nel runtime necessario alla lavorazione, puliscili a fine flusso o secondo retention documentata, e non copiarli in fixture, log o report salvo richiesta esplicita e dati sintetici.
- Se una modifica tocca cleanup, backup, restore, incident response o gestione file temporanei, descrivi impatto sui dati utente e verifica almeno il percorso di rimozione o recupero rilevante.
- Per modifiche a runtime dir, backup, restore o VPS, verifica anche `docs/VPS_RUNBOOK.md`.

## 7) Testing e verifica minima

Prima del commit, esegui i check rilevanti alla modifica:
- gate completo locale: `bash scripts/ci_verify.sh`;
- suite completa: `make test`;
- compilazione/import: `make compile`;
- test mirati: `.venv/bin/python -m unittest tests.<modulo>`;
- smoke Telegram: `make smoke-ui`, solo quando serve e quando l'ambiente locale lo permette.

Se un check non è eseguibile nell'ambiente corrente, dichiaralo esplicitamente con motivo e rischio residuo.
Nelle risposte finali non ripetere l'elenco delle verifiche eseguite come rito: citale solo se sono richieste esplicitamente, se servono per PR/release/audit, se falliscono, se non sono eseguibili o se lasciano un rischio residuo utile da conoscere.

## 7.1) Risposte finali e prossimi passi

- Non includere messaggi celebrativi o contabili sui check, come "123 test superati", "456 verifiche verdi", "tutto verde" o formule simili. Se le verifiche sono rilevanti, riportale in modo sintetico e operativo, privilegiando errori, limiti o rischi residui rispetto ai conteggi.
- Se uno o più test/check falliscono, dirlo sempre in modo esplicito: indica quale comando o check è fallito, il motivo noto o il sintomo principale, l'impatto pratico e il prossimo passo consigliato. Non nascondere un fallimento dietro formule generiche o un riepilogo positivo.
- Quando la risposta lascia aperte una o più azioni sensate, proponi il prossimo passo o una breve lista di prossimi passi concreti. Se ci sono alternative, rendile facili da scegliere con opzioni brevi, numerate o nominate, indicando l'effetto pratico di ciascuna.
- Non forzare un prossimo passo quando la richiesta è completamente chiusa e non c'è una decisione utile da prendere.

## 8) Documentazione e roadmap

- Aggiorna la documentazione quando l'utente lo chiede o quando cambia un comportamento utente, operativo o di sviluppo.
- Non aggiornare il changelog di release nelle PR normali.
- Nella roadmap, gli item completati vanno rimossi dalla checklist; non usare checkbox segnate come completate per elementi già fatti.
- Non aggiungere roadmap laterali se la task può essere chiusa con un intervento piccolo e verificabile.

## 9) Commit, PR e release

- Un commit deve essere coeso: una modifica logica principale.
- Messaggi commit chiari, in forma imperativa, con scope quando utile.
- Per operazioni GitHub usa dove possibile il tool/plugin GitHub come canale primario per repository, PR, issue, commenti, review, metadata e creazione PR; ricorri a `gh`/git locali solo quando il plugin non copre bene l'operazione, ad esempio branch/commit/push locali, stato auth, log GitHub Actions o inspect di run CI.
- Per togliere una PR dallo stato draft usa `gh pr ready <numero>` invece del tool GitHub connector `mark_pull_request_ready_for_review`: il connector attuale inciampa su `PullRequest.htmlUrl`, campo non valido nello schema GraphQL GitHub, mentre `gh` usa il percorso affidabile.
- Il flusso ufficiale è branch dedicato, PR verso `main`, CI verde e squash merge.
- Il titolo PR deve seguire Conventional Commits perché guida `release-please`; scrivilo come frase da changelog, orientata al cambiamento rilasciabile e non all'attività interna.
- Prima di aprire o mergiare una PR, usa `scripts/preflight_publish.sh` o `make preflight-publish` per classificare il diff, bloccare tocchi accidentali ai file release-owned e capire se il deploy VPS è davvero atteso.
- Quando l'utente chiede di "caricare", "pubblicare", "pubblica" o formule simili una modifica, considera incluso l'intero flusso GitHub: branch/commit mirato, push, PR, monitoraggio check e merge appena i check richiesti sono verdi, salvo richiesta esplicita di fermarsi a push o PR. Considera incluso anche il deploy VPS quando `scripts/preflight_publish.sh`/`make preflight-publish` o la natura della PR indicano che il deploy su VPS è sensato e atteso; in quel caso segui comunque `docs/VPS_RUNBOOK.md` e riporta comandi, esito e verifiche. Dove possibile usa `scripts/publish_change.sh "<titolo conventional>"`.
- Per modifiche minuscole e a basso rischio, chiaramente solo documentali o di istruzioni operative, evita la trafila lunga branch/PR/release se non aggiunge valore: stai su `main` aggiornato e usa `make publish-docs TITLE="chore(docs): <descrizione>"`, che deve fare preflight/check mirati, commit diretto e push senza PR. Questa scorciatoia vale solo per `AGENTS.md`, `README.md` o `docs/**`, senza deploy/release attesi, e non vale per codice runtime, script, workflow CI, configurazione, deploy, dati, release-owned files o cambi ambigui.
- Al termine di un flusso pubblicato e mergiato, elimina sempre la branch remota e la branch locale di lavoro quando non servono più, poi verifica con `git fetch --prune`, `git branch --list 'codex/*'` e, se utile, `git ls-remote --heads origin <branch>`. Se la branch corrente non può essere eliminata perché è checkoutata, spostati su una base sicura o su `origin/main` detached e completa il cleanup prima della risposta finale.
- Quando fai squash merge, non sovrascrivere il subject rimuovendo il suffisso `(#PR)`: i guardrail su `main` richiedono commit nel formato `docs: esempio (#123)`. Se usi `gh pr merge`, lascia che GitHub/CLI mantenga il titolo PR con suffisso oppure passa esplicitamente un subject completo come `docs: esempio (#123)`.
- Quando inizi una nuova operazione GitHub o riprendi lavoro su una PR, controlla prima se ci sono commenti/review bot o thread inline rimasti aperti, inclusi quelli di `chatgpt-codex-connector`/`chatgpt-codex-connector[bot]`/Codex connector bot; se sono azionabili, implementa quanto segnalano, verifica la correzione e chiudi/elimina/risolvi il commento o thread quando possibile.
- Prima di togliere una PR da draft o mergiarla, esegui `scripts/check_codex_bot_comments.py --pr <numero> --fail`; se trova commenti aperti del Codex connector bot, fermati, implementali e ripeti i check prima del merge.
- Dopo che una PR viene marcata ready, dopo che i check GitHub diventano verdi e subito prima del merge, ripeti il controllo dei commenti bot: le review del Codex connector possono arrivare in ritardo rispetto ai primi check. Se il merge e gia avvenuto e compare una review/commento bot tardivo sulla PR appena chiusa, considera il flusso non concluso: apri una PR correttiva mirata, implementa il rilievo oppure documenta esplicitamente perche non e azionabile, e ricontrolla il thread prima della risposta finale.
- Dopo il merge di una PR funzionale e dopo l'eventuale merge della Release PR, ricontrolla le PR appena chiuse con `scripts/check_codex_bot_comments.py --pr <numero> --fail` e `gh pr view <numero> --json reviews,comments`; aspetta un breve intervallo operativo se il Codex connector ha appena iniziato una review o se GitHub mostra review/check ancora in corso. Non dichiarare "pubblicato", "done" o "nessun commento aperto" finche questo controllo post-merge non e stato eseguito sull'ultimo stato disponibile.
- Quando inizi un nuovo comando o una nuova operazione su questa repository e l'ultima run GitHub Actions rilevante per il branch/SHA corrente risulta `failed`, sospendi l'attività richiesta quanto basta per ispezionare prima il problema (`scripts/current_failed_runs.py`, `gh run list`, `gh run view`, log/check della PR o del branch corrente). Non inseguire run vecchie o di branch non correlati. Se la causa è chiara, riproducibile e correggibile localmente senza allargare lo scope in modo rischioso, sistemala e verifica la correzione prima di procedere; se invece dipende da segreti, infrastruttura, flaky esterno o richiede una scelta di prodotto, riportalo subito all'utente con evidenza e proposta di prossimo passo.
- Prima di aprire o mergiare una PR, fai una review interna del diff e correggi automaticamente solo problemi chiari, locali e non ambigui.
- Non lasciare commenti bot su GitHub per la review salvo richiesta esplicita dell'utente; riporta eventuali rilievi in chat.
- Le PR devono indicare: contesto/problema, soluzione adottata, impatti/rischi, classificazione del cambio, impatto deploy/release e test effettuati.
- Se una PR deve produrre una release, includi una sezione `Release note` di 1-3 frasi in linguaggio naturale; se è solo manutenzione interna, usa un tipo non rilasciabile (`chore:`, `ci:`, `test:`, `refactor:`, `build:`). Usa `skip-changelog` solo per escludere la PR dalle release note generate da GitHub, non come sostituto del tipo PR per `release-please`.
- Se apri una PR come draft per far partire i check, monitora i check della PR e rimuovi automaticamente lo stato draft appena i check richiesti sono verdi, salvo richiesta esplicita contraria o dubbi residui da risolvere prima della review.
- Per il versioning, la repository è `release-please`-first:
  - non aggiornare manualmente `CHANGELOG.md`, `.release-please-manifest.json`, il campo `version` di `pyproject.toml` o `src/docmolder/__init__.py` nelle PR normali;
  - il bump versione e il changelog di release spettano solo alla Release PR generata dal workflow automatico;
  - dopo il merge di una PR funzionale, se `release-please` apre o aggiorna una Release PR, monitorala automaticamente, aspetta i check richiesti, rimuovi eventuale draft se presente e mergiala senza chiedere un via esplicito ulteriore;
  - fermati prima del merge della Release PR solo se i check falliscono, se la Release PR contiene cambi inattesi rispetto a versione/changelog/manifest previsti, se emergono conflitti o se l'utente ha chiesto esplicitamente di non rilasciare;
  - se una modifica ordinaria tocca quei file, fermati e riallinea la PR al flusso ufficiale prima del merge.

## 10) Deploy e operazioni

- Il workflow `Deploy VPS` automatico deve restare path-aware: parte su `main` solo per file deploy-relevant. Per verifiche senza deploy usa `VPS Check`; per ripristinare una revisione usa `Rollback VPS`.
- Non fare deploy inutili: prima di mergeare o avviare workflow che possono deployare, verifica che il diff sia davvero deploy-relevant e che il deploy sia coerente con la richiesta corrente.
- Se target, rischio, intento o consenso operativo sono ambigui, fermati e chiedi conferma prima di procedere.
- Per deploy da Codex cloud, seguire `docs/CODEX_CLOUD_DEPLOY.md`.
- Per deploy o manutenzione VPS, seguire `docs/VPS_RUNBOOK.md` e riportare sempre comandi eseguiti, esito e verifiche.
- Dopo un deploy, non limitarti allo stato `active`: controlla anche log recenti e percorso utente minimo quando possibile.

## 11) Definizione di Done

Una modifica è “done” se:
- risolve la richiesta senza regressioni evidenti;
- mantiene coerenza con architettura e convenzioni esistenti;
- include verifiche eseguite e limiti noti;
- aggiorna documentazione o roadmap solo quando serve davvero;
- non lascia file temporanei, dati utente o modifiche non correlate.

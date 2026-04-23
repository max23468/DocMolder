# AGENTS.md — Istruzioni operative per Codex (DocMolder)

Questo file definisce linee guida persistenti per gli agenti che lavorano in questa repository.
Scope: intera repository, salvo override in `AGENTS.md` più specifici in sottocartelle.

## 1) Contesto da leggere prima

Prima di modifiche non banali, orientati con i documenti rilevanti per la task:
- `docs/CONTEXT.md` per lo stato sintetico del progetto;
- `docs/DECISIONS.md` per il perimetro prodotto;
- `docs/ROADMAP.md` per le priorità correnti;
- `docs/LOCAL_DEV.md` per setup e comandi di verifica;
- `docs/VERSIONING.md` e `docs/RELEASE_PROCESS.md` quando la task riguarda commit, PR, release o deploy.

Il file `AGENTS.md` nella root è solo un puntatore: in caso di dubbio prevale questo file.

## 2) Obiettivo di lavoro

- Preferire modifiche chiare, coese e verificabili.
- Le modifiche importanti sono accettabili quando servono, ma vanno prima esplicitate come piano e poi spezzate in passaggi comprensibili, testabili e, quando possibile, accompagnati da rollback o mitigazione chiari.
- Preferire robustezza, leggibilità e semplicità operativa.
- Evitare side-effect non richiesti rispetto alla task dell'utente.
- Tenere DocMolder nel suo perimetro: utility documentale Telegram-first, semplice, guidata e affidabile.

## 3) Prima di intervenire

- Controlla lo stato del worktree con `git status --short`.
- Comprendi il flusso toccato prima di editare: handler Telegram, pipeline documentale, session store, servizi, config o deploy.
- Non revertire modifiche già presenti se non richiesto esplicitamente.
- Se la richiesta è ambigua, fermati e fai domande mirate all'utente prima di scegliere approccio, scope o comportamento.

## 4) Stile e qualità del codice

- Segui le convenzioni già presenti nel progetto.
- Usa nomi espliciti e coerenti con il dominio del progetto.
- Evita blocchi troppo grandi: favorisci funzioni piccole e testabili.
- Non aggiungere commenti ridondanti; commenta solo decisioni non ovvie.
- Non inserire `try/except` attorno agli import.
- Non introdurre nuove dipendenze senza avvisare prima l'utente e spiegare motivazione, impatto e alternative.

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
- Per modifiche a runtime dir, backup, restore o VPS, verifica anche `docs/VPS_RUNBOOK.md`.

## 7) Testing e verifica minima

Prima del commit, esegui i check rilevanti alla modifica:
- suite completa: `make test`;
- compilazione/import: `make compile`;
- test mirati: `.venv/bin/python -m unittest tests.<modulo>`;
- smoke Telegram: `make smoke-ui`, solo quando serve e quando l'ambiente locale lo permette.

Se un check non è eseguibile nell'ambiente corrente, dichiaralo esplicitamente con motivo e rischio residuo.
Nelle risposte finali non ripetere l'elenco delle verifiche eseguite come rito: citale solo se sono richieste esplicitamente, se servono per PR/release/audit, se falliscono, se non sono eseguibili o se lasciano un rischio residuo utile da conoscere.

## 8) Documentazione e roadmap

- Aggiorna la documentazione quando l'utente lo chiede o quando cambia un comportamento utente, operativo o di sviluppo.
- Non aggiornare il changelog di release nelle PR normali.
- Nella roadmap, gli item completati vanno rimossi dalla checklist; non usare checkbox segnate come completate per elementi già fatti.
- Non aggiungere roadmap laterali se la task può essere chiusa con un intervento piccolo e verificabile.

## 9) Commit, PR e release

- Un commit deve essere coeso: una modifica logica principale.
- Messaggi commit chiari, in forma imperativa, con scope quando utile.
- Il flusso ufficiale è branch dedicato, PR verso `main`, CI verde e squash merge.
- Il titolo PR deve seguire Conventional Commits perché guida `release-please`.
- Quando fai squash merge, non sovrascrivere il subject rimuovendo il suffisso `(#PR)`: i guardrail su `main` richiedono commit nel formato `docs: esempio (#123)`.
- Quando inizi una nuova operazione GitHub o riprendi lavoro su una PR, controlla prima se ci sono commenti/review bot o thread inline rimasti aperti; se sono azionabili, implementa quanto segnalano, verifica la correzione e chiudi/elimina/risolvi il commento o thread quando possibile.
- Prima di aprire o mergiare una PR, fai una review interna del diff e correggi automaticamente solo problemi chiari, locali e non ambigui.
- Non lasciare commenti bot su GitHub per la review salvo richiesta esplicita dell'utente; riporta eventuali rilievi in chat.
- Le PR devono indicare: contesto/problema, soluzione adottata, impatti/rischi e test effettuati.
- Se apri una PR come draft per far partire i check, monitora i check della PR e rimuovi automaticamente lo stato draft appena i check richiesti sono verdi, salvo richiesta esplicita contraria o dubbi residui da risolvere prima della review.
- Per il versioning, la repository è `release-please`-first:
  - non aggiornare manualmente `CHANGELOG.md`, `.release-please-manifest.json`, `pyproject.toml` o `src/docmolder/__init__.py` nelle PR normali;
  - il bump versione e il changelog di release spettano solo alla Release PR generata dal workflow automatico;
  - dopo il merge di una PR funzionale, se `release-please` apre o aggiorna una Release PR, monitorala automaticamente, aspetta i check richiesti, rimuovi eventuale draft se presente e mergiala senza chiedere un via esplicito ulteriore;
  - fermati prima del merge della Release PR solo se i check falliscono, se la Release PR contiene cambi inattesi rispetto a versione/changelog/manifest previsti, se emergono conflitti o se l'utente ha chiesto esplicitamente di non rilasciare;
  - se una modifica ordinaria tocca quei file, fermati e riallinea la PR al flusso ufficiale prima del merge.

## 10) Deploy e operazioni

- Esegui deploy, reboot, modifiche VPS o aggiornamenti `.env` solo quando l'utente li ha richiesti esplicitamente o ha già dato consenso chiaro per quella specifica operazione.
- Prima di un'azione operativa con impatto su VPS, servizio o configurazione, chiedi consenso esplicito indicando cosa farai, perché serve, impatto atteso, verifica prevista e possibile rollback.
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

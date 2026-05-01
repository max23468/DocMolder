# Readiness 1.0

Questo documento definisce quando `DocMolder` può essere promosso a `1.0.0` e
conserva il record della promozione eseguita.

La 1.0 non aggiunge automaticamente nuove feature: serve a dichiarare stabile il perimetro attuale del prodotto, il flusso operativo e le aspettative minime per utenti e maintainer.

## Stato della promozione

La promozione a `1.0.0` è stata completata il 2026-04-28. La linea stabile
corrente e `1.x`; dopo un follow-up documentale sul cleanup del target release,
la versione live e `docmolder-v1.0.1`.

## Baseline corrente

- release stabile corrente: `docmolder-v1.0.1`
- canale ordinario corrente: PR su `main`, CI prudente, Release Please e deploy via webhook privato GitHub -> VPS
- perimetro prodotto: utility documentale Telegram-first, non storage permanente, non editor PDF generalista

## Stato audit corrente

Verifica del 2026-04-28 sulla VPS `docmolder.duckdns.org`, aggiornata dopo la
release `1.0.1`:

- tag live: `docmolder-v1.0.1`
- healthcheck con env VPS: `status: ok`
- smoke tecnico VPS: `DocMolder smoke check OK`
- log `docmolder` ultimi 10 minuti: nessun warning/error
- smoke Telegram Desktop `make smoke-ui` completato con piano `full`
- evidenza runtime dello smoke Telegram:
  - job `images_to_pdf` riuscito
  - job `pdf_grayscale` riuscito sul PDF generato

Questa baseline conferma che la promozione e il follow-up `1.0.1` sono stati
pubblicati e verificati. Il target temporaneo `DOCMOLDER_RELEASE_TARGET_VERSION`
deve restare assente da `/etc/docmolder/release.env` dopo la release.

## Criteri per dire "1.0"

### Prodotto

- i flussi principali sono chiari e non richiedono nuove decisioni di prodotto:
  - PDF da immagini con formato originale o A4
  - compressione PDF
  - scala di grigi
  - merge PDF
  - split PDF
  - estrazione, riordino ed eliminazione pagine
  - rotazione manuale e auto-orientamento PDF
  - watermark testuale
  - raddrizzamento foto documento
  - storico e rilancio job
- la superficie pubblica resta essenziale: `/start`, `/help`, `/history`, `/status`, `/reset`
- `/admin` resta nascosto agli utenti comuni e coerente con il modello operativo corrente
- non ci sono feature critiche già decise ma non implementate

### UX Telegram

- i messaggi principali sono comprensibili senza leggere la documentazione
- le tastiere inline mostrano azioni compatibili e non propongono operazioni impossibili
- gli errori utente più comuni suggeriscono un prossimo passo pratico
- `/status` e `/history` aiutano davvero a recuperare il contesto

### Dati e sicurezza

- i file utente restano temporanei
- i log non contengono contenuti documentali o segreti
- backup SQLite, runtime dir e file env restano confinati alla VPS
- le decisioni ancora aperte su cancellazione completa e pruning job sono note e non bloccano la 1.0 se dichiarate come limite del servizio

### Operatività

- deploy standard via webhook VPS funzionante
- auto-release VPS funzionante
- healthcheck e smoke tecnico post-deploy funzionanti
- backup SQLite recente e verificabile
- runbook VPS aggiornato rispetto al comportamento reale
- rollback documentato come fallback operativo

### Qualità

- gate locale completo passa
- smoke Telegram funzionale rapido passa almeno sui flussi principali
- non ci sono commenti Codex connector aperti sulla PR di preparazione 1.0
- non ci sono run fallite sul branch o SHA corrente

## Smoke test richiesti per una promozione major

Prima di una PR che promuove a una major `X.0.0`:

1. Smoke tecnico VPS:
   - servizio `docmolder` active
   - revisione live allineata
   - healthcheck `status: ok`
   - log recenti senza warning/error nuovi legati al deploy
2. Smoke Telegram rapido:
   - `make smoke-ui` oppure `scripts/smoke_telegram_desktop.py --plan full`
   - verifica che il bot risponda in chat privata
   - verifica PDF da immagini, compressione/follow-up e storico
3. Verifica UI mirata:
   - controllo manuale rapido di leggibilità messaggi e pulsanti inline su almeno un risultato PDF

Se Telegram Desktop non è disponibile nell'ambiente corrente, la PR 1.0 deve dirlo esplicitamente e lasciare il smoke funzionale come pre-merge manuale.

## Meccanica release major esplicita

La 1.0 segue il criterio generale per le major release definito in
[VERSIONING.md](./VERSIONING.md#criterio-per-release-major-x00), con una
particolarità: può essere motivata dalla stabilizzazione del perimetro attuale,
anche senza introdurre breaking change.

Il flusso SemVer normale pre-1.0 porta:

- `fix:` a patch
- `feat:` a minor
- breaking change a minor finché il major corrente e `0`

Per promuovere intenzionalmente `0.x` a `1.0.0`, o una futura linea stabile a
una nuova major `X.0.0`, serve quindi un percorso esplicito di graduation
release. Il percorso atteso è:

1. aprire una PR dedicata, ad esempio `docs(release): prepare DocMolder X.0`
2. includere in PR il risultato della checklist di questo documento
3. includere nel corpo PR la sezione `Major release rationale`
4. coordinare il target major nel flusso Release Please prima del merge finale
5. mergeare la PR su `main`, lasciando che il webhook esegua il deploy
6. attendere conferma di Release Please, tag `docmolder-vX.0.0` e deploy del commit release
7. verificare GitHub Release, health, smoke tecnico e log post-release

Una major non va ottenuta con bump manuali casuali dei file release-owned dentro
una feature PR ordinaria.

## Major release rationale

`docmolder-v1.0.0` e giustificata come release di stabilizzazione, non come
breaking change.

- Contratto utente stabile: la superficie pubblica resta `/start`, `/help`,
  `/history`, `/status`, `/reset`; i flussi principali PDF/immagini sono
  definiti e verificati.
- Contratto operativo stabile: il percorso ordinario resta PR su `main`,
  Release Please, webhook privato GitHub -> VPS, healthcheck e smoke
  post-deploy.
- Contratto dati dichiarato: file utente temporanei, retention breve, job
  history non permanente e assenza di cancellazione completa self-service nel
  perimetro attuale.
- Perimetro prodotto stabile: DocMolder resta utility documentale Telegram-first,
  non editor PDF generalista, non storage documentale permanente e non dashboard
  web-first.
- Smoke richiesti: gate locale, smoke Telegram Desktop, health/smoke tecnico VPS
  prima e dopo release.

## Decisione condivisa prima del bump

Prima di impostare il target `1.0.0`, sono confermati:

- nome e posizionamento pubblici restano quelli correnti
- non vogliamo introdurre nuove feature prima della 1.0
- accettiamo come limiti dichiarati: best-effort, retention breve, storico job non permanente, cancellazione completa self-service non ancora presente
- il maintainer è pronto a considerare i cambi successivi alla 1.0 come contratti più stabili, soprattutto per UX, runbook e dati

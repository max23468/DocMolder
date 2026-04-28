# Readiness 1.0

Questo documento definisce quando `DocMolder` puo essere promosso a `1.0.0`.

La 1.0 non aggiunge automaticamente nuove feature: serve a dichiarare stabile il perimetro attuale del prodotto, il flusso operativo e le aspettative minime per utenti e maintainer.

## Baseline corrente

- release stabile corrente: `docmolder-v0.12.0`
- canale ordinario: PR su `main`, deploy via webhook privato GitHub -> VPS, auto-release VPS
- perimetro prodotto: utility documentale Telegram-first, non storage permanente, non editor PDF generalista

## Stato audit corrente

Verifica del 2026-04-28 sulla VPS `docmolder.duckdns.org`:

- revisione live: `d20a5b6`
- tag live: `docmolder-v0.12.0`
- healthcheck con env VPS: `status: ok`
- smoke tecnico VPS: `DocMolder smoke check OK`
- log `docmolder` ultimi 10 minuti: nessun warning/error

Questa baseline conferma che `0.12.0` e un punto di partenza valido per la
readiness. Prima del bump effettivo a `1.0.0` resta comunque necessario ripetere
uno smoke post-release e completare lo smoke funzionale Telegram.

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
- non ci sono feature critiche gia decise ma non implementate

### UX Telegram

- i messaggi principali sono comprensibili senza leggere la documentazione
- le tastiere inline mostrano azioni compatibili e non propongono operazioni impossibili
- gli errori utente piu comuni suggeriscono un prossimo passo pratico
- `/status` e `/history` aiutano davvero a recuperare il contesto

### Dati e sicurezza

- i file utente restano temporanei
- i log non contengono contenuti documentali o segreti
- backup SQLite, runtime dir e file env restano confinati alla VPS
- le decisioni ancora aperte su cancellazione completa e pruning job sono note e non bloccano la 1.0 se dichiarate come limite del servizio

### Operativita

- deploy standard via webhook VPS funzionante
- auto-release VPS funzionante
- healthcheck e smoke tecnico post-deploy funzionanti
- backup SQLite recente e verificabile
- runbook VPS aggiornato rispetto al comportamento reale
- rollback documentato come fallback operativo

### Qualita

- gate locale completo passa
- smoke Telegram funzionale rapido passa almeno sui flussi principali
- non ci sono commenti Codex connector aperti sulla PR di preparazione 1.0
- non ci sono run fallite sul branch o SHA corrente

## Smoke test richiesti

Prima della PR che promuove a `1.0.0`:

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
   - controllo manuale rapido di leggibilita messaggi e pulsanti inline su almeno un risultato PDF

Se Telegram Desktop non e disponibile nell'ambiente corrente, la PR 1.0 deve dirlo esplicitamente e lasciare il smoke funzionale come pre-merge manuale.

## Meccanica release 1.0

La 1.0 segue il criterio generale per le major release definito in
[VERSIONING.md](./VERSIONING.md#criterio-per-release-major-x00), con una
particolarita: puo essere motivata dalla stabilizzazione del perimetro attuale,
anche senza introdurre breaking change.

Il flusso SemVer normale pre-1.0 porta:

- `fix:` a patch
- `feat:` a minor
- breaking change a minor finche il major corrente e `0`

Per promuovere intenzionalmente `0.x` a `1.0.0`, serve quindi un percorso esplicito di graduation release. Il percorso atteso e:

1. aprire una PR dedicata, ad esempio `docs(release): prepare DocMolder 1.0`
2. includere in PR il risultato della checklist di questo documento
3. includere nel corpo PR la sezione `Major release rationale`
4. mergeare la PR su `main`
5. far girare auto-release VPS con target esplicito `1.0.0`
6. verificare tag, GitHub Release, deploy del commit release e smoke post-release

La 1.0 non va ottenuta con bump manuali casuali dei file release-owned dentro una feature PR ordinaria.

## Decisione condivisa prima del bump

Prima di impostare il target `1.0.0`, confermare:

- il nome e posizionamento pubblico restano quelli correnti
- non vogliamo introdurre nuove feature prima della 1.0
- accettiamo come limiti dichiarati: best-effort, retention breve, storico job non permanente, cancellazione completa self-service non ancora presente
- il maintainer e pronto a considerare i cambi successivi alla 1.0 come contratti piu stabili, soprattutto per UX, runbook e dati

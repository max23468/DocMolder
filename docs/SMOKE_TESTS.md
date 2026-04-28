# Smoke Test Post-Deploy

Questa guida definisce come verificare `DocMolder` dopo un deploy senza perdere tempo in test manuali macchinosi.

Obiettivo: separare i controlli in tre livelli, dal più veloce al più realistico.

## Livello 1: Smoke Tecnico VPS

Questo livello non verifica davvero l'esperienza utente, ma dice subito se il deploy è sano.

Checklist minima:

```bash
sudo systemctl is-active docmolder
sudo -u docmolder git -C /opt/docmolder/app rev-parse HEAD
sudo journalctl -u docmolder -n 30 --no-pager
```

Passa se:

- il servizio è `active`
- la revisione live coincide con l'ultimo commit deployato
- i log recenti mostrano `Application started`
- non ci sono errori immediati di bootstrap

Quando usarlo:

- sempre, subito dopo `update-vps.sh`
- prima di fare qualsiasi test funzionale

## Livello 2: Smoke Rapido via Telegram Desktop Scriptato

Questo è il modo consigliato per i prossimi smoke test funzionali.

Perché è più veloce:

- evita click manuali ripetitivi
- usa scorciatoie tastiera stabili di Telegram Desktop
- automatizza l'invio di file locali senza dipendere dal mouse
- permette di rilanciare gli stessi flussi sempre nello stesso ordine

### Nota importante

La Bot API da sola non basta per simulare un utente che scrive al bot.

Con il token del bot puoi:

- interrogare il bot
- inviare messaggi dal bot verso un utente

Ma non puoi:

- impersonare un utente reale che scrive al bot
- coprire da sola un flusso end-to-end chat-first

Per i veri smoke test dei flussi utente, il canale giusto è una automazione della chat utente, oggi tramite Telegram Desktop.

### Script disponibile

È disponibile lo script:

- [scripts/smoke_telegram_desktop.py](../scripts/smoke_telegram_desktop.py)

Target rapido:

```bash
make smoke-ui
```

Oppure:

```bash
.venv/bin/python scripts/smoke_telegram_desktop.py --plan full
```

Modalità utili:

```bash
.venv/bin/python scripts/smoke_telegram_desktop.py --list-plans
.venv/bin/python scripts/smoke_telegram_desktop.py --plan wizard-a4 --pause
.venv/bin/python scripts/smoke_telegram_desktop.py --plan public-trust --pause
.venv/bin/python scripts/smoke_telegram_desktop.py --plan full --cleanup-assets
```

### Piani supportati

- `wizard-a4`: reset, invio 2 immagini, `PDF da immagini`, conferma A4, scelta bordi stretti
- `pdf-followup`: reset, invio PDF, `Comprimi PDF`, breve attesa, `Scala di grigi`
- `history`: invia `/history`
- `public-trust`: verifica `/start`, `/help`, `/start privacy`, `/status`, upload PDF, output, `/history` e `/reset`; con `--pause` permette di controllare anche la conferma inline di cancellazione dati live
- `full`: combina i passaggi principali per un controllo funzionale rapido

### Come lavora

Lo script:

1. crea fixture piccole locali
2. attiva Telegram Desktop
3. apre la chat `DocMolder` con ricerca rapida
4. invia messaggi via tastiera
5. incolla file via clipboard di macOS
6. opzionalmente si ferma tra gli step se usi `--pause`
7. opzionalmente ripulisce gli asset se usi `--cleanup-assets`

### Prerequisiti

- Telegram Desktop aperto e già autenticato
- permessi Accessibilità abilitati per Terminale / app che esegue lo script
- virtualenv del progetto disponibile

### Vantaggio pratico

Il punto lento dei test recenti non era il bot, ma l'interazione manuale con Telegram Desktop.

Questo script elimina quasi tutto il lavoro ripetitivo:

- apertura chat
- invio messaggi
- allegato immagini
- allegato PDF

## Livello 3: Verifica UI Mirata

Questo livello è utile, ma solo per i casi in cui serve davvero verificare la resa reale in chat.

Va riservato a:

- pulsanti inline
- reply keyboard
- copy finale e leggibilità del flusso
- regressioni apparentemente solo UI/conversazionali

### Limiti osservati

Durante i test reali recenti:

- i click via accessibility in Telegram desktop non erano sempre affidabili
- il passaggio più lento era l'invio allegati
- i test testuali funzionavano meglio via tastiera che via mouse

### Trucchi che hanno funzionato

- `Cmd+K` per aprire rapidamente la chat `DocMolder`
- `KP_Enter` per inviare il messaggio in questa installazione Telegram
- clipboard di macOS per incollare immagini o file locali in chat
- script locale per riusare questi passaggi senza rifarli a mano

### Quando usarlo

- solo dopo che i livelli 1 e 2 sono verdi
- quando si vuole verificare davvero il feeling utente finale

## Modalità Consigliate

Per evitare test lenti, usare queste tre modalità standard.

### Modalità A: deploy smoke minimo

Usa solo il Livello 1.

Quando usarla:

- fix tecnici interni
- refactor senza impatto UX

Tempo atteso: 1-2 minuti.

### Modalità B: deploy smoke funzionale rapido

Usa Livello 1 + Livello 2.

Quando usarla:

- cambi sui flussi Telegram
- cambi a sessione, follow-up, parser testuale, storico, pulsanti

Tempo atteso: 3-6 minuti.

Questa dovrebbe diventare la modalità standard.

### Modalità C: deploy smoke completo

Usa Livello 1 + Livello 2 + una piccola verifica del Livello 3.

Quando usarla:

- modifiche UX importanti
- cambi sui pulsanti inline
- regressioni sospette solo nella UI Telegram

Tempo atteso: 5-10 minuti.

## Asset di Test

Per velocizzare gli smoke test conviene avere asset locali stabili e piccoli.

Suggerimento:

- mantenere una cartella repo tipo `tmp/manual-test-assets/` solo locale
- usare 2 immagini semplici e 1 PDF minimo
- evitare file reali utente nei test manuali

Gli asset vengono già creati automaticamente dallo script desktop in `tmp/manual-test-assets/`.

Se in futuro servirà un livello ancora più forte, la strada giusta non è la Bot API ma un client utente dedicato via MTProto, con credenziali separate di test.

## Raccomandazione Operativa

Per i prossimi deploy:

- fare sempre Livello 1
- adottare Livello 2 come default per gli smoke test funzionali
- usare Livello 3 solo come controllo finale mirato, non come percorso principale

In pratica:

- Telegram Desktop scriptato deve essere il canale primario di smoke test funzionale
- la verifica UI manuale deve restare un controllo secondario e mirato

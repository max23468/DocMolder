# Operatività Telegram

Panoramica pratica delle capacità operative Telegram introdotte nel bot.

## Comandi utente

- `/history`: mostra gli ultimi job personali, con dettaglio e rilancio.
- `/last`: rilancia l'ultimo job personale senza dover reinviare i file.
- `/access`: mostra stato accesso, sessione corrente e coda personale.
- `/status`: riepilogo rapido della sessione corrente.
- `/reset`: azzera sessione e preferenze rapide.

## Deep link supportati

Il bot supporta anche payload su `/start <payload>` per scorciatoie contestuali:

- `/start help`
- `/start history`
- `/start status`
- `/start access`
- `/start last`
- `/start retry_<id>`
- `/start retry_latest`

I deep link di retry sono limitati ai job dell'utente che li apre.

## Console admin

Se `DOCMOLDER_ADMIN_USER_IDS` è configurata, gli admin possono usare:

- `/admin`: panoramica generale.
- `/queue`: stato coda, job queued/running e ultimi falliti.
- `/health`: stato runtime, SQLite, backup e worker.
- `/metrics`: metriche Telegram aggregate da `app_meta`.
- `/job <selector>`: dettaglio rapido di un job.
- `/retry <selector>`: rilancia un job esistente.
- `/pause`: mette il bot in modalità manutenzione.
- `/resume`: riattiva il servizio.

Selector supportati per `/job` e `/retry`:

- id numerico
- `latest`
- `failed`
- `running`
- `queued`
- `succeeded`

Per `/retry` è disponibile anche:

- `--no-auto-rotate`

utile per rilanciare un job disabilitando la correzione automatica dell'orientamento PDF.

## Dashboard inline admin

La dashboard inline permette scorciatoie veloci per:

- panoramica
- coda
- health
- metriche
- pausa/ripresa servizio
- ultimo fallito
- ultimo running
- ultimo queued
- ultimo succeeded
- ultimo job in assoluto

## Resilienza Bot API

I flussi Telegram più sensibili usano retry automatici su:

- `429 RetryAfter`
- `TimedOut`
- `NetworkError`

Le metriche aggregate tengono traccia di:

- comandi
- callback
- upload documento/foto
- retry `sendMessage`
- retry `sendDocument`

## Anti-spam e hardening

- callback admin con anti-replay leggero a finestra breve
- validazione più stretta dei callback più importanti
- messaggi uniformi per callback invalide o scadute
- digest sugli alert admin ripetuti
- throttling delle notifiche admin per nuovi utenti

## Note operative

- il bot resta in polling, coerentemente con le decisioni architetturali correnti
- i file utente restano temporanei; non è stato introdotto storage permanente dei file
- le metriche Telegram attuali sono volutamente leggere e persistono in `app_meta`

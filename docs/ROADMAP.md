# Roadmap Prodotto

Questa roadmap raccoglie direzione, priorità e prossimi passi correnti di
`DocMolder`. Lo storico esteso della vecchia roadmap sta in
[`ROADMAP_HISTORY.md`](./ROADMAP_HISTORY.md); release e versioni restano in
`CHANGELOG.md`, GitHub Releases e nei documenti di release.

## Ora

- Tenere lo sviluppo feature in pausa dopo la linea `1.x` iniziale completata.
- Concentrarsi su stabilizzazione prudente, osservazione del soft launch e
  manutenzione ordinaria.
- Monitorare `/admin`, healthcheck, log recenti, alert Telegram admin e soglie
  operative prima di riaprire una nuova fase.

## Prossimo

- Eseguire smoke Telegram `public-trust` quando serve una verifica funzionale
  reale dopo deploy, correzioni o cambi operativi.
- Raccogliere frizioni UX o failure ricorrenti prima di definire nuove funzioni.
- Aprire una nuova fase solo con bug riproducibile, regressione utente, soglia
  operativa superata, feedback concreto o decisione esplicita di prodotto.

## Più avanti

- Rivalutare crescita pubblica, canali, automazioni o architettura solo dopo
  evidenza reale di uso, limiti o attriti.
- Mantenere il perimetro Telegram-first, pubblico prudente e best-effort finché
  una decisione dedicata non cambia il modello di servizio.

## Bloccato

- Nessuna nuova fase prodotto è approvata. Ogni riapertura deve definire
  obiettivo, verifiche, impatto release/deploy e perimetro Telegram-first.

## Fatto recente

- La readiness `1.0.0` è chiusa e documentata in
  [`ONE_DOT_ZERO_READINESS.md`](./ONE_DOT_ZERO_READINESS.md).
- La roadmap 1.x iniziale è completata fino a `docmolder-v1.5.0`.
- Sono chiusi i blocchi privacy/retention, UX trust, preset leggeri, qualità
  output/scansioni e osservabilità prudente.

## Regole

- La roadmap non è un changelog.
- La roadmap non conserva checklist completate o fasi chiuse come archivio.
- Le idee non promosse stanno in `BACKLOG.md`.
- Le decisioni stabili stanno in `DECISIONS.md` o in ADR dedicate.
- Aggiornare la roadmap solo quando cambiano direzione, priorità, fase o
  backlog; non per micro-decisioni chiuse nello stesso intervento.
- Ogni voce attiva deve indicare un prossimo passo operativo reale.

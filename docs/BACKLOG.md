# Backlog DocMolder

Il backlog raccoglie possibilità, debiti e decisioni non ancora promosse in roadmap.

Una voce nel backlog non è scope approvato. La roadmap corrente resta
[ROADMAP.md](./ROADMAP.md); le decisioni aperte strutturali restano in
[DECISIONS_PENDING.md](./DECISIONS_PENDING.md) finché non vengono trasformate in
decisioni stabili.

## Idee prodotto

- Valutare eventuali esplorazioni OCR solo come ricerca tecnica non pubblica,
  senza promessa utente e senza allargare il perimetro Telegram-first.
- Valutare una futura localizzazione inglese o multilingua solo dopo segnali
  reali di uso, mantenendo l'italiano come lingua prodotto iniziale.
- Valutare una promozione pubblica più ampia solo se le soglie operative Fase 13
  restano sotto controllo con dati reali.

## Backlog tecnico

- Migrare progressivamente decisioni stabili da `docs/DECISIONS.md` a
  `docs/decisions/`, mantenendo `DECISIONS.md` come riepilogo finché serve.
- Valutare una procedura più guidata per export o restore dei backup SQLite in
  manutenzione.
- Rivedere le soglie prudenziali Fase 13 dopo osservazione reale in produzione.
- Valutare CodeQL o altri check GitHub solo se la superficie o il rischio
  crescono.

## Operatività

- Valutare alert esterni oltre agli alert Telegram admin.
- Definire il livello minimo di smoke test post-deploy da considerare
  bloccante.
- Formalizzare una policy di rotazione del token Telegram.
- Valutare una procedura minimale di incidente, con template operativo.
- Valutare se separare ulteriormente backup, runtime e log su filesystem.

## Bug

- Nessun bug aperto in questo documento.
- La `Codex feedback inbox` GitHub resta la fonte operativa per thread Codex
  actionable.

## Debiti

- Mantenere separati roadmap, backlog e decisioni: la roadmap non deve tornare a
  essere una lista di possibilità.
- Evitare che nuove idee prodotto spingano DocMolder verso editor PDF
  generalista, document management, web app o API pubblica senza decisione
  esplicita.
- Verificare periodicamente che `docs/CONTEXT.md` resti un handoff sintetico e
  non sostituisca runbook o documenti specialistici.

## Attività operative ricorrenti

- Eseguire `make github-maintenance` prima di publish, merge, release o giro sui
  commenti Codex.
- Usare `make ops-report` o i comandi del runbook per verifiche operative e VPS.
- Verificare il riallineamento release/tag in `publish_doctor`/`preflight_publish` prima di commit o merge quando si toccano i file di rilascio
  o ci sono dubbi di allineamento del release metadata.
- Usare smoke Telegram mirati quando il cambio tocca flussi utente, deploy o
  comportamento operativo.

## Regole

- Quando una voce diventa prioritaria, promuoverla in `docs/ROADMAP.md`.
- Quando una voce diventa decisione stabile, collegarla o spostarla in
  `docs/decisions/`.
- Non usare il backlog come storico dei lavori completati.

# Changelog

Questo file raccoglie le modifiche rilevanti di `DocMolder`.

Il formato e semplice e orientato al progetto: aggiorniamo il changelog solo quando una modifica e gia effettiva nel codice o nella documentazione, non per elementi ancora pianificati in roadmap.

## Indice

- [2026-04-06](#2026-04-06)

## 2026-04-06

### Aggiunto

- scelta guidata tra formato originale immagini e impaginazione A4 con bordi configurabili durante la creazione di PDF da immagini
- possibilita di rifare un'elaborazione PDF senza auto-rotazione quando il risultato e stato corretto automaticamente
- changelog di progetto per raccogliere le modifiche rilevanti gia introdotte

### Modificato

- il flusso PDF privilegia la correzione automatica dell'orientamento nelle elaborazioni compatibili al posto della rotazione manuale esposta come azione principale
- il README e la documentazione interna descrivono in modo piu coerente le funzionalita attuali
- la roadmap e stata riorganizzata come checklist operativa separata dal changelog
- i flussi da immagini che producono PDF in scala di grigi generano ora il PDF grigio direttamente, senza dipendere da una riconversione successiva del PDF
- i messaggi di presa in carico, lavorazione e risultato spiegano meglio quando una conversione PDF puo richiedere piu tempo o usare fallback che non preservano pienamente la struttura nativa

### Tecnico

- ampliata la copertura dei test per il layout dei PDF da immagini e per l'auto-orientamento dei PDF
- ampliata la copertura dei test per PDF vuoti o corrotti, PDF multipagina piu pesanti e documenti con pagine quadrate o orientamenti misti
- aggiunto tracciamento di durata job, dimensione input/output e modalita effettiva del risultato per migliorare il monitoraggio tecnico
- aggiornato il contesto tecnico del progetto per riflettere il nuovo flusso PDF

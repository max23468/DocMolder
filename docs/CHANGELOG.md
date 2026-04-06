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
- comando `/history` con storico degli ultimi job utente, dettaglio essenziale e possibilita di rilanciare una lavorazione gia eseguita
- nuove funzioni PDF su singolo documento: estrazione pagine, riordino pagine, eliminazione pagine, rotazione manuale e watermark testuale

### Modificato

- il flusso PDF privilegia la correzione automatica dell'orientamento nelle elaborazioni compatibili al posto della rotazione manuale esposta come azione principale
- il README e la documentazione interna descrivono in modo piu coerente le funzionalita attuali
- la roadmap e stata riorganizzata come checklist operativa separata dal changelog
- i flussi da immagini che producono PDF in scala di grigi generano ora il PDF grigio direttamente, senza dipendere da una riconversione successiva del PDF
- i messaggi di presa in carico, lavorazione e risultato spiegano meglio quando una conversione PDF puo richiedere piu tempo o usare fallback che non preservano pienamente la struttura nativa
- il report admin evidenzia meglio utilizzo, qualita dei job, fallback raster e azioni che falliscono piu spesso
- il bot puo inviare report admin periodici giornalieri e settimanali senza duplicare lo stesso riepilogo dopo un riavvio
- i limiti operativi comunicano meglio i valori effettivi su file, burst upload e job concorrenti
- la roadmap ora passa direttamente alle fasi funzionali e tecniche successive dopo il completamento della fase operativa
- la tastiera principale e i messaggi guida espongono anche lo storico lavori personale
- il bot gestisce ora piccoli step conversazionali persistenti per chiedere in chat selezione pagine o testo watermark prima di mettere in coda il job
- i report admin periodici evitano ora l'invio di riepiloghi vuoti quando nel periodo non c'e nulla di utile da mostrare

### Tecnico

- ampliata la copertura dei test per il layout dei PDF da immagini e per l'auto-orientamento dei PDF
- ampliata la copertura dei test per PDF vuoti o corrotti, PDF multipagina piu pesanti e documenti con pagine quadrate o orientamenti misti
- aggiunto tracciamento di durata job, dimensione input/output e modalita effettiva del risultato per migliorare il monitoraggio tecnico
- introdotto uno storage meta persistente per report admin periodici e stato operativo del bot
- la riaccodatura dei job dopo riavvio ripulisce meglio stato, errori e metriche residue dei job incompleti
- aggiornato il contesto tecnico del progetto per riflettere il nuovo flusso PDF
- aggiunta una query dedicata per recuperare gli ultimi job di un utente e ampliata la copertura test su storico, dettagli e rilancio dei job
- ampliata la pipeline PDF con operazioni native di estrazione, riordino, eliminazione, rotazione manuale e watermark, insieme ai relativi test automatici

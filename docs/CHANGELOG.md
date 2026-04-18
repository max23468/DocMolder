# Changelog

Questo file raccoglie le modifiche rilevanti di `DocMolder`.

Il formato e semplice e orientato al progetto: aggiorniamo il changelog solo quando una modifica e gia effettiva nel codice o nella documentazione, non per elementi ancora pianificati in roadmap.

## Indice

- [2026-04-18](#2026-04-18)
- [2026-04-15](#2026-04-15)
- [2026-04-06](#2026-04-06)

## 2026-04-18

### Modificato

- riepilogo sessione utente reso piu esplicito con file presenti, anteprima contenuto, azioni consigliate, azioni alternative e prossimo passo suggerito
- messaggi di stato, upload PDF e raccolta immagini allineati al nuovo recap strutturato della sessione
- prompt guidati per estrazione, riordino, eliminazione pagine e watermark resi piu chiari con esempi concreti
- input pagina resi piu tolleranti accettando anche sequenze separate da spazi, come `3 1 2`
- i PDF prodotti dal bot offrono ora azioni di continuazione direttamente dal messaggio risultato, senza dover ricaricare il file per i passaggi successivi piu comuni
- introdotta una memoria rapida e revocabile per alcune scelte frequenti, come preset di compressione e layout immagini verso PDF, azzerata con `/reset`
- alcune richieste testuali naturali su PDF singolo vengono capite direttamente, ad esempio estrazione pagine, rotazione e watermark con parametro gia incluso
- lo storico utente distingue meglio i job per stato, separando piu chiaramente lavori in corso, riusciti e falliti
- i job rilanciati dallo storico o dal risultato tracciano ora esplicitamente la loro origine, cosi `/history` li evidenzia come rilanci separati
- help, prompt guidati e messaggi di correzione input sono stati rifiniti per spiegare meglio formati attesi, limiti e scorciatoie disponibili
- aggiunta [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md) con una strategia esplicita per smoke test post-deploy piu rapidi
- aggiunto [scripts/smoke_telegram_desktop.py](../scripts/smoke_telegram_desktop.py) per automatizzare i principali smoke test post-deploy su Telegram Desktop
- formalizzato Telegram Desktop scriptato come canale principale per smoke test funzionali, lasciando la verifica UI manuale solo per controlli mirati

## 2026-04-15

### Aggiunto

- workflow GitHub Actions di CI (`.github/workflows/ci.yml`) con test unitari e compilazione su Python 3.11, 3.12 e 3.13
- template GitHub per PR e issue (`bug` e `feature`) per standardizzare la gestione del backlog anche in modalita maintainer singolo
- guida operativa `docs/GITHUB_ALIGNMENT.md` con impostazioni repository e best practice GitHub orientate a un progetto gestito da una sola persona

### Modificato

- indice documentazione e README aggiornati per includere la nuova guida di allineamento GitHub

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
- la pipeline PDF gestisce in modo piu robusto il cleanup delle cartelle job anche in caso di errore, oltre a imporre un timeout esplicito ai passaggi `Ghostscript`
- i report admin usano ora una struttura tipizzata dedicata invece di un dizionario generico di contatori
- i payload dei job passano ora da una struttura tipizzata dedicata invece di essere manipolati come JSON anonimo in piu punti del bot
- i file restituiti usano ora nomi piu leggibili, derivati dal file sorgente e dal tipo di trasformazione eseguita
- la tastiera delle azioni e le etichette utente derivano ora da un catalogo centrale condiviso, evitando disallineamenti tra azioni supportate e azioni esposte
- i messaggi operativi di coda e avvio lavorazione sono stati centralizzati fuori dal modulo bot
- la logica di payload job, enqueue e riesecuzione del payload e stata spostata in un modulo dedicato per separare meglio UI Telegram e orchestration dei job

### Tecnico

- ampliata la copertura dei test per il layout dei PDF da immagini e per l'auto-orientamento dei PDF
- ampliata la copertura dei test per PDF vuoti o corrotti, PDF multipagina piu pesanti e documenti con pagine quadrate o orientamenti misti
- aggiunto tracciamento di durata job, dimensione input/output e modalita effettiva del risultato per migliorare il monitoraggio tecnico
- introdotto uno storage meta persistente per report admin periodici e stato operativo del bot
- la riaccodatura dei job dopo riavvio ripulisce meglio stato, errori e metriche residue dei job incompleti
- aggiornato il contesto tecnico del progetto per riflettere il nuovo flusso PDF
- aggiunta una query dedicata per recuperare gli ultimi job di un utente e ampliata la copertura test su storico, dettagli e rilancio dei job
- ampliata la pipeline PDF con operazioni native di estrazione, riordino, eliminazione, rotazione manuale e watermark, insieme ai relativi test automatici
- ridotti alcuni fallback con `except Exception` troppo ampi nella pipeline PDF, distinguendo meglio timeout `Ghostscript` e errori attesi di processing
- ampliata la copertura test su timeout `Ghostscript`, cleanup delle cartelle job e gestione degli errori utente durante l'esecuzione dei job
- aggiunti test dedicati per roundtrip del payload job, allineamento delle azioni esposte e naming degli output

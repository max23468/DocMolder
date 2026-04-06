# Roadmap Prodotto

Questa roadmap raccoglie le priorità attuali di `DocMolder`.

Va letta dentro il perimetro definito in [docs/DECISIONS.md](/Users/Matteo/Documents/DocMolder/docs/DECISIONS.md): `DocMolder` resta una utility documentale chat-first, semplice, guidata e affidabile.

## Indice

- [Fase 1: Rifinitura Prodotto](#fase-1-rifinitura-prodotto)
- [Fase 2: Affidabilità Operativa Avanzata](#fase-2-affidabilita-operativa-avanzata)
- [Fase 3: Comprensione Linguaggio Naturale](#fase-3-comprensione-linguaggio-naturale)
- [Fase 4: Estensioni PDF Mirate](#fase-4-estensioni-pdf-mirate)
- [Fase 5: Evoluzione Esperienza Utente](#fase-5-evoluzione-esperienza-utente)
- [Fase 6: Scansione Documento da Foto](#fase-6-scansione-documento-da-foto)

## Fase 1: Rifinitura Prodotto

- [ ] rendere più esplicito il recap della sessione corrente con file presenti e azioni consigliate
- [ ] aggiungere suggerimenti contestuali sul prossimo passo utile in base al tipo di file ricevuto
- [ ] suggerire azioni utili anche dopo il risultato finale, in base al file appena prodotto
- [ ] migliorare i messaggi finali per renderli più brevi, chiari e uniformi
- [ ] uniformare meglio lo stile visivo e il tono dei messaggi del bot
- [ ] rendere più guidati gli input per selezione pagine e watermark
- [ ] migliorare i messaggi di errore e correzione input per aiutare subito l'utente a riprovare nel formato giusto
- [ ] aggiungere micro-spiegazioni più chiare per scelte come compressione e operazioni PDF sensibili
- [ ] aggiungere spiegazioni preventive più chiare prima delle operazioni PDF più invasive
- [ ] migliorare `/history` con distinzione più chiara tra job riusciti, falliti e rilanciati
- [ ] rendere più naturali alcune richieste testuali frequenti come estrazione pagina, rotazione e watermark
- [ ] introdurre template rapidi per pochi flussi ricorrenti e coerenti, come “scansiona e comprimi” o “foto in A4”
- [ ] rifinire ulteriormente testi azione e dettagli job per massima chiarezza utente

## Fase 2: Affidabilità Operativa Avanzata

- [ ] aggiungere uno smoke check post-deploy sulla VPS
- [ ] rendere la verifica tecnica post-deploy più completa, non limitata al solo stato del servizio
- [ ] introdurre alert admin per errori ripetuti o tassi di fallimento anomali
- [ ] migliorare backup e ripristino del database SQLite
- [ ] introdurre backup automatico del database SQLite con una strategia semplice e verificabile
- [ ] rafforzare test end-to-end o pseudo end-to-end sui flussi Telegram principali

## Fase 3: Comprensione Linguaggio Naturale

- [ ] migliorare il parser degli intenti per capire meglio formulazioni meno rigide e più naturali
- [ ] estrarre dal testo parametri utili come pagine, gradi di rotazione, watermark e livello di compressione
- [ ] ampliare sinonimi e varianti colloquiali per azioni e trasformazioni frequenti
- [ ] introdurre tolleranza leggera agli errori di battitura nelle richieste testuali più comuni
- [ ] gestire meglio frasi miste con azione e contesto, ad esempio richieste riferite esplicitamente a PDF, immagini o pagine
- [ ] aggiungere disambiguazione guidata quando una richiesta testuale può voler dire più cose diverse
- [ ] sfruttare meglio il contesto immediato della conversazione per interpretare il messaggio successivo

## Fase 4: Estensioni PDF Mirate

- [ ] aggiungere split PDF in più file
- [ ] valutare export ZIP per output multipli

## Fase 5: Evoluzione Esperienza Utente

- [ ] gestire meglio riferimenti contestuali come “questo PDF”, “quello” o “l'ultimo job”
- [ ] rafforzare i test conversazionali realistici multi-step sui flussi Telegram più importanti

## Fase 6: Scansione Documento da Foto

- [ ] aggiungere una modalità dedicata di scansione documento distinta dal semplice ritaglio bordi
- [ ] rilevare il contorno del foglio fotografato invece di basarsi solo sul bounding box del contenuto
- [ ] introdurre correzione prospettica per raddrizzare fogli fotografati in modo non perfettamente frontale
- [ ] migliorare la distinzione tra sfondo e carta anche con illuminazione irregolare o sfondi simili al foglio
- [ ] aggiungere una normalizzazione preliminare di luminosità e contrasto prima del ritaglio
- [ ] rendere il rilevamento bordi più robusto tramite strategie basate su edge detection e contorni
- [ ] introdurre fallback tra più strategie di ritaglio, ad esempio foglio, contenuto o formato originale
- [ ] aggiungere un post-processing da scansione per pulizia sfondo, contrasto e resa più leggibile del documento
- [ ] introdurre controlli di qualità input per segnalare foto troppo storte, scure o incomplete
- [ ] migliorare la gestione dei margini finali per evitare ritagli troppo aggressivi

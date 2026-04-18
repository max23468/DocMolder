# Roadmap Prodotto

Questa roadmap raccoglie le priorità attuali di `DocMolder`.

Va letta dentro il perimetro definito in [docs/DECISIONS.md](./DECISIONS.md): `DocMolder` resta una utility documentale chat-first, semplice, guidata e affidabile.

## Indice

- [Fase 1: Rifinitura Prodotto](#fase-1-rifinitura-prodotto)
- [Fase 2: Affidabilità Operativa Avanzata](#fase-2-affidabilita-operativa-avanzata)
- [Fase 3: Comprensione Linguaggio Naturale](#fase-3-comprensione-linguaggio-naturale)
- [Fase 4: Estensioni PDF Mirate](#fase-4-estensioni-pdf-mirate)
- [Fase 5: Evoluzione Esperienza Utente](#fase-5-evoluzione-esperienza-utente)
- [Fase 6: Scansione Documento da Foto](#fase-6-scansione-documento-da-foto)
- [Fase 7: Robustezza VPS e Performance](#fase-7-robustezza-vps-e-performance)
- [Fase 8: Ottimizzazione del Funzionamento](#fase-8-ottimizzazione-del-funzionamento)

## Fase 1: Rifinitura Prodotto

Completata.

## Fase 2: Affidabilità Operativa Avanzata

Completata.

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

## Fase 7: Robustezza VPS e Performance

- [ ] aggiungere un health check post-deploy più forte, non limitato al solo stato `active` del servizio
- [ ] introdurre backup automatico di SQLite con strategia semplice e restore verificabile
- [ ] configurare meglio rotazione log e housekeeping della VPS
- [ ] rendere più rigoroso il cleanup di file temporanei e directory di runtime per evitare accumuli inutili sulla VPS
- [ ] aggiungere monitor leggero di CPU, RAM, disco e crescita del runtime dir
- [ ] introdurre alert su errori anomali o aumenti anomali dei job falliti
- [ ] introdurre limiti più intelligenti sui batch pesanti per evitare saturazione di RAM e CPU su upload molto grandi
- [ ] aggiungere downscale preventivo delle immagini enormi quando eccedono chiaramente il necessario per un PDF leggibile
- [ ] regolare meglio il parallelismo effettivo dei job più costosi per non sovraccaricare la VPS
- [ ] aggiungere piccoli test di carico locali e ripetibili sui flussi più pesanti
- [ ] profilare i flussi più costosi come compressione, grayscale e foto verso PDF
- [ ] rendere più esplicite e controllate le dipendenze di sistema tra locale e VPS
- [ ] aggiungere verifica periodica dello spazio disco disponibile sulla VPS
- [ ] mantenere una retention corta e automatica per log e backup in modo da limitare l'occupazione disco

## Fase 8: Ottimizzazione del Funzionamento

- [ ] introdurre una analisi strutturata della sessione corrente, non limitata a un semplice recap testuale, con conteggi, tipo di contenuti, azioni consigliate ed eventuali warning
- [ ] evitare di ricalcolare più volte nella stessa catena le azioni supportate o esposte, riusando un risultato già inferito quando possibile
- [ ] profilare e ottimizzare meglio il flusso immagini verso PDF per ridurre uso di memoria sui batch più pesanti
- [ ] sostituire il dispatch lineare delle azioni nel processor con una mappa più chiara tra azione e handler
- [ ] distinguere meglio nel codice e nei messaggi le nozioni di azioni supportate, azioni esposte e azioni consigliate
- [ ] consolidare naming output e metadati job per avere convenzioni più coerenti tra file restituiti, storico e riepiloghi utente
- [ ] valutare se una parte minima dello stato upload usato per i limiti operativi debba sopravvivere ai riavvii invece di restare solo in memoria

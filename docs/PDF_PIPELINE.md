# Pipeline PDF

Questa guida descrive i flussi PDF di `DocMolder` e i compromessi principali della pipeline.

## Indice

- [Obiettivo generale](#obiettivo-generale)
- [Flussi principali](#flussi-principali)
- [Auto-orientamento PDF](#auto-orientamento-pdf)
- [Quando entra in gioco Ghostscript](#quando-entra-in-gioco-ghostscript)
- [Quando entra in gioco il raster fallback](#quando-entra-in-gioco-il-raster-fallback)

## Obiettivo generale

La pipeline cerca di:

- produrre un risultato sempre utilizzabile
- preservare il PDF nativo quando possibile
- usare fallback piu invasivi solo quando necessario

## Flussi principali

### PDF in scala di grigi

Ordine logico:

1. eventuale preparazione del PDF con auto-orientamento
2. tentativo tramite `Ghostscript`, se disponibile
3. tentativo di conversione nativa delle immagini interne del PDF
4. fallback raster come ultima opzione

Tradeoff:

- i primi percorsi preservano meglio struttura e testo
- il fallback raster privilegia la compatibilita, ma puo perdere testo ricercabile, layer o metadati

### Compressione PDF

Preset disponibili:

- `light`
- `medium`
- `strong`

Ordine logico:

- `light`: ottimizzazione lossless della struttura
- `medium`: compressione conservativa, poi eventuale fallback `Ghostscript`, poi lossless se serve
- `strong`: compressione conservativa piu aggressiva, poi `Ghostscript`, poi raster se necessario

Tradeoff:

- piu si forza la compressione, piu aumenta il rischio di cambiare la natura del PDF
- il percorso raster e il piu invasivo

### Unione PDF

Per l'unione:

- il bot richiede almeno due PDF
- puo preparare i documenti con auto-orientamento prima della fusione
- produce un unico output PDF finale

### Operazioni native su singolo PDF

Per un singolo PDF il bot supporta anche:

- estrazione pagine
- riordino completo delle pagine
- eliminazione pagine
- rotazione manuale di tutte le pagine
- watermark testuale

Questi flussi:

- restano nativi, senza passare da rasterizzazione
- chiedono in chat solo il minimo input necessario, per esempio `1,3,5-7` oppure un testo semplice
- validano in modo esplicito selezioni pagina, ordine completo o gradi ammessi

### PDF da immagini

Per le immagini:

- il bot puo creare un PDF mantenendo il formato originale delle immagini
- oppure puo impaginarle in A4
- se usa A4, chiede anche il tipo di bordo
- in alcuni flussi puo applicare ritaglio bordi e conversione in scala di grigi
- quando il risultato richiesto e un PDF in scala di grigi da immagini, il bot lo genera direttamente in grigio invece di creare prima un PDF a colori e riconvertirlo dopo

## Auto-orientamento PDF

Quando il flusso lo supporta:

- il sistema osserva l'orientamento dominante delle pagine
- ruota solo le pagine che risultano fuori direzione rispetto alla maggioranza
- se interviene, il messaggio finale lo esplicita
- il bot puo offrire un rerun senza auto-rotazione

Scopo:

- migliorare i casi pratici di PDF quasi corretti ma con poche pagine girate male

## Quando entra in gioco Ghostscript

`Ghostscript` viene usato solo se disponibile nel sistema.

Serve soprattutto per:

- scala di grigi piu fedele su alcuni PDF
- compressione PDF nativa in alcuni preset

Per evitare job troppo lunghi:

- i passaggi `Ghostscript` hanno un timeout esplicito configurabile con `DOCMOLDER_GHOSTSCRIPT_TIMEOUT_SECONDS`
- se il timeout scatta, la pipeline lo tratta come un fallimento gestito e passa al fallback successivo

Se fallisce o non esiste:

- la pipeline non si ferma subito
- prova altre strategie
- i messaggi utente cercano di anticipare che, nei casi complessi, il risultato potrebbe richiedere piu tempo o passare a un fallback compatibile

## Quando entra in gioco il raster fallback

Il fallback raster viene usato quando i tentativi piu conservativi non bastano.

Implicazioni:

- il risultato visivo viene mantenuto
- il PDF puo perdere caratteristiche native utili
- per questo e importante tracciare bene quanto spesso accade
- quando questo succede, i messaggi finali cercano di esplicitare meglio il compromesso fatto sul PDF nativo

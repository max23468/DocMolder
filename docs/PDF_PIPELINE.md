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
- usare fallback più invasivi solo quando necessario

## Flussi principali

### PDF in scala di grigi

Ordine logico:

1. eventuale preparazione del PDF con auto-orientamento
2. tentativo tramite `Ghostscript`, se disponibile
3. tentativo di conversione nativa delle immagini interne del PDF
4. fallback raster come ultima opzione

Tradeoff:

- i primi percorsi preservano meglio struttura e testo
- il fallback raster privilegia la compatibilità, ma può perdere testo ricercabile, layer o metadati

### Compressione PDF

Preset disponibili:

- `light`
- `medium`
- `strong`

Ordine logico:

- `light`: ottimizzazione lossless della struttura
- `medium`: compressione conservativa, poi eventuale fallback `Ghostscript`, poi lossless se serve
- `strong`: compressione conservativa più aggressiva, poi `Ghostscript`, poi raster se necessario

Tradeoff:

- più si forza la compressione, più aumenta il rischio di cambiare la natura del PDF
- il percorso raster è il più invasivo

### Unione PDF

Per l'unione:

- il bot richiede almeno due PDF
- può preparare i documenti con auto-orientamento prima della fusione
- produce un unico output PDF finale

### Operazioni native su singolo PDF

Per un singolo PDF il bot supporta anche:

- divisione del PDF in un file per pagina, con scelta tra archivio ZIP e PDF separati
- estrazione pagine
- riordino completo delle pagine
- eliminazione pagine
- rotazione manuale di tutte le pagine
- watermark testuale

Questi flussi:

- restano nativi, senza passare da rasterizzazione
- quando producono più output, possono raccoglierli in un unico ZIP oppure inviarli come file separati se l'utente lo preferisce
- chiedono in chat solo il minimo input necessario, per esempio `1,3,5-7` oppure un testo semplice
- validano in modo esplicito selezioni pagina, ordine completo o gradi ammessi

### PDF da immagini

Per le immagini:

- il bot può creare un PDF mantenendo il formato originale delle immagini
- oppure può impaginarle in A4
- se usa A4, chiede anche il tipo di bordo
- in alcuni flussi può applicare ritaglio bordi e conversione in scala di grigi
- per foto di fogli può usare "Raddrizza foto documento", con rilevamento contorno, correzione prospettica, profili `Più leggibile`, `Mantieni colore` e `Bianco/nero pulito`, più fallback conservativo se il foglio non è chiaro
- il feedback della compressione segnala quando la riduzione è minima o quando il PDF sembra già ottimizzato
- quando il risultato richiesto è un PDF in scala di grigi da immagini, il bot lo genera direttamente in grigio invece di creare prima un PDF a colori e riconvertirlo dopo
- le immagini con lato molto grande vengono ridotte prima della conversione, entro `DOCMOLDER_IMAGE_PDF_MAX_SOURCE_SIDE_PX`, per proteggere RAM e CPU della VPS
- nei batch, ogni immagine preparata viene scritta come PDF temporaneo di una pagina e poi unita nel PDF finale, così il processo evita di tenere tutte le pagine rasterizzate in memoria contemporaneamente

## Auto-orientamento PDF

Quando il flusso lo supporta:

- il sistema osserva l'orientamento dominante delle pagine
- ruota solo le pagine che risultano fuori direzione rispetto alla maggioranza
- se interviene, il messaggio finale lo esplicita
- il bot può offrire un rerun senza auto-rotazione

Scopo:

- migliorare i casi pratici di PDF quasi corretti ma con poche pagine girate male

## Quando entra in gioco Ghostscript

`Ghostscript` viene usato solo se disponibile nel sistema.

Serve soprattutto per:

- scala di grigi più fedele su alcuni PDF
- compressione PDF nativa in alcuni preset

Per evitare job troppo lunghi:

- i passaggi `Ghostscript` hanno un timeout esplicito configurabile con `DOCMOLDER_GHOSTSCRIPT_TIMEOUT_SECONDS`
- se il timeout scatta, la pipeline lo tratta come un fallimento gestito e passa al fallback successivo

Se fallisce o non esiste:

- la pipeline non si ferma subito
- prova altre strategie
- i messaggi utente cercano di anticipare che, nei casi complessi, il risultato potrebbe richiedere più tempo o passare a un fallback compatibile

## Quando entra in gioco il raster fallback

Il fallback raster viene usato quando i tentativi più conservativi non bastano.

Implicazioni:

- il risultato visivo viene mantenuto
- il PDF può perdere caratteristiche native utili
- per questo è importante tracciare bene quanto spesso accade
- quando questo succede, i messaggi finali cercano di esplicitare meglio il compromesso fatto sul PDF nativo

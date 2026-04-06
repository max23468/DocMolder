# Roadmap Prodotto

Questa roadmap raccoglie le priorità attuali di `DocMolder`.

## Indice

- [Fase 1: Qualità e Affidabilità](#fase-1-qualita-e-affidabilita)
- [Fase 2: Operatività e Controllo](#fase-2-operativita-e-controllo)
- [Fase 3: Estensione Funzionale](#fase-3-estensione-funzionale)
- [Fase 4: Miglioramenti Tecnici](#fase-4-miglioramenti-tecnici)

## Fase 1: Qualità e Affidabilità

- [ ] ampliare i test automatici su PDF reali, corrotti, pesanti o con struttura insolita
- [ ] rendere la conversione in scala di grigi più coerente anche senza `Ghostscript`
- [ ] migliorare messaggi utente e fallback quando una trasformazione non preserva bene il PDF nativo o richiede più tempo del previsto
- [ ] tracciare meglio tempi di elaborazione, peso input/output e ricorso ai fallback più invasivi

## Fase 2: Operatività e Controllo

- [ ] metriche più leggibili su utilizzo, errori e job falliti
- [ ] strumenti admin per capire rapidamente quali trasformazioni causano più problemi
- [ ] report admin periodici con riepilogo giornaliero o settimanale
- [ ] introdurre o rifinire limiti su dimensione file, numero allegati e carico concorrente per utente
- [ ] rendere più robusta la ripartenza dei job dopo crash o riavvio del servizio
- [ ] politiche di retention e manutenzione più visibili anche lato documentazione

## Fase 3: Estensione Funzionale

- [ ] storico lavori per l'utente, con elenco delle conversioni già eseguite e possibilità di recuperare risultati o dettagli essenziali del job
- [ ] estrazione pagine
- [ ] riordino pagine
- [ ] eliminazione pagine
- [ ] rotazione pagine manuale
- [ ] watermark

## Fase 4: Miglioramenti Tecnici

- [ ] rendere il cleanup delle cartelle di lavoro più robusto anche nei casi di errore o interruzione del job
- [ ] aggiungere timeout espliciti alle chiamate verso strumenti esterni come `Ghostscript`
- [ ] ampliare i test automatici sui fallback della pipeline e sulla ripartenza dei job dopo riavvio
- [ ] ridurre gli `except Exception` troppo ampi nella pipeline PDF, distinguendo meglio i fallimenti attesi dai problemi imprevisti
- [ ] validare in modo più rigoroso gli input tecnici sensibili, come i gradi ammessi per la rotazione manuale
- [ ] tracciare in modo esplicito quale strategia ha prodotto il risultato finale, ad esempio `lossless`, `conservative`, `ghostscript` o `raster`
- [ ] introdurre una struttura tipizzata per il payload dei job, invece di affidarsi solo a JSON con chiavi opzionali
- [ ] sostituire strutture generiche come `dict[str, int]` con tipi più espliciti per statistiche e report interni
- [ ] separare meglio la logica del bot Telegram dalla gestione della coda, dei job e dell'orchestrazione interna
- [ ] allineare meglio le azioni supportate dal modello interno con quelle realmente esposte all'utente
- [ ] centralizzare meglio i messaggi operativi legati ai job, agli errori e agli stati intermedi
- [ ] migliorare la generazione dei nomi file in output per renderli più informativi e più utili lato utente e supporto

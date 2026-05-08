# Pipeline Excel

Questa guida descrive il flusso Excel di `DocMolder`.

## Perimetro

Il bot supporta l'azione `Sblocca modifica Excel` per file:

- `.xlsx`
- `.xlsm`
- `.xls`
- `.xlsb`

La funzione riguarda file che si aprono già senza password, ma hanno fogli o
struttura workbook protetti dalla modifica.

Non fa:

- recupero password
- brute force
- apertura di file cifrati
- aggiramento di password richiesta all'apertura

## Strategia tecnica

Per `.xlsx` e `.xlsm` il bot lavora direttamente sul pacchetto Office Open XML:

- conserva il contenitore e il formato originale
- rimuove protezioni di modifica da `workbook.xml` e dai fogli XML
- preserva gli altri file interni, inclusi asset e macro presenti nel pacchetto

Per `.xls` il bot usa LibreOffice in modalità headless quando disponibile sul
server:

- apre il file in un profilo temporaneo isolato
- prova a rimuovere la protezione dai fogli tramite UNO
- salva una copia nello stesso formato originale
- applica un timeout esplicito con `DOCMOLDER_LIBREOFFICE_TIMEOUT_SECONDS`

Se LibreOffice non è installato, o se il foglio richiede davvero una password
per essere sbloccato, il job fallisce con un messaggio utente controllato.

Per `.xlsb` LibreOffice non è sufficiente, perché non espone un export `.xlsb`
affidabile. Il formato resta supportabile solo con un engine dedicato capace di
salvare `.xlsb` originale. La strada validata nello spike è Aspose.Cells, ma in
produzione va usato solo con licenza configurata: la modalità evaluation aggiunge
fogli watermark al workbook.

Warning operativo: non configurare Aspose.Cells in produzione senza licenza
valida. L'evaluation mode altera il file aggiungendo fogli di avviso e quindi
non è accettabile per documenti utente.

Quando `aspose-cells-python` è installato e `DOCMOLDER_ASPOSE_CELLS_LICENSE_PATH`
punta a una licenza valida, il bot usa Aspose.Cells per `.xlsb`, applica la
licenza prima di aprire il file, rimuove protezioni semplici di workbook/fogli e
salva una copia `.xlsb`. Senza licenza configurata, il job `.xlsb` fallisce con
un messaggio controllato invece di produrre un file alterato.

## Dipendenze operative

Il percorso `.xlsx/.xlsm` non richiede dipendenze Python aggiuntive.

Il percorso `.xls` richiede sul server:

- LibreOffice Calc
- bridge Python UNO (`python3-uno` sui sistemi Debian/Ubuntu)

Gli script di setup VPS installano questi pacchetti insieme alle dipendenze
operative già presenti.

Il percorso `.xlsb` richiede inoltre:

- extra Python `docmolder[xlsb]`, che installa `aspose-cells-python`
- licenza Aspose.Cells salvata fuori repo
- `DOCMOLDER_ASPOSE_CELLS_LICENSE_PATH` valorizzato con il percorso della licenza

Non salvare la licenza in repository e non puntare la variabile a file di prova
o evaluation: se la licenza non è valida, il job deve fallire invece di
restituire un workbook alterato.

Sulla VPS attuale il runtime Aspose via .NET funziona con
`DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`; il codice imposta questo flag prima di
importare Aspose per evitare dipendenze ICU aggiuntive.

## Dati e sicurezza

I file Excel seguono le stesse regole degli altri documenti utente:

- download solo nella directory temporanea del job
- nessun contenuto documento nei log
- output restituito in chat
- cleanup della directory job a fine elaborazione

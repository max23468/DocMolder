# Pipeline Excel

Questa guida descrive il flusso Excel di `DocMolder`.

## Perimetro

Il bot supporta l'azione `Sblocca modifica Excel` per file:

- `.xlsx`
- `.xlsm`
- `.xls`

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

Il formato `.xlsb` non è supportato. DocMolder non integra engine dedicati e non
prova conversioni tramite LibreOffice, perché il formato non può essere
salvato in modo affidabile nel perimetro operativo attuale.

## Dipendenze operative

Il percorso `.xlsx/.xlsm` non richiede dipendenze Python aggiuntive.

Il percorso `.xls` richiede sul server:

- LibreOffice Calc
- bridge Python UNO (`python3-uno` sui sistemi Debian/Ubuntu)

Gli script di setup VPS installano questi pacchetti insieme alle dipendenze
operative già presenti.

## Dati e sicurezza

I file Excel seguono le stesse regole degli altri documenti utente:

- download solo nella directory temporanea del job
- nessun contenuto documento nei log
- output restituito in chat
- cleanup della directory job a fine elaborazione

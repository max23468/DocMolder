# Operations

Questa guida raccoglie il runbook minimo per gestire `DocMolder` in esercizio.

## Indice

- [Verifiche rapide](#verifiche-rapide)
- [Riavvio del servizio](#riavvio-del-servizio)
- [Dove guardare in caso di problemi](#dove-guardare-in-caso-di-problemi)
- [Percorsi tipici](#percorsi-tipici)
- [Ghostscript](#ghostscript)
- [Admin e osservabilita](#admin-e-osservabilita)

## Verifiche rapide

Controlli iniziali:

- il servizio deve risultare attivo
- il log non deve mostrare crash ripetuti
- il runtime dir deve essere accessibile
- il database SQLite deve essere raggiungibile dal processo

Su VPS:

```bash
sudo systemctl status docmolder
sudo journalctl -u docmolder -n 50 --no-pager
```

## Riavvio del servizio

```bash
sudo systemctl restart docmolder
```

Dopo il riavvio:

- controlla i log
- verifica che il bot risponda a `/start`
- verifica che i job incompleti vengano riaccodati correttamente

## Dove guardare in caso di problemi

Se il bot non parte:

- variabili ambiente mancanti o errate
- virtualenv non coerente
- permessi sui percorsi runtime
- dipendenze di sistema mancanti come `Ghostscript`

Se i job falliscono:

- controlla i log del servizio
- verifica se il problema coinvolge PDF corrotti o protetti
- verifica se `Ghostscript` e disponibile ma sta fallendo
- controlla spazio disco e permessi sotto il runtime dir

Se il bot accumula file temporanei:

- verifica il cleanup schedulato
- controlla l'eta delle cartelle sotto `jobs`
- verifica che i job falliti non restino bloccati prima della pulizia

## Percorsi tipici

Locale:

- runtime dir sotto `./data/runtime`
- job temporanei sotto `./data/runtime/jobs`
- database tipico `./data/runtime/docmolder.db`

VPS consigliata:

- runtime dir `/opt/docmolder/data/runtime`
- database `/opt/docmolder/data/runtime/docmolder.db`

## Ghostscript

Serve per migliorare alcune elaborazioni PDF:

- conversione in scala di grigi piu fedele
- compressione PDF nativa in alcuni casi

Se manca o fallisce:

- il bot prova fallback alternativi
- la qualita del risultato puo cambiare
- e utile verificare quale strategia effettiva e stata usata

## Admin e osservabilita

Se `DOCMOLDER_ADMIN_USER_IDS` e configurata:

- gli admin ricevono notifica al primo accesso di un nuovo utente
- `/admin` mostra metriche sintetiche su utenti, job e attivita recenti
- il bot puo inviare anche riepiloghi admin giornalieri e settimanali

Quando qualcosa non torna, guarda prima:

- numero job in coda
- job falliti recenti
- utenti piu attivi
- tipo di trasformazione che fallisce piu spesso
- durata media dei job, peso medio di input/output e quanti risultati stanno passando da fallback raster
- tasso di successo e tasso di fallimento mostrati nel riepilogo admin

## Retention e manutenzione

Regole pratiche attuali:

- i file di lavoro dei job restano temporanei
- le cartelle job residue vengono pulite dal cleanup schedulato
- i job incompleti vengono rimessi in coda dopo riavvio, ma con stato operativo ripulito
- la documentazione operativa e di deploy va tenuta allineata quando cambiano retention, cleanup o cadenza dei report admin

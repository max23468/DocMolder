# Brand DocMolder

## Sintesi

`DocMolder` e una utility documentale Telegram-first per privati, freelance e professionisti.

La direzione scelta per il brand e:

- professionale, per comunicare affidabilita sul lavoro con documenti
- smart, per far percepire velocita e fluidita
- amichevole, per mantenere il bot semplice e vicino all'utente

Tagline guida:

- `PDF e scansioni pronti, in pochi tocchi.`

## Posizionamento

DocMolder non si presenta come suite complessa o assistente generico.
Si presenta come uno strumento nitido e guidato:

- prende file direttamente in chat
- riduce attrito e passaggi inutili
- restituisce un output pulito senza chiedere all'utente di imparare un software

Messaggio chiave:

- `Manda il file, scegli l'azione, ricevi il risultato.`

## Identita visiva

### Idea del logo

Il marchio combina:

- un foglio/documento con angoli morbidi, per dare affidabilita e accessibilita
- una piega in alto, per richiamare il documento in modo immediato
- un accento circolare con freccia, per suggerire trasformazione, passaggio rapido e output pronto

### Palette

- `Ink` `#11212D`: fondo principale, serio e tecnico
- `Slate` `#274053`: testo e struttura secondaria
- `Teal` `#19A7A8`: azione primaria, precisione, stato positivo
- `Mist` `#C9F1F0`: superfici leggere, supporto e respiro
- `Paper` `#F6F2E8`: superfici documento
- `Coral` `#FF7A59`: accento, callout, freccia di trasformazione

### Asset in repository

- logo orizzontale: [assets/brand/docmolder-logo.svg](../assets/brand/docmolder-logo.svg)
- marchio quadrato: [assets/brand/docmolder-mark.svg](../assets/brand/docmolder-mark.svg)
- icone: [assets/brand/icons/pdf.svg](../assets/brand/icons/pdf.svg), [assets/brand/icons/merge.svg](../assets/brand/icons/merge.svg), [assets/brand/icons/compress.svg](../assets/brand/icons/compress.svg), [assets/brand/icons/watermark.svg](../assets/brand/icons/watermark.svg), [assets/brand/icons/scan.svg](../assets/brand/icons/scan.svg)
- avatar Telegram generato: [assets/brand/docmolder-telegram-profile.png](../assets/brand/docmolder-telegram-profile.png)
- avatar JPG per Bot API: [assets/brand/docmolder-telegram-profile.jpg](../assets/brand/docmolder-telegram-profile.jpg)
- app icon: [assets/brand/docmolder-app-icon.png](../assets/brand/docmolder-app-icon.png)
- share card: [assets/brand/docmolder-share-card.png](../assets/brand/docmolder-share-card.png)

## Linee guida UI e copy

### Principi

- una decisione per volta
- messaggi brevi, espliciti e rassicuranti
- tecnicismo solo quando serve davvero
- verbi chiari: `crea`, `comprimi`, `unisci`, `estrai`, `ruota`

### Tono di voce

- diretto ma non freddo
- competente ma non rigido
- utile prima di tutto

### Pattern di microcopy

- bene: `Ti propongo solo le azioni compatibili con i file ricevuti.`
- bene: `Ti invio il PDF appena e pronto.`
- bene: `Se preferisci, uso un fallback compatibile.`

Da evitare:

- frasi troppo verbose
- promesse da assistente “intelligente” generico
- linguaggio troppo tecnico nella prima risposta

## Applicazione su Telegram

Il brand viene applicato in tre livelli:

- onboarding e help del bot
- tastiera rapida e etichette azioni
- metadata profilo Telegram: nome, descrizione, short description, comandi, menu

### Sync operativo

Per rigenerare asset e sincronizzare Telegram:

```bash
make brand-assets
make telegram-brand-sync
```

Oppure:

```bash
.venv/bin/python scripts/sync_telegram_branding.py
```

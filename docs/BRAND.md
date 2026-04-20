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

La direzione definitiva usa un documento astratto, chiaro e leggibile anche in piccolo.

Il marchio combina:

- un foglio con angoli morbidi e piega in alto, per comunicare subito il dominio documentale
- una barra teal verticale, come tratto distintivo e segnale di precisione
- un badge corallo con freccia, per suggerire trasformazione rapida e output pronto

### Palette

- `Ink` `#132836`: fondo principale, serio e tecnico
- `Slate` `#35536B`: testo e struttura secondaria
- `Teal` `#28ADB0`: azione primaria, precisione, stato positivo
- `Mist` `#CBEAEC`: superfici leggere, supporto e respiro
- `Paper` `#F4EEDD`: superfici documento
- `Coral` `#FF7A59`: accento, callout, freccia di trasformazione

### Asset in repository

- sorgente master del marchio: [assets/brand/docmolder-mark-master.png](../assets/brand/docmolder-mark-master.png)
- logo orizzontale definitivo: [assets/brand/docmolder-logo-horizontal.png](../assets/brand/docmolder-logo-horizontal.png)
- variante quadrata: [assets/brand/docmolder-logo-square.png](../assets/brand/docmolder-logo-square.png)
- variante iOS rounded: [assets/brand/docmolder-logo-ios-rounded.png](../assets/brand/docmolder-logo-ios-rounded.png)
- variante Telegram circle: [assets/brand/docmolder-logo-telegram-circle.png](../assets/brand/docmolder-logo-telegram-circle.png)
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

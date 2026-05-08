from __future__ import annotations

from pathlib import Path

from telegram import BotCommand

BRAND_NAME = "DocMolder"
BRAND_TAGLINE = "PDF e scansioni pronti, in pochi tocchi."
BRAND_VOICE = "utility professionale, smart e amichevole"

BRAND_COLORS: dict[str, str] = {
    "ink": "#132836",
    "slate": "#35536B",
    "teal": "#28ADB0",
    "mist": "#CBEAEC",
    "paper": "#F4EEDD",
    "coral": "#FF7A59",
}

TELEGRAM_NAME = BRAND_NAME
TELEGRAM_DESCRIPTION = (
    "DocMolder è la utility Telegram per sistemare PDF, scansioni e immagini senza passare "
    "da editor complicati. Riceve file in chat, propone solo le azioni compatibili e restituisce "
    "un risultato pulito, rapido e guidato."
)
TELEGRAM_SHORT_DESCRIPTION = "Utility Telegram per PDF, scansioni e immagini, rapida e guidata."

TELEGRAM_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Apri DocMolder e vedi le azioni principali"),
    ("help", "Guida rapida e flussi consigliati"),
    ("history", "Rivedi gli ultimi lavori"),
    ("status", "Controlla la sessione corrente"),
    ("reset", "Azzera sessione e scorciatoie"),
)

MAIN_MENU_ROWS: tuple[tuple[str, str], ...] = (
    ("Guida rapida", "Crea PDF"),
    ("Comprimi PDF", "Unisci PDF"),
    ("Foto in A4", "Scansiona e comprimi"),
    ("Storico lavori", "Sessione attiva"),
)

MAIN_MENU_PLACEHOLDER = "Invia PDF, immagini o Excel, oppure scegli un'azione rapida"

LEGACY_MENU_LABELS: dict[str, str] = {
    "Cosa posso fare": "Guida rapida",
    "Crea PDF da immagini": "Crea PDF",
    "Mostra sessione": "Sessione attiva",
    "Azzera sessione": "Azzera sessione",
}


def build_telegram_commands() -> list[BotCommand]:
    return [BotCommand(command, description) for command, description in TELEGRAM_COMMANDS]


def get_brand_asset_path(project_root: Path, filename: str) -> Path:
    return project_root / "assets" / "brand" / filename

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Crea PDF da immagini", callback_data="action:images_to_pdf")],
            [InlineKeyboardButton("Scala di grigi", callback_data="action:pdf_grayscale")],
            [InlineKeyboardButton("Comprimi PDF", callback_data="action:pdf_compress")],
            [InlineKeyboardButton("Unisci PDF", callback_data="action:pdf_merge")],
            [InlineKeyboardButton("Ruota pagine", callback_data="action:pdf_rotate")],
            [InlineKeyboardButton("Correggi orientamento", callback_data="action:auto_orient")],
        ]
    )


def build_compression_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Leggera", callback_data="compress:light")],
            [InlineKeyboardButton("Media", callback_data="compress:medium")],
            [InlineKeyboardButton("Forte", callback_data="compress:strong")],
        ]
    )


def build_rotation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("90°", callback_data="rotate:90")],
            [InlineKeyboardButton("180°", callback_data="rotate:180")],
            [InlineKeyboardButton("270°", callback_data="rotate:270")],
        ]
    )

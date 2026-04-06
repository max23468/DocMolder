from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def build_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Crea PDF da immagini", callback_data="action:images_to_pdf")],
            [InlineKeyboardButton("Ritaglia bordi e crea PDF", callback_data="action:images_to_pdf_crop")],
            [InlineKeyboardButton("Scala di grigi", callback_data="action:pdf_grayscale")],
            [InlineKeyboardButton("Comprimi PDF", callback_data="action:pdf_compress")],
            [InlineKeyboardButton("Unisci PDF", callback_data="action:pdf_merge")],
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


def build_images_pdf_layout_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Si, impagina in A4", callback_data=f"images_pdf_layout:a4:{action}")],
            [InlineKeyboardButton("No, mantieni formato originale", callback_data=f"images_pdf_layout:original:{action}")],
        ]
    )


def build_images_pdf_margin_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Bordi larghi", callback_data=f"images_pdf_margin:wide:{action}")],
            [InlineKeyboardButton("Bordi stretti", callback_data=f"images_pdf_margin:narrow:{action}")],
            [InlineKeyboardButton("Nessun bordo", callback_data=f"images_pdf_margin:none:{action}")],
        ]
    )


def build_result_pdf_keyboard(
    *,
    offer_grayscale: bool = True,
    undo_rotation_job_id: int | None = None,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if offer_grayscale:
        rows.append([InlineKeyboardButton("Converti in scala di grigi", callback_data="result:pdf_grayscale")])
    if undo_rotation_job_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    "Rifai senza rotazione automatica",
                    callback_data=f"result:undo_rotate:{undo_rotation_job_id}",
                )
            ]
        )
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Cosa posso fare"), KeyboardButton("Crea PDF da immagini")],
            [KeyboardButton("Comprimi PDF"), KeyboardButton("Unisci PDF")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Invia immagini o PDF, oppure usa il menu",
    )

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from docmolder.branding import MAIN_MENU_PLACEHOLDER, MAIN_MENU_ROWS
from docmolder.models import SupportedAction
from docmolder.action_catalog import get_action_label


def _build_action_button_label(action: SupportedAction) -> str:
    return "Aggiungi watermark" if action == SupportedAction.PDF_WATERMARK else get_action_label(action)


def build_actions_keyboard(actions: list[SupportedAction]) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for action in actions:
        rows.append([InlineKeyboardButton(_build_action_button_label(action), callback_data=f"action:{action.value}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def build_compression_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Leggera", callback_data="compress:light")],
            [InlineKeyboardButton("Media", callback_data="compress:medium")],
            [InlineKeyboardButton("Forte", callback_data="compress:strong")],
        ]
    )


def build_split_output_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ZIP unico", callback_data="split_output:zip")],
            [InlineKeyboardButton("PDF separati", callback_data="split_output:files")],
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
    quick_actions: list[SupportedAction] | None = None,
    undo_rotation_job_id: int | None = None,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for action in quick_actions or []:
        rows.append([InlineKeyboardButton(_build_action_button_label(action), callback_data=f"result:{action.value}")])
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


def build_history_keyboard(job_ids: list[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for job_id in job_ids:
        rows.append(
            [
                InlineKeyboardButton(f"Dettagli #{job_id}", callback_data=f"history:details:{job_id}"),
                InlineKeyboardButton(f"Rifai #{job_id}", callback_data=f"history:rerun:{job_id}"),
            ]
        )
    return InlineKeyboardMarkup(rows)


def build_rotate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("90°", callback_data="rotate:90")],
            [InlineKeyboardButton("180°", callback_data="rotate:180")],
            [InlineKeyboardButton("270°", callback_data="rotate:270")],
        ]
    )


def build_admin_dashboard_keyboard(*, service_paused: bool) -> InlineKeyboardMarkup:
    service_button = "Riprendi servizio" if service_paused else "Pausa servizio"
    service_action = "resume" if service_paused else "pause"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Panoramica", callback_data="admin:overview"),
                InlineKeyboardButton("Coda", callback_data="admin:queue"),
            ],
            [
                InlineKeyboardButton("Health", callback_data="admin:health"),
                InlineKeyboardButton(service_button, callback_data=f"admin:{service_action}"),
            ],
            [
                InlineKeyboardButton("Metriche", callback_data="admin:metrics"),
                InlineKeyboardButton("Manutenzione", callback_data="admin:maintenance"),
            ],
            [
                InlineKeyboardButton("Ultimo fallito", callback_data="admin:failed"),
                InlineKeyboardButton("In esecuzione", callback_data="admin:running"),
            ],
            [
                InlineKeyboardButton("Ultimo queued", callback_data="admin:queued"),
                InlineKeyboardButton("Ultimo riuscito", callback_data="admin:succeeded"),
            ],
            [
                InlineKeyboardButton("Ultimo job", callback_data="admin:latest"),
                InlineKeyboardButton("Aggiorna", callback_data="admin:refresh"),
            ],
        ]
    )


def build_access_review_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approva", callback_data=f"access:approve:{user_id}"),
                InlineKeyboardButton("Rifiuta", callback_data=f"access:reject:{user_id}"),
            ]
        ]
    )


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(left), KeyboardButton(right)] for left, right in MAIN_MENU_ROWS],
        resize_keyboard=True,
        input_field_placeholder=MAIN_MENU_PLACEHOLDER,
    )

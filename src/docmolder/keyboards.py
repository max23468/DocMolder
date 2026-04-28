from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from docmolder.branding import MAIN_MENU_PLACEHOLDER, MAIN_MENU_ROWS
from docmolder.models import JobStatus, SupportedAction, UserSession
from docmolder.processing import A4_MARGIN_NARROW_PX, A4_MARGIN_NONE_PX, A4_MARGIN_WIDE_PX
from docmolder.action_catalog import SessionAnalysis, get_action_label, infer_session_analysis

_DEFAULT_ACTION_BUTTON_LIMIT = 3
_COMPRESSION_LABELS = {
    "light": "leggera",
    "medium": "media",
    "strong": "forte",
}
_SPLIT_OUTPUT_LABELS = {
    "zip": "ZIP unico",
    "files": "PDF separati",
}


def _build_action_button_label(action: SupportedAction) -> str:
    return "Aggiungi watermark" if action == SupportedAction.PDF_WATERMARK else get_action_label(action)


def build_actions_keyboard(actions: list[SupportedAction]) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    for action in actions:
        rows.append([InlineKeyboardButton(_build_action_button_label(action), callback_data=f"action:{action.value}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


def build_session_actions_keyboard(
    session: UserSession,
    *,
    expanded: bool = False,
    analysis: SessionAnalysis | None = None,
) -> InlineKeyboardMarkup | None:
    analysis = analysis or infer_session_analysis(session)
    all_actions = list(analysis.exposed_actions)
    if not all_actions:
        return None

    recommended_actions = list(analysis.recommended_actions)
    primary_actions = recommended_actions[:_DEFAULT_ACTION_BUTTON_LIMIT] or all_actions[:_DEFAULT_ACTION_BUTTON_LIMIT]
    visible_actions = all_actions if expanded else primary_actions
    rows = [[InlineKeyboardButton(_build_action_button_label(action), callback_data=f"action:{action.value}")] for action in visible_actions]

    hidden_actions = [action for action in all_actions if action not in primary_actions]
    if hidden_actions:
        if expanded:
            rows.append([InlineKeyboardButton("Meno azioni", callback_data="action:less")])
        else:
            rows.append([InlineKeyboardButton(f"Altre azioni ({len(hidden_actions)})", callback_data="action:more")])
    return InlineKeyboardMarkup(rows)


def build_compression_keyboard(preset: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Leggera", callback_data="compress:light")],
        [InlineKeyboardButton("Media", callback_data="compress:medium")],
        [InlineKeyboardButton("Forte", callback_data="compress:strong")],
    ]
    if preset in _COMPRESSION_LABELS:
        rows.insert(0, [InlineKeyboardButton(f"Usa preset: {_COMPRESSION_LABELS[preset]}", callback_data=f"compress:{preset}")])
    return InlineKeyboardMarkup(rows)


def build_split_output_keyboard(preset: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("ZIP unico", callback_data="split_output:zip")],
        [InlineKeyboardButton("PDF separati", callback_data="split_output:files")],
    ]
    if preset in _SPLIT_OUTPUT_LABELS:
        rows.insert(0, [InlineKeyboardButton(f"Usa preset: {_SPLIT_OUTPUT_LABELS[preset]}", callback_data=f"split_output:{preset}")])
    return InlineKeyboardMarkup(rows)


def build_images_pdf_layout_keyboard(
    action: str,
    *,
    preset_layout: str | None = None,
    preset_margin_px: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Si, impagina in A4", callback_data=f"images_pdf_layout:a4:{action}")],
        [InlineKeyboardButton("No, mantieni formato originale", callback_data=f"images_pdf_layout:original:{action}")],
    ]
    if preset_layout == "original":
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    "Usa preset: formato originale",
                    callback_data=f"images_pdf_layout:original:{action}",
                )
            ],
        )
    elif preset_layout == "a4":
        margin_key = _margin_key_from_px(preset_margin_px)
        if margin_key is not None:
            rows.insert(
                0,
                [
                    InlineKeyboardButton(
                        f"Usa preset: A4 {_margin_label_from_key(margin_key)}",
                        callback_data=f"images_pdf_preset:a4:{margin_key}:{action}",
                    )
                ],
            )
    return InlineKeyboardMarkup(rows)


def build_images_pdf_margin_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Bordi larghi", callback_data=f"images_pdf_margin:wide:{action}")],
            [InlineKeyboardButton("Bordi stretti", callback_data=f"images_pdf_margin:narrow:{action}")],
            [InlineKeyboardButton("Nessun bordo", callback_data=f"images_pdf_margin:none:{action}")],
        ]
    )


def _margin_key_from_px(value: str | None) -> str | None:
    if value == str(A4_MARGIN_WIDE_PX):
        return "wide"
    if value == str(A4_MARGIN_NARROW_PX):
        return "narrow"
    if value == str(A4_MARGIN_NONE_PX):
        return "none"
    return None


def _margin_label_from_key(key: str) -> str:
    if key == "wide":
        return "bordi larghi"
    if key == "none":
        return "senza bordi"
    return "bordi stretti"


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


def build_admin_dashboard_keyboard(
    *,
    service_paused: bool,
    available_job_statuses: set[JobStatus] | None = None,
) -> InlineKeyboardMarkup:
    service_button = "Riprendi servizio" if service_paused else "Pausa servizio"
    service_action = "resume" if service_paused else "pause"
    statuses = available_job_statuses
    rows = [
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
    ]

    job_buttons: list[InlineKeyboardButton] = []
    if statuses is None or statuses:
        job_buttons.append(InlineKeyboardButton("Ultimo job", callback_data="admin:latest"))
    if statuses is None or JobStatus.FAILED in statuses:
        job_buttons.append(InlineKeyboardButton("Ultimo fallito", callback_data="admin:failed"))
    if statuses is None or JobStatus.RUNNING in statuses:
        job_buttons.append(InlineKeyboardButton("In esecuzione", callback_data="admin:running"))
    if statuses is None or JobStatus.QUEUED in statuses:
        job_buttons.append(InlineKeyboardButton("Ultimo queued", callback_data="admin:queued"))
    if statuses is None or JobStatus.SUCCEEDED in statuses:
        job_buttons.append(InlineKeyboardButton("Ultimo riuscito", callback_data="admin:succeeded"))

    for index in range(0, len(job_buttons), 2):
        rows.append(job_buttons[index : index + 2])
    rows.append([InlineKeyboardButton("Aggiorna", callback_data="admin:refresh")])
    return InlineKeyboardMarkup(rows)


def build_access_review_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approva", callback_data=f"access:approve:{user_id}"),
                InlineKeyboardButton("Rifiuta", callback_data=f"access:reject:{user_id}"),
            ]
        ]
    )


def build_delete_data_request_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Cancella tutti i miei dati", callback_data="delete_data:request")],
        ]
    )


def build_delete_data_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Conferma cancellazione", callback_data="delete_data:confirm")],
            [InlineKeyboardButton("Annulla", callback_data="delete_data:cancel")],
        ]
    )


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(left), KeyboardButton(right)] for left, right in MAIN_MENU_ROWS],
        resize_keyboard=True,
        input_field_placeholder=MAIN_MENU_PLACEHOLDER,
    )

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from docmolder.branding import MAIN_MENU_PLACEHOLDER, MAIN_MENU_ROWS
from docmolder.models import JobStatus, SupportedAction, UserSession
from docmolder.processing_models import A4_MARGIN_NARROW_PX, A4_MARGIN_NONE_PX, A4_MARGIN_WIDE_PX
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
    rows: list[list[InlineKeyboardButton]] = []
    for action in visible_actions:
        if action == SupportedAction.PDF_COMPRESS:
            rows.append(
                [
                    InlineKeyboardButton("Comprimi subito", callback_data="quick:pdf_compress"),
                    InlineKeyboardButton("Livello…", callback_data="action:pdf_compress"),
                ]
            )
        elif action == SupportedAction.PDF_SPLIT:
            rows.append(
                [
                    InlineKeyboardButton("Dividi subito", callback_data="quick:pdf_split"),
                    InlineKeyboardButton("Modalità…", callback_data="action:pdf_split"),
                ]
            )
        else:
            rows.append([InlineKeyboardButton(_build_action_button_label(action), callback_data=f"action:{action.value}")])

    hidden_actions = [action for action in all_actions if action not in primary_actions]
    if hidden_actions:
        if expanded:
            rows.append([InlineKeyboardButton("Meno azioni", callback_data="action:less")])
        else:
            rows.append(
                [InlineKeyboardButton(f"Pagine e altre modifiche ({len(hidden_actions)})", callback_data="action:more")]
            )
    if analysis.inventory.pdf_count > 1:
        for index in range(len(session.files)):
            controls: list[InlineKeyboardButton] = []
            if index > 0:
                controls.append(InlineKeyboardButton(f"↑ {index + 1}", callback_data=f"session:move:{index}:up"))
            if index < len(session.files) - 1:
                controls.append(InlineKeyboardButton(f"↓ {index + 1}", callback_data=f"session:move:{index}:down"))
            controls.append(InlineKeyboardButton(f"Rimuovi {index + 1}", callback_data=f"session:remove:{index}"))
            rows.append(controls)
    rows.append([InlineKeyboardButton("Nuovo lavoro", callback_data="session:new")])
    return InlineKeyboardMarkup(rows)


def build_compression_keyboard(preset: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Leggera", callback_data="compress:light")],
        [InlineKeyboardButton("Media", callback_data="compress:medium")],
        [InlineKeyboardButton("Forte", callback_data="compress:strong")],
    ]
    if preset in _COMPRESSION_LABELS:
        rows.insert(
            0, [InlineKeyboardButton(f"Usa preset: {_COMPRESSION_LABELS[preset]}", callback_data=f"compress:{preset}")]
        )
    rows.append([InlineKeyboardButton("Annulla", callback_data="session:cancel")])
    return InlineKeyboardMarkup(rows)


def build_split_output_keyboard(preset: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Una pagina per file · ZIP", callback_data="split_output:zip")],
        [InlineKeyboardButton("Una pagina per file · separati", callback_data="split_output:files")],
        [InlineKeyboardButton("Gruppi personalizzati · ZIP", callback_data="split_output:groups")],
        [InlineKeyboardButton("Ogni N pagine · ZIP", callback_data="split_output:chunks")],
    ]
    if preset in _SPLIT_OUTPUT_LABELS:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    f"Usa preset: {_SPLIT_OUTPUT_LABELS[preset]}", callback_data=f"split_output:{preset}"
                )
            ],
        )
    rows.append([InlineKeyboardButton("Annulla", callback_data="session:cancel")])
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
    rows.append([InlineKeyboardButton("Annulla", callback_data="session:cancel")])
    return InlineKeyboardMarkup(rows)


def build_images_pdf_margin_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Bordi larghi", callback_data=f"images_pdf_margin:wide:{action}")],
            [InlineKeyboardButton("Bordi stretti", callback_data=f"images_pdf_margin:narrow:{action}")],
            [InlineKeyboardButton("Nessun bordo", callback_data=f"images_pdf_margin:none:{action}")],
            [
                InlineKeyboardButton("Indietro", callback_data="session:back"),
                InlineKeyboardButton("Annulla", callback_data="session:cancel"),
            ],
        ]
    )


def build_document_photo_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Più leggibile", callback_data="document_photo_mode:readable")],
            [InlineKeyboardButton("Mantieni colore", callback_data="document_photo_mode:color")],
            [InlineKeyboardButton("Bianco/nero pulito", callback_data="document_photo_mode:bw")],
            [InlineKeyboardButton("Annulla", callback_data="session:cancel")],
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
    expanded: bool = False,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    actions = quick_actions or []
    visible_actions = actions if expanded else actions[:4]
    for action in visible_actions:
        rows.append([InlineKeyboardButton(_build_action_button_label(action), callback_data=f"result:{action.value}")])
    if len(actions) > 4:
        rows.append(
            [
                InlineKeyboardButton(
                    "Meno azioni" if expanded else f"Altre azioni ({len(actions) - 4})",
                    callback_data="result:less" if expanded else "result:more",
                )
            ]
        )
    rows.append([InlineKeyboardButton("Unisci con un altro PDF", callback_data="result:merge")])
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
            [InlineKeyboardButton("Annulla", callback_data="session:cancel")],
        ]
    )


def build_admin_dashboard_keyboard(
    *,
    service_paused: bool,
    available_job_statuses: set[JobStatus] | None = None,
    daily_reports_enabled: bool = True,
    weekly_reports_enabled: bool = True,
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
        [
            InlineKeyboardButton(
                f"Giornaliero: {'attivo' if daily_reports_enabled else 'disattivo'}",
                callback_data="admin:daily_toggle",
            ),
            InlineKeyboardButton(
                f"Settimanale: {'attivo' if weekly_reports_enabled else 'disattivo'}",
                callback_data="admin:weekly_toggle",
            ),
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
            [InlineKeyboardButton("Ripristina preferenze", callback_data="preferences:clear")],
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

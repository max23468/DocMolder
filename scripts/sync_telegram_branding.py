#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from docmolder.brand_assets import render_brand_assets
from docmolder.branding import (
    TELEGRAM_DESCRIPTION,
    TELEGRAM_NAME,
    TELEGRAM_SHORT_DESCRIPTION,
    build_telegram_commands,
    get_brand_asset_path,
)
from docmolder.config import load_settings


def _call_bot_api(token: str, method: str, fields: dict[str, str], file_field: tuple[str, Path] | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if file_field is None:
        data = urllib.parse.urlencode(fields).encode("utf-8")
        request = urllib.request.Request(url, data=data)
    else:
        boundary = f"----DocMolderBoundary{uuid4().hex}"
        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
            body.extend(value.encode("utf-8"))
            body.extend(b"\r\n")

        upload_name, upload_path = file_field
        mime_type = mimetypes.guess_type(upload_path.name)[0] or "application/octet-stream"
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="{upload_name}"; filename="{upload_path.name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8")
        )
        body.extend(upload_path.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"{method} failed: {payload}")
    return payload


def _language_payloads(language_code: str) -> tuple[dict[str, str], ...]:
    codes = ("", language_code) if language_code else ("",)
    payloads: list[dict[str, str]] = []
    for code in dict.fromkeys(codes):
        payloads.append({"language_code": code} if code else {})
    return tuple(payloads)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincronizza nome, descrizione, comandi e avatar Telegram di DocMolder.")
    parser.add_argument("--token", help="Telegram bot token. Se omesso, uso DOCMOLDER_TELEGRAM_TOKEN/.env.")
    parser.add_argument("--language-code", default="it", help="Lingua da sincronizzare oltre al default globale.")
    parser.add_argument("--skip-photo", action="store_true", help="Aggiorna solo metadati e comandi, senza foto profilo.")
    args = parser.parse_args()

    settings = None
    try:
        settings = load_settings()
    except ValidationError:
        settings = None

    token = args.token or os.getenv("DOCMOLDER_TELEGRAM_TOKEN")
    if token is None and settings is not None:
        token = settings.telegram_token
    if token is None:
        raise SystemExit(
            "Token Telegram mancante. Imposta DOCMOLDER_TELEGRAM_TOKEN oppure usa --token per sincronizzare il brand."
        )

    render_brand_assets(PROJECT_ROOT / "assets" / "brand")

    command_payload = json.dumps(
        [{"command": command.command, "description": command.description} for command in build_telegram_commands()],
        ensure_ascii=False,
    )

    for language_payload in _language_payloads(args.language_code):
        _call_bot_api(token, "setMyName", {"name": TELEGRAM_NAME, **language_payload})
        _call_bot_api(token, "setMyDescription", {"description": TELEGRAM_DESCRIPTION, **language_payload})
        _call_bot_api(
            token,
            "setMyShortDescription",
            {"short_description": TELEGRAM_SHORT_DESCRIPTION, **language_payload},
        )
        _call_bot_api(token, "setMyCommands", {"commands": command_payload, **language_payload})

    _call_bot_api(token, "setChatMenuButton", {"menu_button": json.dumps({"type": "commands"})})

    if not args.skip_photo:
        profile_photo = get_brand_asset_path(PROJECT_ROOT, "docmolder-telegram-profile.jpg")
        _call_bot_api(
            token,
            "setMyProfilePhoto",
            {"photo": json.dumps({"type": "static", "photo": "attach://profile_photo"})},
            file_field=("profile_photo", profile_photo),
        )

    print("Telegram branding sincronizzato con successo.")


if __name__ == "__main__":
    main()

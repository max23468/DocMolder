"""Telegram messaging helpers with chunking and parse-mode fallback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from telegram.constants import ParseMode
from telegram.error import BadRequest

TelegramApiCall = Callable[..., Awaitable[Any]]


def chunk_message(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for line in text.splitlines():
        extra = len(line) + (1 if current else 0)
        if current and current_length + extra > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
            continue
        current.append(line)
        current_length += extra
    if current:
        chunks.append("\n".join(current))
    return chunks


async def send_telegram_message(
    bot: Any,
    *,
    chat_id: int,
    text: str,
    api_call: TelegramApiCall,
    reply_to_message_id: int | None = None,
    parse_mode: str | None = None,
    chunk_limit: int = 3500,
    **kwargs: Any,
) -> Any:
    chunks = chunk_message(text, limit=chunk_limit)
    last_result: Any = None
    for index, chunk in enumerate(chunks):
        call_kwargs = {
            **kwargs,
            "chat_id": chat_id,
            "text": chunk,
            "reply_to_message_id": reply_to_message_id,
        }
        if parse_mode is not None:
            call_kwargs["parse_mode"] = parse_mode
        if "reply_markup" in call_kwargs and index != len(chunks) - 1:
            call_kwargs.pop("reply_markup", None)
        try:
            last_result = await api_call("sendMessage", bot.send_message, **call_kwargs)
        except BadRequest:
            if parse_mode is None:
                raise
            fallback_kwargs = dict(call_kwargs)
            fallback_kwargs.pop("parse_mode", None)
            last_result = await api_call("sendMessage", bot.send_message, **fallback_kwargs)
    return last_result


async def send_html_message(
    bot: Any,
    *,
    chat_id: int,
    text: str,
    api_call: TelegramApiCall,
    reply_to_message_id: int | None = None,
    **kwargs: Any,
) -> Any:
    return await send_telegram_message(
        bot,
        chat_id=chat_id,
        text=text,
        api_call=api_call,
        reply_to_message_id=reply_to_message_id,
        parse_mode=ParseMode.HTML,
        **kwargs,
    )

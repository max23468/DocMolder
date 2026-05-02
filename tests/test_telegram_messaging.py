from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telegram.constants import ParseMode
from telegram.error import BadRequest

from docmolder.telegram_messaging import chunk_message, send_html_message, send_telegram_message


class TelegramMessagingTest(unittest.IsolatedAsyncioTestCase):
    def test_chunk_message_splits_on_lines(self) -> None:
        chunks = chunk_message("prima\nseconda\nterza", limit=13)

        self.assertEqual(chunks, ["prima\nseconda", "terza"])

    def test_chunk_message_splits_single_overlong_line(self) -> None:
        chunks = chunk_message("abcdefghij", limit=4)

        self.assertEqual(chunks, ["abcd", "efgh", "ij"])
        self.assertTrue(all(len(chunk) <= 4 for chunk in chunks))

    def test_chunk_message_rejects_non_positive_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "positivo"):
            chunk_message("test", limit=0)

    async def test_send_telegram_message_chunks_and_keeps_reply_markup_on_last_chunk(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        api_call = AsyncMock(return_value="ok")

        await send_telegram_message(
            bot,
            chat_id=12,
            text="prima\nseconda\nterza",
            api_call=api_call,
            chunk_limit=13,
            reply_markup="keyboard",
        )

        self.assertEqual(api_call.await_count, 2)
        self.assertNotIn("reply_markup", api_call.await_args_list[0].kwargs)
        self.assertEqual(api_call.await_args_list[1].kwargs["reply_markup"], "keyboard")

    async def test_send_telegram_message_retries_without_parse_mode_on_bad_request(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        api_call = AsyncMock(side_effect=[BadRequest("bad html"), "ok"])

        result = await send_telegram_message(
            bot,
            chat_id=12,
            text="<b>rotto",
            api_call=api_call,
            parse_mode=ParseMode.HTML,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(api_call.await_count, 2)
        self.assertEqual(api_call.await_args_list[0].kwargs["parse_mode"], ParseMode.HTML)
        self.assertNotIn("parse_mode", api_call.await_args_list[1].kwargs)

    async def test_send_telegram_message_reraises_bad_request_without_parse_mode(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        api_call = AsyncMock(side_effect=BadRequest("bad request"))

        with self.assertRaises(BadRequest):
            await send_telegram_message(
                bot,
                chat_id=12,
                text="test",
                api_call=api_call,
            )

        api_call.assert_awaited_once()

    async def test_send_html_message_uses_html_parse_mode(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        api_call = AsyncMock(return_value="ok")

        result = await send_html_message(
            bot,
            chat_id=12,
            text="<b>ok</b>",
            api_call=api_call,
            reply_to_message_id=34,
        )

        self.assertEqual(result, "ok")
        api_call.assert_awaited_once()
        self.assertEqual(api_call.await_args.kwargs["parse_mode"], ParseMode.HTML)
        self.assertEqual(api_call.await_args.kwargs["reply_to_message_id"], 34)

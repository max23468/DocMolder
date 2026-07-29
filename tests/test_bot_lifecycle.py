from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from telegram.constants import ChatType
from telegram.ext import ApplicationHandlerStop


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.action_catalog import build_session_file
from docmolder.bot import (
    MIXED_SESSION_MESSAGE,
    _download_session_files,
    _job_worker,
    _post_shutdown,
    _private_chat_only,
    _validate_session_for_upload,
)
from docmolder.models import FileKind, UserSession
from docmolder.processing import ProcessingUserError


class BotLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_private_chat_guard_stops_group_updates(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type=ChatType.GROUP),
            effective_message=message,
        )

        with self.assertRaises(ApplicationHandlerStop):
            await _private_chat_only(update, SimpleNamespace())
        message.reply_text.assert_awaited_once()

    async def test_post_shutdown_cancels_background_tasks(self) -> None:
        async def wait_forever() -> None:
            await asyncio.Future()

        deps = SimpleNamespace(
            job_worker_task=asyncio.create_task(wait_forever()),
            cleanup_task=asyncio.create_task(wait_forever()),
            admin_report_task=asyncio.create_task(wait_forever()),
        )

        await _post_shutdown(SimpleNamespace(bot_data={"deps": deps}))

        self.assertTrue(deps.job_worker_task.cancelled())
        self.assertTrue(deps.cleanup_task.cancelled())
        self.assertTrue(deps.admin_report_task.cancelled())

    async def test_post_shutdown_allows_missing_background_tasks(self) -> None:
        deps = SimpleNamespace(job_worker_task=None, cleanup_task=None, admin_report_task=None)

        await _post_shutdown(SimpleNamespace(bot_data={"deps": deps}))

    async def test_job_worker_marks_queue_item_done_after_unhandled_error(self) -> None:
        queue: asyncio.Queue[int] = asyncio.Queue()
        await queue.put(123)
        deps = SimpleNamespace(job_queue=queue)
        application = SimpleNamespace(bot_data={"deps": deps})

        with (
            patch("docmolder.bot._process_job", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch("docmolder.bot.logger.exception") as log_exception,
        ):
            worker_task = asyncio.create_task(_job_worker(application))
            await asyncio.wait_for(queue.join(), timeout=1)
            worker_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await worker_task
        log_exception.assert_called_once()

    async def test_download_rechecks_actual_file_size(self) -> None:
        class OversizedTelegramFile:
            async def download_to_drive(self, *, custom_path: str) -> None:
                Path(custom_path).write_bytes(b"x" * 1025)

        settings = SimpleNamespace(max_file_size_mb=0, max_session_files=5)
        deps = SimpleNamespace(settings=settings)
        bot = SimpleNamespace(get_file=AsyncMock(return_value=OversizedTelegramFile()))
        application = SimpleNamespace(bot_data={"deps": deps}, bot=bot)
        session = UserSession(user_id=7, files=[build_session_file("file-1", "source.pdf", FileKind.PDF)])

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ProcessingUserError, "budget del job"):
                await _download_session_files(application, session, Path(temp_dir))


class BotUploadValidationTest(unittest.TestCase):
    def test_validate_session_for_upload_rejects_session_file_limit(self) -> None:
        session = UserSession(
            user_id=7,
            files=[build_session_file("pdf-1", "source.pdf", FileKind.PDF)],
        )

        message = _validate_session_for_upload(session, FileKind.PDF, max_session_files=1)

        self.assertIsNotNone(message)
        self.assertIn("Limite attuale: 1 file", message)

    def test_validate_session_for_upload_rejects_mixed_file_kinds(self) -> None:
        session = UserSession(
            user_id=7,
            files=[build_session_file("pdf-1", "source.pdf", FileKind.PDF)],
        )

        message = _validate_session_for_upload(session, FileKind.IMAGE, max_session_files=5)

        self.assertEqual(message, MIXED_SESSION_MESSAGE)


if __name__ == "__main__":
    unittest.main()

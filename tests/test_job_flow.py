from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.action_catalog import build_session_file
from docmolder.job_flow import enqueue_job, run_job_payload
from docmolder.models import FileKind, JobPayload, SupportedAction, UserSession
from docmolder.processing import A4_MARGIN_NARROW_PX, ProcessingResult, ProcessingUserError
from docmolder.session_store import InMemorySessionStore


class JobFlowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.store = InMemorySessionStore()
        self.job_queue: asyncio.Queue[int] = asyncio.Queue()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_enqueue_job_rejects_action_not_supported_by_session(self) -> None:
        deps = SimpleNamespace(session_store=self.store, job_queue=self.job_queue)
        session = UserSession(user_id=7, files=[build_session_file("pdf-1", "doc.pdf", FileKind.PDF)])

        with self.assertRaisesRegex(ProcessingUserError, "non è più disponibile"):
            await enqueue_job(
                deps=deps,
                user_id=7,
                chat_id=99,
                reply_to_message_id=None,
                action=SupportedAction.IMAGES_TO_PDF,
                session=session,
            )

        self.assertTrue(self.job_queue.empty())

    async def test_run_job_payload_rebuilds_session_downloads_files_and_calls_processor(self) -> None:
        downloaded_pdf = self.runtime_dir / "input.pdf"
        downloaded_pdf.write_bytes(b"%PDF")
        session = UserSession(user_id=7, files=[build_session_file("pdf-1", "Contratto.pdf", FileKind.PDF)])
        payload = JobPayload.from_session(session, page_selection="1", image_pdf_margin_px=None)
        job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action=SupportedAction.PDF_EXTRACT_PAGES.value,
            payload_json=payload.to_json(),
        )
        calls: list[tuple] = []

        class FakeProcessor:
            def process(self, *args):
                calls.append(args)
                return ProcessingResult(
                    output_path=self_output,
                    output_name=self_output.name,
                    message="ok",
                )

        self_output = self.runtime_dir / "out.pdf"
        self_output.write_bytes(b"%PDF out")

        async def download_session_files(_application, rebuilt_session: UserSession, input_dir: Path):
            self.assertEqual(rebuilt_session.files[0].file_name, "Contratto.pdf")
            self.assertTrue(input_dir.is_dir())
            return [downloaded_pdf]

        result = await run_job_payload(
            application=SimpleNamespace(),
            processor=FakeProcessor(),
            job=job,
            job_dir=self.runtime_dir / "job",
            download_session_files=download_session_files,
        )

        self.assertEqual(result.output_name, "out.pdf")
        self.assertEqual(calls[0][0], SupportedAction.PDF_EXTRACT_PAGES)
        self.assertEqual(calls[0][1], [downloaded_pdf])
        self.assertEqual(calls[0][2], "Contratto_extracted_pages")
        self.assertEqual(calls[0][5], "1")
        self.assertEqual(calls[0][9], A4_MARGIN_NARROW_PX)


if __name__ == "__main__":
    unittest.main()

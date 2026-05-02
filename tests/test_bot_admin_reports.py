from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.bot import (
    BotDependencies,
    _build_admin_report,
    _build_periodic_admin_report,
    _maybe_send_admin_anomaly_alerts,
    _detect_admin_anomaly_alerts,
    _maybe_send_admin_report_for_period,
)
from docmolder.config import Settings
from docmolder.processing import DocumentProcessor
from docmolder.models import AdminActionStat, AdminStats, AdminUserStat
from docmolder.session_store import InMemorySessionStore


class BotAdminReportsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name) / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.settings = Settings.model_construct(
            telegram_token="test-token",
            allowed_user_ids=[],
            admin_user_ids=[],
            default_language="it",
            session_ttl_minutes=30,
            max_session_files=20,
            max_file_size_mb=20,
            upload_burst_limit=8,
            upload_burst_window_seconds=30,
            max_active_jobs_per_user=2,
            cleanup_interval_minutes=30,
            stale_job_retention_hours=6,
            job_history_retention_days=30,
            admin_slow_job_threshold_ms=30000,
            health_max_queued_jobs=20,
            health_max_running_jobs=5,
            health_max_running_job_age_seconds=3600,
            health_max_runtime_dir_bytes=2_147_483_648,
            health_max_database_bytes=134_217_728,
            health_max_backup_age_seconds=172800,
            health_max_finished_jobs_24h=300,
            health_max_active_users_7d=100,
            health_max_failure_rate_percent=40,
            health_failure_rate_min_finished_jobs=10,
            telegram_brand_sync_enabled=True,
            runtime_dir=self.runtime_dir,
            database_path=self.runtime_dir / "docmolder.db",
            sqlite_backup_dir=self.runtime_dir / "backups",
        )
        self.store = InMemorySessionStore()
        self.processor = DocumentProcessor(self.runtime_dir)
        self.deps = BotDependencies(self.settings, self.store, self.processor)
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.application = SimpleNamespace(bot=self.bot, bot_data={"deps": self.deps})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_admin_report_includes_processing_metrics(self) -> None:
        report = _build_admin_report(
            AdminStats(
                known_users_total=1,
                known_users_last_24h=1,
                known_users_last_7d=1,
                active_users_last_24h=1,
                active_users_last_7d=1,
                completed_actions_total=3,
                completed_actions_last_24h=3,
                completed_actions_last_7d=3,
                active_sessions=0,
                images_to_pdf_total=1,
                pdf_compress_total=1,
                pdf_grayscale_total=1,
                pdf_merge_total=0,
                pdf_split_total=0,
                pdf_extract_pages_total=0,
                pdf_reorder_pages_total=0,
                pdf_delete_pages_total=0,
                pdf_rotate_total=0,
                pdf_watermark_total=0,
                auto_orient_total=0,
                jobs_queued=0,
                jobs_running=0,
                jobs_failed=0,
                jobs_succeeded=3,
                jobs_finished_last_24h=3,
                jobs_failed_last_24h=0,
                raster_results_total=1,
                avg_duration_ms=1500,
                avg_input_bytes=4096,
                avg_output_bytes=2048,
            ),
            [AdminUserStat(user_id=7, label="@mario", completed_actions=3)],
            [AdminActionStat(action="pdf_compress", total=2)],
            [],
            [],
        )

        self.assertIn("Metriche tecniche medie", report)
        self.assertIn("Utenti attivi ultime 24 ore: 1", report)
        self.assertIn("Finestra ultime 24 ore", report)
        self.assertIn("1.5s", report)
        self.assertIn("4.0 KB", report)
        self.assertIn("2.0 KB", report)
        self.assertIn("Sintesi qualità", report)
        self.assertIn("100%", report)
        self.assertIn("Errori più frequenti", report)
        self.assertIn("Job lenti ultime 24 ore", report)
        self.assertIn("Comprimi PDF: 2", report)
        self.assertIn("Dividi PDF: 0", report)

    def test_build_admin_report_uses_weekly_slow_job_label(self) -> None:
        report = _build_admin_report(
            self.store.build_admin_stats(),
            [],
            [],
            [],
            [],
            [],
            activity_window_label="della settimana",
            completed_jobs_heading="Job completati della settimana",
            failed_jobs_heading="Job falliti della settimana",
            slow_jobs_heading="Job lenti della settimana",
        )

        self.assertIn("Job lenti della settimana", report)
        self.assertNotIn("Job lenti ultime 24 ore", report)

    async def test_maybe_send_admin_report_for_period_persists_last_sent(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        self.store.record_completed_action(7, "pdf_compress")
        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
        )

        self.bot.send_message.assert_awaited()
        self.assertEqual(self.store.get_meta("admin_report_daily_last_sent"), "2026-04-06")

        self.bot.send_message.reset_mock()
        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
        )
        self.bot.send_message.assert_not_awaited()

    async def test_maybe_send_admin_report_for_period_skips_empty_period(self) -> None:
        self.deps.settings.admin_user_ids = [999]

        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
        )

        self.bot.send_message.assert_not_awaited()
        self.assertIsNone(self.store.get_meta("admin_report_daily_last_sent"))

    async def test_maybe_send_admin_report_for_period_daily_skips_without_new_users_or_operations(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        failed_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(failed_job.id, "Errore di test")

        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="daily",
            report_date="2026-04-06",
            should_send=True,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
            require_new_users_or_completed_actions=True,
        )

        self.bot.send_message.assert_not_awaited()
        self.assertIsNone(self.store.get_meta("admin_report_daily_last_sent"))

    async def test_maybe_send_admin_report_for_period_weekly_skips_without_new_users_or_operations(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        failed_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=123,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(failed_job.id, "Errore di test")

        await _maybe_send_admin_report_for_period(
            self.application,
            self.deps,
            period="weekly",
            report_date="2026-04-06",
            should_send=True,
            since_days=7,
            title="Riepilogo admin settimanale DocMolder",
            require_new_users_or_completed_actions=True,
        )

        self.bot.send_message.assert_not_awaited()
        self.assertIsNone(self.store.get_meta("admin_report_weekly_last_sent"))

    def test_build_periodic_admin_report_prefixes_title(self) -> None:
        report = _build_periodic_admin_report(
            self.deps,
            since_days=1,
            title="Riepilogo admin giornaliero DocMolder",
        )

        self.assertTrue(report.startswith("Riepilogo admin giornaliero DocMolder"))
        self.assertIn("Errori più frequenti ultime 24 ore", report)
        self.assertIn("Job completati nelle ultime 24 ore", report)

    def test_detect_admin_anomaly_alerts_reports_failure_rate_and_repeated_action(self) -> None:
        self.deps.settings.admin_alert_window_minutes = 30
        self.deps.settings.admin_alert_min_finished_jobs = 4
        self.deps.settings.admin_alert_failure_rate_percent = 50
        self.deps.settings.admin_alert_repeated_failures_threshold = 3

        for index in range(4):
            job = self.store.create_job(
                user_id=7,
                chat_id=99,
                reply_to_message_id=900 + index,
                action="pdf_compress",
                payload_json='{"files":[]}',
            )
            self.store.mark_job_failed(job.id, "Errore di test")

        success_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=999,
            action="images_to_pdf",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_succeeded(success_job.id, "Ok")

        alerts = _detect_admin_anomaly_alerts(self.deps)

        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["key"], "failure-rate")
        self.assertIn("tasso di fallimento anomalo", alerts[0]["text"])
        self.assertIn("Comprimi PDF: 4", alerts[0]["text"])
        self.assertIn("docmolder-healthcheck", alerts[0]["text"])
        self.assertEqual(alerts[1]["key"], "repeated-failures:pdf_compress")
        self.assertIn("errori ripetuti su Comprimi PDF", alerts[1]["text"])
        self.assertIn("runbook", alerts[1]["text"])

    async def test_maybe_send_admin_anomaly_alerts_respects_cooldown(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        self.deps.settings.admin_alert_window_minutes = 30
        self.deps.settings.admin_alert_min_finished_jobs = 3
        self.deps.settings.admin_alert_failure_rate_percent = 60
        self.deps.settings.admin_alert_repeated_failures_threshold = 3
        self.deps.settings.admin_alert_cooldown_minutes = 120

        for index in range(3):
            job = self.store.create_job(
                user_id=7,
                chat_id=99,
                reply_to_message_id=1000 + index,
                action="pdf_compress",
                payload_json='{"files":[]}',
            )
            self.store.mark_job_failed(job.id, "Errore di test")

        await _maybe_send_admin_anomaly_alerts(self.application, self.deps)
        first_send_count = self.bot.send_message.await_count
        self.assertGreaterEqual(first_send_count, 1)

        await _maybe_send_admin_anomaly_alerts(self.application, self.deps)
        self.assertEqual(self.bot.send_message.await_count, first_send_count)

    async def test_maybe_send_admin_anomaly_alerts_appends_digest_after_suppressed_duplicates(self) -> None:
        self.deps.settings.admin_user_ids = [999]
        self.deps.settings.admin_alert_window_minutes = 30
        self.deps.settings.admin_alert_min_finished_jobs = 3
        self.deps.settings.admin_alert_failure_rate_percent = 60
        self.deps.settings.admin_alert_repeated_failures_threshold = 3
        self.deps.settings.admin_alert_cooldown_minutes = 120

        for index in range(3):
            job = self.store.create_job(
                user_id=7,
                chat_id=99,
                reply_to_message_id=2000 + index,
                action="pdf_compress",
                payload_json='{"files":[]}',
            )
            self.store.mark_job_failed(job.id, "Errore di test")

        await _maybe_send_admin_anomaly_alerts(self.application, self.deps)
        self.bot.send_message.reset_mock()
        await _maybe_send_admin_anomaly_alerts(self.application, self.deps)

        self.store.set_meta("admin_alert:failure-rate:last_sent_at", "2000-01-01T00:00:00+00:00")
        self.store.set_meta("admin_alert:repeated-failures:pdf_compress:last_sent_at", "2000-01-01T00:00:00+00:00")

        newer_job = self.store.create_job(
            user_id=7,
            chat_id=99,
            reply_to_message_id=2999,
            action="pdf_compress",
            payload_json='{"files":[]}',
        )
        self.store.mark_job_failed(newer_job.id, "Errore di test")

        await _maybe_send_admin_anomaly_alerts(self.application, self.deps)

        sent_texts = [call.kwargs["text"] for call in self.bot.send_message.await_args_list]
        self.assertTrue(any("soppresso" in text for text in sent_texts))

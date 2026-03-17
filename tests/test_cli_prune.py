import json
import unittest
from argparse import Namespace
from datetime import datetime
from unittest.mock import patch

from qzcli import cli
from qzcli.store import JobRecord, JobStore
from tests.support import temporary_config_state
from tests.test_cli_proxy import FakeDisplay


class CLIPruneTests(unittest.TestCase):
    def _args(self, **overrides):
        args = {
            "days": 14,
            "dry_run": False,
            "status": None,
            "yes": True,
        }
        args.update(overrides)
        return Namespace(**args)

    def test_prune_dry_run_only_reports_statistics(self):
        with temporary_config_state() as base:
            display = FakeDisplay()
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            store.add(
                JobRecord(
                    job_id="job-old",
                    status="job_failed",
                    finished_at="2026-02-01T00:00:00",
                )
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_store", return_value=store), \
                 patch("qzcli.store.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime.fromisoformat("2026-03-15T12:00:00")
                mock_datetime.min = datetime.min
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                result = cli.cmd_prune(self._args(dry_run=True))

            self.assertEqual(result, 0)
            self.assertEqual(store.list_job_ids(), ["job-old"])
            self.assertFalse((base / "jobs.archive.jsonl").exists())
            self.assertTrue(any("扫描任务数: 1" in line for line in display.lines))
            self.assertTrue(any("可清理任务数: 1" in line for line in display.lines))

    def test_prune_archives_and_deletes_matching_jobs(self):
        with temporary_config_state() as base:
            display = FakeDisplay()
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            store.add(
                JobRecord(
                    job_id="job-failed",
                    status="job_failed",
                    finished_at="2026-02-01T00:00:00",
                )
            )
            store.add(
                JobRecord(
                    job_id="job-running",
                    status="job_running",
                    updated_at="2026-02-01T00:00:00",
                )
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_store", return_value=store), \
                 patch("qzcli.store.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime.fromisoformat("2026-03-15T12:00:00")
                mock_datetime.min = datetime.min
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                result = cli.cmd_prune(self._args())

            self.assertEqual(result, 0)
            self.assertEqual(store.list_job_ids(), ["job-running"])
            self.assertTrue(any("已清理 1 个任务记录" in msg for msg in display.successes))

            archive_lines = (base / "jobs.archive.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(archive_lines), 1)
            payload = json.loads(archive_lines[0])
            self.assertEqual(payload["job"]["job_id"], "job-failed")

    def test_prune_status_filter_only_deletes_selected_terminal_status(self):
        with temporary_config_state() as base:
            display = FakeDisplay()
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            store.add(
                JobRecord(
                    job_id="job-failed",
                    status="job_failed",
                    finished_at="2026-02-01T00:00:00",
                )
            )
            store.add(
                JobRecord(
                    job_id="job-stopped",
                    status="job_stopped",
                    finished_at="2026-02-01T00:00:00",
                )
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_store", return_value=store), \
                 patch("qzcli.store.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime.fromisoformat("2026-03-15T12:00:00")
                mock_datetime.min = datetime.min
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                result = cli.cmd_prune(self._args(status="job_failed"))

            self.assertEqual(result, 0)
            self.assertEqual(store.list_job_ids(), ["job-stopped"])

    def test_prune_archive_failure_keeps_store_unchanged(self):
        with temporary_config_state() as base:
            display = FakeDisplay()
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            store.add(
                JobRecord(
                    job_id="job-failed",
                    status="job_failed",
                    finished_at="2026-02-01T00:00:00",
                )
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_store", return_value=store), \
                 patch.object(store, "archive_jobs", side_effect=OSError("disk full")), \
                 patch("qzcli.store.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime.fromisoformat("2026-03-15T12:00:00")
                mock_datetime.min = datetime.min
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                result = cli.cmd_prune(self._args())

            self.assertEqual(result, 1)
            self.assertEqual(store.list_job_ids(), ["job-failed"])
            self.assertFalse((base / "jobs.archive.jsonl").exists())
            self.assertTrue(any("清理失败: disk full" in msg for msg in display.errors))


if __name__ == "__main__":
    unittest.main()

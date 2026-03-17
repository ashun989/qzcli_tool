import json
from datetime import datetime
import unittest

from qzcli.store import JobRecord, JobStore
from tests.support import temporary_config_state


class JobRecordTests(unittest.TestCase):
    def test_from_api_response_extracts_resource_fields_and_url(self):
        api_data = {
            "job_id": "job-123",
            "name": "demo-job",
            "status": "job_running",
            "workspace_id": "ws-001",
            "project_id": "project-001",
            "project_name": "Project A",
            "logic_compute_group_name": "H200 Group",
            "created_at": "1700000000000",
            "finished_at": "1700003600000",
            "command": "python train.py",
            "running_time_ms": "65000",
            "priority_level": "4",
            "framework_config": [
                {
                    "gpu_count": 8,
                    "instance_count": 2,
                    "instance_spec_price_info": {
                        "gpu_info": {
                            "gpu_product_simple": "H200",
                        }
                    },
                }
            ],
        }

        job = JobRecord.from_api_response(api_data, source="unit-test")

        self.assertEqual(job.job_id, "job-123")
        self.assertEqual(job.name, "demo-job")
        self.assertEqual(job.workspace_id, "ws-001")
        self.assertEqual(job.project_name, "Project A")
        self.assertEqual(job.compute_group_name, "H200 Group")
        self.assertEqual(job.gpu_count, 8)
        self.assertEqual(job.instance_count, 2)
        self.assertEqual(job.gpu_type, "H200")
        self.assertEqual(job.source, "unit-test")
        self.assertIn("distributedTrainingDetail/job-123?spaceId=ws-001", job.url)
        self.assertTrue(job.created_at)
        self.assertTrue(job.finished_at)

    def test_from_dict_ignores_unknown_fields(self):
        job = JobRecord.from_dict(
            {
                "job_id": "job-123",
                "name": "demo",
                "status": "job_running",
                "unknown_field": "ignored",
            }
        )

        self.assertEqual(job.job_id, "job-123")
        self.assertEqual(job.name, "demo")
        self.assertFalse(hasattr(job, "unknown_field"))


class JobStoreTests(unittest.TestCase):
    def test_add_update_list_and_remove_jobs(self):
        with temporary_config_state() as base:
            store = JobStore(store_file=base / "jobs.json")

            store.add(JobRecord(job_id="job-1", name="older", created_at="2024-01-01T00:00:00"))
            store.add(JobRecord(job_id="job-2", name="newer", created_at="2024-01-02T00:00:00", status="job_running"))

            jobs = store.list()
            self.assertEqual([job.job_id for job in jobs], ["job-2", "job-1"])
            self.assertEqual(store.count(), 2)

            updated = store.update("job-2", status="job_stopped", source="manual")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.status, "job_stopped")
            self.assertEqual(updated.source, "manual")

            running_jobs = store.list(status="job_running")
            self.assertEqual(running_jobs, [])

            self.assertTrue(store.remove("job-1"))
            self.assertEqual(store.list_job_ids(), ["job-2"])
            self.assertFalse(store.remove("job-missing"))

    def test_update_from_api_preserves_existing_source_and_metadata(self):
        with temporary_config_state() as base:
            store = JobStore(store_file=base / "jobs.json")
            store.add(
                JobRecord(
                    job_id="job-1",
                    name="seed",
                    source="external-script",
                    metadata={"tag": "keep"},
                )
            )

            store.update_from_api(
                "job-1",
                {
                    "job_id": "job-1",
                    "name": "updated-name",
                    "status": "job_running",
                    "workspace_id": "ws-1",
                },
            )

            job = store.get("job-1")
            self.assertIsNotNone(job)
            self.assertEqual(job.name, "updated-name")
            self.assertEqual(job.source, "external-script")
            self.assertEqual(job.metadata, {"tag": "keep"})

    def test_import_from_file_supports_plain_and_tab_formats(self):
        with temporary_config_state() as base:
            store = JobStore(store_file=base / "jobs.json")
            import_file = base / "jobs.txt"
            import_file.write_text(
                "# comment\n"
                "job-plain\n"
                "eval-name\tstep-1\tjob-tabbed\n"
                "not-a-job\n"
                "job-plain\n",
                encoding="utf-8",
            )

            count = store.import_from_file(import_file, source="import-test")

            self.assertEqual(count, 2)
            self.assertEqual(sorted(store.list_job_ids()), ["job-plain", "job-tabbed"])
            self.assertEqual(store.get("job-tabbed").name, "eval-name")
            self.assertEqual(store.get("job-plain").source, "import-test")

    def test_find_prunable_jobs_only_returns_terminal_jobs_beyond_ttl(self):
        with temporary_config_state() as base:
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            now = datetime.fromisoformat("2026-03-15T12:00:00")

            store.add(
                JobRecord(
                    job_id="job-old-succeeded",
                    status="job_succeeded",
                    finished_at="2026-02-01T00:00:00",
                )
            )
            store.add(
                JobRecord(
                    job_id="job-recent-failed",
                    status="job_failed",
                    finished_at="2026-03-10T00:00:00",
                )
            )
            store.add(
                JobRecord(
                    job_id="job-running",
                    status="job_running",
                    updated_at="2026-01-01T00:00:00",
                )
            )
            store.add(
                JobRecord(
                    job_id="job-unknown",
                    status="unknown",
                    updated_at="2026-01-01T00:00:00",
                )
            )

            jobs = store.find_prunable_jobs(14, now=now)

            self.assertEqual([job.job_id for job in jobs], ["job-old-succeeded"])

    def test_find_prunable_jobs_falls_back_to_updated_then_created_time(self):
        with temporary_config_state() as base:
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            now = datetime.fromisoformat("2026-03-15T12:00:00")

            store.add(
                JobRecord(
                    job_id="job-use-updated",
                    status="job_failed",
                    updated_at="2026-02-20T08:00:00",
                )
            )
            store.add(
                JobRecord(
                    job_id="job-use-created",
                    status="job_stopped",
                    created_at="2026-02-10T08:00:00",
                )
            )
            store.add(
                JobRecord(
                    job_id="job-no-time",
                    status="job_succeeded",
                )
            )

            jobs = store.find_prunable_jobs(14, now=now)

            self.assertEqual(
                sorted(job.job_id for job in jobs),
                ["job-use-created", "job-use-updated"],
            )

    def test_prune_archives_then_removes_matching_jobs(self):
        with temporary_config_state() as base:
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            now = datetime.fromisoformat("2026-03-15T12:00:00")
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

            result = store.prune(14, now=now)

            self.assertEqual(result["eligible"], 1)
            self.assertEqual(result["pruned"], 1)
            self.assertEqual(store.list_job_ids(), ["job-running"])

            archive_lines = (base / "jobs.archive.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(archive_lines), 1)
            payload = json.loads(archive_lines[0])
            self.assertEqual(payload["reason"], "ttl_expired")
            self.assertEqual(payload["ttl_days"], 14)
            self.assertEqual(payload["job"]["job_id"], "job-failed")

    def test_prune_dry_run_does_not_modify_store_or_archive(self):
        with temporary_config_state() as base:
            store = JobStore(
                store_file=base / "jobs.json",
                archive_file=base / "jobs.archive.jsonl",
            )
            now = datetime.fromisoformat("2026-03-15T12:00:00")
            store.add(
                JobRecord(
                    job_id="job-failed",
                    status="job_failed",
                    finished_at="2026-02-01T00:00:00",
                )
            )

            result = store.prune(14, dry_run=True, now=now)

            self.assertEqual(result["eligible"], 1)
            self.assertEqual(result["pruned"], 0)
            self.assertEqual(store.list_job_ids(), ["job-failed"])
            self.assertFalse((base / "jobs.archive.jsonl").exists())


if __name__ == "__main__":
    unittest.main()

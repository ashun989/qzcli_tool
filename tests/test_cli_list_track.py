import unittest
from argparse import Namespace
from unittest.mock import patch

from qzcli import cli
from qzcli.config import save_cookie, save_resources
from qzcli.store import JobRecord, JobStore
from tests.support import temporary_config_state
from tests.test_cli_proxy import FakeDisplay


class FakeListDisplay(FakeDisplay):
    def print_jobs_table(self, jobs, **kwargs):
        self.lines.append("TABLE:" + ",".join(job.job_id for job in jobs))

    def print_jobs_wide(self, jobs):
        self.lines.append("WIDE:" + ",".join(job.job_id for job in jobs))


class FakeListAPI:
    def __init__(self, results_by_workspace):
        self.results_by_workspace = results_by_workspace
        self.calls = []

    def list_jobs_with_cookie(self, workspace_id, cookie, page_num=1, page_size=20):
        self.calls.append((workspace_id, cookie, page_num, page_size))
        jobs = list(self.results_by_workspace.get(workspace_id, []))
        start = (page_num - 1) * page_size
        end = start + page_size
        return {"jobs": jobs[start:end], "total": len(jobs)}


class CLIListTrackTests(unittest.TestCase):
    def _cookie_args(self, **overrides):
        args = {
            "limit": 20,
            "status": None,
            "running": False,
            "no_refresh": False,
            "verbose": False,
            "url": True,
            "wide": False,
            "compact": True,
            "cookie": True,
            "workspace": None,
            "all_ws": True,
            "track": True,
        }
        args.update(overrides)
        return Namespace(**args)

    def test_list_cookie_track_syncs_all_workspaces(self):
        with temporary_config_state() as base:
            display = FakeListDisplay()
            store = JobStore(store_file=base / "jobs.json")
            save_cookie("session=test-cookie")
            save_resources("ws-1", {"projects": [], "compute_groups": [], "specs": []}, name="公共项目空间")
            save_resources("ws-2", {"projects": [], "compute_groups": [], "specs": []}, name="CI Team")
            api = FakeListAPI(
                {
                    "ws-1": [
                        {
                            "job_id": "job-1",
                            "name": "train-a",
                            "status": "job_running",
                            "workspace_id": "ws-1",
                            "created_at": "1700000000000",
                        }
                    ],
                    "ws-2": [
                        {
                            "job_id": "job-2",
                            "name": "train-b",
                            "status": "job_queuing",
                            "workspace_id": "ws-2",
                            "created_at": "1700003600000",
                        }
                    ],
                }
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_list_cookie(self._cookie_args())

            self.assertEqual(result, 0)
            self.assertEqual(sorted(store.list_job_ids()), ["job-1", "job-2"])
            self.assertEqual(store.get("job-1").metadata.get("workspace_name"), "公共项目空间")
            self.assertEqual(store.get("job-2").metadata.get("workspace_name"), "CI Team")
            self.assertTrue(any("已同步到本地追踪列表" in line for line in display.lines))

    def test_list_cookie_track_updates_existing_jobs_instead_of_duplicating(self):
        with temporary_config_state() as base:
            display = FakeListDisplay()
            store = JobStore(store_file=base / "jobs.json")
            store.add(
                JobRecord(
                    job_id="job-1",
                    name="old-name",
                    status="job_queuing",
                    source="manual-script",
                    metadata={"tag": "keep"},
                )
            )
            save_cookie("session=test-cookie")
            save_resources("ws-1", {"projects": [], "compute_groups": [], "specs": []}, name="公共项目空间")
            api = FakeListAPI(
                {
                    "ws-1": [
                        {
                            "job_id": "job-1",
                            "name": "new-name",
                            "status": "job_running",
                            "workspace_id": "ws-1",
                            "created_at": "1700000000000",
                        }
                    ]
                }
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_list_cookie(self._cookie_args(workspace="ws-1", all_ws=False))

            self.assertEqual(result, 0)
            self.assertEqual(store.count(), 1)
            self.assertEqual(store.get("job-1").name, "new-name")
            self.assertEqual(store.get("job-1").status, "job_running")
            self.assertEqual(store.get("job-1").source, "manual-script")
            self.assertEqual(store.get("job-1").metadata["tag"], "keep")
            self.assertEqual(store.get("job-1").metadata["workspace_name"], "公共项目空间")
            self.assertTrue(any("新增 0，更新 1" in line for line in display.lines))

    def test_list_cookie_track_deduplicates_duplicate_job_ids(self):
        with temporary_config_state() as base:
            display = FakeListDisplay()
            store = JobStore(store_file=base / "jobs.json")
            save_cookie("session=test-cookie")
            save_resources("ws-1", {"projects": [], "compute_groups": [], "specs": []}, name="公共项目空间")
            save_resources("ws-2", {"projects": [], "compute_groups": [], "specs": []}, name="CI Team")
            api = FakeListAPI(
                {
                    "ws-1": [
                        {
                            "job_id": "job-dup",
                            "name": "first-copy",
                            "status": "job_running",
                            "workspace_id": "ws-1",
                            "created_at": "1700000000000",
                        }
                    ],
                    "ws-2": [
                        {
                            "job_id": "job-dup",
                            "name": "second-copy",
                            "status": "job_running",
                            "workspace_id": "ws-2",
                            "created_at": "1700003600000",
                        }
                    ],
                }
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_list_cookie(self._cookie_args())

            self.assertEqual(result, 0)
            self.assertEqual(store.count(), 1)
            self.assertEqual(store.get("job-dup").name, "second-copy")
            self.assertTrue(any("新增 1，更新 0，总计 1" in line for line in display.lines))

    def test_list_cookie_track_fetches_all_pages_before_sync(self):
        with temporary_config_state() as base:
            display = FakeListDisplay()
            store = JobStore(store_file=base / "jobs.json")
            save_cookie("session=test-cookie")
            save_resources("ws-1", {"projects": [], "compute_groups": [], "specs": []}, name="公共项目空间")
            api = FakeListAPI(
                {
                    "ws-1": [
                        {
                            "job_id": f"job-{index}",
                            "name": f"train-{index}",
                            "status": "job_running",
                            "workspace_id": "ws-1",
                            "created_at": str(1700000000000 + index),
                        }
                        for index in range(105)
                    ]
                }
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_list_cookie(self._cookie_args(workspace="ws-1", all_ws=False, limit=20))

            self.assertEqual(result, 0)
            self.assertEqual(store.count(), 105)
            self.assertEqual(
                api.calls,
                [
                    ("ws-1", "session=test-cookie", 1, 100),
                    ("ws-1", "session=test-cookie", 2, 100),
                ],
            )
            self.assertTrue(any("总计 105" in line for line in display.lines))

    def test_list_rejects_track_without_cookie_mode(self):
        display = FakeListDisplay()

        with patch("qzcli.cli.get_display", return_value=display):
            result = cli.cmd_list(
                Namespace(
                    track=True,
                    cookie=False,
                    limit=20,
                    status=None,
                    running=False,
                    no_refresh=False,
                    verbose=False,
                    url=True,
                    wide=False,
                    compact=True,
                    workspace=None,
                    all_ws=False,
                )
            )

        self.assertEqual(result, 1)
        self.assertTrue(any("--track 仅支持 --cookie 模式" in msg for msg in display.errors))

    def test_list_cookie_without_track_does_not_write_store(self):
        with temporary_config_state() as base:
            display = FakeListDisplay()
            store = JobStore(store_file=base / "jobs.json")
            save_cookie("session=test-cookie")
            save_resources("ws-1", {"projects": [], "compute_groups": [], "specs": []}, name="公共项目空间")
            api = FakeListAPI(
                {
                    "ws-1": [
                        {
                            "job_id": "job-1",
                            "name": "train-a",
                            "status": "job_running",
                            "workspace_id": "ws-1",
                            "created_at": "1700000000000",
                        }
                    ]
                }
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_list_cookie(self._cookie_args(workspace="ws-1", all_ws=False, track=False))

            self.assertEqual(result, 0)
            self.assertEqual(store.count(), 0)
            self.assertFalse(any("已同步到本地追踪列表" in line for line in display.lines))


if __name__ == "__main__":
    unittest.main()

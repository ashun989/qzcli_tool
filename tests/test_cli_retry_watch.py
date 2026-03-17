import copy
import os
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from qzcli import cli
from qzcli.api import QzAPIError
from qzcli.config import get_cookie, save_cookie, save_login_credentials
from qzcli.store import JobStore
from tests.support import temporary_config_state
from tests.test_cli_proxy import FakeDisplay


class FakeRetryWatchAPI:
    def __init__(self):
        self.created_payloads = []
        self.list_calls = []
        self.detail_calls = []
        self._detail_indexes = {}
        self.jobs = [
            {
                "job_id": "job-old",
                "name": "qz_train_narbd_sft2",
                "created_at": "1700000000000",
                "status": "job_failed",
                "project_name": "Project A",
                "logic_compute_group_name": "H200 Group",
            }
        ]
        self.detail_sequences = {
            "job-old": [
                {
                    "job_id": "job-old",
                    "name": "qz_train_narbd_sft2",
                    "status": "job_failed",
                    "workspace_id": "ws-1",
                    "project_id": "project-1",
                    "logic_compute_group_id": "lcg-1",
                    "framework": "pytorch",
                    "command": "python train.py",
                    "priority_level": "4",
                    "created_at": "1700000000000",
                    "framework_config": [
                        {
                            "image": "repo/image:latest",
                            "image_type": "SOURCE_OFFICIAL",
                            "instance_count": 1,
                            "gpu_count": 8,
                            "shm_gi": 0,
                            "instance_spec_price_info": {
                                "quota_id": "spec-9",
                            },
                        }
                    ],
                }
            ],
            "job-running": [
                {
                    "job_id": "job-running",
                    "name": "qz_train_narbd_sft2",
                    "status": "job_running",
                    "workspace_id": "ws-1",
                    "project_id": "project-1",
                    "logic_compute_group_id": "lcg-1",
                    "framework": "pytorch",
                    "command": "python train.py",
                    "task_priority": 4,
                    "framework_config": [
                        {
                            "image": "repo/image:latest",
                            "image_type": "SOURCE_OFFICIAL",
                            "instance_count": 1,
                            "gpu_count": 8,
                            "shm_gi": 0,
                            "spec_id": "spec-9",
                        }
                    ],
                }
            ],
            "job-new": [
                {
                    "job_id": "job-new",
                    "name": "qz_train_narbd_sft2",
                    "status": "job_running",
                    "workspace_id": "ws-1",
                    "project_id": "project-1",
                    "logic_compute_group_id": "lcg-1",
                    "framework": "pytorch",
                    "command": "python train.py",
                    "task_priority": 4,
                    "framework_config": [
                        {
                            "image": "repo/image:latest",
                            "image_type": "SOURCE_OFFICIAL",
                            "instance_count": 1,
                            "gpu_count": 8,
                            "shm_gi": 0,
                            "spec_id": "spec-9",
                        }
                    ],
                },
                {
                    "job_id": "job-new",
                    "name": "qz_train_narbd_sft2",
                    "status": "job_succeeded",
                    "workspace_id": "ws-1",
                    "project_id": "project-1",
                    "logic_compute_group_id": "lcg-1",
                    "framework": "pytorch",
                    "command": "python train.py",
                    "task_priority": 4,
                    "framework_config": [
                        {
                            "image": "repo/image:latest",
                            "image_type": "SOURCE_OFFICIAL",
                            "instance_count": 1,
                            "gpu_count": 8,
                            "shm_gi": 0,
                            "spec_id": "spec-9",
                        }
                    ],
                },
            ],
        }

    def list_jobs_with_cookie(self, workspace_id, cookie, page_num=1, page_size=100):
        self.list_calls.append((workspace_id, cookie, page_num, page_size))
        return {"jobs": list(self.jobs), "total": len(self.jobs)}

    def get_job_detail(self, job_id):
        self.detail_calls.append(job_id)
        sequence = self.detail_sequences[job_id]
        index = self._detail_indexes.get(job_id, 0)
        if index < len(sequence) - 1:
            self._detail_indexes[job_id] = index + 1
        return copy.deepcopy(sequence[index])

    def create_job(self, payload):
        self.created_payloads.append(copy.deepcopy(payload))
        return {"job_id": "job-new"}


class FakeRetryWatchRefreshAPI(FakeRetryWatchAPI):
    def __init__(self):
        super().__init__()
        self.login_calls = []
        self.fail_first_cookie_check = True

    def list_jobs_with_cookie(self, workspace_id, cookie, page_num=1, page_size=100):
        self.list_calls.append((workspace_id, cookie, page_num, page_size))
        if self.fail_first_cookie_check:
            self.fail_first_cookie_check = False
            raise QzAPIError("Cookie 已过期或无效，请重新获取", 401)
        return {"jobs": list(self.jobs), "total": len(self.jobs)}

    def login_with_cas(self, username, password):
        self.login_calls.append((username, password))
        return "session=refreshed-cookie"


class CLIRetryWatchTests(unittest.TestCase):
    def test_build_retry_payload_normalizes_priority_and_spec_id(self):
        payload = cli._build_retry_payload(
            {
                "job_id": "job-old",
                "name": "demo-job",
                "status": "job_failed",
                "workspace_id": "ws-1",
                "project_id": "project-1",
                "logic_compute_group_id": "lcg-1",
                "framework": "pytorch",
                "command": "python train.py",
                "priority_level": "4",
                "framework_config": [
                    {
                        "image": "repo/image:latest",
                        "image_type": "SOURCE_OFFICIAL",
                        "instance_count": 1,
                        "shm_gi": 0,
                        "instance_spec_price_info": {"quota_id": "spec-1"},
                    }
                ],
            }
        )

        self.assertNotIn("job_id", payload)
        self.assertEqual(payload["task_priority"], 4)
        self.assertEqual(payload["framework_config"][0]["spec_id"], "spec-1")

    def test_cmd_retry_watch_resubmits_failed_job_and_tracks_new_job(self):
        with temporary_config_state() as base, patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchAPI()
            store = JobStore(store_file=base / "jobs.json")
            save_cookie("cookie=1", workspace_id="ws-1")
            config_dir = base / "retry-configs"

            args = Namespace(
                job_id=None,
                name="qz_train_narbd_sft2",
                workspace="ws-1",
                max_retries=1,
                config_dir=str(config_dir),
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_retry_watch(args)

            self.assertEqual(result, 0)
            self.assertEqual(len(api.created_payloads), 1)
            self.assertEqual(api.created_payloads[0]["task_priority"], 4)
            self.assertEqual(api.created_payloads[0]["framework_config"][0]["spec_id"], "spec-9")
            self.assertIsNotNone(store.get("job-new"))
            self.assertEqual(store.get("job-new").metadata["retry_of"], "job-old")

            snapshot_files = list(Path(config_dir).glob("*.json"))
            self.assertEqual(len(snapshot_files), 1)
            self.assertTrue(any("已自动重提" in msg for msg in display.successes))

    def test_cmd_retry_watch_returns_immediately_when_job_is_running(self):
        with temporary_config_state() as base, patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchAPI()
            store = JobStore(store_file=base / "jobs.json")

            args = Namespace(
                job_id="job-running",
                name=None,
                workspace=None,
                max_retries=1,
                config_dir=str(base / "retry-configs"),
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_retry_watch(args)

            self.assertEqual(result, 0)
            self.assertEqual(api.created_payloads, [])
            self.assertTrue(any("已挂上监控" in msg for msg in display.successes))
            self.assertTrue(store.get("job-running").metadata["retry_watch_enabled"])

    def test_cmd_retry_watch_follows_latest_retry_chain_for_root_job_id(self):
        with temporary_config_state() as base, patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchAPI()
            store = JobStore(store_file=base / "jobs.json")
            store.add(
                cli.JobRecord(
                    job_id="job-root",
                    name="qz_train_narbd_sft2",
                    metadata={"retry_submitted_job_id": "job-running"},
                )
            )

            args = Namespace(
                job_id="job-root",
                name=None,
                workspace=None,
                max_retries=1,
                config_dir=str(base / "retry-configs"),
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_retry_watch(args)

            self.assertEqual(result, 0)
            self.assertEqual(api.detail_calls[-1], "job-running")
            self.assertTrue(any("监控链已切换到最新任务" in line for line in display.lines))

    def test_cmd_retry_watch_does_not_resubmit_same_failed_job_twice(self):
        with temporary_config_state() as base, patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchAPI()
            store = JobStore(store_file=base / "jobs.json")
            save_cookie("cookie=1", workspace_id="ws-1")
            args = Namespace(
                job_id="job-old",
                name=None,
                workspace=None,
                max_retries=1,
                config_dir=str(base / "retry-configs"),
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                first_result = cli.cmd_retry_watch(args)
                second_result = cli.cmd_retry_watch(args)

            self.assertEqual(first_result, 0)
            self.assertEqual(second_result, 0)
            self.assertEqual(len(api.created_payloads), 1)
            self.assertEqual(api.detail_calls[-1], "job-new")
            self.assertTrue(any("监控链已切换到最新任务" in line for line in display.lines))

    def test_cmd_retry_watch_lists_candidates_when_duplicate_names_exist(self):
        with temporary_config_state() as base, patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchAPI()
            api.jobs = [
                {
                    "job_id": "job-a",
                    "name": "qz_train_narbd_sft2",
                    "created_at": "1700000000000",
                    "status": "job_running",
                    "project_name": "Project A",
                    "logic_compute_group_name": "H200 Group",
                },
                {
                    "job_id": "job-b",
                    "name": "qz_train_narbd_sft2",
                    "created_at": "1700000100000",
                    "status": "job_failed",
                    "project_name": "Project B",
                    "logic_compute_group_name": "A800 Group",
                },
            ]
            save_cookie("cookie=1", workspace_id="ws-1")

            args = Namespace(
                job_id=None,
                name="qz_train_narbd_sft2",
                workspace="ws-1",
                max_retries=1,
                config_dir=str(base / "retry-configs"),
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("sys.stdin.isatty", return_value=False):
                result = cli.cmd_retry_watch(args)

            self.assertEqual(result, 2)
            self.assertEqual(api.created_payloads, [])
            self.assertTrue(any("检测到同名任务候选" in line for line in display.lines))
            self.assertTrue(any("job-a" in line for line in display.lines))
            self.assertTrue(any("job-b" in line for line in display.lines))

    def test_cmd_retry_watch_prompts_to_select_candidate_when_interactive(self):
        with temporary_config_state() as base, patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchAPI()
            api.jobs = [
                {
                    "job_id": "job-a",
                    "name": "qz_train_narbd_sft2",
                    "created_at": "1700000000000",
                    "status": "job_running",
                    "project_name": "Project A",
                    "logic_compute_group_name": "H200 Group",
                },
                {
                    "job_id": "job-b",
                    "name": "qz_train_narbd_sft2",
                    "created_at": "1700000100000",
                    "status": "job_failed",
                    "project_name": "Project B",
                    "logic_compute_group_name": "A800 Group",
                },
            ]
            api.detail_sequences["job-b"] = [
                {
                    "job_id": "job-b",
                    "name": "qz_train_narbd_sft2",
                    "status": "job_failed",
                    "workspace_id": "ws-1",
                    "project_id": "project-2",
                    "logic_compute_group_id": "lcg-2",
                    "framework": "pytorch",
                    "command": "python train.py --retry",
                    "task_priority": 4,
                    "framework_config": [
                        {
                            "image": "repo/image:latest",
                            "image_type": "SOURCE_OFFICIAL",
                            "instance_count": 1,
                            "gpu_count": 8,
                            "shm_gi": 0,
                            "spec_id": "spec-2",
                        }
                    ],
                }
            ]
            store = JobStore(store_file=base / "jobs.json")
            save_cookie("cookie=1", workspace_id="ws-1")

            args = Namespace(
                job_id=None,
                name="qz_train_narbd_sft2",
                workspace="ws-1",
                max_retries=1,
                config_dir=str(base / "retry-configs"),
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store), \
                 patch("sys.stdin.isatty", return_value=True), \
                 patch("builtins.input", return_value="1"):
                result = cli.cmd_retry_watch(args)

            self.assertEqual(result, 0)
            self.assertEqual(len(api.created_payloads), 1)
            self.assertIsNotNone(store.get("job-new"))
            self.assertTrue(any("已选择任务: job-b" in msg for msg in display.successes))

    def test_resolve_retry_watch_job_id_refreshes_expired_cookie_with_saved_login(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchRefreshAPI()
            save_cookie("session=expired-cookie", workspace_id="ws-1")
            save_login_credentials("login-user", "login-pass")

            job_id = cli._resolve_retry_watch_job_id(display, api, "qz_train_narbd_sft2", "ws-1")

            self.assertEqual(job_id, "job-old")
            self.assertEqual(api.login_calls, [("login-user", "login-pass")])
            self.assertEqual(get_cookie()["cookie"], "session=refreshed-cookie")
            self.assertTrue(any("Cookie 已自动刷新" in msg for msg in display.successes))

    def test_resolve_retry_watch_job_id_reports_missing_saved_login_credentials(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeRetryWatchRefreshAPI()
            save_cookie("session=expired-cookie", workspace_id="ws-1")

            with self.assertRaisesRegex(ValueError, "未保存 login 凭证"):
                cli._resolve_retry_watch_job_id(display, api, "qz_train_narbd_sft2", "ws-1")


if __name__ == "__main__":
    unittest.main()

import io
import json
import os
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from qzcli import cli
from qzcli.config import save_resources
from qzcli.store import JobStore
from tests.support import temporary_config_state
from tests.test_cli_proxy import FakeDisplay


class FakeCreateAPI:
    def __init__(self, create_result=None, specs_result=None):
        self.create_result = create_result if create_result is not None else {}
        self.specs_result = specs_result if specs_result is not None else []
        self.created_payload = None
        self.list_specs_group_id = None

    def create_job(self, payload):
        self.created_payload = payload
        return self.create_result

    def list_specs(self, group_id):
        self.list_specs_group_id = group_id
        return self.specs_result


class CLICreateSpecsTests(unittest.TestCase):
    def _write_json_file(self, path: Path, payload):
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_cmd_create_success_tracks_job(self):
        with temporary_config_state() as base, patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeCreateAPI(create_result={"job_id": "job-123"})
            store = JobStore(store_file=base / "jobs.json")
            payload = {
                "name": "demo-job",
                "logic_compute_group_id": "lcg-1",
                "project_id": "project-1",
                "framework": "pytorch",
                "command": "python train.py",
                "task_priority": 4,
                "workspace_id": "ws-1",
                "framework_config": [
                    {
                        "image": "repo/image:latest",
                        "image_type": "SOURCE_OFFICIAL",
                        "instance_count": 1,
                        "shm_gi": 0,
                        "spec_id": "spec-1",
                    }
                ],
            }
            config_file = base / "job.json"
            self._write_json_file(config_file, payload)

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("qzcli.cli.get_store", return_value=store):
                result = cli.cmd_create(Namespace(file=str(config_file), json=False))

            self.assertEqual(result, 0)
            self.assertEqual(api.created_payload["name"], "demo-job")
            self.assertIsNotNone(store.get("job-123"))
            self.assertEqual(store.get("job-123").name, "demo-job")
            self.assertTrue(any("已自动追踪新任务" in msg for msg in display.successes))

    def test_cmd_create_rejects_invalid_json(self):
        with temporary_config_state() as base:
            display = FakeDisplay()
            config_file = base / "job.json"
            config_file.write_text("{bad json", encoding="utf-8")

            with patch("qzcli.cli.get_display", return_value=display):
                result = cli.cmd_create(Namespace(file=str(config_file), json=False))

            self.assertEqual(result, 1)
            self.assertTrue(any("JSON 解析失败" in msg for msg in display.errors))

    def test_cmd_create_rejects_missing_required_fields(self):
        with temporary_config_state() as base:
            display = FakeDisplay()
            config_file = base / "job.json"
            self._write_json_file(config_file, {"name": "demo"})

            with patch("qzcli.cli.get_display", return_value=display):
                result = cli.cmd_create(Namespace(file=str(config_file), json=False))

            self.assertEqual(result, 1)
            self.assertTrue(any("缺少必填字段" in msg for msg in display.errors))

    def test_cmd_create_succeeds_without_job_id_but_warns(self):
        with temporary_config_state() as base:
            display = FakeDisplay()
            api = FakeCreateAPI(create_result={"message": "ok"})
            payload = {
                "name": "demo-job",
                "logic_compute_group_id": "lcg-1",
                "project_id": "project-1",
                "framework": "pytorch",
                "command": "python train.py",
                "task_priority": 4,
                "workspace_id": "ws-1",
                "framework_config": [
                    {
                        "image": "repo/image:latest",
                        "image_type": "SOURCE_OFFICIAL",
                        "instance_count": 1,
                        "shm_gi": 0,
                        "spec_id": "spec-1",
                    }
                ],
            }
            config_file = base / "job.json"
            self._write_json_file(config_file, payload)

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api):
                result = cli.cmd_create(Namespace(file=str(config_file), json=False))

            self.assertEqual(result, 0)
            self.assertTrue(any("未能自动追踪" in msg for msg in display.warnings))

    def test_cmd_specs_resolves_workspace_and_group_names(self):
        with temporary_config_state():
            display = FakeDisplay()
            api = FakeCreateAPI(
                specs_result=[
                    {
                        "id": "spec-1",
                        "gpu_count": 8,
                        "cpu_count": 96,
                        "memory_size_gib": 480,
                        "gpu_info": {"gpu_product_simple": "H200"},
                    }
                ]
            )
            save_resources(
                "ws-1",
                {
                    "projects": [],
                    "compute_groups": [{"id": "lcg-1", "name": "H200 Group", "gpu_type": "H200"}],
                    "specs": [],
                },
                name="CI Team",
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api):
                result = cli.cmd_specs(Namespace(workspace="CI", group="H200", json=False))

            self.assertEqual(result, 0)
            self.assertEqual(api.list_specs_group_id, "lcg-1")
            self.assertTrue(any("规格列表" in line for line in display.lines))
            self.assertTrue(any("spec-1" in line for line in display.lines))

    def test_cmd_specs_reports_missing_cache(self):
        with temporary_config_state():
            display = FakeDisplay()

            with patch("qzcli.cli.get_display", return_value=display):
                result = cli.cmd_specs(Namespace(workspace="CI", group="H200", json=False))

            self.assertEqual(result, 1)
            self.assertTrue(any("请先运行 qzcli res -u" in msg for msg in display.errors))

    def test_cmd_specs_json_outputs_raw_response(self):
        with temporary_config_state():
            display = FakeDisplay()
            api = FakeCreateAPI(
                specs_result=[
                    {
                        "id": "spec-1",
                        "gpu_count": 8,
                        "cpu_count": 96,
                        "memory_size_gib": 480,
                    }
                ]
            )
            save_resources(
                "ws-1",
                {
                    "projects": [],
                    "compute_groups": [{"id": "lcg-1", "name": "H200 Group", "gpu_type": "H200"}],
                    "specs": [],
                },
                name="CI Team",
            )

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    result = cli.cmd_specs(Namespace(workspace="CI", group="H200", json=True))

            self.assertEqual(result, 0)
            self.assertIn('"id": "spec-1"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

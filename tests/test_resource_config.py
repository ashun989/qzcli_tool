import unittest

from qzcli.config import (
    find_resource_by_name,
    find_workspace_by_name,
    get_workspace_resources,
    list_cached_workspaces,
    save_resources,
    set_workspace_name,
    update_workspace_compute_groups,
    update_workspace_projects,
)
from tests.support import temporary_config_state


class ResourceConfigTests(unittest.TestCase):
    def test_save_resources_and_lookup_helpers(self):
        with temporary_config_state():
            save_resources(
                "ws-1",
                {
                    "projects": [{"id": "project-1", "name": "Project Alpha"}],
                    "compute_groups": [{"id": "lcg-1", "name": "H200 Main", "gpu_type": "H200"}],
                    "specs": [{"id": "spec-1", "gpu_count": 8}],
                },
                name="CI Team",
            )

            ws = get_workspace_resources("ws-1")
            self.assertIsNotNone(ws)
            self.assertEqual(ws["name"], "CI Team")
            self.assertEqual(find_workspace_by_name("CI Team"), "ws-1")
            self.assertEqual(find_workspace_by_name("ci"), "ws-1")
            self.assertEqual(find_resource_by_name("ws-1", "compute_groups", "H200"), ws["compute_groups"]["lcg-1"])

            cached = list_cached_workspaces()
            self.assertEqual(len(cached), 1)
            self.assertEqual(cached[0]["project_count"], 1)
            self.assertEqual(cached[0]["compute_group_count"], 1)
            self.assertEqual(cached[0]["spec_count"], 1)

    def test_update_workspace_projects_and_compute_groups_are_incremental(self):
        with temporary_config_state():
            first_projects = update_workspace_projects(
                "ws-2",
                [{"id": "project-1", "name": "Project One"}],
                name="Workspace Two",
            )
            second_projects = update_workspace_projects(
                "ws-2",
                [
                    {"id": "project-1", "name": "Project One Updated"},
                    {"id": "project-2", "name": "Project Two"},
                ],
            )
            first_groups = update_workspace_compute_groups(
                "ws-2",
                [{"id": "lcg-1", "name": "Cluster A", "gpu_type": "A100"}],
            )
            second_groups = update_workspace_compute_groups(
                "ws-2",
                [
                    {"id": "lcg-1", "name": "Cluster A Updated", "gpu_type": "A100"},
                    {"id": "lcg-2", "name": "Cluster B", "gpu_type": "H200"},
                ],
            )

            ws = get_workspace_resources("ws-2")
            self.assertEqual(first_projects, 1)
            self.assertEqual(second_projects, 1)
            self.assertEqual(first_groups, 1)
            self.assertEqual(second_groups, 1)
            self.assertEqual(ws["projects"]["project-1"]["name"], "Project One Updated")
            self.assertEqual(ws["compute_groups"]["lcg-1"]["name"], "Cluster A Updated")
            self.assertEqual(find_workspace_by_name("Workspace Two"), "ws-2")

    def test_set_workspace_name_creates_empty_workspace_entry(self):
        with temporary_config_state():
            self.assertTrue(set_workspace_name("ws-empty", "Empty Workspace"))

            ws = get_workspace_resources("ws-empty")
            self.assertEqual(ws["name"], "Empty Workspace")
            self.assertEqual(ws["projects"], {})
            self.assertEqual(ws["compute_groups"], {})


if __name__ == "__main__":
    unittest.main()

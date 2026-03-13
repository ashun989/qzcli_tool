import os
import unittest
from argparse import Namespace
from unittest.mock import patch

from qzcli import cli
from qzcli.config import get_cookie, get_login_credentials, init_config, save_login_credentials
from tests.support import temporary_config_state
from tests.test_cli_proxy import FakeDisplay


class FakeLoginAPI:
    def __init__(self, cookie="session=test-cookie"):
        self.cookie = cookie
        self.calls = []

    def login_with_cas(self, username, password):
        self.calls.append((username, password))
        return self.cookie


class CLILoginTests(unittest.TestCase):
    def test_login_uses_saved_login_credentials_without_prompting(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_LOGIN_USERNAME", None)
            os.environ.pop("QZCLI_LOGIN_PASSWORD", None)
            save_login_credentials("user-from-config", "pass-from-config")
            display = FakeDisplay()
            api = FakeLoginAPI()

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("builtins.input") as mock_input, \
                 patch("getpass.getpass") as mock_getpass:
                result = cli.cmd_login(Namespace(username=None, password=None, workspace="ws-1"))

            self.assertEqual(result, 0)
            self.assertEqual(api.calls, [("user-from-config", "pass-from-config")])
            self.assertFalse(mock_input.called)
            self.assertFalse(mock_getpass.called)
            self.assertEqual(get_cookie()["workspace_id"], "ws-1")
            self.assertTrue(any("已保存的认证信息" in line for line in display.lines))

    def test_login_uses_dedicated_environment_credentials_without_prompting(self):
        with temporary_config_state(), patch.dict(
            os.environ,
            {"QZCLI_LOGIN_USERNAME": "user-from-env", "QZCLI_LOGIN_PASSWORD": "pass-from-env"},
            clear=False,
        ):
            display = FakeDisplay()
            api = FakeLoginAPI()

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("builtins.input") as mock_input, \
                 patch("getpass.getpass") as mock_getpass:
                result = cli.cmd_login(Namespace(username=None, password=None, workspace=None))

            self.assertEqual(result, 0)
            self.assertEqual(api.calls, [("user-from-env", "pass-from-env")])
            self.assertFalse(mock_input.called)
            self.assertFalse(mock_getpass.called)

    def test_login_does_not_reuse_init_credentials(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_USERNAME", None)
            os.environ.pop("QZCLI_PASSWORD", None)
            os.environ.pop("QZCLI_LOGIN_USERNAME", None)
            os.environ.pop("QZCLI_LOGIN_PASSWORD", None)
            init_config("openapi-user", "openapi-pass")
            display = FakeDisplay()
            api = FakeLoginAPI()

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("builtins.input", return_value="typed-user") as mock_input, \
                 patch("getpass.getpass", return_value="typed-pass") as mock_getpass:
                result = cli.cmd_login(Namespace(username=None, password=None, workspace=None))

            self.assertEqual(result, 0)
            self.assertEqual(api.calls, [("typed-user", "typed-pass")])
            self.assertTrue(mock_input.called)
            self.assertTrue(mock_getpass.called)

    def test_login_saves_explicit_credentials_for_future_reuse(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            api = FakeLoginAPI()

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api):
                result = cli.cmd_login(Namespace(username="save-user", password="save-pass", workspace=None))

            self.assertEqual(result, 0)
            self.assertEqual(get_login_credentials(), ("save-user", "save-pass"))

    def test_login_prompts_when_no_saved_credentials_exist(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_USERNAME", None)
            os.environ.pop("QZCLI_PASSWORD", None)
            os.environ.pop("QZCLI_LOGIN_USERNAME", None)
            os.environ.pop("QZCLI_LOGIN_PASSWORD", None)
            display = FakeDisplay()
            api = FakeLoginAPI()

            with patch("qzcli.cli.get_display", return_value=display), \
                 patch("qzcli.cli.get_api", return_value=api), \
                 patch("builtins.input", return_value="typed-user") as mock_input, \
                 patch("getpass.getpass", return_value="typed-pass") as mock_getpass:
                result = cli.cmd_login(Namespace(username=None, password=None, workspace=None))

            self.assertEqual(result, 0)
            self.assertEqual(api.calls, [("typed-user", "typed-pass")])
            self.assertTrue(mock_input.called)
            self.assertTrue(mock_getpass.called)


if __name__ == "__main__":
    unittest.main()

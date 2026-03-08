import os
import unittest
from argparse import Namespace
from unittest.mock import patch

from qzcli import cli
from qzcli.config import get_proxy_url, save_proxy_url
from tests.support import temporary_config_state


class FakeDisplay:
    def __init__(self):
        self.lines = []
        self.errors = []
        self.successes = []
        self.warnings = []

    def print(self, message, *args, **kwargs):
        self.lines.append(str(message))

    def print_error(self, message):
        self.errors.append(str(message))

    def print_success(self, message):
        self.successes.append(str(message))

    def print_warning(self, message):
        self.warnings.append(str(message))


class CLIProxyTests(unittest.TestCase):
    def test_requests_proxy_url_uses_socks5h_for_socks5(self):
        self.assertEqual(
            cli._requests_proxy_url("socks5://127.0.0.1:1080"),
            "socks5h://127.0.0.1:1080",
        )

    def test_invalid_proxy_scheme_is_rejected(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            display = FakeDisplay()
            args = Namespace(proxy="http://127.0.0.1:7890", show=False, clear=False, test=False)

            with patch("qzcli.cli.get_display", return_value=display):
                result = cli.cmd_proxy(args)

            self.assertEqual(result, 1)
            self.assertTrue(any("仅支持 https://" in msg for msg in display.errors))

    def test_show_proxy_displays_config_source_and_value(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)
            save_proxy_url("https://proxy.example:8443")
            display = FakeDisplay()
            args = Namespace(proxy=None, show=True, clear=False, test=False)

            with patch("qzcli.cli.get_display", return_value=display):
                result = cli.cmd_proxy(args)

            self.assertEqual(result, 0)
            self.assertTrue(any("配置文件" in line for line in display.lines))
            self.assertTrue(any("https://proxy.example:8443" in line for line in display.lines))

    def test_clear_proxy_resets_saved_value(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)
            save_proxy_url("https://proxy.example:8443")
            display = FakeDisplay()
            args = Namespace(proxy=None, show=False, clear=True, test=False)

            with patch("qzcli.cli.get_display", return_value=display):
                result = cli.cmd_proxy(args)

            self.assertEqual(result, 0)
            self.assertEqual(get_proxy_url(), "")
            self.assertTrue(any("已清除保存的代理配置" in msg for msg in display.successes))


if __name__ == "__main__":
    unittest.main()

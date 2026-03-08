import os
import unittest
from unittest.mock import patch

from qzcli.config import clear_proxy_url, get_proxy_source, get_proxy_url, load_config, save_proxy_url
from tests.support import temporary_config_state


class ProxyConfigTests(unittest.TestCase):
    def test_default_proxy_is_empty(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)

            self.assertEqual(get_proxy_url(), "")
            self.assertIsNone(get_proxy_source())

    def test_proxy_url_is_saved_to_config(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)

            save_proxy_url("https://proxy.example:8443")

            self.assertEqual(load_config()["proxy_url"], "https://proxy.example:8443")
            self.assertEqual(get_proxy_url(), "https://proxy.example:8443")
            self.assertEqual(get_proxy_source(), "config")

    def test_environment_variable_overrides_config(self):
        with temporary_config_state(), patch.dict(
            os.environ,
            {"QZCLI_PROXY_URL": "socks5://127.0.0.1:1080"},
            clear=False,
        ):
            save_proxy_url("https://proxy.example:8443")

            self.assertEqual(get_proxy_url(), "socks5://127.0.0.1:1080")
            self.assertEqual(get_proxy_source(), "env")

    def test_clear_proxy_url_resets_config_value(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)
            save_proxy_url("https://proxy.example:8443")

            clear_proxy_url()

            self.assertEqual(get_proxy_url(), "")
            self.assertIsNone(get_proxy_source())
            self.assertEqual(load_config()["proxy_url"], "")


if __name__ == "__main__":
    unittest.main()

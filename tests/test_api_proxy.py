import os
import unittest
from unittest.mock import patch

import requests

from qzcli.api import QzAPI, QzAPIError
from qzcli.config import save_proxy_url
from tests.support import temporary_config_state


class DummySession:
    def __init__(self):
        self.proxies = {}
        self.headers = {}
        self.cookies = []

    def get(self, *_args, **_kwargs):
        raise requests.RequestException("boom")


class APIProxyTests(unittest.TestCase):
    def test_https_proxy_mapping_is_applied_to_http_and_https(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)
            save_proxy_url("https://proxy.example:8443")

            api = QzAPI(username="user", password="pass")

            self.assertEqual(
                api._get_proxies(),
                {
                    "http": "https://proxy.example:8443",
                    "https": "https://proxy.example:8443",
                },
            )

    def test_socks5_proxy_mapping_is_applied_to_http_and_https(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)
            save_proxy_url("socks5://127.0.0.1:1080")

            api = QzAPI(username="user", password="pass")

            self.assertEqual(
                api._get_proxies(),
                {
                    "http": "socks5h://127.0.0.1:1080",
                    "https": "socks5h://127.0.0.1:1080",
                },
            )

    def test_login_with_cas_session_inherits_proxy(self):
        with temporary_config_state(), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QZCLI_PROXY_URL", None)
            save_proxy_url("socks5://127.0.0.1:1080")
            session = DummySession()
            api = QzAPI(username="user", password="pass")

            with patch("qzcli.api.requests.Session", return_value=session):
                with self.assertRaises(QzAPIError) as ctx:
                    api.login_with_cas("user", "pass")

            self.assertIn("无法连接到启智平台", str(ctx.exception))
            self.assertEqual(
                session.proxies,
                {
                    "http": "socks5h://127.0.0.1:1080",
                    "https": "socks5h://127.0.0.1:1080",
                },
            )


if __name__ == "__main__":
    unittest.main()

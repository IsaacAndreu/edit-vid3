from __future__ import annotations

import unittest

from pipeline.clients.youtube_proxy import (
    ProxyConfig,
    ProxyConfigError,
    new_session_id,
    proxy_host_label,
    scrub_proxy_env,
    with_sticky_session,
)


class StickySessionTests(unittest.TestCase):
    def test_suffix_is_appended_to_username_only(self) -> None:
        url = with_sticky_session("http://user:secret@proxy.example:8000", "abc123")
        self.assertEqual(url, "http://user-time-30-session-abc123:secret@proxy.example:8000")

    def test_percent_encoded_password_and_path_are_preserved(self) -> None:
        url = with_sticky_session("socks5://u:p%40ss%3Aword@host:1080/path", "s1")
        self.assertEqual(url, "socks5://u-time-30-session-s1:p%40ss%3Aword@host:1080/path")

    def test_scheme_less_proxy_defaults_to_http(self) -> None:
        self.assertEqual(with_sticky_session("user:pw@host:1", "s1"), "http://user-time-30-session-s1:pw@host:1")

    def test_proxy_without_credentials_is_unchanged(self) -> None:
        self.assertEqual(with_sticky_session("http://host:8000", "s1"), "http://host:8000")

    def test_suffix_is_not_appended_twice(self) -> None:
        once = with_sticky_session("http://user:pw@host:1", "s1")
        self.assertEqual(with_sticky_session(once, "s1"), once)

    def test_custom_suffix_template(self) -> None:
        url = with_sticky_session("http://user:pw@host:1", "s1", suffix_template="_sess_{session_id}")
        self.assertEqual(url, "http://user_sess_s1:pw@host:1")

    def test_rejects_unsafe_session_ids_and_empty_urls(self) -> None:
        with self.assertRaises(ProxyConfigError):
            with_sticky_session("http://user:pw@host:1", "bad@id")
        with self.assertRaises(ProxyConfigError):
            with_sticky_session("", "abc")

    def test_session_ids_are_random_and_safe(self) -> None:
        first, second = new_session_id(), new_session_id()
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 10)
        self.assertTrue(first.isalnum())


class ProxyConfigTests(unittest.TestCase):
    def test_metadata_falls_back_to_download_proxy(self) -> None:
        config = ProxyConfig.from_values(download="http://u:p@res.example:1", metadata=None)
        self.assertEqual(config.metadata, "http://u:p@res.example:1")
        self.assertTrue(config.shares_exit_ip)
        self.assertEqual(config.for_role("metadata", "s1"), "http://u-time-30-session-s1:p@res.example:1")
        self.assertEqual(config.for_role("download", "s1"), config.for_role("metadata", "s1"))

    def test_separate_proxies_per_role(self) -> None:
        config = ProxyConfig.from_values(download="http://u:p@res.example:1", metadata="http://m:w@dc.example:2")
        self.assertFalse(config.shares_exit_ip)
        self.assertEqual(config.for_role("download", "s1"), "http://u-time-30-session-s1:p@res.example:1")
        self.assertEqual(config.for_role("metadata", "s1"), "http://m-time-30-session-s1:w@dc.example:2")

    def test_unconfigured_roles_are_direct(self) -> None:
        config = ProxyConfig.from_values(download="  ", metadata="")
        self.assertIsNone(config.for_role("download", "s1"))
        self.assertIsNone(config.for_role("metadata", "s1"))
        self.assertEqual(config.describe(), "metadatos=directo, descargas=directo")

    def test_describe_never_leaks_credentials(self) -> None:
        config = ProxyConfig.from_values(download="http://user:topsecret@res.example:1", metadata=None)
        description = config.describe()
        self.assertNotIn("topsecret", description)
        self.assertNotIn("user", description)
        self.assertIn("res.example:1", description)
        self.assertEqual(proxy_host_label(None), "directo")

    def test_unknown_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ProxyConfig().for_role("other", "s1")


class ScrubEnvTests(unittest.TestCase):
    def test_removes_every_proxy_variable_and_keeps_the_rest(self) -> None:
        env = {
            "PATH": "/usr/bin",
            "HTTP_PROXY": "http://a",
            "https_proxy": "http://b",
            "ALL_PROXY": "socks5://c",
            "NO_PROXY": "localhost",
        }
        scrubbed = scrub_proxy_env(env)
        self.assertEqual(scrubbed, {"PATH": "/usr/bin", "NO_PROXY": "localhost"})
        self.assertEqual(env["HTTP_PROXY"], "http://a", "the original mapping must not be mutated")


if __name__ == "__main__":
    unittest.main()

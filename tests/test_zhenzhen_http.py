import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests as raw_requests


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "comfly_zhenzhen_http_test", PLUGIN_ROOT / "zhenzhen_http.py"
)
zhenzhen_http = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(zhenzhen_http)


class ZhenzhenHttpTests(unittest.TestCase):
    def setUp(self):
        zhenzhen_http.reset_endpoint_cache()

    @staticmethod
    def _response(status_code=401):
        response = Mock()
        response.status_code = status_code
        response.close = Mock()
        return response

    def test_health_check_falls_back_to_cn_and_preserves_legacy_preference(self):
        healthy = self._response()
        with patch.object(
            zhenzhen_http._requests,
            "get",
            side_effect=[raw_requests.ConnectionError("org unavailable"), healthy],
        ) as probe:
            chosen = zhenzhen_http.choose_zhenzhen_base_url(force=True)

        self.assertEqual(chosen, zhenzhen_http.FALLBACK_BASE_URL)
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(
            probe.call_args_list[0].args[0],
            f"{zhenzhen_http.PRIMARY_BASE_URL}/v1/models",
        )
        self.assertEqual(
            probe.call_args_list[1].args[0],
            f"{zhenzhen_http.FALLBACK_BASE_URL}/v1/models",
        )

    def test_selected_endpoint_rewrites_path_query_and_fragment(self):
        with patch.object(
            zhenzhen_http,
            "choose_zhenzhen_base_url",
            return_value=zhenzhen_http.FALLBACK_BASE_URL,
        ):
            rewritten = zhenzhen_http.rewrite_zhenzhen_url(
                "https://ai.t8star.org/v1/images/tasks/abc?async=true#result"
            )

        self.assertEqual(
            rewritten,
            "https://ai.t8star.cn/v1/images/tasks/abc?async=true#result",
        )

    def test_non_zhenzhen_hosts_are_never_probed_or_rewritten(self):
        response = self._response(200)
        with patch.object(
            zhenzhen_http, "choose_zhenzhen_base_url"
        ) as choose, patch.object(
            zhenzhen_http._requests, "request", return_value=response
        ) as request:
            actual = zhenzhen_http.post(
                "https://api.seedance.nz/v1/images/generations", json={"model": "x"}
            )

        self.assertIs(actual, response)
        choose.assert_not_called()
        self.assertEqual(
            request.call_args.args[:2],
            ("POST", "https://api.seedance.nz/v1/images/generations"),
        )

    def test_http_error_response_does_not_trigger_domain_retry(self):
        response = self._response(500)
        with patch.object(
            zhenzhen_http,
            "choose_zhenzhen_base_url",
            return_value=zhenzhen_http.PRIMARY_BASE_URL,
        ), patch.object(
            zhenzhen_http._requests, "request", return_value=response
        ) as request:
            actual = zhenzhen_http.post(
                f"{zhenzhen_http.PRIMARY_BASE_URL}/v1/images/generations",
                json={"model": "x"},
            )

        self.assertIs(actual, response)
        request.assert_called_once()

    def test_post_read_connection_error_is_not_retried(self):
        with patch.object(
            zhenzhen_http,
            "choose_zhenzhen_base_url",
            return_value=zhenzhen_http.PRIMARY_BASE_URL,
        ), patch.object(
            zhenzhen_http._requests,
            "request",
            side_effect=raw_requests.ConnectionError("response stream reset"),
        ) as request:
            with self.assertRaises(raw_requests.ConnectionError):
                zhenzhen_http.post(
                    f"{zhenzhen_http.PRIMARY_BASE_URL}/v1/images/generations",
                    json={"model": "x"},
                )

        request.assert_called_once()

    def test_tls_handshake_reset_retries_post_once_via_cn(self):
        response = self._response(200)
        calls = []

        def do_handshake():
            raise raw_requests.ConnectionError("TLS handshake reset")

        def send(method, url, **kwargs):
            calls.append((method, url))
            if len(calls) == 1:
                do_handshake()
            return response

        with patch.object(
            zhenzhen_http,
            "choose_zhenzhen_base_url",
            return_value=zhenzhen_http.PRIMARY_BASE_URL,
        ), patch.object(zhenzhen_http._requests, "request", side_effect=send):
            actual = zhenzhen_http.post(
                f"{zhenzhen_http.PRIMARY_BASE_URL}/v1/images/generations",
                json={"model": "x"},
            )

        self.assertIs(actual, response)
        self.assertEqual(
            calls,
            [
                ("POST", "https://ai.t8star.org/v1/images/generations"),
                ("POST", "https://ai.t8star.cn/v1/images/generations"),
            ],
        )

    def test_wrapped_tls_handshake_trace_is_detected(self):
        response = self._response(200)
        calls = []

        def do_handshake():
            raise ConnectionResetError(10054, "TLS handshake reset")

        def wrapped_handshake_error():
            try:
                do_handshake()
            except ConnectionResetError as root_error:
                try:
                    raise RuntimeError("urllib3 protocol error") from root_error
                except RuntimeError as protocol_error:
                    raise raw_requests.ConnectionError(
                        "requests connection error"
                    ) from protocol_error

        def send(method, url, **kwargs):
            calls.append((method, url))
            if len(calls) == 1:
                wrapped_handshake_error()
            return response

        with patch.object(
            zhenzhen_http,
            "choose_zhenzhen_base_url",
            return_value=zhenzhen_http.PRIMARY_BASE_URL,
        ), patch.object(zhenzhen_http._requests, "request", side_effect=send):
            actual = zhenzhen_http.post(
                f"{zhenzhen_http.PRIMARY_BASE_URL}/v1/images/generations",
                json={"model": "x"},
            )

        self.assertIs(actual, response)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1][1].startswith(zhenzhen_http.FALLBACK_BASE_URL))

    def test_polling_get_retries_once_after_connection_error(self):
        response = self._response(200)
        with patch.object(
            zhenzhen_http,
            "choose_zhenzhen_base_url",
            return_value=zhenzhen_http.PRIMARY_BASE_URL,
        ), patch.object(
            zhenzhen_http._requests,
            "request",
            side_effect=[raw_requests.ConnectionError("reset"), response],
        ) as request:
            actual = zhenzhen_http.get(
                f"{zhenzhen_http.PRIMARY_BASE_URL}/v1/images/tasks/task-1"
            )

        self.assertIs(actual, response)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            request.call_args_list[1].args[1],
            "https://ai.t8star.cn/v1/images/tasks/task-1",
        )

    def test_session_uses_same_rewrite_policy(self):
        response = self._response(200)
        with patch.object(
            zhenzhen_http,
            "choose_zhenzhen_base_url",
            return_value=zhenzhen_http.FALLBACK_BASE_URL,
        ), patch.object(
            zhenzhen_http._requests.Session,
            "request",
            return_value=response,
        ) as request:
            actual = zhenzhen_http.Session().get(
                f"{zhenzhen_http.PRIMARY_BASE_URL}/v1/models"
            )

        self.assertIs(actual, response)
        self.assertEqual(
            request.call_args.args[:2],
            ("GET", "https://ai.t8star.cn/v1/models"),
        )


if __name__ == "__main__":
    unittest.main()

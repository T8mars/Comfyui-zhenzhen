import unittest
from unittest import mock

import requests

from t8star_http import (
    T8STAR_RETRY_DELAYS,
    create_alternating_route_session,
    create_t8star_session,
    safe_chat_post,
    safe_get_content,
    safe_upload_post,
)


class FakeResponse:
    def __init__(self, status_code=200, chunks=(), content=b""):
        self.status_code = status_code
        self.headers = {}
        self.chunks = chunks
        self._content = content
        self.closed = False

    @property
    def content(self):
        if isinstance(self._content, Exception):
            raise self._content
        return self._content

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )

    def iter_content(self, chunk_size):
        del chunk_size
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class FakeSession:
    outcomes = []
    calls = []

    def __init__(self):
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def request(self, method, url, **kwargs):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "trust_env": self.trust_env,
                "kwargs": kwargs,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


class T8StarSessionTests(unittest.TestCase):
    def setUp(self):
        FakeSession.outcomes = []
        FakeSession.calls = []
        self.session_patch = mock.patch.object(requests, "Session", FakeSession)
        self.sleep_patch = mock.patch("time.sleep")
        self.sleep = self.sleep_patch.start()
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        self.sleep_patch.stop()

    def test_first_direct_attempt_can_succeed(self):
        FakeSession.outcomes = [FakeResponse(200)]

        response = create_t8star_session().post(
            "https://ai.t8star.org/v1/images/edits?async=true",
            timeout=60,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls], [False]
        )
        self.sleep.assert_not_called()

    def test_caller_owned_retry_count_maps_one_to_one_to_routes(self):
        sessions = [
            create_alternating_route_session(attempt)
            for attempt in range(5)
        ]

        self.assertEqual(
            [session.trust_env for session in sessions],
            [False, True, False, True, False],
        )

    def test_network_failure_falls_back_to_proxy(self):
        FakeSession.outcomes = [
            requests.exceptions.SSLError("direct failed"),
            FakeResponse(200),
        ]

        create_t8star_session().get("https://ai.t8star.org/v1/tasks/1")

        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls], [False, True]
        )
        self.sleep.assert_called_once_with(T8STAR_RETRY_DELAYS[0])

    def test_get_failures_use_direct_proxy_direct_proxy_then_raise(self):
        failures = [
            requests.exceptions.ConnectTimeout("direct 1"),
            requests.exceptions.ProxyError("proxy 1"),
            requests.exceptions.ReadTimeout("direct 2"),
            requests.exceptions.SSLError("proxy 2"),
        ]
        FakeSession.outcomes = list(failures)

        with mock.patch("builtins.print") as print_mock:
            with self.assertRaises(requests.exceptions.SSLError) as raised:
                create_t8star_session().get(
                    "https://ai.t8star.org/v1/images/edits?signature=secret"
                )

        self.assertIs(raised.exception, failures[-1])
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls],
            [False, True, False, True],
        )
        self.assertEqual(self.sleep.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in self.sleep.call_args_list],
            list(T8STAR_RETRY_DELAYS),
        )
        logged = " ".join(
            " ".join(str(argument) for argument in call.args)
            for call in print_mock.call_args_list
        )
        self.assertNotIn("signature=secret", logged)

    def test_retryable_http_status_uses_next_route(self):
        FakeSession.outcomes = [FakeResponse(503), FakeResponse(200)]

        response = create_t8star_session().get(
            "https://ai.t8star.org/v1/tasks/1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls], [False, True]
        )

    def test_final_http_status_wins_over_an_earlier_transport_error(self):
        FakeSession.outcomes = [
            requests.exceptions.SSLError("direct failed"),
            FakeResponse(503),
            FakeResponse(503),
            FakeResponse(503),
        ]

        response = create_t8star_session().get(
            "https://ai.t8star.org/v1/tasks/1"
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls],
            [False, True, False, True],
        )

    def test_business_4xx_is_not_retried(self):
        FakeSession.outcomes = [FakeResponse(401)]

        response = create_t8star_session().post(
            "https://ai.t8star.org/v1/images/generations"
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(len(FakeSession.calls), 1)

    def test_paid_post_transport_failure_is_not_retried(self):
        failure = requests.exceptions.ConnectTimeout("ambiguous submit")
        FakeSession.outcomes = [failure]

        with self.assertRaises(requests.exceptions.ConnectTimeout):
            create_t8star_session().post(
                "https://ai.t8star.org/v1/images/generations"
            )

        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls], [False]
        )
        self.sleep.assert_not_called()

    def test_http_500_is_not_retried(self):
        FakeSession.outcomes = [FakeResponse(500)]

        response = create_t8star_session().get(
            "https://ai.t8star.org/v1/tasks/1"
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(FakeSession.calls), 1)

    def test_tls_eof_while_reading_body_restarts_on_next_route(self):
        FakeSession.outcomes = [
            FakeResponse(
                200,
                (
                    b"partial",
                    requests.exceptions.SSLError("TLS EOF"),
                ),
            ),
            FakeResponse(200, (b"complete", b"-body")),
        ]

        body = safe_get_content("https://cdn.example.com/result.bin")

        self.assertEqual(body, b"complete-body")
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls],
            [False, True],
        )

    def test_explicit_safe_upload_retries_ssl_eof(self):
        FakeSession.outcomes = [
            requests.exceptions.SSLError("TLS EOF"),
            FakeResponse(200),
        ]

        response = safe_upload_post(
            "https://ai.t8star.org/v1/files",
            files={"file": ("x.bin", b"data")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls],
            [False, True],
        )

    def test_explicit_chat_retries_transport_and_temporary_status(self):
        temporary = FakeResponse(503)
        FakeSession.outcomes = [
            requests.exceptions.SSLError("TLS EOF"),
            temporary,
            FakeResponse(200),
        ]

        response = safe_chat_post(
            "https://ai.t8star.org/v1/chat/completions",
            json={"model": "test"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls],
            [False, True, False],
        )
        self.assertEqual(
            [call.args[0] for call in self.sleep.call_args_list], [1, 5]
        )
        self.assertTrue(temporary.closed)

    def test_streaming_chat_retries_tls_eof_while_buffering(self):
        interrupted = FakeResponse(
            200, content=requests.exceptions.SSLError("TLS EOF")
        )
        success = FakeResponse(200, content=b"data: complete\n\n")
        FakeSession.outcomes = [interrupted, success]

        response = safe_chat_post(
            "https://ai.t8star.org/v1/chat/completions", stream=True
        )

        self.assertIs(response, success)
        self.assertTrue(interrupted.closed)
        self.assertEqual(
            [call["trust_env"] for call in FakeSession.calls], [False, True]
        )
        self.sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()

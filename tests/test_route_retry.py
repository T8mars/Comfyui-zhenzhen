import ast
import os
import unittest
from pathlib import Path
from unittest import mock

import midjourney_low_price_nodes as midjourney
import seedance_low_price_nodes as seedance


class FakeResponse:
    def __init__(self, status_code=200, payload=None, chunks=()):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = "{}"
        self.headers = {}
        self.chunks = chunks
        self.closed = False

    def json(self):
        return self._payload

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise seedance.requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )

    def iter_content(self, chunk_size):
        del chunk_size
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class RouteRetryTests(unittest.TestCase):
    def test_safe_request_runs_all_routes_with_fixed_waits(self):
        outcomes = iter([
            seedance.requests.ConnectionError("direct"),
            FakeResponse(503),
            FakeResponse(502),
            FakeResponse(200),
        ])
        routes = []
        sleeps = []

        class Session:
            def get(self, _url, **_kwargs):
                outcome = next(outcomes)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        response = seedance._request_with_retry(
            "get",
            "https://api.seedance.nz/v1/tasks/1",
            sleep=sleeps.append,
            session_factory=lambda attempt: routes.append(attempt) or Session(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(routes, [0, 1, 2, 3])
        self.assertEqual(sleeps, [1, 5, 10])

    def test_http_500_is_not_retried(self):
        routes = []

        class Session:
            def get(self, _url, **_kwargs):
                return FakeResponse(500)

        response = seedance._request_with_retry(
            "get",
            "https://api.seedance.nz/v1/tasks/1",
            session_factory=lambda attempt: routes.append(attempt) or Session(),
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(routes, [0])

    def test_stream_tls_eof_is_retried_inside_consumer_boundary(self):
        outcomes = iter(
            [
                FakeResponse(
                    chunks=(
                        b"partial",
                        seedance.requests.exceptions.SSLError("TLS EOF"),
                    )
                ),
                FakeResponse(chunks=(b"complete", b"-body")),
            ]
        )
        routes = []
        sleeps = []

        class Session:
            def get(self, _url, **_kwargs):
                return next(outcomes)

        def consume(response):
            return b"".join(response.iter_content(chunk_size=64))

        body = seedance._request_with_retry(
            "get",
            "https://cdn.example.test/result.bin",
            sleep=sleeps.append,
            session_factory=lambda attempt: routes.append(attempt) or Session(),
            _consume=consume,
            stream=True,
        )

        self.assertEqual(body, b"complete-body")
        self.assertEqual(routes, [0, 1])
        self.assertEqual(sleeps, [1])

    def test_paid_submit_is_sent_once(self):
        response = FakeResponse(200, {"id": "task-1"})
        with mock.patch.object(seedance, "_post_once", return_value=response) as post:
            task_id, _ = seedance.submit_task(
                {"model": "seedance"},
                {"base_url": "https://api.seedance.nz", "api_key": "sk-test"},
            )

        self.assertEqual(task_id, "task-1")
        post.assert_called_once()

    def test_credentials_do_not_fall_back_to_environment(self):
        with mock.patch.dict(
            os.environ,
            {"SEEDANCE_API_KEY": "sk-environment-secret"},
            clear=False,
        ):
            with self.assertRaises(seedance.SeedanceLowPriceError):
                seedance.resolve_config(None)

    def test_seedance_retry_sessions_follow_fixed_route_order(self):
        with mock.patch.object(
            seedance,
            "_build_session",
            side_effect=lambda trust_env=True: trust_env,
        ) as build_session:
            routes = [seedance._get_session(attempt) for attempt in range(4)]

        self.assertEqual(routes, [False, True, False, True])
        self.assertEqual(
            [call.kwargs["trust_env"] for call in build_session.call_args_list],
            [False, True, False, True],
        )

    def test_midjourney_retry_sessions_follow_fixed_route_order(self):
        with mock.patch.object(
            midjourney,
            "_build_session",
            side_effect=lambda trust_env=True: trust_env,
        ) as build_session:
            routes = [
                midjourney._midjourney_session(attempt)
                for attempt in range(4)
            ]

        self.assertEqual(routes, [False, True, False, True])
        self.assertEqual(
            [call.kwargs["trust_env"] for call in build_session.call_args_list],
            [False, True, False, True],
        )

    def test_nodes_with_retry_widgets_use_caller_owned_route_attempts(self):
        source_path = Path(__file__).resolve().parents[1] / "Comfly.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        target_classes = {
            "Comfly_kling_multi_image2video",
            "Comfly_gpt_image_1_edit",
            "Comfly_gpt_image_2_official",
            "Comfly_gpt_image_2_official_ratio",
            "Comfly_gpt_image_2_official_ratio_stable",
        }

        checked = set()
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name not in target_classes:
                continue
            retry_method = next(
                child
                for child in node.body
                if isinstance(child, ast.FunctionDef)
                and child.name == "make_request_with_retry"
            )
            calls = [
                child
                for child in ast.walk(retry_method)
                if isinstance(child, ast.Call)
            ]
            self.assertTrue(
                any(
                    isinstance(call.func, ast.Name)
                    and call.func.id == "create_alternating_route_session"
                    for call in calls
                ),
                node.name,
            )
            self.assertFalse(
                any(
                    isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Attribute)
                    and isinstance(call.func.value.value, ast.Name)
                    and call.func.value.value.id == "self"
                    and call.func.value.attr == "session"
                    for call in calls
                ),
                node.name,
            )
            checked.add(node.name)

        self.assertEqual(checked, target_classes)

    def test_submit_retry_widget_is_decoupled_from_result_downloads(self):
        source_path = Path(__file__).resolve().parents[1] / "Comfly.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        official_classes = {
            "Comfly_gpt_image_2_official",
            "Comfly_gpt_image_2_official_ratio",
            "Comfly_gpt_image_2_official_ratio_stable",
        }

        checked = set()
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name not in official_classes:
                continue
            methods = {
                child.name: child
                for child in node.body
                if isinstance(child, ast.FunctionDef)
            }
            async_method = methods["_async_official"]
            async_calls = [
                child
                for child in ast.walk(async_method)
                if isinstance(child, ast.Call)
            ]
            self.assertTrue(
                any(
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr == "make_request_with_retry"
                    for call in async_calls
                ),
                node.name,
            )

            for method_name in ("_decode_b64_url_one", "_items_to_tensors"):
                method = methods[method_name]
                self.assertNotIn(
                    "max_retries",
                    [argument.arg for argument in method.args.args],
                    f"{node.name}.{method_name}",
                )
                self.assertTrue(
                    any(
                        isinstance(child, ast.Name)
                        and child.id == "RESULT_DOWNLOAD_ATTEMPTS"
                        for child in ast.walk(method)
                    ),
                    f"{node.name}.{method_name}",
                )
            checked.add(node.name)

        self.assertEqual(checked, official_classes)


if __name__ == "__main__":
    unittest.main()

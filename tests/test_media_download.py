import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import media_download


def _png_bytes(color=(20, 40, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _rgba_png_bytes():
    buffer = io.BytesIO()
    image = Image.new("RGBA", (3, 2), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 0))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class MediaDownloadTests(unittest.TestCase):
    def test_tencent_cos_fallback_preserves_signed_path_and_query(self):
        source = (
            "https://bucket-1250000000.cos.ap-hongkong.myqcloud.com/"
            "output/video.mp4?q-signature=private-marker#fragment"
        )
        self.assertEqual(
            media_download.tencent_cos_media_url_fallback(source),
            (
                "https://bucket-1250000000.cos.ap-hongkong.tencentcos.cn/"
                "output/video.mp4?q-signature=private-marker#fragment"
            ),
        )
        self.assertIsNone(
            media_download.tencent_cos_media_url_fallback(
                "https://cdn.example.test/output/video.mp4"
            )
        )

    def test_route_error_tries_official_tencent_cos_domain(self):
        source = (
            "https://bucket-1250000000.cos.ap-hongkong.myqcloud.com/"
            "output/video.mp4?q-signature=private-marker"
        )
        fallback = media_download.tencent_cos_media_url_fallback(source)
        expected = object()
        calls = []

        def getter(url, **_kwargs):
            calls.append(url)
            if url == source:
                raise media_download.requests.exceptions.SSLError("unexpected EOF")
            return expected

        response = media_download.get_media_response(
            source,
            request_get=getter,
            direct_get=None,
        )
        self.assertIs(response, expected)
        self.assertEqual(calls, [source, fallback])

    def test_connection_failure_retries_without_environment_proxy(self):
        primary_calls = []
        direct_calls = []

        def primary_get(url, **kwargs):
            primary_calls.append((url, kwargs))
            raise requests.exceptions.ConnectionError("broken environment proxy")

        def direct_get(url, **kwargs):
            direct_calls.append((url, kwargs))
            return _FakeResponse(content=_png_bytes())

        image = media_download.download_image_with_retry(
            "https://cdn.test/result.png",
            request_get=primary_get,
            direct_get=direct_get,
        )

        self.assertEqual(image.size, (8, 6))
        self.assertEqual(len(primary_calls), 1)
        self.assertEqual(len(direct_calls), 1)
        self.assertEqual(direct_calls[0][1]["timeout"], (120.0, 300.0))

    def test_http_error_does_not_switch_download_route(self):
        direct_calls = []

        def primary_get(_url, **_kwargs):
            response = _FakeResponse(status_code=403)
            response.raise_for_status()

        with self.assertRaises(RuntimeError):
            media_download.download_image_with_retry(
                "https://cdn.test/result.png",
                max_attempts=1,
                request_get=primary_get,
                direct_get=lambda *args, **kwargs: direct_calls.append(
                    (args, kwargs)
                ),
            )

        self.assertEqual(direct_calls, [])

    def test_alpha_download_preserves_transparency(self):
        image = media_download.download_image_with_alpha_retry(
            "https://example.invalid/layer",
            request_get=lambda _url, **_kwargs: _FakeResponse(
                content=_rgba_png_bytes()
            ),
        )

        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (3, 2))
        self.assertEqual(image.getpixel((1, 0))[3], 0)

    @patch.object(media_download.time, "sleep")
    def test_retries_when_result_url_is_not_decodable_yet(self, sleep):
        responses = iter(
            [
                _FakeResponse(content=b"result is still being prepared"),
                _FakeResponse(content=_png_bytes()),
            ]
        )
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return next(responses)

        image = media_download.download_image_with_retry(
            "https://example.invalid/result", request_get=fake_get
        )

        self.assertEqual(image.size, (8, 6))
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1]["timeout"], (120.0, 300.0))
        self.assertIn("image/", calls[0][1]["headers"]["Accept"])
        sleep.assert_called_once_with(1)

    def test_download_timeout_has_120_second_floor_without_reducing_longer_values(self):
        self.assertEqual(media_download.media_download_seconds(15), 120.0)
        self.assertEqual(media_download.media_download_seconds(120), 120.0)
        self.assertEqual(media_download.media_download_seconds(300), 300.0)
        self.assertEqual(media_download.media_download_seconds(1200), 1200.0)
        self.assertEqual(media_download.media_download_timeout(15), (120.0, 120.0))
        self.assertEqual(media_download.media_download_timeout(45), (120.0, 120.0))
        self.assertEqual(media_download.media_download_timeout(60), (120.0, 120.0))
        self.assertEqual(media_download.media_download_timeout(100), (120.0, 120.0))
        self.assertEqual(media_download.media_download_timeout(120), (120.0, 120.0))
        self.assertEqual(media_download.media_download_timeout(180), (120.0, 180.0))
        self.assertEqual(media_download.media_download_timeout(300), (120.0, 300.0))
        self.assertEqual(media_download.media_download_timeout(1200), (120.0, 1200.0))

    @patch.object(media_download.time, "sleep")
    def test_retries_transient_http_failure(self, sleep):
        responses = iter(
            [
                _FakeResponse(status_code=503),
                _FakeResponse(content=_png_bytes((80, 40, 20))),
            ]
        )

        image = media_download.download_image_with_retry(
            "https://example.invalid/result",
            request_get=lambda _url, **_kwargs: next(responses),
        )

        self.assertEqual(image.getpixel((0, 0)), (80, 40, 20))
        sleep.assert_called_once_with(1)

    @patch.object(media_download.time, "sleep")
    def test_terminal_error_does_not_leak_signed_url(self, sleep):
        signed_url = "https://example.invalid/result?token=secret-value"

        def fail(_url, **_kwargs):
            raise requests.exceptions.ConnectionError(
                "connection failed for " + signed_url
            )

        with self.assertRaises(RuntimeError) as context:
            media_download.download_image_with_retry(
                signed_url, max_attempts=2, request_get=fail
            )

        message = str(context.exception)
        self.assertNotIn("secret-value", message)
        self.assertNotIn("example.invalid", message)
        self.assertIn("ConnectionError", message)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()

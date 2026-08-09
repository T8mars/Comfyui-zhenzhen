import io
import unittest
from unittest.mock import patch

import requests
from PIL import Image

import media_download


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGBA", (2, 1), (255, 0, 0, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, status=200, content=b"", error=None):
        self.status_code = status
        self._content = content
        self.error = error
        self.closed = False

    @property
    def content(self):
        if self.error:
            raise self.error
        return self._content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, route, response):
        self.route = route
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, *_args, **_kwargs):
        return self.response


class MediaDownloadRetryTests(unittest.TestCase):
    def test_tls_eof_uses_all_routes_and_fixed_waits(self):
        responses = [
            FakeResponse(error=requests.exceptions.SSLError("EOF")),
            FakeResponse(error=requests.exceptions.ChunkedEncodingError("EOF")),
            FakeResponse(status=503),
            FakeResponse(content=png_bytes()),
        ]
        routes = []

        def session_for(attempt):
            routes.append(media_download.T8STAR_ROUTE_ATTEMPTS[attempt][0])
            return FakeSession(attempt, responses[attempt])

        with patch.object(media_download, "create_alternating_route_session", side_effect=session_for), patch.object(
            media_download.time, "sleep"
        ) as sleep:
            image = media_download.download_image_with_alpha_retry("https://cdn.test/layer.png")

        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(routes, ["direct", "proxy", "direct", "proxy"])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 5, 10])
        self.assertTrue(all(response.closed for response in responses))

    def test_business_404_is_not_retried(self):
        calls = []

        def session_for(attempt):
            calls.append(attempt)
            return FakeSession(attempt, FakeResponse(status=404))

        with patch.object(media_download, "create_alternating_route_session", side_effect=session_for):
            with self.assertRaises(requests.HTTPError):
                media_download.download_image_with_retry("https://cdn.test/missing.png")

        self.assertEqual(calls, [0])


if __name__ == "__main__":
    unittest.main()

"""Resilient media-result downloads shared by Zhenzhen nodes."""

from __future__ import annotations

import io
import threading
import time
from typing import Any

try:
    from . import zhenzhen_http as requests
except ImportError:  # Support the existing standalone unit-test import path.
    import zhenzhen_http as requests
from PIL import Image, UnidentifiedImageError


_IMAGE_HEADERS = {
    "User-Agent": "ComfyUI-Zhenzhen/2.0",
    "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
}
MEDIA_DOWNLOAD_MIN_TIMEOUT = 120.0
_DIRECT_SESSION_LOCAL = threading.local()


def media_download_seconds(timeout: float = 300.0) -> float:
    """Apply the 120-second media-download floor to a scalar timeout."""
    try:
        requested_timeout = float(timeout)
    except (TypeError, ValueError):
        requested_timeout = 300.0
    return max(MEDIA_DOWNLOAD_MIN_TIMEOUT, requested_timeout)


def media_download_timeout(timeout: float = 300.0) -> tuple[float, float]:
    """Build a connect/read timeout while preserving longer read values."""
    return (
        MEDIA_DOWNLOAD_MIN_TIMEOUT,
        media_download_seconds(timeout),
    )


def _request_timeout(timeout: float) -> tuple[float, float]:
    return media_download_timeout(timeout)


def _direct_session() -> Any:
    session = getattr(_DIRECT_SESSION_LOCAL, "session", None)
    if session is not None:
        return session

    session = requests.Session()
    session.trust_env = False
    _DIRECT_SESSION_LOCAL.session = session
    return session


def direct_media_get(url: str, **kwargs: Any) -> Any:
    """Download directly, bypassing broken HTTP(S)_PROXY environment values."""
    return _direct_session().get(url, **kwargs)


def _should_retry_without_proxy(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.ProxyError,
            ConnectionError,
        ),
    )


def get_media_response(
    url: str,
    *,
    request_get: Any = None,
    direct_get: Any = None,
    **kwargs: Any,
) -> Any:
    """GET generated media, retrying route failures without environment proxies."""
    getter = request_get or requests.get
    fallback_getter = direct_get
    if fallback_getter is None and request_get is None:
        fallback_getter = direct_media_get

    try:
        return getter(url, **kwargs)
    except Exception as error:
        if fallback_getter is None or not _should_retry_without_proxy(error):
            raise
        return fallback_getter(url, **kwargs)


def _failure_summary(error: BaseException) -> str:
    if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    return type(error).__name__


def download_image_with_retry(
    url: str,
    *,
    timeout: float = 300,
    max_attempts: int = 5,
    request_get: Any = None,
    direct_get: Any = None,
) -> Image.Image:
    """Download and fully decode an image, retrying transient or not-yet-ready results."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Image result URL is empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    getter = request_get or requests.get
    fallback_getter = direct_get
    if fallback_getter is None and request_get is None:
        fallback_getter = direct_media_get
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = get_media_response(
                url,
                request_get=getter,
                direct_get=fallback_getter,
                headers=_IMAGE_HEADERS,
                timeout=_request_timeout(timeout),
            )
            response.raise_for_status()
            if not response.content:
                raise OSError("Image response was empty")
            with Image.open(io.BytesIO(response.content)) as image:
                image.load()
                return image.convert("RGB")
        except (
            requests.exceptions.RequestException,
            UnidentifiedImageError,
            OSError,
            ValueError,
        ) as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 8))

    summary = _failure_summary(last_error or RuntimeError("unknown image error"))
    raise RuntimeError(
        f"Image result download failed after {max_attempts} attempts ({summary})"
    ) from last_error


def download_image_with_alpha_retry(
    url: str,
    *,
    timeout: float = 300,
    max_attempts: int = 5,
    request_get: Any = None,
    direct_get: Any = None,
) -> Image.Image:
    """Download and fully decode an image without discarding its alpha channel."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Image result URL is empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    getter = request_get or requests.get
    fallback_getter = direct_get
    if fallback_getter is None and request_get is None:
        fallback_getter = direct_media_get
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = get_media_response(
                url,
                request_get=getter,
                direct_get=fallback_getter,
                headers=_IMAGE_HEADERS,
                timeout=_request_timeout(timeout),
            )
            response.raise_for_status()
            if not response.content:
                raise OSError("Image response was empty")
            with Image.open(io.BytesIO(response.content)) as image:
                image.load()
                return image.convert("RGBA")
        except (
            requests.exceptions.RequestException,
            UnidentifiedImageError,
            OSError,
            ValueError,
        ) as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(min(2 ** (attempt - 1), 8))

    summary = _failure_summary(last_error or RuntimeError("unknown image error"))
    raise RuntimeError(
        f"Image result download failed after {max_attempts} attempts ({summary})"
    ) from last_error


__all__ = [
    "MEDIA_DOWNLOAD_MIN_TIMEOUT",
    "media_download_seconds",
    "media_download_timeout",
    "direct_media_get",
    "get_media_response",
    "download_image_with_retry",
    "download_image_with_alpha_retry",
]

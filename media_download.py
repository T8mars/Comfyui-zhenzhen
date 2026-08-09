"""Resilient media-result downloads shared by Zhenzhen nodes."""

from __future__ import annotations

import io
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from PIL import Image, UnidentifiedImageError

try:
    from .t8star_http import (
        T8STAR_RETRY_DELAYS,
        T8STAR_RETRYABLE_NETWORK_ERRORS,
        T8STAR_RETRYABLE_STATUS_CODES,
        T8STAR_ROUTE_ATTEMPTS,
        create_alternating_route_session,
    )
except ImportError:
    from t8star_http import (
        T8STAR_RETRY_DELAYS,
        T8STAR_RETRYABLE_NETWORK_ERRORS,
        T8STAR_RETRYABLE_STATUS_CODES,
        T8STAR_ROUTE_ATTEMPTS,
        create_alternating_route_session,
    )


_IMAGE_HEADERS = {
    "User-Agent": "ComfyUI-Zhenzhen/2.0",
    "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
}


def _request_timeout(timeout: float) -> tuple[float, float]:
    try:
        read_timeout = float(timeout)
    except (TypeError, ValueError):
        read_timeout = 300.0
    return (15.0, max(30.0, min(read_timeout, 600.0)))


def _failure_summary(error: BaseException) -> str:
    if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
        return f"HTTP {error.response.status_code}"
    return type(error).__name__


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _download_image(
    url: str,
    *,
    mode: str,
    timeout: float,
    max_attempts: int,
    request_get: Any,
) -> Image.Image:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Image result URL is empty")
    attempts = max(1, min(int(max_attempts), len(T8STAR_ROUTE_ATTEMPTS)))
    last_error: BaseException | None = None
    safe_url = _safe_url(url)

    for attempt in range(attempts):
        if attempt:
            time.sleep(T8STAR_RETRY_DELAYS[attempt - 1])
        response = None
        try:
            if request_get is None:
                with create_alternating_route_session(attempt) as session:
                    response = session.get(
                        url, headers=_IMAGE_HEADERS, timeout=_request_timeout(timeout)
                    )
                    image = _decode_image_response(response, mode)
            else:
                response = request_get(
                    url, headers=_IMAGE_HEADERS, timeout=_request_timeout(timeout)
                )
                image = _decode_image_response(response, mode)
            return image
        except requests.exceptions.HTTPError as error:
            last_error = error
            status = error.response.status_code if error.response is not None else None
            if status not in T8STAR_RETRYABLE_STATUS_CODES:
                raise
        except (*T8STAR_RETRYABLE_NETWORK_ERRORS, UnidentifiedImageError, OSError, ValueError) as error:
            last_error = error
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        print(
            f"[zhenzhen] Image download failed for {safe_url} "
            f"(attempt {attempt + 1}/{attempts}, "
            f"mode={T8STAR_ROUTE_ATTEMPTS[attempt][0]}): "
            f"{type(last_error).__name__}"
        )

    summary = _failure_summary(last_error or RuntimeError("unknown image error"))
    raise RuntimeError(
        f"Image result download failed after {attempts} attempts ({summary})"
    ) from last_error


def _decode_image_response(response: requests.Response, mode: str) -> Image.Image:
    if response.status_code in T8STAR_RETRYABLE_STATUS_CODES:
        raise requests.exceptions.HTTPError(
            f"retryable HTTP {response.status_code}", response=response
        )
    response.raise_for_status()
    content = response.content
    if not content:
        raise OSError("Image response was empty")
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        return image.convert(mode)


def download_image_with_retry(
    url: str,
    *,
    timeout: float = 300,
    max_attempts: int = len(T8STAR_ROUTE_ATTEMPTS),
    request_get: Any = None,
) -> Image.Image:
    """Download and fully decode an image, retrying transient or not-yet-ready results."""
    return _download_image(
        url,
        mode="RGB",
        timeout=timeout,
        max_attempts=max_attempts,
        request_get=request_get,
    )


def download_image_with_alpha_retry(
    url: str,
    *,
    timeout: float = 300,
    max_attempts: int = len(T8STAR_ROUTE_ATTEMPTS),
    request_get: Any = None,
) -> Image.Image:
    """Download and fully decode an image without discarding its alpha channel."""
    return _download_image(
        url,
        mode="RGBA",
        timeout=timeout,
        max_attempts=max_attempts,
        request_get=request_get,
    )


__all__ = ["download_image_with_retry", "download_image_with_alpha_retry"]

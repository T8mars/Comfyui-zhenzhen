"""Resilient media-result downloads shared by Zhenzhen nodes."""

from __future__ import annotations

import io
import time
from typing import Any

import requests
from PIL import Image, UnidentifiedImageError


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


def download_image_with_retry(
    url: str,
    *,
    timeout: float = 300,
    max_attempts: int = 5,
    request_get: Any = None,
) -> Image.Image:
    """Download and fully decode an image, retrying transient or not-yet-ready results."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Image result URL is empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    getter = request_get or requests.get
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = getter(
                url,
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
) -> Image.Image:
    """Download and fully decode an image without discarding its alpha channel."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Image result URL is empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    getter = request_get or requests.get
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = getter(
                url,
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


__all__ = ["download_image_with_retry", "download_image_with_alpha_retry"]

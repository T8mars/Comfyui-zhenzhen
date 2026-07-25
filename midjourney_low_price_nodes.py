"""Unified Midjourney actions for the domestic Zhenzhen low-price API."""

from __future__ import annotations

import io
import json
import mimetypes
import os
import ssl
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

import numpy as np
import requests
import torch
from PIL import Image, ImageDraw, ImageFont

try:
    from .seedance_low_price_nodes import (
        COMFYUI_AVAILABLE,
        BUNDLED_ROOT_YR_CERT,
        CONFIG_TYPE,
        DEFAULT_BASE_URL,
        VIDEO_TYPE,
        SeedanceLowPriceError,
        _SSLContextAdapter,
        _headers,
        _response_json,
        _video_from_path,
        extract_error_message,
        image_to_png_bytes,
        make_error_video,
        resolve_config,
        upload_media,
    )
except ImportError:
    from seedance_low_price_nodes import (
        COMFYUI_AVAILABLE,
        BUNDLED_ROOT_YR_CERT,
        CONFIG_TYPE,
        DEFAULT_BASE_URL,
        VIDEO_TYPE,
        SeedanceLowPriceError,
        _SSLContextAdapter,
        _headers,
        _response_json,
        _video_from_path,
        extract_error_message,
        image_to_png_bytes,
        make_error_video,
        resolve_config,
        upload_media,
    )

try:
    import comfy.utils
except ImportError:
    comfy = None


_SESSION_LOCAL = threading.local()


def _midjourney_session() -> requests.Session:
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is not None:
        return session
    if not BUNDLED_ROOT_YR_CERT.is_file():
        raise RuntimeError(
            f"Bundled TLS certificate is missing: "
            f"{BUNDLED_ROOT_YR_CERT.name}"
        )
    context = ssl.create_default_context(cafile=requests.certs.where())
    context.load_verify_locations(cafile=str(BUNDLED_ROOT_YR_CERT))
    session = requests.Session()
    session.mount(
        f"{DEFAULT_BASE_URL}/",
        _SSLContextAdapter(context),
    )
    _SESSION_LOCAL.session = session
    return session


MIDJOURNEY_SPEEDS = ["unset", "relax", "fast", "turbo"]
MIDJOURNEY_VERSIONS = [
    "unset",
    "5",
    "5.1",
    "5.2",
    "6",
    "6.1",
    "7",
    "8.1",
    "8.2",
]
MIDJOURNEY_DIMENSIONS = ["unset", "SQUARE", "PORTRAIT", "LANDSCAPE"]
MIDJOURNEY_QUALITIES = ["unset", "0.25", "0.5", "1", "2"]
MIDJOURNEY_DIRECTIONS = ["unset", "left", "right", "up", "down"]
MIDJOURNEY_MODAL_MODES = ["region", "outpaint"]
MIDJOURNEY_VIDEO_TYPES = [
    "vid_1.1_i2v_480",
    "vid_1.1_i2v_720",
    "vid_1.1_i2v_start_end_480",
    "vid_1.1_i2v_start_end_720",
]
MIDJOURNEY_ANIMATE_MODES = ["manual", "auto"]
MIDJOURNEY_MOTIONS = ["low", "high"]
MIDJOURNEY_BATCH_SIZES = [1, 2, 4]
MAX_MIDJOURNEY_IMAGES = 4

MIDJOURNEY_STRUCTURED_FIELDS = (
    "size",
    "quality",
    "style",
    "version",
    "seed",
    "negative_prompt",
    "stylize",
    "chaos",
    "weird",
    "tile",
    "niji",
    "iw",
    "cw",
    "sw",
    "cref",
    "sref",
    "dref",
    "dw",
    "repeat",
    "raw",
    "draft",
    "hd",
    "stop",
    "extra",
)

MIDJOURNEY_ACTION_SPECS: Dict[str, Dict[str, Any]] = {
    "midjourney-imagine": {
        "action": "imagine",
        "execution_mode": "async",
        "required_fields": ("prompt",),
        "required_one_of": (),
        "allowed_fields": (
            "prompt",
            "image_urls",
            "speed",
            "metadata",
            *MIDJOURNEY_STRUCTURED_FIELDS,
        ),
        "result_family": "image",
    },
    "midjourney-blend": {
        "action": "blend",
        "execution_mode": "async",
        "required_fields": ("image_urls",),
        "required_one_of": (),
        "allowed_fields": (
            "image_urls",
            "dimensions",
            "size",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-describe": {
        "action": "describe",
        "execution_mode": "sync_or_async",
        "required_fields": ("image_urls",),
        "required_one_of": (),
        "allowed_fields": ("image_urls", "speed", "metadata"),
        "result_family": "text",
    },
    "midjourney-edits": {
        "action": "edits",
        "execution_mode": "async",
        "required_fields": ("prompt", "image_urls"),
        "required_one_of": (),
        "allowed_fields": (
            "prompt",
            "image_urls",
            "speed",
            "metadata",
            *MIDJOURNEY_STRUCTURED_FIELDS,
        ),
        "result_family": "image",
    },
    "midjourney-upscale": {
        "action": "upscale",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (("index", "custom_id"),),
        "allowed_fields": (
            "task_id",
            "index",
            "custom_id",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-variation": {
        "action": "variation",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (("index", "custom_id"),),
        "allowed_fields": (
            "task_id",
            "index",
            "custom_id",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-high-variation": {
        "action": "high-variation",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (("index", "custom_id"),),
        "allowed_fields": (
            "task_id",
            "index",
            "custom_id",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-low-variation": {
        "action": "low-variation",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (("index", "custom_id"),),
        "allowed_fields": (
            "task_id",
            "index",
            "custom_id",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-reroll": {
        "action": "reroll",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (),
        "allowed_fields": ("task_id", "custom_id", "speed", "metadata"),
        "result_family": "image",
    },
    "midjourney-zoom": {
        "action": "zoom",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (),
        "allowed_fields": (
            "task_id",
            "index",
            "custom_id",
            "zoom_ratio",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-pan": {
        "action": "pan",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (("direction", "custom_id"),),
        "allowed_fields": (
            "task_id",
            "index",
            "direction",
            "custom_id",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-inpaint": {
        "action": "inpaint",
        "execution_mode": "modal_stage",
        "required_fields": ("task_id",),
        "required_one_of": (),
        "allowed_fields": (
            "task_id",
            "index",
            "custom_id",
            "speed",
            "metadata",
        ),
        "result_family": "modal",
    },
    "midjourney-modal": {
        "action": "modal",
        "execution_mode": "async",
        "required_fields": ("task_id",),
        "required_one_of": (),
        "allowed_fields": (
            "task_id",
            "prompt",
            "mask_url",
            "speed",
            "metadata",
        ),
        "result_family": "image",
    },
    "midjourney-video": {
        "action": "video",
        "execution_mode": "async",
        "required_fields": (),
        "required_one_of": (("image_urls", "task_id"),),
        "allowed_fields": (
            "prompt",
            "image_urls",
            "task_id",
            "index",
            "video_type",
            "animate_mode",
            "motion",
            "batch_size",
            "end_url",
        ),
        "result_family": "video",
    },
    "midjourney-remix-strong": {
        "action": "remix-strong",
        "execution_mode": "async",
        "required_fields": ("task_id", "index"),
        "required_one_of": (),
        "allowed_fields": ("task_id", "index", "prompt", "speed"),
        "result_family": "image",
    },
    "midjourney-remix-subtle": {
        "action": "remix-subtle",
        "execution_mode": "async",
        "required_fields": ("task_id", "index"),
        "required_one_of": (),
        "allowed_fields": ("task_id", "index", "prompt", "speed"),
        "result_family": "image",
    },
}
MIDJOURNEY_OPERATIONS = list(MIDJOURNEY_ACTION_SPECS)

_RUNNING_STATUSES = {
    "NOT_START",
    "CREATED",
    "SUBMITTED",
    "QUEUED",
    "PENDING",
    "PROCESSING",
    "IN_PROGRESS",
    "RUNNING",
}
_COMPLETED_STATUSES = {"SUCCESS", "SUCCEEDED", "COMPLETED", "COMPLETE"}
_FAILED_STATUSES = {
    "CANCEL",
    "FAILURE",
    "FAILED",
    "ERROR",
    "CANCELLED",
    "CANCELED",
}
_ENVELOPE_KEYS = ("data", "result", "task", "output")
_TASK_KEYS = (
    "status",
    "task_id",
    "id",
    "image_urls",
    "images",
    "video_urls",
    "videos",
    "grid_image_url",
    "description",
    "prompt",
    "text",
    "buttons",
)


def _coerce_progress(value: Any) -> Optional[int]:
    try:
        return max(0, min(100, int(str(value).strip().rstrip("%"))))
    except (TypeError, ValueError):
        return None


def _extract_task_id(value: Any) -> Optional[str]:
    if isinstance(value, list):
        for item in value:
            task_id = _extract_task_id(item)
            if task_id:
                return task_id
        return None
    if not isinstance(value, dict):
        return None
    for key in ("task_id", "id"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    for key in _ENVELOPE_KEYS:
        nested = value.get(key)
        if isinstance(nested, (dict, list)):
            task_id = _extract_task_id(nested)
            if task_id:
                return task_id
    return None


def _unwrap_task_data(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None

    data = value.get("data")
    candidates = data if isinstance(data, list) else [data]
    for candidate in candidates:
        if isinstance(candidate, dict):
            unwrapped = _unwrap_task_data(candidate)
            if unwrapped is not None:
                return unwrapped

    direct_keys = tuple(key for key in _TASK_KEYS if key != "id")
    if any(key in value for key in direct_keys):
        return value

    for key in ("result", "task", "output"):
        nested = value.get(key)
        candidates = nested if isinstance(nested, list) else [nested]
        for candidate in candidates:
            if isinstance(candidate, dict):
                unwrapped = _unwrap_task_data(candidate)
                if unwrapped is not None:
                    return unwrapped
    if isinstance(value.get("id"), str):
        return value
    return None


def submit_midjourney_action(
    action: str,
    payload: Dict[str, Any],
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Tuple[Optional[str], Dict[str, Any]]:
    action_text = str(action or "").strip().strip("/")
    if not action_text:
        raise SeedanceLowPriceError("Midjourney action is required")
    url = f"{config['base_url']}/v1/midjourney/generations/{action_text}"
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            sleep(min(2 ** attempt + 1, 15))
        try:
            response = _midjourney_session().post(
                url,
                headers=_headers(config["api_key"]),
                json=payload,
                timeout=config.get("timeout", 60),
            )
        except requests.ConnectTimeout as exc:
            last_error = f"network error: {type(exc).__name__}: {exc}"
            continue
        except requests.RequestException as exc:
            raise RuntimeError(
                "Midjourney submit transport failed after the request may have "
                "reached the server; it was not retried to avoid a duplicate "
                f"paid task: {type(exc).__name__}: {exc}"
            ) from exc

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                f"Midjourney {action_text} rejected "
                f"(HTTP {response.status_code}): {message}"
            )
        if not isinstance(data, dict):
            raise SeedanceLowPriceError(
                "Midjourney submit returned a non-object JSON response"
            )
        return _extract_task_id(data), data
    raise RuntimeError(
        f"Midjourney submit failed after 3 attempts: {last_error}"
    )


def poll_midjourney_task(
    task_id: str,
    config: Dict[str, Any],
    on_progress: Optional[Callable[[int], None]] = None,
    stop_on_modal: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    task_id_text = str(task_id or "").strip()
    if not task_id_text:
        raise SeedanceLowPriceError("Midjourney task_id is required for polling")
    route_templates = (
        "/v1/midjourney/{task_id}",
        "/v1/midjourney/tasks/{task_id}",
        "/v1/tasks/{task_id}",
    )
    active_route: Optional[str] = None
    started = clock()
    failures = 0
    while True:
        if clock() - started > config.get("max_poll_time", 1800):
            raise RuntimeError("Midjourney polling timed out")
        sleep(config.get("poll_interval", 4))
        routes = (active_route,) if active_route else route_templates
        response = None
        last_not_found = None
        route_used = ""
        for route_template in routes:
            if not route_template:
                continue
            route = route_template.format(task_id=task_id_text)
            try:
                candidate = _midjourney_session().get(
                    f"{config['base_url']}{route}",
                    headers=_headers(config["api_key"], json_content=False),
                    timeout=30,
                )
            except requests.RequestException:
                failures += 1
                if failures >= 6:
                    raise RuntimeError(
                        "Midjourney polling failed after repeated network errors"
                    )
                response = None
                break
            if candidate.status_code == 404 and active_route is None:
                last_not_found = candidate
                continue
            response = candidate
            route_used = route_template
            break

        if response is None:
            if last_not_found is not None:
                raise SeedanceLowPriceError(
                    "Midjourney task was not found on any supported query route"
                )
            sleep(min(max(1, failures) * 2, 10))
            continue

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"Midjourney polling repeatedly returned "
                    f"HTTP {response.status_code}: {message}"
                )
            sleep(min(failures * 2, 10))
            continue
        if response.status_code != 200:
            raise SeedanceLowPriceError(
                f"Midjourney polling rejected "
                f"(HTTP {response.status_code}): {message}"
            )
        if not isinstance(data, dict):
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    "Midjourney polling repeatedly returned invalid JSON"
                )
            continue

        task_data = _unwrap_task_data(data)
        if not isinstance(task_data, dict):
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    "Midjourney polling response has no task data"
                )
            continue

        active_route = route_used
        failures = 0
        status = str(task_data.get("status") or "").strip().upper()
        progress = _coerce_progress(task_data.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        if status in _COMPLETED_STATUSES:
            return data
        if status == "MODAL":
            if stop_on_modal:
                return data
            raise SeedanceLowPriceError(
                "Midjourney task requires modal follow-up input"
            )
        if status in _FAILED_STATUSES:
            reason = (
                task_data.get("fail_reason")
                or task_data.get("error")
                or extract_error_message(task_data, "Midjourney task failed")
            )
            raise SeedanceLowPriceError(
                f"Midjourney task failed: {reason}"
            )
        if status and status not in _RUNNING_STATUSES:
            print(
                f"[Midjourney Low Price] Unknown status '{status}', "
                "continuing to poll"
            )


def _containers(value: Any) -> List[Dict[str, Any]]:
    containers: List[Dict[str, Any]] = []
    queue: List[Any] = [value]
    seen: Set[int] = set()
    while queue:
        item = queue.pop(0)
        if isinstance(item, dict):
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)
            containers.append(item)
            for key in _ENVELOPE_KEYS:
                nested = item.get(key)
                if isinstance(nested, (dict, list)):
                    queue.append(nested)
        elif isinstance(item, list):
            queue.extend(child for child in item if isinstance(child, dict))
    return containers


def _append_url(target: List[str], value: Any) -> None:
    if isinstance(value, str):
        url = value.strip()
        if url.startswith(("http://", "https://")) and url not in target:
            target.append(url)


def _collect_url_values(target: List[str], value: Any) -> None:
    if isinstance(value, str):
        _append_url(target, value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                for key in ("url", "image_url", "video_url"):
                    _append_url(target, item.get(key))
            else:
                _append_url(target, item)


def extract_midjourney_results(final_response: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(final_response, dict):
        raise SeedanceLowPriceError(
            "Midjourney response must be a JSON object"
        )
    containers = _containers(final_response)
    task_data = _unwrap_task_data(final_response)
    if task_data is not None:
        containers = [task_data] + [
            item for item in containers if item is not task_data
        ]
    image_urls: List[str] = []
    video_urls: List[str] = []
    grid_image_url = ""
    buttons: List[Any] = []
    text = ""
    status = ""
    for container in containers:
        if not status and container.get("status") is not None:
            status = str(container.get("status") or "").strip()
        if not grid_image_url:
            candidate = container.get("grid_image_url")
            if isinstance(candidate, str) and candidate.startswith(
                ("http://", "https://")
            ):
                grid_image_url = candidate
        for key in ("image_urls", "images"):
            _collect_url_values(image_urls, container.get(key))
        _append_url(image_urls, container.get("image_url"))
        for key in ("video_urls", "videos"):
            _collect_url_values(video_urls, container.get(key))
        _append_url(video_urls, container.get("video_url"))
        if not buttons and isinstance(container.get("buttons"), list):
            buttons = container["buttons"]

    for key in ("description", "prompt", "text"):
        for container in containers:
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break
        if text:
            break
    if grid_image_url in image_urls:
        image_urls.remove(grid_image_url)
    return {
        "task_id": _extract_task_id(final_response) or "",
        "status": status,
        "image_urls": image_urls,
        "grid_image_url": grid_image_url,
        "video_urls": video_urls,
        "text": text,
        "buttons": buttons,
    }


def mask_to_midjourney_png_bytes(mask: Any) -> bytes:
    if mask is None:
        raise SeedanceLowPriceError("mask input is empty")
    array = (
        mask.detach().cpu().numpy()
        if hasattr(mask, "detach")
        else np.asarray(mask)
    )
    if array.ndim == 4:
        array = array[0, ..., 0]
    elif array.ndim == 3:
        array = array[0]
    if array.ndim != 2:
        raise SeedanceLowPriceError(
            f"Unexpected MASK shape: {array.shape}"
        )
    normalized = np.asarray(array, dtype=np.float32)
    if normalized.max() > 1.0:
        normalized = normalized / 255.0
    normalized = np.clip(normalized, 0.0, 1.0)
    alpha = np.rint((1.0 - normalized) * 255.0).astype(np.uint8)
    rgba = np.full((*alpha.shape, 4), 255, dtype=np.uint8)
    rgba[..., 3] = alpha
    buffer = io.BytesIO()
    Image.fromarray(rgba).save(buffer, format="PNG")
    return buffer.getvalue()


def _output_directory() -> str:
    try:
        import folder_paths

        output_dir = folder_paths.get_output_directory()
    except ImportError:
        output_dir = (
            os.environ.get("SEEDANCE_OUTPUT_DIR")
            or tempfile.gettempdir()
        )
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _download_file(
    url: str,
    prefix: str,
    fallback_extension: str,
    max_retries: int = 3,
) -> str:
    output_dir = _output_directory()
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        if attempt:
            time.sleep(2 ** attempt)
        path = ""
        try:
            response = _midjourney_session().get(
                url, stream=True, timeout=300
            )
            response.raise_for_status()
            extension = os.path.splitext(urlsplit(url).path)[1].lower()
            if not extension or len(extension) > 10:
                content_type = response.headers.get("Content-Type", "")
                media_type = content_type.split(";", 1)[0].strip().lower()
                extension = mimetypes.guess_extension(media_type) or (
                    f".{fallback_extension.lstrip('.')}"
                )
            path = os.path.join(
                output_dir,
                f"{prefix}_{uuid.uuid4().hex[:12]}{extension}",
            )
            with open(path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)
            if os.path.getsize(path) <= 0:
                raise RuntimeError("downloaded file is empty")
            return path
        except Exception as exc:
            last_error = exc
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
    raise RuntimeError(
        f"Midjourney result download failed after "
        f"{max_retries} attempts: {last_error}"
    )


def download_image_with_path(url: str) -> Tuple[torch.Tensor, str]:
    raw_path = _download_file(url, "midjourney_image", "png")
    try:
        with Image.open(raw_path) as image:
            rgb = image.convert("RGB")
            array = np.asarray(rgb, dtype=np.float32).copy() / 255.0
        return torch.from_numpy(array).unsqueeze(0), raw_path
    except Exception:
        try:
            os.remove(raw_path)
        except OSError:
            pass
        raise


def download_video_with_path(url: str) -> Tuple[Any, str]:
    path = _download_file(url, "midjourney_video", "mp4")
    return _video_from_path(path), path


def make_error_image(message: str) -> torch.Tensor:
    size = 512
    image = Image.new("RGB", (size, size), (28, 16, 20))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    text = f"Midjourney error\n\n{message}"
    lines: List[str] = []
    for paragraph in text.splitlines():
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if len(candidate) > 56 and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    y = 28
    for line in lines:
        draw.text((28, y), line, fill=(255, 205, 210), font=font)
        y += 18
        if y > size - 28:
            break
    array = np.asarray(image, dtype=np.float32).copy() / 255.0
    return torch.from_numpy(array).unsqueeze(0)


class Comfly_midjourney_lowprice:
    """All documented Midjourney actions through the domestic API."""

    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (
        "IMAGE",
        "IMAGE",
        "IMAGE",
        "IMAGE",
        "IMAGE",
        VIDEO_TYPE,
        VIDEO_TYPE,
        VIDEO_TYPE,
        VIDEO_TYPE,
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "image1",
        "image2",
        "image3",
        "image4",
        "grid_image",
        "video1",
        "video2",
        "video3",
        "video4",
        "text",
        "primary_url",
        "result_urls",
        "primary_path",
        "result_paths",
        "task_id",
        "buttons_json",
        "response",
    )

    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {}
        for index in range(1, MAX_MIDJOURNEY_IMAGES + 1):
            optional[f"image{index}"] = (
                "IMAGE",
                {
                    "tooltip": (
                        f"本地图片 {index}，不能与同槽 image_url 同时使用。"
                    )
                },
            )
        optional["end_image"] = (
            "IMAGE",
            {"tooltip": "视频可选结束帧。"},
        )
        optional["mask"] = (
            "MASK",
            {
                "tooltip": (
                    "Modal 局部重绘遮罩，ComfyUI 白色区域会被重绘。"
                )
            },
        )
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = (
            "BOOLEAN",
            {
                "default": False,
                "tooltip": "失败时返回占位结果而不是中止工作流。",
            },
        )

        required: Dict[str, tuple] = {
            "operation": (
                MIDJOURNEY_OPERATIONS,
                {"default": "midjourney-imagine"},
            ),
            "prompt": (
                "STRING",
                {
                    "multiline": True,
                    "default": "",
                    "tooltip": "提示词或编辑指令，支持外部 STRING 节点。",
                },
            ),
            "speed": (MIDJOURNEY_SPEEDS, {"default": "unset"}),
            "size": (
                "STRING",
                {
                    "default": "",
                    "tooltip": "画面比例，例如 16:9；设置后优先于 dimensions。",
                },
            ),
            "dimensions": (
                MIDJOURNEY_DIMENSIONS,
                {"default": "unset"},
            ),
            "quality": (MIDJOURNEY_QUALITIES, {"default": "unset"}),
            "style": ("STRING", {"default": ""}),
            "version": (MIDJOURNEY_VERSIONS, {"default": "unset"}),
            "seed": (
                "INT",
                {
                    "default": -1,
                    "min": -1,
                    "max": 4294967295,
                    "step": 1,
                },
            ),
            "negative_prompt": (
                "STRING",
                {"multiline": True, "default": ""},
            ),
            "stylize": (
                "INT",
                {"default": -1, "min": -1, "max": 1000, "step": 1},
            ),
            "chaos": (
                "INT",
                {"default": -1, "min": -1, "max": 100, "step": 1},
            ),
            "weird": (
                "INT",
                {"default": -1, "min": -1, "max": 3000, "step": 1},
            ),
            "tile": ("BOOLEAN", {"default": False}),
            "niji": ("BOOLEAN", {"default": False}),
            "iw": (
                "FLOAT",
                {
                    "default": -1.0,
                    "min": -1.0,
                    "max": 3.0,
                    "step": 0.1,
                },
            ),
            "cw": (
                "INT",
                {"default": -1, "min": -1, "max": 100, "step": 1},
            ),
            "sw": (
                "INT",
                {"default": -1, "min": -1, "max": 1000, "step": 1},
            ),
            "cref": (
                "STRING",
                {"default": "", "tooltip": "角色参考图 URL。"},
            ),
            "sref": (
                "STRING",
                {"default": "", "tooltip": "风格参考图 URL。"},
            ),
            "dref": (
                "STRING",
                {"default": "", "tooltip": "深度参考图 URL。"},
            ),
            "dw": (
                "FLOAT",
                {
                    "default": -1.0,
                    "min": -1.0,
                    "max": 100.0,
                    "step": 0.1,
                },
            ),
            "repeat": (
                "INT",
                {"default": 0, "min": 0, "max": 40, "step": 1},
            ),
            "raw": ("BOOLEAN", {"default": False}),
            "draft": ("BOOLEAN", {"default": False}),
            "hd": ("BOOLEAN", {"default": False}),
            "stop": (
                "INT",
                {"default": 0, "min": 0, "max": 100, "step": 1},
            ),
            "extra": ("STRING", {"default": ""}),
            "task_id": (
                "STRING",
                {
                    "default": "",
                    "tooltip": "源 Midjourney 任务 ID，可连接上游节点。",
                },
            ),
            "index": (
                "INT",
                {
                    "default": -1,
                    "min": -1,
                    "max": 4,
                    "step": 1,
                    "tooltip": (
                        "图像操作用 1-4，Video 任务模式用 0-3。"
                    ),
                },
            ),
            "custom_id": (
                "STRING",
                {"default": "", "tooltip": "可选按钮 customId。"},
            ),
            "direction": (
                MIDJOURNEY_DIRECTIONS,
                {"default": "unset"},
            ),
            "zoom_ratio": (
                "FLOAT",
                {
                    "default": 2.0,
                    "min": 1.0,
                    "max": 2.0,
                    "step": 0.1,
                },
            ),
            "modal_mode": (
                MIDJOURNEY_MODAL_MODES,
                {
                    "default": "region",
                    "tooltip": (
                        "region 使用遮罩；outpaint 不发送遮罩。"
                    ),
                },
            ),
            "video_type": (
                MIDJOURNEY_VIDEO_TYPES,
                {"default": "vid_1.1_i2v_480"},
            ),
            "animate_mode": (
                MIDJOURNEY_ANIMATE_MODES,
                {"default": "manual"},
            ),
            "motion": (MIDJOURNEY_MOTIONS, {"default": "high"}),
            "batch_size": (MIDJOURNEY_BATCH_SIZES, {"default": 1}),
            "metadata_json": (
                "STRING",
                {
                    "multiline": True,
                    "default": "",
                    "tooltip": "可选任务 metadata JSON 对象。",
                },
            ),
        }
        for index in range(1, MAX_MIDJOURNEY_IMAGES + 1):
            required[f"image_url{index}"] = (
                "STRING",
                {
                    "default": "",
                    "tooltip": (
                        f"公网图片 URL 或 data URL {index}。"
                    ),
                },
            )
        required["end_url"] = (
            "STRING",
            {"default": "", "tooltip": "可选视频结束帧 URL。"},
        )
        required["mask_url"] = (
            "STRING",
            {"default": "", "tooltip": "可选 Modal 遮罩 URL。"},
        )
        return {"required": required, "optional": optional}

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        operation=None,
        speed=None,
        version=None,
        dimensions=None,
        quality=None,
        direction=None,
        modal_mode=None,
        video_type=None,
        animate_mode=None,
        motion=None,
        batch_size=None,
        index=None,
        **kwargs,
    ):
        if operation not in MIDJOURNEY_ACTION_SPECS:
            return f"Unsupported Midjourney operation: {operation}"
        enum_values = {
            "speed": (speed, MIDJOURNEY_SPEEDS),
            "version": (version, MIDJOURNEY_VERSIONS),
            "dimensions": (dimensions, MIDJOURNEY_DIMENSIONS),
            "quality": (quality, MIDJOURNEY_QUALITIES),
            "direction": (direction, MIDJOURNEY_DIRECTIONS),
            "modal_mode": (modal_mode, MIDJOURNEY_MODAL_MODES),
            "video_type": (video_type, MIDJOURNEY_VIDEO_TYPES),
            "animate_mode": (
                animate_mode,
                MIDJOURNEY_ANIMATE_MODES,
            ),
            "motion": (motion, MIDJOURNEY_MOTIONS),
        }
        for field, (value, allowed) in enum_values.items():
            if value is not None and value not in allowed:
                return f"Unsupported {field}: {value}"
        if (
            batch_size is not None
            and int(batch_size) not in MIDJOURNEY_BATCH_SIZES
        ):
            return "batch_size must be 1, 2, or 4"
        if index is not None and not -1 <= int(index) <= 4:
            return "index must be between -1 and 4"
        return True

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _update_progress(progress_bar: Any, value: float) -> None:
        if progress_bar is not None:
            try:
                progress_bar.update_absolute(int(value), 100)
            except Exception:
                pass

    @staticmethod
    def _media_reference(value: Any, field: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if not text.startswith(("http://", "https://", "data:image/")):
            raise SeedanceLowPriceError(
                f"{field} must be an http(s) URL or image data URL"
            )
        return text

    def _collect_materials(
        self,
        operation: str,
        values: Dict[str, Any],
        config: Dict[str, Any],
        progress_cb: Callable[[float], None],
    ) -> Dict[str, Any]:
        direct_image_actions = {
            "midjourney-imagine",
            "midjourney-blend",
            "midjourney-describe",
            "midjourney-edits",
            "midjourney-video",
        }
        local_jobs = 0
        if operation in direct_image_actions:
            local_jobs += sum(
                1
                for index in range(1, MAX_MIDJOURNEY_IMAGES + 1)
                if values.get(f"image{index}") is not None
            )
        if (
            operation == "midjourney-video"
            and values.get("end_image") is not None
        ):
            local_jobs += 1
        if (
            operation == "midjourney-modal"
            and self._text(values.get("modal_mode")) == "region"
            and values.get("mask") is not None
        ):
            local_jobs += 1

        uploaded = 0
        image_urls: List[str] = []
        if operation in direct_image_actions:
            for index in range(1, MAX_MIDJOURNEY_IMAGES + 1):
                image = values.get(f"image{index}")
                image_url = self._media_reference(
                    values.get(f"image_url{index}"),
                    f"image_url{index}",
                )
                if image is not None and image_url:
                    raise SeedanceLowPriceError(
                        f"image{index} and image_url{index} "
                        "cannot both be used"
                    )
                if image is not None:
                    image_url = upload_media(
                        image_to_png_bytes(image),
                        f"midjourney_image_{index}.png",
                        "image/png",
                        config,
                    )
                    uploaded += 1
                    progress_cb(uploaded / max(local_jobs, 1))
                if image_url:
                    image_urls.append(image_url)

        end_url = ""
        if operation == "midjourney-video":
            end_image = values.get("end_image")
            end_url = self._media_reference(
                values.get("end_url"), "end_url"
            )
            if end_image is not None and end_url:
                raise SeedanceLowPriceError(
                    "end_image and end_url cannot both be used"
                )
            if end_image is not None:
                end_url = upload_media(
                    image_to_png_bytes(end_image),
                    "midjourney_end_frame.png",
                    "image/png",
                    config,
                )
                uploaded += 1
                progress_cb(uploaded / max(local_jobs, 1))

        mask_url = ""
        if operation == "midjourney-modal":
            modal_mode = self._text(values.get("modal_mode")) or "region"
            mask = values.get("mask")
            if modal_mode == "outpaint":
                mask = None
                supplied_mask_url = ""
            else:
                supplied_mask_url = self._media_reference(
                    values.get("mask_url"), "mask_url"
                )
            if (
                modal_mode != "outpaint"
                and mask is not None
                and supplied_mask_url
            ):
                raise SeedanceLowPriceError(
                    "mask and mask_url cannot both be used"
                )
            if mask is not None:
                supplied_mask_url = upload_media(
                    mask_to_midjourney_png_bytes(mask),
                    "midjourney_mask.png",
                    "image/png",
                    config,
                )
                uploaded += 1
                progress_cb(uploaded / max(local_jobs, 1))
            mask_url = supplied_mask_url
            if modal_mode == "region" and not mask_url:
                raise SeedanceLowPriceError(
                    "midjourney-modal region mode requires a mask"
                )

        if local_jobs == 0:
            progress_cb(1.0)
        return {
            "image_urls": image_urls,
            "end_url": end_url,
            "mask_url": mask_url,
        }

    def _metadata(self, raw_value: Any) -> Optional[Dict[str, Any]]:
        text = self._text(raw_value)
        if not text:
            return None
        try:
            value = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise SeedanceLowPriceError(
                f"metadata_json must be valid JSON: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise SeedanceLowPriceError(
                "metadata_json must contain a JSON object"
            )
        return value

    @staticmethod
    def _validate_structured_compatibility(
        payload: Dict[str, Any],
    ) -> None:
        version = str(payload.get("version") or "").strip()
        niji = bool(payload.get("niji"))
        if niji and version and version not in {"5", "6", "7"}:
            raise SeedanceLowPriceError(
                "niji requires version 5, 6, or 7"
            )
        if payload.get("raw") and version == "5":
            raise SeedanceLowPriceError(
                "raw requires version 5.1 or newer"
            )
        if (
            payload.get("draft")
            and version
            and version not in {"7", "8.1", "8.2"}
        ):
            raise SeedanceLowPriceError(
                "draft requires version 7 or newer"
            )
        if payload.get("hd") and version and version not in {"8.1", "8.2"}:
            raise SeedanceLowPriceError(
                "hd supports only version 8.1 or 8.2"
            )
        if "stop" in payload and version:
            supported = (
                {"5", "6"}
                if niji
                else {"5", "5.1", "5.2", "6", "6.1"}
            )
            if version not in supported:
                raise SeedanceLowPriceError(
                    f"stop is not supported by version {version}"
                )

    def _build_payload(
        self,
        operation: str,
        materials: Dict[str, Any],
        **values,
    ) -> Dict[str, Any]:
        if operation not in MIDJOURNEY_ACTION_SPECS:
            raise SeedanceLowPriceError(
                f"Unsupported Midjourney operation: {operation}"
            )
        spec = MIDJOURNEY_ACTION_SPECS[operation]
        allowed = set(spec["allowed_fields"])
        payload: Dict[str, Any] = {}

        prompt = self._text(values.get("prompt"))
        if "prompt" in allowed and prompt:
            payload["prompt"] = prompt
        image_urls = list(materials.get("image_urls") or [])
        if "image_urls" in allowed and image_urls:
            payload["image_urls"] = image_urls

        task_id = self._text(values.get("task_id"))
        if "task_id" in allowed and task_id:
            payload["task_id"] = task_id
        custom_id = self._text(values.get("custom_id"))
        if "custom_id" in allowed and custom_id:
            payload["custom_id"] = custom_id
        raw_index = values.get("index")
        index = int(raw_index) if raw_index is not None else -1
        if "index" in allowed and index >= 0 and not custom_id:
            payload["index"] = index

        speed = self._text(values.get("speed"))
        if "speed" in allowed and speed and speed != "unset":
            payload["speed"] = speed
        size = self._text(values.get("size"))
        if "size" in allowed and size:
            payload["size"] = size
        dimensions = self._text(values.get("dimensions"))
        if (
            "dimensions" in allowed
            and dimensions
            and dimensions != "unset"
            and not size
        ):
            payload["dimensions"] = dimensions
        if "direction" in allowed and not custom_id:
            direction = self._text(values.get("direction"))
            if direction and direction != "unset":
                payload["direction"] = direction
        if "zoom_ratio" in allowed and not custom_id:
            zoom_ratio = float(values.get("zoom_ratio") or 2.0)
            if not 1.0 <= zoom_ratio <= 2.0:
                raise SeedanceLowPriceError(
                    "zoom_ratio must be between 1.0 and 2.0"
                )
            payload["zoom_ratio"] = zoom_ratio

        if "mask_url" in allowed and materials.get("mask_url"):
            payload["mask_url"] = materials["mask_url"]
        if "end_url" in allowed and materials.get("end_url"):
            payload["end_url"] = materials["end_url"]
        if operation == "midjourney-video":
            payload["video_type"] = self._text(values.get("video_type"))
            payload["animate_mode"] = self._text(
                values.get("animate_mode")
            )
            payload["motion"] = self._text(values.get("motion"))
            payload["batch_size"] = int(values.get("batch_size") or 1)

        for field in ("quality", "version"):
            if field in allowed:
                value = self._text(values.get(field))
                if value and value != "unset":
                    payload[field] = value
        for field in (
            "style",
            "negative_prompt",
            "cref",
            "sref",
            "dref",
            "extra",
        ):
            if field not in allowed:
                continue
            value = self._text(values.get(field))
            if value:
                if field in {"cref", "sref", "dref"}:
                    value = self._media_reference(value, field)
                payload[field] = value

        sentinel_ints = {
            "seed": -1,
            "stylize": -1,
            "chaos": -1,
            "weird": -1,
            "cw": -1,
            "sw": -1,
            "repeat": 0,
            "stop": 0,
        }
        for field, sentinel in sentinel_ints.items():
            if field not in allowed:
                continue
            raw_value = values.get(field)
            value = int(raw_value if raw_value is not None else sentinel)
            if value > sentinel:
                payload[field] = value
        if payload.get("repeat") == 1:
            raise SeedanceLowPriceError(
                "repeat must be 0 (unset) or 2-40"
            )
        if "stop" in payload and payload["stop"] < 10:
            raise SeedanceLowPriceError(
                "stop must be 0 (unset) or 10-100"
            )

        for field in ("iw", "dw"):
            if field in allowed:
                raw_value = values.get(field)
                value = float(
                    raw_value if raw_value is not None else -1.0
                )
                if value >= 0:
                    payload[field] = value
        for field in ("tile", "niji", "raw", "draft", "hd"):
            if field in allowed and bool(values.get(field, False)):
                payload[field] = True

        self._validate_structured_compatibility(payload)
        if "metadata" in allowed:
            metadata = self._metadata(values.get("metadata_json"))
            if metadata is not None:
                payload["metadata"] = metadata

        if operation == "midjourney-blend" and not 2 <= len(image_urls) <= 4:
            raise SeedanceLowPriceError(
                "midjourney-blend requires 2-4 images"
            )
        if (
            operation == "midjourney-describe"
            and len(image_urls) != 1
        ):
            raise SeedanceLowPriceError(
                "midjourney-describe requires exactly one image"
            )

        missing = [
            field
            for field in spec["required_fields"]
            if field not in payload
            or payload[field] is None
            or payload[field] == ""
            or payload[field] == []
        ]
        if missing:
            raise SeedanceLowPriceError(
                f"{operation} requires: {', '.join(missing)}"
            )
        for field_group in spec["required_one_of"]:
            if not any(
                field in payload and payload[field] not in ("", None, [])
                for field in field_group
            ):
                raise SeedanceLowPriceError(
                    f"{operation} requires {' or '.join(field_group)}"
                )

        if operation == "midjourney-imagine" and len(image_urls) > 4:
            raise SeedanceLowPriceError(
                "midjourney-imagine accepts at most 4 images"
            )
        if (
            operation == "midjourney-edits"
            and not 1 <= len(image_urls) <= 4
        ):
            raise SeedanceLowPriceError(
                "midjourney-edits requires 1-4 images"
            )

        one_based_actions = {
            "midjourney-upscale",
            "midjourney-variation",
            "midjourney-high-variation",
            "midjourney-low-variation",
            "midjourney-remix-strong",
            "midjourney-remix-subtle",
        }
        if (
            operation in one_based_actions
            and "custom_id" not in payload
            and not 1 <= int(payload.get("index", -1)) <= 4
        ):
            raise SeedanceLowPriceError(
                f"{operation} index must be 1-4"
            )
        if (
            operation
            in {"midjourney-zoom", "midjourney-pan", "midjourney-inpaint"}
            and "index" in payload
            and not 1 <= int(payload["index"]) <= 4
        ):
            raise SeedanceLowPriceError(
                f"{operation} index must be 1-4 when supplied"
            )

        if operation == "midjourney-video":
            has_images = bool(payload.get("image_urls"))
            has_task = bool(payload.get("task_id"))
            if has_images == has_task:
                raise SeedanceLowPriceError(
                    "midjourney-video requires exactly one source: "
                    "image or task_id"
                )
            if has_images and len(payload["image_urls"]) != 1:
                raise SeedanceLowPriceError(
                    "midjourney-video accepts exactly one start image"
                )
            if has_images and not prompt:
                raise SeedanceLowPriceError(
                    "midjourney-video direct image mode requires prompt"
                )
            if payload["animate_mode"] == "auto":
                if not has_task or "index" not in payload:
                    raise SeedanceLowPriceError(
                        "midjourney-video auto mode requires "
                        "task_id and index 0-3"
                    )
            if has_images and "index" in payload:
                raise SeedanceLowPriceError(
                    "midjourney-video index is only valid with task_id"
                )
            if (
                has_task
                and "index" in payload
                and not 0 <= payload["index"] <= 3
            ):
                raise SeedanceLowPriceError(
                    "midjourney-video task index must be 0-3"
                )
            if payload["batch_size"] not in MIDJOURNEY_BATCH_SIZES:
                raise SeedanceLowPriceError(
                    "midjourney-video batch_size must be 1, 2, or 4"
                )
            has_end = bool(payload.get("end_url"))
            is_start_end = "_start_end_" in payload["video_type"]
            if has_end and not is_start_end:
                resolution = (
                    "720" if "720" in payload["video_type"] else "480"
                )
                payload["video_type"] = (
                    f"vid_1.1_i2v_start_end_{resolution}"
                )
            elif is_start_end and not has_end:
                raise SeedanceLowPriceError(
                    "start/end video_type requires end_image or end_url"
                )

        return {
            key: value
            for key, value in payload.items()
            if key in allowed
        }

    @staticmethod
    def _response_status(response: Dict[str, Any]) -> str:
        if not isinstance(response, dict):
            return ""
        task_data = _unwrap_task_data(response)
        if isinstance(task_data, dict):
            return str(task_data.get("status") or "").strip().upper()
        return str(response.get("status") or "").strip().upper()

    def _make_error_result(self, message: str) -> Dict[str, Any]:
        response = json.dumps(
            {"error": message}, ensure_ascii=False, indent=2
        )
        return {
            "ui": {"text": ["", "", "", "", response]},
            "result": (
                make_error_image(message),
                None,
                None,
                None,
                None,
                make_error_video(message),
                None,
                None,
                None,
                "",
                "",
                "[]",
                "",
                "[]",
                "",
                "[]",
                response,
            ),
        }

    def execute(
        self,
        operation: str,
        prompt: str = "",
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        values = {**kwargs, "prompt": prompt}
        try:
            return self._execute_inner(operation, api_config, values)
        except Exception as exc:
            if not skip_error:
                raise
            return self._make_error_result(
                f"Midjourney Low Price: {type(exc).__name__}: {exc}"
            )

    def _execute_inner(
        self,
        operation: str,
        api_config: Any,
        values: Dict[str, Any],
    ):
        validation = self.VALIDATE_INPUTS(
            operation=operation,
            speed=values.get("speed"),
            version=values.get("version"),
            dimensions=values.get("dimensions"),
            quality=values.get("quality"),
            direction=values.get("direction"),
            modal_mode=values.get("modal_mode"),
            video_type=values.get("video_type"),
            animate_mode=values.get("animate_mode"),
            motion=values.get("motion"),
            batch_size=values.get("batch_size"),
            index=values.get("index"),
        )
        if validation is not True:
            raise SeedanceLowPriceError(validation)

        spec = MIDJOURNEY_ACTION_SPECS[operation]
        config = resolve_config(api_config)
        progress_bar = (
            comfy.utils.ProgressBar(100)
            if COMFYUI_AVAILABLE and comfy is not None
            else None
        )
        self._update_progress(progress_bar, 0)
        materials = self._collect_materials(
            operation,
            values,
            config,
            lambda fraction: self._update_progress(
                progress_bar, fraction * 15
            ),
        )
        payload = self._build_payload(
            operation, materials, **values
        )
        self._update_progress(progress_bar, 15)
        submitted_task_id, submit_response = submit_midjourney_action(
            spec["action"], payload, config
        )
        self._update_progress(progress_bar, 20)

        final_response = submit_response
        submit_extracted = extract_midjourney_results(submit_response)
        submit_status = self._response_status(submit_response)
        submit_is_complete = submit_status in _COMPLETED_STATUSES
        submit_is_modal = submit_status == "MODAL"
        submit_has_sync_result = (
            spec["execution_mode"] == "sync_or_async"
            and bool(self._text(submit_extracted.get("text")))
        )
        should_poll = bool(submitted_task_id) and (
            (
                spec["execution_mode"] == "sync_or_async"
                and not submit_has_sync_result
            )
            or (
                not submit_is_complete
                and not submit_is_modal
            )
        )
        if should_poll:
            final_response = poll_midjourney_task(
                submitted_task_id,
                config,
                on_progress=lambda progress: self._update_progress(
                    progress_bar, 20 + progress / 100.0 * 60
                ),
                stop_on_modal=spec["execution_mode"] == "modal_stage",
            )
        elif (
            not submitted_task_id
            and spec["execution_mode"] != "sync_or_async"
        ):
            raise SeedanceLowPriceError(
                f"{operation} returned no task id"
            )
        self._update_progress(progress_bar, 82)

        extracted = extract_midjourney_results(final_response)
        result_task_id = submitted_task_id or extracted["task_id"]
        if (
            spec["execution_mode"] == "modal_stage"
            and self._response_status(final_response) != "MODAL"
        ):
            raise SeedanceLowPriceError(
                "midjourney-inpaint did not reach MODAL state"
            )

        image_objects: List[Any] = []
        image_paths: List[str] = []
        video_objects: List[Any] = []
        video_paths: List[str] = []
        warnings: List[Dict[str, Any]] = []
        successful_downloads = 0

        image_urls = list(extracted.get("image_urls") or [])
        grid_url = self._text(extracted.get("grid_image_url"))
        video_urls = list(extracted.get("video_urls") or [])
        artifact_count = max(
            1,
            len(image_urls) + (1 if grid_url else 0) + len(video_urls),
        )
        artifact_index = 0
        for url in image_urls:
            artifact_index += 1
            path = ""
            image = None
            try:
                image, path = download_image_with_path(url)
                successful_downloads += 1
            except Exception as exc:
                warnings.append(
                    {
                        "artifact_index": artifact_index,
                        "kind": "image",
                        "error": type(exc).__name__,
                    }
                )
            image_objects.append(image)
            image_paths.append(path)
            self._update_progress(
                progress_bar,
                82 + artifact_index / artifact_count * 15,
            )

        grid_image = None
        grid_path = ""
        if grid_url:
            artifact_index += 1
            try:
                grid_image, grid_path = download_image_with_path(grid_url)
                successful_downloads += 1
            except Exception as exc:
                warnings.append(
                    {
                        "artifact_index": artifact_index,
                        "kind": "grid_image",
                        "error": type(exc).__name__,
                    }
                )
            self._update_progress(
                progress_bar,
                82 + artifact_index / artifact_count * 15,
            )

        for url in video_urls:
            artifact_index += 1
            path = ""
            video = None
            try:
                video, path = download_video_with_path(url)
                successful_downloads += 1
            except Exception as exc:
                warnings.append(
                    {
                        "artifact_index": artifact_index,
                        "kind": "video",
                        "error": type(exc).__name__,
                    }
                )
            video_objects.append(video)
            video_paths.append(path)
            self._update_progress(
                progress_bar,
                82 + artifact_index / artifact_count * 15,
            )

        has_artifacts = bool(image_urls or grid_url or video_urls)
        if has_artifacts and successful_downloads == 0:
            raise SeedanceLowPriceError(
                "All Midjourney result artifacts failed to download"
            )
        if (
            not has_artifacts
            and spec["result_family"] in {"image", "video"}
        ):
            raise SeedanceLowPriceError(
                f"{operation} completed without downloadable media"
            )
        text = self._text(extracted.get("text"))
        if spec["result_family"] == "text" and not text:
            raise SeedanceLowPriceError(
                f"{operation} completed without text output"
            )

        all_urls = [
            *image_urls,
            *([grid_url] if grid_url else []),
            *video_urls,
        ]
        result_paths = [
            *image_paths,
            *([grid_path] if grid_url else []),
            *video_paths,
        ]
        response_payload = final_response
        if warnings:
            response_payload = dict(final_response)
            response_payload["_zhenzhen_local"] = {
                "download_warnings": warnings
            }
        response = json.dumps(
            response_payload, ensure_ascii=False, indent=2
        )
        primary_url = all_urls[0] if all_urls else ""
        primary_path = result_paths[0] if result_paths else ""
        padded_images = (image_objects + [None] * 4)[:4]
        padded_videos = (video_objects + [None] * 4)[:4]
        self._update_progress(progress_bar, 100)
        return {
            "ui": {
                "text": [
                    text,
                    primary_url,
                    primary_path,
                    result_task_id,
                    response,
                ]
            },
            "result": (
                *padded_images,
                grid_image,
                *padded_videos,
                text,
                primary_url,
                json.dumps(all_urls, ensure_ascii=False),
                primary_path,
                json.dumps(result_paths, ensure_ascii=False),
                result_task_id,
                json.dumps(
                    extracted.get("buttons") or [],
                    ensure_ascii=False,
                ),
                response,
            ),
        }


__all__ = [
    "Comfly_midjourney_lowprice",
    "MIDJOURNEY_ACTION_SPECS",
    "MIDJOURNEY_OPERATIONS",
    "extract_midjourney_results",
    "poll_midjourney_task",
    "submit_midjourney_action",
]

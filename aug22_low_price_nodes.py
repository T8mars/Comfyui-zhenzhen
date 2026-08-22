"""Domestic low-price Omni, Hunyuan 3D, and GK v2 utility nodes."""

from __future__ import annotations

import io
import json
import os
import shutil
import struct
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import requests
import torch

from .media_download import direct_media_get, get_media_response, media_download_timeout
from .seedance_low_price_nodes import (
    CONFIG_TYPE,
    VIDEO_TYPE,
    COMFYUI_AVAILABLE,
    PROMPT_MAX_LENGTH,
    SeedanceLowPriceError,
    _Comfly_apimart_video_base,
    _get_session,
    _headers,
    download_image,
    extract_error_message,
    extract_image_url,
    image_to_png_bytes,
    poll_image_task,
    resolve_config,
    submit_image_task,
    upload_media,
    video_to_mp4_bytes,
)

try:
    import comfy.utils
except ImportError:
    comfy = None

try:
    from comfy_api.latest import Types as _ComfyTypes
except ImportError:
    _ComfyTypes = None


ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_MODEL = (
    "zhenzhen-video-g-omni-flash-lowprice"
)
ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_MODES = [
    "text",
    "frame",
    "reference_images",
    "reference_video",
]
ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_SECONDS = ["4", "6", "8", "10"]
ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_RESOLUTIONS = ["720p", "1080p", "4k"]
ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_RATIOS = ["16:9", "9:16"]

HUNYUAN3D_TEXT_MODEL = "hunyuan3d-v3.1-text-to-3d"
HUNYUAN3D_IMAGE_MODEL = "hunyuan3d-v3.1-image-to-3d"
HUNYUAN3D_MODELS = [HUNYUAN3D_TEXT_MODEL, HUNYUAN3D_IMAGE_MODEL]
HUNYUAN3D_GENERATE_TYPES = ["Normal", "Geometry", "Sketch"]
HUNYUAN3D_IMAGE_VIEWS = [
    "front",
    "left",
    "right",
    "back",
    "top",
    "bottom",
    "front-left",
    "front-right",
]

ZHENZHEN_IMAGE_GK_V2_SEGMENT_MODEL = "zhenzhen-image-gk-v2-segment"
ZHENZHEN_IMAGE_GK_V2_REGION_EDIT_MODEL = "zhenzhen-image-gk-v2-region-edit"
ZHENZHEN_IMAGE_GK_V2_REGION_SELECTION_MODES = [
    "object_indices",
    "boxes",
    "selection_regions",
]


class _FallbackFile3D:
    """Test-only fallback matching the native File3D methods used by ComfyUI."""

    def __init__(self, source: Any, file_format: str = ""):
        self._source = source
        self._format = file_format.lstrip(".").lower() or self._infer_format()

    def _infer_format(self) -> str:
        if isinstance(self._source, str):
            return Path(self._source).suffix.lstrip(".").lower()
        return ""

    @property
    def format(self) -> str:
        return self._format

    @property
    def is_disk_backed(self) -> bool:
        return isinstance(self._source, str)

    def get_source(self):
        if hasattr(self._source, "seek"):
            self._source.seek(0)
        return self._source

    def get_bytes(self) -> bytes:
        if isinstance(self._source, str):
            return Path(self._source).read_bytes()
        self._source.seek(0)
        return self._source.read()

    def save_to(self, path: str) -> str:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(self._source, str):
            source = Path(self._source)
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
        else:
            self._source.seek(0)
            destination.write_bytes(self._source.read())
        return str(destination)


File3D = _ComfyTypes.File3D if _ComfyTypes is not None else _FallbackFile3D


def file3d_from_path(path: str):
    return File3D(str(path), file_format="glb")


def minimal_glb_bytes(label: str = "Zhenzhen placeholder") -> bytes:
    document = {
        "asset": {"version": "2.0", "generator": "ComfyUI-Zhenzhen"},
        "scene": 0,
        "scenes": [{"nodes": []}],
        "nodes": [],
        "extras": {"message": str(label or "Zhenzhen placeholder")[:240]},
    }
    json_chunk = json.dumps(
        document, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    total_length = 12 + 8 + len(json_chunk)
    return (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
    )


def placeholder_file3d(message: str = "Hunyuan 3D generation failed"):
    return File3D(io.BytesIO(minimal_glb_bytes(message)), file_format="glb")


def _progress_bar():
    if COMFYUI_AVAILABLE:
        return comfy.utils.ProgressBar(100)
    return None


def _update_progress(progress: Any, value: float) -> None:
    if progress is not None:
        try:
            progress.update_absolute(int(value), 100)
        except Exception:
            pass


def _response_json(response: Any) -> Dict[str, Any]:
    try:
        value = response.json() if response.text else {}
    except ValueError:
        value = {}
    return value if isinstance(value, dict) else {}


def _task_record(value: Dict[str, Any]) -> Dict[str, Any]:
    data = value.get("data") if isinstance(value, dict) else None
    return data if isinstance(data, dict) else value


def submit_3d_task(payload: Dict[str, Any], config: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    url = f"{config['base_url']}/v1/3d/generations"
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            time.sleep(min(2 ** attempt + 1, 15))
        try:
            response = _get_session().post(
                url,
                headers=_headers(config["api_key"]),
                json=payload,
                timeout=config.get("timeout", 60),
            )
        except requests.ConnectTimeout as error:
            last_error = f"network error: {type(error).__name__}: {error}"
            continue
        except requests.RequestException as error:
            raise RuntimeError(
                "3D submit transport failed after the request may have reached the "
                "server; it was not retried to avoid a duplicate paid task. "
                f"Check the provider console before retrying: {type(error).__name__}: {error}"
            ) from error

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                f"3D submit rejected (HTTP {response.status_code}): {message}"
            )
        record = _task_record(data)
        task_id = (
            data.get("task_id")
            or data.get("id")
            or record.get("task_id")
            or record.get("id")
        )
        if not task_id:
            raise SeedanceLowPriceError("3D submit response did not contain task_id/id")
        return str(task_id), data
    raise RuntimeError(f"3D submit failed after 3 attempts: {last_error}")


def poll_3d_task(
    task_id: str,
    config: Dict[str, Any],
    on_progress: Optional[Any] = None,
) -> Dict[str, Any]:
    url = f"{config['base_url']}/v1/3d/generations/{task_id}"
    start = time.monotonic()
    failures = 0
    success = {"SUCCESS", "SUCCEEDED", "COMPLETED"}
    failed = {"FAILURE", "FAILED", "CANCELLED", "CANCELED"}
    while True:
        if time.monotonic() - start > config.get("max_poll_time", 1800):
            raise RuntimeError(f"3D polling timed out [task_id: {task_id}]")
        time.sleep(config.get("poll_interval", 4))
        try:
            response = _get_session().get(
                url,
                headers=_headers(config["api_key"], json_content=False),
                timeout=30,
            )
        except requests.RequestException:
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"3D polling failed after repeated network errors [task_id: {task_id}]"
                )
            time.sleep(min(failures * 2, 10))
            continue

        if response.status_code != 200:
            data = _response_json(response)
            message = extract_error_message(data, response.text[:300])
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise SeedanceLowPriceError(
                    f"3D polling rejected (HTTP {response.status_code}): {message} "
                    f"[task_id: {task_id}]"
                )
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"3D polling repeatedly returned HTTP {response.status_code}: {message} "
                    f"[task_id: {task_id}]"
                )
            time.sleep(min(failures * 2, 10))
            continue

        result = _response_json(response)
        failures = 0
        record = _task_record(result)
        status = str(record.get("status") or result.get("status") or "").strip().upper()
        raw_progress = record.get("progress") or result.get("progress")
        if on_progress is not None and raw_progress is not None:
            try:
                on_progress(max(0, min(100, int(str(raw_progress).rstrip("%")))))
            except (TypeError, ValueError):
                pass
        if status in success:
            return result
        if status in failed:
            reason = extract_error_message(record, "3D generation failed")
            raise SeedanceLowPriceError(
                f"3D task failed: {reason} [task_id: {task_id}]"
            )


def extract_3d_url(final_response: Dict[str, Any]) -> str:
    candidates: List[tuple[int, int, str]] = []

    def visit(value: Any, path: str = "root") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}")
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
            return
        if not isinstance(value, str):
            return
        url = value.strip()
        if not url.startswith(("http://", "https://")):
            return
        score = 0
        if urlsplit(url).path.lower().endswith(".glb"):
            score += 100
        if ".file_urls[" in path:
            score += 20
        if path.endswith(".file_url"):
            score += 10
        if path.endswith(".result_url"):
            score += 5
        candidates.append((score, len(candidates), url))

    visit(final_response)
    if not candidates:
        raise SeedanceLowPriceError("3D task completed but no model URL was returned")
    return max(candidates, key=lambda item: (item[0], -item[1]))[2]


def _validate_glb(path: str) -> None:
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        header = handle.read(12)
    if len(header) != 12 or header[:4] != b"glTF":
        raise SeedanceLowPriceError("Downloaded 3D result is not a GLB file")
    version = int.from_bytes(header[4:8], "little")
    declared_length = int.from_bytes(header[8:12], "little")
    if version != 2 or declared_length != size:
        raise SeedanceLowPriceError("Downloaded GLB header is invalid or incomplete")


def download_glb(url: str, max_retries: int = 5, attempt_timeout: float = 300.0) -> str:
    try:
        import folder_paths

        output_dir = folder_paths.get_output_directory()
    except ImportError:
        output_dir = os.environ.get("SEEDANCE_OUTPUT_DIR") or tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"hunyuan3d_{uuid.uuid4().hex[:12]}.glb")
    part_path = f"{path}.part"
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        if attempt:
            time.sleep(min(2 ** attempt, 15))
        response = None
        try:
            started = time.monotonic()
            response = get_media_response(
                url,
                request_get=_get_session().get,
                direct_get=direct_media_get,
                headers={"User-Agent": "ComfyUI-Zhenzhen/2.0", "Accept": "model/gltf-binary,*/*"},
                stream=True,
                timeout=media_download_timeout(attempt_timeout),
                allow_redirects=True,
            )
            response.raise_for_status()
            with open(part_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    if chunk:
                        handle.write(chunk)
                    if time.monotonic() - started > attempt_timeout:
                        raise TimeoutError(
                            f"GLB download exceeded {attempt_timeout:.0f}s attempt limit"
                        )
            if not os.path.isfile(part_path) or os.path.getsize(part_path) == 0:
                raise RuntimeError("Downloaded GLB is empty")
            _validate_glb(part_path)
            os.replace(part_path, path)
            return path
        except Exception as error:
            last_error = error
            try:
                os.remove(part_path)
            except OSError:
                pass
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    try:
        os.remove(path)
    except OSError:
        pass
    raise RuntimeError(f"GLB download failed after {max_retries} attempts: {last_error}")


def extract_image_operation_result(final_response: Dict[str, Any]) -> Dict[str, Any]:
    task_data = final_response.get("data") if isinstance(final_response, dict) else None
    containers: List[Any] = [task_data]
    if isinstance(task_data, dict):
        containers.extend((task_data.get("data"), task_data.get("content")))
        upstream = task_data.get("data")
        if isinstance(upstream, dict):
            containers.append(upstream.get("content"))
    for container in containers:
        if isinstance(container, dict) and isinstance(container.get("result"), dict):
            return container["result"]
    raise SeedanceLowPriceError(
        "Image utility task completed but no result object was returned"
    )


def extract_region_edit_url(final_response: Dict[str, Any]) -> str:
    try:
        return extract_image_url(final_response)
    except SeedanceLowPriceError:
        result = extract_image_operation_result(final_response)
        for key in ("image_url", "result_url", "url"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise SeedanceLowPriceError("Region edit completed but no image URL was returned")


class Comfly_zhenzhen_video_g_omni_flash_lowprice_v2(_Comfly_apimart_video_base):
    """Documented low-price text, frame, image-reference, and video-reference modes."""

    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            f"image{index}": ("IMAGE",) for index in range(1, 4)
        }
        optional.update(
            {
                "input_video": (VIDEO_TYPE,),
                "video_url": ("STRING", {"default": ""}),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            }
        )
        return {
            "required": {
                "mode": (
                    ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_MODES,
                    {"default": "text"},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (
                    ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_SECONDS,
                    {"default": "6"},
                ),
                "resolution": (
                    ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_RESOLUTIONS,
                    {"default": "720p"},
                ),
                "aspect_ratio": (
                    ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_RATIOS,
                    {"default": "16:9"},
                ),
                "nsfw_check": ("BOOLEAN", {"default": False}),
            },
            "optional": optional,
        }

    FUNCTION = "generate"

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        mode=None,
        prompt=None,
        seconds=None,
        resolution=None,
        aspect_ratio=None,
        video_url=None,
        strict=False,
        **kwargs,
    ):
        if mode not in (None, *ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_MODES):
            return f"Unsupported Omni Lowprice mode: {mode}"
        if seconds is not None and str(seconds) not in ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_SECONDS:
            return "Omni Lowprice seconds must be 4, 6, 8, or 10"
        if resolution not in (None, *ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_RESOLUTIONS):
            return f"Unsupported Omni Lowprice resolution: {resolution}"
        if aspect_ratio not in (None, *ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_RATIOS):
            return f"Unsupported Omni Lowprice aspect_ratio: {aspect_ratio}"
        prompt_text = str(prompt or "").strip()
        if strict and not prompt_text:
            return "Omni Lowprice prompt is required"
        if len(prompt_text) > PROMPT_MAX_LENGTH:
            return f"Omni Lowprice prompt exceeds {PROMPT_MAX_LENGTH} characters"
        direct_url = str(video_url or "").strip()
        if direct_url:
            parsed = urlsplit(direct_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return "Omni Lowprice video_url must be an http(s) URL"
        if not strict:
            return True

        image_slots = [
            index for index in range(1, 4) if kwargs.get(f"image{index}") is not None
        ]
        has_local_video = kwargs.get("input_video") is not None
        if mode == "text":
            if image_slots or has_local_video or direct_url:
                return "Omni text mode does not accept reference media"
        elif mode == "frame":
            if image_slots != [1] or has_local_video or direct_url:
                return "Omni frame mode requires exactly image1"
        elif mode == "reference_images":
            if len(image_slots) not in {1, 3} or image_slots != list(
                range(1, len(image_slots) + 1)
            ):
                return "Omni reference_images mode requires image1 or image1..image3"
            if has_local_video or direct_url:
                return "Omni reference_images mode does not accept video"
        elif mode == "reference_video":
            if image_slots:
                return "Omni reference_video mode does not accept images"
            if has_local_video == bool(direct_url):
                return "Omni reference_video mode requires exactly one input_video or video_url"
        return True

    @staticmethod
    def build_payload(values: Dict[str, Any], media: Dict[str, Any]) -> Dict[str, Any]:
        mode = values["mode"]
        payload: Dict[str, Any] = {
            "model": ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_MODEL,
            "prompt": str(values["prompt"]).strip(),
            "resolution": values["resolution"],
            "aspect_ratio": values["aspect_ratio"],
            "nsfw_check": bool(values["nsfw_check"]),
        }
        if mode != "reference_video":
            payload["seconds"] = str(values["seconds"])
        if mode == "frame":
            payload["generation_type"] = "frame"
            payload["images"] = list(media["images"])
        elif mode == "reference_images":
            payload["generation_type"] = "reference"
            payload["images"] = list(media["images"])
        elif mode == "reference_video":
            payload["metadata"] = {"video_url": media["video_url"]}
        return payload

    def generate(
        self,
        mode: str,
        prompt: str,
        seconds: str,
        resolution: str,
        aspect_ratio: str,
        nsfw_check: bool,
        input_video: Any = None,
        video_url: str = "",
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        progress = _progress_bar()
        values = {
            "mode": mode,
            "prompt": prompt,
            "seconds": seconds,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "nsfw_check": nsfw_check,
            "input_video": input_video,
            "video_url": video_url,
            **kwargs,
        }
        try:
            validation = self.VALIDATE_INPUTS(strict=True, **values)
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            media: Dict[str, Any] = {}
            if mode in ("frame", "reference_images"):
                images = [
                    kwargs[f"image{index}"]
                    for index in range(1, 4)
                    if kwargs.get(f"image{index}") is not None
                ]
                image_urls = []
                for index, image in enumerate(images, 1):
                    image_urls.append(
                        upload_media(
                            image_to_png_bytes(image),
                            f"zhenzhen_omni_lowprice_reference_{index}.png",
                            "image/png",
                            config,
                        )
                    )
                    _update_progress(progress, index / len(images) * 15)
                media["images"] = image_urls
            elif mode == "reference_video":
                direct_url = str(video_url or "").strip()
                if direct_url:
                    media["video_url"] = direct_url
                else:
                    media["video_url"] = upload_media(
                        video_to_mp4_bytes(input_video),
                        "zhenzhen_omni_lowprice_reference.mp4",
                        "video/mp4",
                        config,
                    )
                _update_progress(progress, 15)
            payload = self.build_payload(values, media)
            return self._finish_video(payload, config, task_id, progress)
        except Exception as error:
            if not skip_error:
                raise
            return self._error_result(
                ZHENZHEN_VIDEO_G_OMNI_FLASH_LOWPRICE_MODEL, task_id, error
            )


class Comfly_hunyuan3d_v3_1_lowprice:
    COMFLY_CONCURRENT_DISABLED = True
    CATEGORY = "zhenzhen/Seedance2 Low Price/3D"
    FUNCTION = "generate"
    OUTPUT_NODE = True
    RETURN_TYPES = ("FILE_3D_GLB", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("model_3d", "model_url", "local_path", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            f"image{index}": ("IMAGE",) for index in range(1, 9)
        }
        optional.update(
            {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            }
        )
        return {
            "required": {
                "model": (HUNYUAN3D_MODELS, {"default": HUNYUAN3D_TEXT_MODEL}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "face_count": (
                    "INT",
                    {
                        "default": 500000,
                        "min": 10000,
                        "max": 1500000,
                        "step": 10000,
                    },
                ),
                "enable_pbr": ("BOOLEAN", {"default": False}),
                "generate_type": (
                    HUNYUAN3D_GENERATE_TYPES,
                    {"default": "Normal"},
                ),
            },
            "optional": optional,
        }

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt=None,
        face_count=None,
        generate_type=None,
        strict=False,
        **kwargs,
    ):
        if model not in (None, *HUNYUAN3D_MODELS):
            return f"Unsupported Hunyuan 3D model: {model}"
        if face_count is not None:
            try:
                value = int(face_count)
            except (TypeError, ValueError):
                return "Hunyuan 3D face_count must be an integer"
            if not 10000 <= value <= 1500000:
                return "Hunyuan 3D face_count must be between 10000 and 1500000"
        if generate_type not in (None, *HUNYUAN3D_GENERATE_TYPES):
            return f"Unsupported Hunyuan 3D generate_type: {generate_type}"
        if not strict:
            return True
        if not str(prompt or "").strip():
            return "Hunyuan 3D prompt is required"
        slots = [index for index in range(1, 9) if kwargs.get(f"image{index}") is not None]
        if model == HUNYUAN3D_TEXT_MODEL and slots:
            return "Hunyuan text-to-3D does not accept images"
        if model == HUNYUAN3D_IMAGE_MODEL:
            if not slots:
                return "Hunyuan image-to-3D requires 1 to 8 images"
            if slots != list(range(1, len(slots) + 1)):
                return "Hunyuan image views must be connected contiguously from image1"
        return True

    def generate(
        self,
        model: str,
        prompt: str,
        face_count: int,
        enable_pbr: bool,
        generate_type: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        try:
            validation = self.VALIDATE_INPUTS(
                model=model,
                prompt=prompt,
                face_count=face_count,
                generate_type=generate_type,
                strict=True,
                **kwargs,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            progress = _progress_bar()
            images = [
                kwargs[f"image{index}"]
                for index in range(1, 9)
                if kwargs.get(f"image{index}") is not None
            ]
            image_urls = []
            for index, image in enumerate(images, 1):
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image),
                        f"hunyuan3d_{HUNYUAN3D_IMAGE_VIEWS[index - 1]}.png",
                        "image/png",
                        config,
                    )
                )
                _update_progress(progress, index / len(images) * 15)
            payload: Dict[str, Any] = {
                "model": model,
                "prompt": str(prompt).strip(),
                "face_count": int(face_count),
                "enable_pbr": bool(enable_pbr),
                "generate_type": generate_type,
            }
            if image_urls:
                payload["images"] = image_urls
            task_id, submitted = submit_3d_task(payload, config)
            _update_progress(progress, 20)
            final = poll_3d_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            model_url = extract_3d_url(final)
            local_path = download_glb(model_url)
            model_3d = file3d_from_path(local_path)
            _update_progress(progress, 100)
            response = json.dumps(
                {
                    "status": "SUCCESS",
                    "model": model,
                    "task_id": task_id,
                    "submit": submitted,
                    "result": final,
                },
                ensure_ascii=False,
                indent=2,
            )
            return {
                "ui": {"text": [model_url, local_path, response]},
                "result": (model_3d, model_url, local_path, task_id, response),
            }
        except Exception as error:
            if not skip_error:
                raise
            message = f"{type(error).__name__}: {error}"
            response = json.dumps(
                {"status": "error", "model": model, "message": message},
                ensure_ascii=False,
                indent=2,
            )
            return {
                "ui": {"text": ["", "", response]},
                "result": (placeholder_file3d(message), "", "", task_id, response),
            }


class Comfly_zhenzhen_image_gk_v2_segment_lowprice:
    COMFLY_CONCURRENT_DISABLED = True
    CATEGORY = "zhenzhen/Seedance2 Low Price/Image Tools"
    FUNCTION = "segment"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_id", "objects_json", "result_json", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_task_id": ("STRING", {"forceInput": True}),
                "include_mask_rle": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, source_task_id=None, strict=False, **kwargs):
        if strict and not str(source_task_id or "").strip():
            return "GK v2 Segment source_task_id is required"
        return True

    def segment(
        self,
        source_task_id: str,
        include_mask_rle: bool,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        try:
            validation = self.VALIDATE_INPUTS(
                source_task_id=source_task_id, strict=True
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            payload = {
                "model": ZHENZHEN_IMAGE_GK_V2_SEGMENT_MODEL,
                "operation": "segment",
                "source_task_id": str(source_task_id).strip(),
                "include_mask_rle": bool(include_mask_rle),
            }
            task_id, submitted = submit_image_task(payload, config)
            final = poll_image_task(task_id, config)
            result = extract_image_operation_result(final)
            image_id = str(result.get("image_id") or "").strip()
            if not image_id:
                raise SeedanceLowPriceError("Segment task completed without image_id")
            objects_json = json.dumps(
                result.get("objects") or [], ensure_ascii=False, indent=2
            )
            result_json = json.dumps(result, ensure_ascii=False, indent=2)
            response = json.dumps(
                {
                    "status": "SUCCESS",
                    "model": ZHENZHEN_IMAGE_GK_V2_SEGMENT_MODEL,
                    "task_id": task_id,
                    "submit": submitted,
                    "result": final,
                },
                ensure_ascii=False,
                indent=2,
            )
            return {
                "ui": {"text": [objects_json, response]},
                "result": (image_id, objects_json, result_json, task_id, response),
            }
        except Exception as error:
            if not skip_error:
                raise
            message = f"{type(error).__name__}: {error}"
            response = json.dumps(
                {
                    "status": "error",
                    "model": ZHENZHEN_IMAGE_GK_V2_SEGMENT_MODEL,
                    "message": message,
                },
                ensure_ascii=False,
                indent=2,
            )
            return {
                "ui": {"text": ["[]", response]},
                "result": ("", "[]", "{}", "", response),
            }


class Comfly_zhenzhen_image_gk_v2_region_edit_lowprice:
    CATEGORY = "zhenzhen/Seedance2 Low Price/Image Tools"
    FUNCTION = "edit"
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_id": ("STRING", {"forceInput": True}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "selection_mode": (
                    ZHENZHEN_IMAGE_GK_V2_REGION_SELECTION_MODES,
                    {"default": "object_indices"},
                ),
                "selection_json": (
                    "STRING",
                    {"multiline": True, "default": "[0]"},
                ),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    @staticmethod
    def parse_selection(selection_mode: str, selection_json: str) -> List[Any]:
        try:
            value = json.loads(str(selection_json or ""))
        except json.JSONDecodeError as error:
            raise SeedanceLowPriceError(
                f"selection_json is invalid JSON: {error.msg}"
            ) from error
        if not isinstance(value, list) or not value:
            raise SeedanceLowPriceError("selection_json must be a non-empty JSON list")
        if selection_mode == "object_indices":
            if any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0
                for item in value
            ):
                raise SeedanceLowPriceError(
                    "object_indices must contain non-negative integers"
                )
        elif selection_mode == "boxes":
            if any(
                not isinstance(item, list)
                or not item
                or any(
                    isinstance(number, bool)
                    or not isinstance(number, (int, float))
                    for number in item
                )
                for item in value
            ):
                raise SeedanceLowPriceError(
                    "boxes must be a JSON list of numeric lists"
                )
        elif selection_mode == "selection_regions":
            if any(not isinstance(item, dict) for item in value):
                raise SeedanceLowPriceError(
                    "selection_regions must be a JSON list of objects"
                )
        else:
            raise SeedanceLowPriceError(
                f"Unsupported selection_mode: {selection_mode}"
            )
        return value

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        image_id=None,
        prompt=None,
        selection_mode=None,
        selection_json=None,
        strict=False,
        **kwargs,
    ):
        if selection_mode not in (
            None,
            *ZHENZHEN_IMAGE_GK_V2_REGION_SELECTION_MODES,
        ):
            return f"Unsupported selection_mode: {selection_mode}"
        if not strict:
            return True
        if not str(image_id or "").strip():
            return "GK v2 Region Edit image_id is required"
        if not str(prompt or "").strip():
            return "GK v2 Region Edit prompt is required"
        try:
            cls.parse_selection(str(selection_mode), str(selection_json or ""))
        except SeedanceLowPriceError as error:
            return str(error)
        return True

    def edit(
        self,
        image_id: str,
        prompt: str,
        selection_mode: str,
        selection_json: str,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        try:
            validation = self.VALIDATE_INPUTS(
                image_id=image_id,
                prompt=prompt,
                selection_mode=selection_mode,
                selection_json=selection_json,
                strict=True,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            payload = {
                "model": ZHENZHEN_IMAGE_GK_V2_REGION_EDIT_MODEL,
                "operation": "region_edit",
                "image_id": str(image_id).strip(),
                "prompt": str(prompt).strip(),
                selection_mode: self.parse_selection(
                    selection_mode, selection_json
                ),
            }
            config = resolve_config(api_config)
            progress = _progress_bar()
            task_id, submitted = submit_image_task(payload, config)
            _update_progress(progress, 20)
            final = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: _update_progress(
                    progress, 20 + value * 0.75
                ),
            )
            image_url = extract_region_edit_url(final)
            image = download_image(image_url)
            _update_progress(progress, 100)
            response = json.dumps(
                {
                    "status": "SUCCESS",
                    "model": ZHENZHEN_IMAGE_GK_V2_REGION_EDIT_MODEL,
                    "task_id": task_id,
                    "submit": submitted,
                    "result": final,
                },
                ensure_ascii=False,
                indent=2,
            )
            return image, image_url, task_id, response
        except Exception as error:
            if not skip_error:
                raise
            response = json.dumps(
                {
                    "status": "error",
                    "model": ZHENZHEN_IMAGE_GK_V2_REGION_EDIT_MODEL,
                    "message": f"{type(error).__name__}: {error}",
                },
                ensure_ascii=False,
                indent=2,
            )
            return torch.ones((1, 512, 512, 3), dtype=torch.float32), "", task_id, response


__all__ = [
    "Comfly_zhenzhen_video_g_omni_flash_lowprice_v2",
    "Comfly_hunyuan3d_v3_1_lowprice",
    "Comfly_zhenzhen_image_gk_v2_segment_lowprice",
    "Comfly_zhenzhen_image_gk_v2_region_edit_lowprice",
]

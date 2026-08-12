"""Low-price Seedance settings and unified media generation nodes."""

from __future__ import annotations

import io
import json
import mimetypes
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import requests
import torch
from PIL import Image

try:
    from .media_download import (
        direct_media_get,
        download_image_with_alpha_retry,
        download_image_with_retry,
        get_media_response,
        media_download_timeout,
    )
except ImportError:
    from media_download import (
        direct_media_get,
        download_image_with_alpha_retry,
        download_image_with_retry,
        get_media_response,
        media_download_timeout,
    )

try:
    import comfy.utils
    from comfy.comfy_types import IO

    VIDEO_TYPE = IO.VIDEO
    AUDIO_TYPE = IO.AUDIO
    COMFYUI_AVAILABLE = True
except ImportError:
    VIDEO_TYPE = "VIDEO"
    AUDIO_TYPE = "AUDIO"
    COMFYUI_AVAILABLE = False


DEFAULT_BASE_URL = "https://api.seedance.nz"
CONFIG_TYPE = "ZHENZHEN_SEEDANCE2_CONFIG"
BUNDLED_ROOT_YR_CERT = (
    Path(__file__).resolve().parent / "certs" / "root-yr-by-x1.pem"
)
PROMPT_MAX_LENGTH = 20480
IMAGE_MAX_BYTES = 30 * 1024 * 1024
MEDIA_MAX_BYTES = 50 * 1024 * 1024
DOMESTIC_FAST_AUDIO_MAX_BYTES = 15 * 1024 * 1024
SECONDS = ["-1"] + [str(value) for value in range(4, 16)]
RESOLUTIONS = ["480p", "720p", "1080p", "2k", "4k", "native1080p", "native4k"]
RATIOS = ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]
MODES = ["text_to_video", "image_to_video", "multimodal_video"]
REGIONS = ["domestic", "global"]
TIERS = ["mini", "fast", "standard"]
MODE_SUFFIXES = {
    "text_to_video": "t2v",
    "image_to_video": "i2v",
    "multimodal_video": "multi",
}

SEEDANCE25_T2V_MODELS = [
    "seedance-2.5-standard-t2v",
    "seedance-2.5-global-standard-t2v",
]
SEEDANCE25_I2V_MODELS = [
    "seedance-2.5-standard-i2v",
    "seedance-2.5-global-standard-i2v",
]
SEEDANCE25_MULTI_MODELS = [
    "seedance-2.5-standard-multi",
    "seedance-2.5-global-standard-multi",
]
SEEDANCE25_MODELS = [
    "seedance-2.5-standard-t2v",
    "seedance-2.5-standard-i2v",
    "seedance-2.5-standard-multi",
    "seedance-2.5-global-standard-t2v",
    "seedance-2.5-global-standard-i2v",
    "seedance-2.5-global-standard-multi",
]
SEEDANCE25_SECONDS = ["-1"] + [str(value) for value in range(4, 31)]
SEEDANCE25_RESOLUTIONS = ["480p", "720p", "1080p", "2k", "4k"]
SEEDANCE25_MAX_IMAGES = 30
SEEDANCE25_MAX_VIDEOS = 10
SEEDANCE25_MAX_AUDIOS = 10
SEEDANCE25_MAX_REFERENCES = 50
SEEDANCE25_MEDIA_MIN_SECONDS = 2.0
SEEDANCE25_MEDIA_MAX_SECONDS = 30.0
SEEDANCE25_MEDIA_TOTAL_MAX_SECONDS = 30.0


class SeedanceLowPriceError(RuntimeError):
    """Non-retryable Seedance API or input error."""


def normalize_base_url(value: str) -> str:
    raw = str(value or DEFAULT_BASE_URL).strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SeedanceLowPriceError(
            f"Invalid Seedance base_url '{raw}'. Expected an http(s) site root."
        )

    path = parsed.path.rstrip("/")
    if parsed.netloc.lower() == "api.seedance.nz" and path.lower().startswith("/docs"):
        path = ""
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _unwrap_api_config(api_config: Any) -> Optional[Dict[str, Any]]:
    value = api_config
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    return value if isinstance(value, dict) else None


def resolve_config(api_config: Any = None) -> Dict[str, Any]:
    """Resolve an explicit workflow setting, then optional environment values."""
    settings = _unwrap_api_config(api_config)
    source = ""
    base_url = ""
    api_key = ""

    if settings is not None:
        base_url = str(settings.get("base_url") or "").strip()
        api_key = str(settings.get("api_key") or settings.get("apiKey") or "").strip()
        if not api_key:
            raise SeedanceLowPriceError(
                "Connected Seedance 2.0 Low Price Settings has an empty api_key."
            )
        source = "settings_node"

    if not api_key:
        api_key = str(os.environ.get("SEEDANCE_API_KEY") or "").strip()
        base_url = str(os.environ.get("SEEDANCE_BASE_URL") or "").strip()
        if api_key:
            source = "environment"

    if not api_key:
        raise SeedanceLowPriceError(
            "Seedance API key is required. Connect the Low Price Settings node, "
            "enter its key in the workflow, or set SEEDANCE_API_KEY."
        )

    config = {
        "base_url": normalize_base_url(base_url or DEFAULT_BASE_URL),
        "api_key": api_key,
        "timeout": int(os.environ.get("SEEDANCE_TIMEOUT", "60")),
        "upload_timeout": int(os.environ.get("SEEDANCE_UPLOAD_TIMEOUT", "180")),
        "poll_interval": float(os.environ.get("SEEDANCE_POLL_INTERVAL", "4")),
        "max_poll_time": int(os.environ.get("SEEDANCE_MAX_POLL_TIME", "1800")),
    }
    print(f"[Seedance Low Price] Config source={source}, base_url={config['base_url']}")
    return config


class Comfly_seedance2_low_price_settings:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {"default": DEFAULT_BASE_URL}),
                "api_key": ("STRING", {"default": ""}),
            }
        }

    RETURN_TYPES = (CONFIG_TYPE,)
    RETURN_NAMES = ("api_config",)
    FUNCTION = "build"
    CATEGORY = "zhenzhen/Seedance2 Low Price"

    def build(self, base_url: str, api_key: str):
        normalized_base = normalize_base_url(base_url)
        normalized_key = str(api_key or "").strip()
        print(f"[Seedance Low Price Settings] Using workflow config for {normalized_base}")
        return ({"base_url": normalized_base, "api_key": normalized_key},)


class _SSLContextAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, context: ssl.SSLContext, **kwargs):
        self._context = context
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._context
        return super().proxy_manager_for(*args, **kwargs)


_SESSION_LOCAL = threading.local()


def _get_session() -> requests.Session:
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is not None:
        return session

    if not BUNDLED_ROOT_YR_CERT.is_file():
        raise RuntimeError(
            f"Bundled TLS certificate is missing: {BUNDLED_ROOT_YR_CERT.name}"
        )

    context = ssl.create_default_context(cafile=requests.certs.where())
    context.load_verify_locations(cafile=str(BUNDLED_ROOT_YR_CERT))

    session = requests.Session()
    session.mount(
        f"{DEFAULT_BASE_URL}/",
        _SSLContextAdapter(
            context,
            pool_connections=8,
            pool_maxsize=30,
            pool_block=True,
        ),
    )
    _SESSION_LOCAL.session = session
    return session


def _headers(api_key: str, json_content: bool = True) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def extract_error_message(data: Any, fallback: str = "") -> str:
    if isinstance(data, list):
        messages = [extract_error_message(item, "") for item in data[:3]]
        return "; ".join(message for message in messages if message) or fallback
    if not isinstance(data, dict):
        return str(data) if data not in (None, "") else fallback

    error = data.get("error")
    if error:
        message = extract_error_message(error, "")
        if message:
            return message

    for key in ("message", "msg", "detail", "code"):
        value = data.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            message = extract_error_message(value, "")
            if message:
                return message
        text = str(value)
        if text.lstrip().startswith(("{", "[")):
            try:
                nested = json.loads(text)
                message = extract_error_message(nested, "")
                if message:
                    return message
            except (TypeError, ValueError):
                pass
        return text
    return fallback


def _response_json(response: requests.Response) -> Any:
    try:
        return response.json() if response.text else {}
    except ValueError:
        return {}


def upload_media(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    url = f"{config['base_url']}/v1/files/upload"
    last_error = "unknown error"
    for attempt in range(5):
        if attempt:
            sleep(min(2 ** attempt, 15))
        try:
            response = _get_session().post(
                url,
                headers=_headers(config["api_key"], json_content=False),
                files={"file": (filename, file_bytes, mime_type)},
                timeout=config.get("upload_timeout", 180),
            )
        except requests.RequestException as exc:
            last_error = f"network error: {type(exc).__name__}: {exc}"
            continue

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429:
            last_error = f"rate limited: {message}"
            sleep(30)
            continue
        if response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                f"Upload rejected (HTTP {response.status_code}): {message}"
            )
        file_url = data.get("url") if isinstance(data, dict) else None
        if not file_url:
            last_error = "upload response did not contain url"
            continue
        return str(file_url)
    raise RuntimeError(f"Upload failed after 5 attempts: {last_error}")


def submit_task(
    payload: Dict[str, Any],
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Tuple[str, Dict[str, Any]]:
    url = f"{config['base_url']}/v1/videos"
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            sleep(min(2 ** attempt + 1, 15))
        try:
            response = _get_session().post(
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
                "Submit transport failed after the request may have reached the server; "
                "it was not retried to avoid creating a duplicate paid task. "
                f"Check the provider console before retrying manually: {type(exc).__name__}: {exc}"
            ) from exc

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                f"Submit rejected (HTTP {response.status_code}): {message}"
            )
        task_id = (data.get("id") or data.get("task_id")) if isinstance(data, dict) else None
        if not task_id:
            raise SeedanceLowPriceError("Submit response did not contain id/task_id")
        return str(task_id), data
    raise RuntimeError(f"Submit failed after 3 attempts: {last_error}")


def _coerce_progress(value: Any) -> Optional[int]:
    try:
        return max(0, min(100, int(str(value).strip().rstrip("%"))))
    except (TypeError, ValueError):
        return None


def poll_task(
    task_id: str,
    config: Dict[str, Any],
    on_progress: Optional[Callable[[int], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    url = f"{config['base_url']}/v1/videos/{task_id}"
    start = clock()
    failures = 0
    while True:
        if clock() - start > config.get("max_poll_time", 1800):
            raise RuntimeError(f"Polling timed out [task_id: {task_id}]")
        sleep(config.get("poll_interval", 4))
        try:
            response = _get_session().get(
                url,
                headers=_headers(config["api_key"], json_content=False),
                timeout=30,
            )
        except requests.RequestException:
            failures += 1
            if failures >= 6:
                raise RuntimeError(f"Polling failed after repeated network errors [task_id: {task_id}]")
            sleep(min(failures * 2, 10))
            continue

        if response.status_code != 200:
            data = _response_json(response)
            message = extract_error_message(data, response.text[:300])
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise SeedanceLowPriceError(
                    f"Polling rejected (HTTP {response.status_code}): {message} "
                    f"[task_id: {task_id}]"
                )
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"Polling repeatedly returned HTTP {response.status_code}: {message} "
                    f"[task_id: {task_id}]"
                )
            sleep(min(failures * 2, 10))
            continue
        try:
            data = response.json()
        except ValueError:
            failures += 1
            if failures >= 6:
                raise RuntimeError(f"Polling repeatedly returned invalid JSON [task_id: {task_id}]")
            continue

        failures = 0
        status = str(data.get("status") or "").strip().lower()
        progress = _coerce_progress(data.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        if status == "completed":
            return data
        if status == "failed":
            message = extract_error_message(data, "video generation failed")
            raise SeedanceLowPriceError(f"Task failed: {message} [task_id: {task_id}]")


def extract_video_url(response: Dict[str, Any]) -> str:
    metadata = response.get("metadata")
    if isinstance(metadata, dict) and metadata.get("url"):
        return str(metadata["url"])
    for key in ("url", "video_url"):
        if response.get(key):
            return str(response[key])
    raise SeedanceLowPriceError("Completed task response did not contain a video URL")


def _video_from_path(path: str) -> Any:
    try:
        from comfy_api.input_impl import VideoFromFile

        return VideoFromFile(path)
    except ImportError:
        return path


def download_video(
    url: str,
    max_retries: int = 5,
    attempt_timeout: float = 180.0,
) -> Any:
    try:
        import folder_paths

        output_dir = folder_paths.get_output_directory()
    except ImportError:
        output_dir = os.environ.get("SEEDANCE_OUTPUT_DIR") or tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"seedance_low_price_{uuid.uuid4().hex[:12]}.mp4")
    part_path = f"{path}.part"
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        if attempt:
            time.sleep(2 ** attempt)
        response = None
        try:
            started = time.monotonic()
            response = get_media_response(
                url,
                request_get=_get_session().get,
                direct_get=direct_media_get,
                stream=True,
                timeout=media_download_timeout(45),
            )
            response.raise_for_status()
            with open(part_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)
                    if time.monotonic() - started > attempt_timeout:
                        raise TimeoutError(
                            f"video download exceeded {attempt_timeout:.0f}s attempt limit"
                        )
            if not os.path.isfile(part_path) or os.path.getsize(part_path) == 0:
                raise RuntimeError("downloaded video is empty")
            os.replace(part_path, path)
            return _video_from_path(path)
        except Exception as exc:
            last_error = exc
            try:
                os.remove(part_path)
            except OSError:
                pass
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
    for candidate in (part_path, path):
        try:
            os.remove(candidate)
        except OSError:
            pass
    raise RuntimeError(f"Video download failed after {max_retries} attempts: {last_error}")


def image_to_png_bytes(image: Any) -> bytes:
    if image is None:
        raise SeedanceLowPriceError("image input is empty")
    array = image.detach().cpu().numpy() if hasattr(image, "detach") else np.asarray(image)
    if array.ndim == 4:
        if array.shape[0] != 1:
            raise SeedanceLowPriceError(
                "Each image slot accepts exactly one IMAGE; split image batches into separate slots"
            )
        array = array[0]
    if array.ndim != 3 or array.shape[-1] not in (3, 4):
        raise SeedanceLowPriceError(f"Unexpected IMAGE shape: {array.shape}")
    if np.issubdtype(array.dtype, np.floating):
        array = np.clip(array, 0.0, 1.0) * 255.0
    array = array.astype(np.uint8)
    pil_image = Image.fromarray(array)
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    result = buffer.getvalue()
    if len(result) > IMAGE_MAX_BYTES:
        raise SeedanceLowPriceError("Image exceeds the 30MB generation limit")
    return result


def _read_path(path: str) -> Tuple[bytes, str]:
    with open(path, "rb") as handle:
        return handle.read(), Path(path).suffix.lower().lstrip(".")


def video_to_mp4_bytes(value: Any) -> bytes:
    data: Optional[bytes] = None
    extension = ""
    if isinstance(value, str) and os.path.isfile(value):
        data, extension = _read_path(value)
    elif isinstance(value, dict):
        path = value.get("file_path") or value.get("path")
        if isinstance(path, str) and os.path.isfile(path):
            data, extension = _read_path(path)
    elif hasattr(value, "get_stream_source"):
        source = value.get_stream_source()
        if isinstance(source, str) and os.path.isfile(source):
            data, extension = _read_path(source)
        elif hasattr(source, "read"):
            data = source.read()
            extension = "mp4"
            try:
                source.seek(0)
            except Exception:
                pass
    if data is None:
        for attribute in ("path", "file_path"):
            path = getattr(value, attribute, None)
            if isinstance(path, str) and os.path.isfile(path):
                data, extension = _read_path(path)
                break
    if data is None:
        raise SeedanceLowPriceError(
            f"Cannot read VIDEO input of type {type(value).__name__}; connect a Load Video node"
        )
    if extension != "mp4":
        raise SeedanceLowPriceError(
            f"Multimodal generation supports MP4 only; received .{extension or 'unknown'}"
        )
    if len(data) > MEDIA_MAX_BYTES:
        raise SeedanceLowPriceError("Video exceeds the 50MB generation limit")
    try:
        import av

        with av.open(io.BytesIO(data), mode="r") as container:
            video_streams = [stream for stream in container.streams if stream.type == "video"]
            if not video_streams:
                raise ValueError("no video stream")
            if next(container.decode(video=0), None) is None:
                raise ValueError("no decodable video frame")
    except Exception as exc:
        raise SeedanceLowPriceError(f"Invalid or undecodable MP4 input: {exc}") from exc
    return data


def audio_to_wav_bytes(audio: Any) -> bytes:
    if not isinstance(audio, dict) or "waveform" not in audio:
        raise SeedanceLowPriceError("Expected ComfyUI AUDIO with waveform/sample_rate")
    waveform = audio["waveform"]
    array = waveform.detach().cpu().float().numpy() if hasattr(waveform, "detach") else np.asarray(waveform)
    if array.ndim == 3:
        if array.shape[0] != 1:
            raise SeedanceLowPriceError(
                "Each audio slot accepts exactly one AUDIO; split audio batches into separate slots"
            )
        array = array[0]
    if array.ndim == 1:
        array = array[np.newaxis, :]
    if array.ndim != 2:
        raise SeedanceLowPriceError(f"Unexpected AUDIO shape: {array.shape}")
    sample_rate = int(audio.get("sample_rate", 44100))
    pcm = (np.clip(array, -1.0, 1.0) * 32767.0).astype(np.int16)
    interleaved = pcm.T.reshape(-1)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(int(pcm.shape[0]))
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(interleaved.tobytes())
    result = buffer.getvalue()
    if len(result) > MEDIA_MAX_BYTES:
        raise SeedanceLowPriceError("Audio exceeds the 50MB generation limit")
    return result


def _seedance25_video_duration_seconds(value: Any) -> float:
    path: Optional[str] = None
    if isinstance(value, str) and os.path.isfile(value):
        path = value
    elif isinstance(value, dict):
        candidate = value.get("file_path") or value.get("path")
        if isinstance(candidate, str) and os.path.isfile(candidate):
            path = candidate
    if path is None:
        for attribute in ("path", "file_path"):
            candidate = getattr(value, attribute, None)
            if isinstance(candidate, str) and os.path.isfile(candidate):
                path = candidate
                break
    if path is None and hasattr(value, "get_stream_source"):
        source = value.get_stream_source()
        if isinstance(source, str) and os.path.isfile(source):
            path = source

    try:
        import av

        source_value: Any = path
        if source_value is None:
            source_value = io.BytesIO(video_to_mp4_bytes(value))
        with av.open(source_value, mode="r") as container:
            if container.duration is not None:
                duration = float(container.duration) / float(av.time_base)
            else:
                durations = [
                    float(stream.duration * stream.time_base)
                    for stream in container.streams
                    if stream.duration is not None and stream.time_base is not None
                ]
                duration = max(durations, default=0.0)
    except SeedanceLowPriceError:
        raise
    except Exception as exc:
        raise SeedanceLowPriceError(
            f"Could not determine Seedance 2.5 reference video duration: {exc}"
        ) from exc
    if duration <= 0:
        raise SeedanceLowPriceError(
            "Could not determine Seedance 2.5 reference video duration"
        )
    return duration


def _seedance25_audio_duration_seconds(audio: Any) -> float:
    if not isinstance(audio, dict) or "waveform" not in audio:
        raise SeedanceLowPriceError("Expected ComfyUI AUDIO with waveform/sample_rate")
    waveform = audio["waveform"]
    shape = getattr(waveform, "shape", None)
    sample_rate = int(audio.get("sample_rate") or 0)
    if not shape or sample_rate <= 0 or int(shape[-1]) <= 0:
        raise SeedanceLowPriceError(
            "Could not determine Seedance 2.5 reference audio duration"
        )
    return float(shape[-1]) / float(sample_rate)


def _validate_seedance25_media_durations(
    video_slots: List[Tuple[int, Any]],
    audio_slots: List[Tuple[int, Any]],
) -> None:
    durations: List[Tuple[str, int, float]] = []
    durations.extend(
        ("video", index, _seedance25_video_duration_seconds(video))
        for index, video in video_slots
    )
    durations.extend(
        ("audio", index, _seedance25_audio_duration_seconds(audio))
        for index, audio in audio_slots
    )
    for media_type, index, duration in durations:
        if not SEEDANCE25_MEDIA_MIN_SECONDS <= duration <= SEEDANCE25_MEDIA_MAX_SECONDS:
            raise SeedanceLowPriceError(
                f"Seedance 2.5 {media_type}{index} duration must be between 2 and 30 "
                f"seconds; received {duration:.3f}s"
            )
    total_duration = sum(duration for _kind, _index, duration in durations)
    if total_duration > SEEDANCE25_MEDIA_TOTAL_MAX_SECONDS:
        raise SeedanceLowPriceError(
            "Seedance 2.5 combined reference video/audio duration must not exceed "
            f"30 seconds; received {total_duration:.3f}s"
        )


def make_error_video(message: str) -> Any:
    import cv2

    path = os.path.join(tempfile.gettempdir(), f"seedance_error_{uuid.uuid4().hex[:10]}.mp4")
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 4.0, (512, 512))
    if not writer.isOpened():
        raise RuntimeError("Could not create skip_error placeholder video")
    frame = np.zeros((512, 512, 3), dtype=np.uint8)
    frame[:, :] = (15, 15, 90)
    cv2.putText(
        frame,
        "Seedance request failed",
        (32, 245),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (230, 230, 255),
        2,
        cv2.LINE_AA,
    )
    for _ in range(8):
        writer.write(frame)
    writer.release()
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError(f"Could not create skip_error placeholder: {message}")
    return _video_from_path(path)


def build_model_name(mode: str, region: str, tier: str) -> str:
    if mode not in MODE_SUFFIXES:
        raise SeedanceLowPriceError(f"Unsupported mode: {mode}")
    if region not in REGIONS:
        raise SeedanceLowPriceError(f"Unsupported region: {region}")
    if tier not in TIERS:
        raise SeedanceLowPriceError(f"Unsupported tier: {tier}")
    global_part = "global-" if region == "global" else ""
    return f"seedance-2.0-{global_part}{tier}-{MODE_SUFFIXES[mode]}"


def validate_common(
    mode: str,
    region: str,
    tier: str,
    prompt: str,
    resolution: str,
    seed: int,
    seconds: str = "5",
    ratio: str = "adaptive",
) -> None:
    build_model_name(mode, region, tier)
    text = str(prompt or "")
    if len(text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(f"prompt exceeds {PROMPT_MAX_LENGTH} characters")
    if mode in ("text_to_video", "multimodal_video") and not text.strip():
        raise SeedanceLowPriceError(f"prompt is required for {mode}")
    if resolution not in RESOLUTIONS:
        raise SeedanceLowPriceError(f"Unsupported resolution: {resolution}")
    if str(seconds) not in SECONDS:
        raise SeedanceLowPriceError(f"Unsupported seconds value: {seconds}")
    if ratio not in RATIOS:
        raise SeedanceLowPriceError(f"Unsupported ratio: {ratio}")
    if resolution in ("native1080p", "native4k") and tier != "standard":
        raise SeedanceLowPriceError(f"{resolution} is only supported by standard tier")
    if int(seed) < -1 or int(seed) > 2147483647:
        raise SeedanceLowPriceError("seed must be between -1 and 2147483647")


class Comfly_seedance2_low_price:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            "generate_audio": ("BOOLEAN", {"default": True}),
            "return_last_frame": ("BOOLEAN", {"default": False}),
            "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1}),
            "api_config": (CONFIG_TYPE,),
            "first_image": ("IMAGE",),
            "last_image": ("IMAGE",),
        }
        for index in range(1, 10):
            optional[f"image{index}"] = ("IMAGE",)
        for index in range(1, 4):
            optional[f"video{index}"] = (VIDEO_TYPE,)
        for index in range(1, 4):
            optional[f"audio{index}"] = (AUDIO_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "mode": (MODES, {"default": "text_to_video"}),
                "region": (REGIONS, {"default": "domestic"}),
                "tier": (TIERS, {"default": "mini"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (SECONDS, {"default": "5"}),
                "resolution": (RESOLUTIONS, {"default": "480p"}),
                "ratio": (RATIOS, {"default": "adaptive"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        mode=None,
        region=None,
        tier=None,
        prompt=None,
        resolution=None,
        seed=-1,
        seconds="5",
        ratio="adaptive",
        **kwargs,
    ):
        if None in (mode, region, tier, resolution):
            return True
        try:
            validate_common(
                mode, region, tier, prompt or "", resolution, seed, seconds, ratio
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _connected(kwargs: Dict[str, Any], prefix: str, count: int) -> List[Tuple[int, Any]]:
        result = []
        for index in range(1, count + 1):
            value = kwargs.get(f"{prefix}{index}")
            if value is not None:
                result.append((index, value))
        indexes = [index for index, _ in result]
        if indexes and indexes != list(range(1, len(indexes) + 1)):
            print(
                f"[Seedance Low Price] {prefix} slots {indexes} contain gaps; "
                f"they are compacted to @{prefix.capitalize()} 1..{len(indexes)}"
            )
        return result

    def _upload(self, data: bytes, filename: str, mime: str, config: Dict[str, Any]) -> str:
        print(f"[Seedance Low Price] Uploading {filename} ({len(data) / 1024:.1f}KB)")
        return upload_media(data, filename, mime, config)

    def _collect_and_upload_media(
        self, mode: str, tier: str, region: str, config: Dict[str, Any], kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        if mode == "text_to_video":
            media_names = ["first_image", "last_image"]
            media_names += [f"image{i}" for i in range(1, 10)]
            media_names += [f"video{i}" for i in range(1, 4)]
            media_names += [f"audio{i}" for i in range(1, 4)]
            if any(kwargs.get(name) is not None for name in media_names):
                raise SeedanceLowPriceError("text_to_video does not accept reference media")
            return {}

        if mode == "image_to_video":
            unrelated = [f"image{i}" for i in range(1, 10)]
            unrelated += [f"video{i}" for i in range(1, 4)]
            unrelated += [f"audio{i}" for i in range(1, 4)]
            if any(kwargs.get(name) is not None for name in unrelated):
                raise SeedanceLowPriceError(
                    "image_to_video only accepts first_image and optional last_image"
                )
            first_image = kwargs.get("first_image")
            if first_image is None:
                raise SeedanceLowPriceError("first_image is required for image_to_video")
            images = [
                self._upload(image_to_png_bytes(first_image), "first_frame.png", "image/png", config)
            ]
            if kwargs.get("last_image") is not None:
                images.append(
                    self._upload(
                        image_to_png_bytes(kwargs["last_image"]),
                        "last_frame.png",
                        "image/png",
                        config,
                    )
                )
            return {"images": images}

        if kwargs.get("first_image") is not None or kwargs.get("last_image") is not None:
            raise SeedanceLowPriceError(
                "multimodal_video uses image1..image9, not first_image/last_image"
            )
        image_slots = self._connected(kwargs, "image", 9)
        video_slots = self._connected(kwargs, "video", 3)
        audio_slots = self._connected(kwargs, "audio", 3)
        if not (image_slots or video_slots or audio_slots):
            raise SeedanceLowPriceError(
                "multimodal_video requires at least one image, video, or audio"
            )

        content: List[Dict[str, Any]] = []
        for index, image in image_slots:
            url = self._upload(
                image_to_png_bytes(image), f"image_{index}.png", "image/png", config
            )
            content.append({"type": "image_url", "image_url": {"url": url}})
        for index, video in video_slots:
            url = self._upload(
                video_to_mp4_bytes(video), f"video_{index}.mp4", "video/mp4", config
            )
            content.append({"type": "video_url", "video_url": {"url": url}})
        for index, audio in audio_slots:
            wav_bytes = audio_to_wav_bytes(audio)
            if region == "domestic" and tier == "fast" and len(wav_bytes) > DOMESTIC_FAST_AUDIO_MAX_BYTES:
                raise SeedanceLowPriceError("Domestic fast audio exceeds the 15MB limit")
            url = self._upload(wav_bytes, f"audio_{index}.wav", "audio/wav", config)
            content.append({"type": "audio_url", "audio_url": {"url": url}})
        return {"content": content}

    @staticmethod
    def _build_payload(
        mode: str,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        generate_audio: bool,
        return_last_frame: bool,
        seed: int,
        media: Dict[str, Any],
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "resolution": resolution,
            "ratio": ratio,
            "seed": int(seed),
            "generate_audio": bool(generate_audio),
            "return_last_frame": bool(return_last_frame),
        }
        payload: Dict[str, Any] = {
            "model": model,
            "seconds": str(seconds),
            "metadata": metadata,
        }
        text = str(prompt or "").strip()
        if text:
            payload["prompt"] = text
        if mode == "image_to_video":
            payload["images"] = media["images"]
        elif mode == "multimodal_video":
            metadata["content"] = media["content"]
        return payload

    def generate(
        self,
        mode: str,
        region: str,
        tier: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        generate_audio: bool = True,
        return_last_frame: bool = False,
        seed: int = -1,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        model = ""
        try:
            pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

            def update_progress(value: int) -> None:
                if pbar is not None:
                    try:
                        pbar.update_absolute(value, 100)
                    except Exception:
                        pass

            validate_common(mode, region, tier, prompt, resolution, seed, seconds, ratio)
            model = build_model_name(mode, region, tier)
            config = resolve_config(api_config)
            media = self._collect_and_upload_media(mode, tier, region, config, kwargs)
            payload = self._build_payload(
                mode,
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                generate_audio,
                return_last_frame,
                seed,
                media,
            )
            update_progress(15)
            print(f"[Seedance Low Price] Submitting model={model}, mode={mode}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(20)

            def on_progress(progress: int) -> None:
                update_progress(20 + int(progress * 0.75))

            final_response = poll_task(task_id, config, on_progress=on_progress)
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "mode": mode,
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "mode": mode,
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


class Comfly_seedance25_standard_low_price:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            "api_config": (CONFIG_TYPE,),
        }
        for index in range(1, SEEDANCE25_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        for index in range(1, SEEDANCE25_MAX_VIDEOS + 1):
            optional[f"video{index}"] = (VIDEO_TYPE,)
        for index in range(1, SEEDANCE25_MAX_AUDIOS + 1):
            optional[f"audio{index}"] = (AUDIO_TYPE,)
        optional.update({
            "generate_audio": ("BOOLEAN", {"default": True}),
            "return_last_frame": ("BOOLEAN", {"default": False}),
            "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647, "step": 1}),
            "skip_error": ("BOOLEAN", {"default": False}),
        })
        return {
            "required": {
                "model": (SEEDANCE25_MODELS, {"default": SEEDANCE25_MODELS[0]}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (SEEDANCE25_SECONDS, {"default": "4"}),
                "resolution": (SEEDANCE25_RESOLUTIONS, {"default": "480p"}),
                "ratio": (RATIOS, {"default": "adaptive"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt=None,
        seconds="4",
        resolution="480p",
        ratio="adaptive",
        seed=-1,
        **kwargs,
    ):
        try:
            cls._validate(model, prompt or "", seconds, resolution, ratio, seed)
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _validate(
        model: Any,
        prompt: str,
        seconds: Any,
        resolution: str,
        ratio: str,
        seed: Any,
    ) -> None:
        if model not in SEEDANCE25_MODELS:
            raise SeedanceLowPriceError(f"Unsupported Seedance 2.5 model: {model}")
        if str(seconds) not in SEEDANCE25_SECONDS:
            raise SeedanceLowPriceError("seconds must be smart (-1) or an integer from 4 to 30")
        if resolution not in SEEDANCE25_RESOLUTIONS:
            raise SeedanceLowPriceError(f"Unsupported Seedance 2.5 resolution: {resolution}")
        if ratio not in RATIOS:
            raise SeedanceLowPriceError(f"Unsupported ratio: {ratio}")
        text = str(prompt or "").strip()
        if len(text) > PROMPT_MAX_LENGTH:
            raise SeedanceLowPriceError(
                f"Seedance prompt must not exceed {PROMPT_MAX_LENGTH} characters"
            )
        if model in SEEDANCE25_T2V_MODELS + SEEDANCE25_MULTI_MODELS and not text:
            raise SeedanceLowPriceError("prompt is required for Seedance 2.5 T2V and Multi")
        if int(seed) < -1 or int(seed) > 2147483647:
            raise SeedanceLowPriceError("seed must be between -1 and 2147483647")

    @staticmethod
    def _connected(kwargs: Dict[str, Any], prefix: str, count: int) -> List[Tuple[int, Any]]:
        result = [
            (index, kwargs[f"{prefix}{index}"])
            for index in range(1, count + 1)
            if kwargs.get(f"{prefix}{index}") is not None
        ]
        indexes = [index for index, _value in result]
        if indexes and indexes != list(range(1, len(indexes) + 1)):
            print(
                f"[Seedance 2.5 Low Price] {prefix} slots {indexes} contain gaps; "
                f"they are compacted to @{prefix.capitalize()} 1..{len(indexes)}"
            )
        return result

    @staticmethod
    def _upload(data: bytes, filename: str, mime: str, config: Dict[str, Any]) -> str:
        print(f"[Seedance 2.5 Low Price] Uploading {filename} ({len(data) / 1024:.1f}KB)")
        return upload_media(data, filename, mime, config)

    def collect_media(
        self,
        kwargs: Dict[str, Any],
        config: Dict[str, Any],
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> Dict[str, Any]:
        model = kwargs.get("model")
        image_slots = self._connected(kwargs, "image", SEEDANCE25_MAX_IMAGES)
        video_slots = self._connected(kwargs, "video", SEEDANCE25_MAX_VIDEOS)
        audio_slots = self._connected(kwargs, "audio", SEEDANCE25_MAX_AUDIOS)

        if model in SEEDANCE25_T2V_MODELS:
            if image_slots or video_slots or audio_slots:
                raise SeedanceLowPriceError("Seedance 2.5 T2V does not accept reference media")
            return {}

        if model in SEEDANCE25_I2V_MODELS:
            if video_slots or audio_slots or any(index > 2 for index, _value in image_slots):
                raise SeedanceLowPriceError(
                    "Seedance 2.5 I2V accepts image1 and optional image2 only"
                )
            if not image_slots or image_slots[0][0] != 1:
                raise SeedanceLowPriceError("image1 is required for Seedance 2.5 I2V")
            urls = []
            for completed, (index, image) in enumerate(image_slots, start=1):
                urls.append(self._upload(
                    image_to_png_bytes(image),
                    f"seedance25_frame_{index}.png",
                    "image/png",
                    config,
                ))
                if on_progress:
                    on_progress(completed / len(image_slots))
            return {"images": urls}

        if model not in SEEDANCE25_MULTI_MODELS:
            raise SeedanceLowPriceError(f"Unsupported Seedance 2.5 model: {model}")
        if not (image_slots or video_slots or audio_slots):
            raise SeedanceLowPriceError(
                "Seedance 2.5 Multi requires at least one image, video, or audio"
            )
        reference_count = len(image_slots) + len(video_slots) + len(audio_slots)
        if reference_count > SEEDANCE25_MAX_REFERENCES:
            raise SeedanceLowPriceError(
                f"Seedance 2.5 Multi accepts at most {SEEDANCE25_MAX_REFERENCES} references"
            )
        _validate_seedance25_media_durations(video_slots, audio_slots)

        total = reference_count
        completed = 0
        content: List[Dict[str, Any]] = []
        for index, image in image_slots:
            url = self._upload(
                image_to_png_bytes(image), f"seedance25_image_{index}.png", "image/png", config
            )
            content.append({"type": "image_url", "image_url": {"url": url}})
            completed += 1
            if on_progress:
                on_progress(completed / total)
        for index, video in video_slots:
            url = self._upload(
                video_to_mp4_bytes(video), f"seedance25_video_{index}.mp4", "video/mp4", config
            )
            content.append({"type": "video_url", "video_url": {"url": url}})
            completed += 1
            if on_progress:
                on_progress(completed / total)
        for index, audio in audio_slots:
            url = self._upload(
                audio_to_wav_bytes(audio), f"seedance25_audio_{index}.wav", "audio/wav", config
            )
            content.append({"type": "audio_url", "audio_url": {"url": url}})
            completed += 1
            if on_progress:
                on_progress(completed / total)
        return {"content": content}

    @staticmethod
    def build_payload(kwargs: Dict[str, Any], media: Dict[str, Any]) -> Dict[str, Any]:
        model = kwargs["model"]
        metadata: Dict[str, Any] = {
            "resolution": kwargs["resolution"],
            "ratio": "adaptive" if model in SEEDANCE25_I2V_MODELS else kwargs["ratio"],
            "generate_audio": bool(kwargs.get("generate_audio", True)),
        }
        if kwargs.get("return_last_frame", False):
            metadata["return_last_frame"] = True
        seed = int(kwargs.get("seed", -1))
        if seed >= 0:
            metadata["seed"] = seed
        payload: Dict[str, Any] = {"model": model, "metadata": metadata}
        if str(kwargs["seconds"]) == "-1":
            metadata["duration"] = -1
        else:
            payload["seconds"] = str(kwargs["seconds"])

        prompt = str(kwargs.get("prompt") or "").strip()
        if prompt:
            payload["prompt"] = prompt
        if model in SEEDANCE25_I2V_MODELS:
            payload["images"] = media["images"][:2]
        elif model in SEEDANCE25_MULTI_MODELS:
            metadata["content"] = media["content"]
        return payload

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        generate_audio: bool = True,
        return_last_frame: bool = False,
        seed: int = -1,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        try:
            pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

            def update_progress(value: int) -> None:
                if pbar is not None:
                    try:
                        pbar.update_absolute(value, 100)
                    except Exception:
                        pass

            self._validate(model, prompt, seconds, resolution, ratio, seed)
            config = resolve_config(api_config)
            request = {
                "model": model,
                "prompt": prompt,
                "seconds": seconds,
                "resolution": resolution,
                "ratio": ratio,
                "generate_audio": generate_audio,
                "return_last_frame": return_last_frame,
                "seed": seed,
                **kwargs,
            }
            media = self.collect_media(
                request,
                config,
                on_progress=lambda progress: update_progress(int(progress * 15)),
            )
            payload = self.build_payload(request, media)
            update_progress(15)
            print(f"[Seedance 2.5 Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(20)

            def on_poll_progress(progress: int) -> None:
                update_progress(20 + int(progress * 0.75))

            final_response = poll_task(task_id, config, on_progress=on_poll_progress)
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


SEEDREAM_MODES = ["text_to_image", "image_edit"]
SEEDREAM_FAMILY_DOMESTIC = "seedream-v5-pro (domestic)"
SEEDREAM_FAMILY_DOLA = "dola-seedream-5.0-pro (overseas)"
SEEDREAM_MODEL_FAMILIES = [SEEDREAM_FAMILY_DOMESTIC, SEEDREAM_FAMILY_DOLA]
SEEDREAM_MODEL_PAIRS = {
    SEEDREAM_FAMILY_DOMESTIC: {
        "text_to_image": "seedream-v5-pro-t2i",
        "image_edit": "seedream-v5-pro-i2i",
    },
    SEEDREAM_FAMILY_DOLA: {
        "text_to_image": "dola-seedream-5.0-pro-t2i",
        "image_edit": "dola-seedream-5.0-pro-i2i",
    },
}
SEEDREAM_MODELS = SEEDREAM_MODEL_PAIRS[SEEDREAM_FAMILY_DOMESTIC]
SEEDREAM_RESOLUTIONS = ["1k", "2k", "custom"]
SEEDREAM_OUTPUT_FORMATS = ["png", "jpeg"]
SEEDREAM_PROMPT_MIN_LENGTH = 5
SEEDREAM_PROMPT_MAX_LENGTH = 2000
SEEDREAM_IMAGE_MAX_BYTES = 10 * 1024 * 1024
SEEDREAM_LAYER_DECOMPOSITION_MODEL = "seedream-v5-pro-layer-decomposition"
DOLA_SEEDREAM_LAYER_DECOMPOSITION_MODEL = (
    "dola-seedream-5.0-pro-layer-decomposition"
)
SEEDREAM_LAYER_DECOMPOSITION_MODELS = [
    SEEDREAM_LAYER_DECOMPOSITION_MODEL,
    DOLA_SEEDREAM_LAYER_DECOMPOSITION_MODEL,
]
SEEDREAM_LAYER_RESOLUTIONS = ["auto", "1k", "1.5k", "2k"]
SEEDREAM_LAYER_SOURCE_MAX_BYTES = 30 * 1024 * 1024
ZHENZHEN_IMAGE_G2_T2I_MODEL = "zhenzhen-image-g2-t2i"
ZHENZHEN_IMAGE_G2_I2I_MODEL = "zhenzhen-image-g2-i2i"
ZHENZHEN_IMAGE_G2_MODELS = [
    ZHENZHEN_IMAGE_G2_T2I_MODEL,
    ZHENZHEN_IMAGE_G2_I2I_MODEL,
]
ZHENZHEN_IMAGE_G2_RESOLUTIONS = ["1k"]
ZHENZHEN_IMAGE_G2_PROMPT_MAX_LENGTH = 20000
ZHENZHEN_IMAGE_G2_MAX_IMAGES = 10
ZHENZHEN_IMAGE_G2_IMAGE_MAX_BYTES = 10 * 1024 * 1024


def validate_seedream_inputs(
    mode: str,
    prompt: str,
    resolution: str,
    width: int,
    height: int,
    output_format: str,
    model_family: str = SEEDREAM_FAMILY_DOMESTIC,
) -> None:
    if mode not in SEEDREAM_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Seedream mode: {mode}")
    prompt_length = len(str(prompt or "").strip())
    if not SEEDREAM_PROMPT_MIN_LENGTH <= prompt_length <= SEEDREAM_PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Seedream prompt length must be {SEEDREAM_PROMPT_MIN_LENGTH}-"
            f"{SEEDREAM_PROMPT_MAX_LENGTH} characters"
        )
    if resolution not in SEEDREAM_RESOLUTIONS:
        raise SeedanceLowPriceError(f"Unsupported Seedream resolution: {resolution}")
    if output_format not in SEEDREAM_OUTPUT_FORMATS:
        raise SeedanceLowPriceError(f"Unsupported Seedream output_format: {output_format}")
    if model_family not in SEEDREAM_MODEL_PAIRS:
        raise SeedanceLowPriceError(
            f"Unsupported Seedream model_family: {model_family}"
        )
    if resolution == "custom":
        if not 240 <= int(width) <= 8192 or not 240 <= int(height) <= 8192:
            raise SeedanceLowPriceError("Seedream custom width/height must be 240-8192")


def build_seedream_payload(
    mode: str,
    prompt: str,
    resolution: str,
    width: int,
    height: int,
    output_format: str,
    image_urls: Optional[List[str]] = None,
    model_family: str = SEEDREAM_FAMILY_DOMESTIC,
) -> Dict[str, Any]:
    validate_seedream_inputs(
        mode,
        prompt,
        resolution,
        width,
        height,
        output_format,
        model_family,
    )
    metadata: Dict[str, Any] = {"output_format": output_format}
    if resolution == "custom":
        metadata["width"] = int(width)
        metadata["height"] = int(height)
    else:
        metadata["resolution"] = resolution
    payload: Dict[str, Any] = {
        "model": SEEDREAM_MODEL_PAIRS[model_family][mode],
        "prompt": str(prompt).strip(),
        "metadata": metadata,
    }
    if mode == "image_edit":
        if not image_urls:
            raise SeedanceLowPriceError("image_edit requires at least one reference image")
        if len(image_urls) > 10:
            raise SeedanceLowPriceError("image_edit accepts at most 10 reference images")
        payload["images"] = list(image_urls)
    elif image_urls:
        raise SeedanceLowPriceError("text_to_image does not accept reference images")
    return payload


def submit_image_task(
    payload: Dict[str, Any],
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Tuple[str, Dict[str, Any]]:
    url = f"{config['base_url']}/v1/image/generations"
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            sleep(min(2 ** attempt + 1, 15))
        try:
            response = _get_session().post(
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
                "Seedream submit transport failed after the request may have reached the server; "
                "it was not retried to avoid a duplicate paid task. Check the provider console "
                f"before retrying manually: {type(exc).__name__}: {exc}"
            ) from exc

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                f"Seedream submit rejected (HTTP {response.status_code}): {message}"
            )

        task_id = None
        if isinstance(data, dict):
            task_id = data.get("task_id") or data.get("id")
            if not task_id and isinstance(data.get("data"), dict):
                task_id = data["data"].get("task_id") or data["data"].get("id")
        if not task_id:
            raise SeedanceLowPriceError("Seedream submit response did not contain task_id/id")
        return str(task_id), data
    raise RuntimeError(f"Seedream submit failed after 3 attempts: {last_error}")


def poll_image_task(
    task_id: str,
    config: Dict[str, Any],
    on_progress: Optional[Callable[[int], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    url = f"{config['base_url']}/v1/image/generations/{task_id}"
    start = clock()
    failures = 0
    while True:
        if clock() - start > config.get("max_poll_time", 1800):
            raise RuntimeError(f"Seedream polling timed out [task_id: {task_id}]")
        sleep(config.get("poll_interval", 4))
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
                    f"Seedream polling failed after repeated network errors [task_id: {task_id}]"
                )
            sleep(min(failures * 2, 10))
            continue

        if response.status_code != 200:
            data = _response_json(response)
            message = extract_error_message(data, response.text[:300])
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise SeedanceLowPriceError(
                    f"Seedream polling rejected (HTTP {response.status_code}): {message} "
                    f"[task_id: {task_id}]"
                )
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"Seedream polling repeatedly returned HTTP {response.status_code}: {message} "
                    f"[task_id: {task_id}]"
                )
            sleep(min(failures * 2, 10))
            continue

        try:
            result = response.json()
        except ValueError:
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"Seedream polling repeatedly returned invalid JSON [task_id: {task_id}]"
                )
            continue

        failures = 0
        top_level = result if isinstance(result, dict) else {}
        record = top_level.get("data")
        if not isinstance(record, dict):
            record = top_level
        status = str(record.get("status") or top_level.get("status") or "").strip().upper()
        progress = _coerce_progress(record.get("progress") or top_level.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        if status == "SUCCESS":
            return result
        if status == "FAILURE":
            reason = record.get("fail_reason") or record.get("message") or record.get("error")
            if isinstance(reason, (dict, list)):
                reason = extract_error_message(reason, "")
            raise SeedanceLowPriceError(
                f"Seedream task failed: {reason or 'image generation failed'} [task_id: {task_id}]"
            )


def extract_image_url(response: Dict[str, Any]) -> str:
    candidates: List[Any] = []
    if isinstance(response, dict):
        candidates.extend([response.get("result_url"), response.get("image_url"), response.get("url")])
        data = response.get("data")
        if isinstance(data, dict):
            candidates.extend([data.get("result_url"), data.get("image_url"), data.get("url")])
            nested = data.get("data")
            if isinstance(nested, dict):
                candidates.extend([nested.get("result_url"), nested.get("image_url"), nested.get("url")])
                content = nested.get("content")
                if isinstance(content, dict):
                    candidates.extend([content.get("image_url"), content.get("url")])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    raise SeedanceLowPriceError("Seedream completed response did not contain an image URL")


def extract_image_urls(response: Dict[str, Any]) -> List[str]:
    """Return the complete documented image_urls array without reordering it."""
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, dict):
                content = nested.get("content")
                if isinstance(content, dict):
                    values = content.get("image_urls")
                    if isinstance(values, (list, tuple)):
                        urls = [
                            str(value or "").strip()
                            for value in values
                            if str(value or "").strip()
                        ]
                        if urls:
                            return urls
    return [extract_image_url(response)]


def _pil_to_image_tensor(image: Image.Image) -> torch.Tensor:
    array = np.asarray(image.convert("RGB"), dtype=np.float32).copy() / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def download_image(url: str, max_retries: int = 3) -> torch.Tensor:
    image = download_image_with_retry(
        url,
        timeout=300,
        max_attempts=max_retries,
        request_get=_get_session().get,
        direct_get=direct_media_get,
    )
    return _pil_to_image_tensor(image)


def download_image_with_mask(url: str) -> Tuple[torch.Tensor, torch.Tensor]:
    """Download one layer as ComfyUI IMAGE plus inverse-alpha MASK."""
    rgba = download_image_with_alpha_retry(url)
    rgb = np.asarray(rgba.convert("RGB"), dtype=np.float32).copy() / 255.0
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.float32).copy() / 255.0
    image = torch.from_numpy(rgb).unsqueeze(0)
    mask = torch.from_numpy(1.0 - alpha).unsqueeze(0)
    return image, mask


class Comfly_sd2_seedream_v5_pro_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            "api_config": (CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
            "model_family": (
                SEEDREAM_MODEL_FAMILIES,
                {"default": SEEDREAM_FAMILY_DOMESTIC},
            ),
        }
        for index in range(1, 11):
            optional[f"image{index}"] = ("IMAGE",)
        return {
            "required": {
                "mode": (SEEDREAM_MODES, {"default": "text_to_image"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (SEEDREAM_RESOLUTIONS, {"default": "1k"}),
                "width": ("INT", {"default": 1024, "min": 240, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 1024, "min": 240, "max": 8192, "step": 8}),
                "output_format": (SEEDREAM_OUTPUT_FORMATS, {"default": "png"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate_image"
    CATEGORY = "zhenzhen/Seedance2 Low Price"

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        mode=None,
        prompt=None,
        resolution=None,
        width=1024,
        height=1024,
        output_format="png",
        model_family=SEEDREAM_FAMILY_DOMESTIC,
        **kwargs,
    ):
        if None in (mode, resolution):
            return True
        try:
            validate_seedream_inputs(
                mode,
                prompt or "",
                resolution,
                width,
                height,
                output_format,
                model_family,
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _reference_images(kwargs: Dict[str, Any]) -> List[Tuple[int, Any]]:
        return [
            (index, kwargs[f"image{index}"])
            for index in range(1, 11)
            if kwargs.get(f"image{index}") is not None
        ]

    def _upload_reference_images(
        self,
        mode: str,
        config: Dict[str, Any],
        kwargs: Dict[str, Any],
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> List[str]:
        references = self._reference_images(kwargs)
        if mode == "text_to_image":
            if references:
                raise SeedanceLowPriceError("text_to_image does not accept reference images")
            return []
        if not references:
            raise SeedanceLowPriceError("image_edit requires 1-10 reference images")

        urls = []
        for position, (slot, image) in enumerate(references, start=1):
            image_bytes = image_to_png_bytes(image)
            if len(image_bytes) > SEEDREAM_IMAGE_MAX_BYTES:
                raise SeedanceLowPriceError(
                    f"Seedream reference image{slot} exceeds the 10MB limit"
                )
            print(
                f"[Seedream Low Price] Uploading image{slot}.png "
                f"({len(image_bytes) / 1024:.1f}KB)"
            )
            urls.append(upload_media(image_bytes, f"image{slot}.png", "image/png", config))
            if on_progress:
                on_progress(int(position / len(references) * 20))
        return urls

    def generate_image(
        self,
        mode: str,
        prompt: str,
        resolution: str,
        width: int,
        height: int,
        output_format: str,
        api_config: Any = None,
        skip_error: bool = False,
        model_family: str = SEEDREAM_FAMILY_DOMESTIC,
        **kwargs,
    ):
        task_id = ""
        model = SEEDREAM_MODEL_PAIRS.get(model_family, {}).get(mode, "")
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_seedream_inputs(
                mode,
                prompt,
                resolution,
                width,
                height,
                output_format,
                model_family,
            )
            config = resolve_config(api_config)
            image_urls = self._upload_reference_images(
                mode, config, kwargs, on_progress=update_progress
            )
            payload = build_seedream_payload(
                mode,
                prompt,
                resolution,
                width,
                height,
                output_format,
                image_urls,
                model_family,
            )
            update_progress(25)
            print(f"[Seedream Low Price] Submitting model={model}, mode={mode}")
            task_id, submit_response = submit_image_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_image_task(
                task_id, config, on_progress=on_poll_progress
            )
            image_url = extract_image_url(final_response)
            output_image = download_image(image_url)
            update_progress(100)
            response = {
                "status": "SUCCESS",
                "mode": mode,
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                output_image,
                image_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "mode": mode,
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            blank = torch.ones((1, 512, 512, 3), dtype=torch.float32)
            return (blank, "", task_id, json.dumps(response, ensure_ascii=False, indent=2))


def validate_zhenzhen_image_g2_inputs(
    model: str,
    prompt: str,
    resolution: str,
    ratio: str,
    strict: bool = True,
) -> None:
    if model not in ZHENZHEN_IMAGE_G2_MODELS:
        raise SeedanceLowPriceError(
            f"Unsupported Zhenzhen Image G-2 model: {model}"
        )
    prompt_text = str(prompt or "").strip()
    if strict and not prompt_text:
        raise SeedanceLowPriceError("Zhenzhen Image G-2 prompt is required")
    if len(prompt_text) > ZHENZHEN_IMAGE_G2_PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            "Zhenzhen Image G-2 prompt cannot exceed "
            f"{ZHENZHEN_IMAGE_G2_PROMPT_MAX_LENGTH} characters"
        )
    if resolution not in ZHENZHEN_IMAGE_G2_RESOLUTIONS:
        raise SeedanceLowPriceError(
            "Zhenzhen Image G-2 resolution must be 1k"
        )
    if ratio not in RATIOS:
        raise SeedanceLowPriceError(
            f"Unsupported Zhenzhen Image G-2 ratio: {ratio}"
        )


def build_zhenzhen_image_g2_payload(
    model: str,
    prompt: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_zhenzhen_image_g2_inputs(
        model,
        prompt,
        resolution,
        ratio,
        strict=True,
    )
    urls = list(image_urls or [])
    if model == ZHENZHEN_IMAGE_G2_I2I_MODEL:
        if not urls:
            raise SeedanceLowPriceError(
                "zhenzhen-image-g2-i2i requires 1-10 reference images"
            )
        if len(urls) > ZHENZHEN_IMAGE_G2_MAX_IMAGES:
            raise SeedanceLowPriceError(
                "zhenzhen-image-g2-i2i accepts at most 10 reference images"
            )

    metadata: Dict[str, Any] = {"resolution": resolution}
    if ratio != "adaptive":
        metadata["ratio"] = ratio

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": str(prompt).strip(),
        "metadata": metadata,
    }
    if model == ZHENZHEN_IMAGE_G2_I2I_MODEL:
        payload["images"] = urls
    return payload


class Comfly_zhenzhen_image_g2_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            "api_config": (CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
        }
        for index in range(1, ZHENZHEN_IMAGE_G2_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        return {
            "required": {
                "model": (
                    ZHENZHEN_IMAGE_G2_MODELS,
                    {"default": ZHENZHEN_IMAGE_G2_T2I_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (
                    ZHENZHEN_IMAGE_G2_RESOLUTIONS,
                    {"default": "1k"},
                ),
                "ratio": (RATIOS, {"default": "adaptive"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate_image"
    CATEGORY = "zhenzhen/Seedance2 Low Price"

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt=None,
        resolution=None,
        ratio=None,
        strict=False,
        **kwargs,
    ):
        if None in (model, resolution, ratio):
            return True
        try:
            validate_zhenzhen_image_g2_inputs(
                model,
                prompt or "",
                resolution,
                ratio,
                strict=bool(strict),
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _reference_images(kwargs: Dict[str, Any]) -> List[Tuple[int, Any]]:
        references = [
            (index, kwargs[f"image{index}"])
            for index in range(1, ZHENZHEN_IMAGE_G2_MAX_IMAGES + 1)
            if kwargs.get(f"image{index}") is not None
        ]
        slots = [slot for slot, _ in references]
        if slots and slots != list(range(1, len(slots) + 1)):
            print(
                "[Zhenzhen Image G-2 Low Price] Reference image slots "
                f"{slots} contain gaps; compacting them in slot order."
            )
        return references

    def _upload_reference_images(
        self,
        model: str,
        config: Dict[str, Any],
        kwargs: Dict[str, Any],
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> List[str]:
        if model == ZHENZHEN_IMAGE_G2_T2I_MODEL:
            return []

        references = self._reference_images(kwargs)
        if not references:
            raise SeedanceLowPriceError(
                "zhenzhen-image-g2-i2i requires 1-10 reference images"
            )

        urls = []
        for position, (slot, image) in enumerate(references, start=1):
            image_bytes = image_to_png_bytes(image)
            if len(image_bytes) > ZHENZHEN_IMAGE_G2_IMAGE_MAX_BYTES:
                raise SeedanceLowPriceError(
                    f"Zhenzhen Image G-2 reference image{slot} exceeds the 10MB limit"
                )
            print(
                f"[Zhenzhen Image G-2 Low Price] Uploading image{slot}.png "
                f"({len(image_bytes) / 1024:.1f}KB)"
            )
            urls.append(
                upload_media(
                    image_bytes,
                    f"zhenzhen_image_g2_reference_{slot}.png",
                    "image/png",
                    config,
                )
            )
            if on_progress:
                on_progress(int(position / len(references) * 20))
        return urls

    def generate_image(
        self,
        model: str,
        prompt: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_zhenzhen_image_g2_inputs(
                model,
                prompt,
                resolution,
                ratio,
                strict=True,
            )
            config = resolve_config(api_config)
            image_urls = self._upload_reference_images(
                model,
                config,
                kwargs,
                on_progress=update_progress,
            )
            payload = build_zhenzhen_image_g2_payload(
                model,
                prompt,
                resolution,
                ratio,
                image_urls,
            )
            update_progress(25)
            print(f"[Zhenzhen Image G-2 Low Price] Submitting model={model}")
            task_id, submit_response = submit_image_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_image_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            image_url = extract_image_url(final_response)
            output_image = download_image(image_url)
            update_progress(100)
            response = {
                "status": "SUCCESS",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                output_image,
                image_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            blank = torch.ones((1, 512, 512, 3), dtype=torch.float32)
            return (blank, "", task_id, json.dumps(response, ensure_ascii=False, indent=2))


HAPPYHORSE_MODES = ["text_to_video", "image_to_video", "reference_to_video"]
HAPPYHORSE_MODELS = {
    "text_to_video": "happyhorse-1.1-t2v",
    "image_to_video": "happyhorse-1.1-i2v",
    "reference_to_video": "happyhorse-1.1-r2v",
}
HAPPYHORSE_MODE_BY_MODEL = {
    model: mode for mode, model in HAPPYHORSE_MODELS.items()
}
HAPPYHORSE_SECONDS = [str(value) for value in range(3, 16)]
HAPPYHORSE_RESOLUTIONS = ["720p", "1080p"]


def validate_happyhorse_settings(
    mode: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
) -> None:
    if mode not in HAPPYHORSE_MODELS:
        raise SeedanceLowPriceError(f"Unsupported HappyHorse mode: {mode}")
    if str(seconds) not in HAPPYHORSE_SECONDS:
        raise SeedanceLowPriceError("HappyHorse seconds must be an integer from 3 to 15")
    if resolution not in HAPPYHORSE_RESOLUTIONS:
        raise SeedanceLowPriceError("HappyHorse resolution must be 720p or 1080p")
    if ratio not in RATIOS:
        raise SeedanceLowPriceError(f"Unsupported HappyHorse ratio: {ratio}")
    text = str(prompt or "").strip()
    if len(text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"HappyHorse prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    if mode in ("text_to_video", "reference_to_video") and not text:
        raise SeedanceLowPriceError(f"HappyHorse {mode} requires a prompt")


def build_happyhorse_payload(
    mode: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_happyhorse_settings(mode, prompt, seconds, resolution, ratio)
    urls = list(image_urls or [])
    if mode == "text_to_video" and urls:
        raise SeedanceLowPriceError("HappyHorse text_to_video does not accept images")
    if mode == "image_to_video" and len(urls) != 1:
        raise SeedanceLowPriceError("HappyHorse image_to_video requires exactly one image")
    if mode == "reference_to_video" and not 1 <= len(urls) <= 9:
        raise SeedanceLowPriceError("HappyHorse reference_to_video requires 1-9 images")

    metadata: Dict[str, Any] = {"resolution": resolution}
    if ratio != "adaptive" and mode != "image_to_video":
        metadata["ratio"] = ratio
    payload: Dict[str, Any] = {
        "model": HAPPYHORSE_MODELS[mode],
        "seconds": str(seconds),
        "metadata": metadata,
    }
    text = str(prompt or "").strip()
    if text:
        payload["prompt"] = text
    if urls:
        payload["images"] = urls
    return payload


class Comfly_happyhorse_1_1_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {"api_config": (CONFIG_TYPE,)}
        for index in range(1, 10):
            optional[f"image{index}"] = ("IMAGE",)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (
                    list(HAPPYHORSE_MODE_BY_MODEL),
                    {"default": HAPPYHORSE_MODELS["text_to_video"]},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (HAPPYHORSE_SECONDS, {"default": "4"}),
                "resolution": (HAPPYHORSE_RESOLUTIONS, {"default": "720p"}),
                "ratio": (RATIOS, {"default": "adaptive"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="4",
        resolution="720p",
        ratio="adaptive",
        **kwargs,
    ):
        if model is None:
            return True
        mode = HAPPYHORSE_MODE_BY_MODEL.get(model)
        if mode is None:
            return f"Unsupported HappyHorse model: {model}"
        try:
            validate_happyhorse_settings(mode, prompt, seconds, resolution, ratio)
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _connected_images(kwargs: Dict[str, Any]) -> List[Tuple[int, Any]]:
        return [
            (index, kwargs[f"image{index}"])
            for index in range(1, 10)
            if kwargs.get(f"image{index}") is not None
        ]

    def _upload_images(
        self,
        mode: str,
        config: Dict[str, Any],
        kwargs: Dict[str, Any],
        on_progress: Optional[Callable[[int], None]] = None,
    ) -> List[str]:
        images = self._connected_images(kwargs)
        if mode == "text_to_video":
            if images:
                raise SeedanceLowPriceError(
                    "HappyHorse text_to_video does not accept connected images"
                )
            return []
        if mode == "image_to_video" and len(images) != 1:
            raise SeedanceLowPriceError(
                "HappyHorse image_to_video requires exactly one connected image"
            )
        if mode == "reference_to_video" and not 1 <= len(images) <= 9:
            raise SeedanceLowPriceError(
                "HappyHorse reference_to_video requires 1-9 connected images"
            )

        urls = []
        for position, (slot, image) in enumerate(images, start=1):
            data = image_to_png_bytes(image)
            urls.append(upload_media(data, f"image{slot}.png", "image/png", config))
            if on_progress:
                on_progress(int(position / len(images) * 20))
        return urls

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        mode = HAPPYHORSE_MODE_BY_MODEL.get(model, "")
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            if not mode:
                raise SeedanceLowPriceError(f"Unsupported HappyHorse model: {model}")
            validate_happyhorse_settings(mode, prompt, seconds, resolution, ratio)
            config = resolve_config(api_config)
            image_urls = self._upload_images(
                mode, config, kwargs, on_progress=update_progress
            )
            payload = build_happyhorse_payload(
                mode, prompt, seconds, resolution, ratio, image_urls
            )
            update_progress(25)
            print(f"[HappyHorse Low Price] Submitting model={model}, mode={mode}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id, config, on_progress=on_poll_progress
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "mode": mode,
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "mode": mode,
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


WAN27_SPICY_MODEL = "wan-2.7-spicy-i2v"
WAN27_SPICY_SECONDS = [str(value) for value in range(2, 16)]
WAN27_SPICY_RESOLUTIONS = ["720p", "1080p"]


def validate_wan27_spicy_inputs(
    prompt: str,
    seconds: str,
    resolution: str,
    negative_prompt: str,
    audio_url: str,
    prompt_extend: bool,
    seed: int,
) -> None:
    if str(seconds) not in WAN27_SPICY_SECONDS:
        raise SeedanceLowPriceError("Wan 2.7 Spicy seconds must be 2-15")
    if resolution not in WAN27_SPICY_RESOLUTIONS:
        raise SeedanceLowPriceError(
            "Wan 2.7 Spicy resolution must be 720p or 1080p"
        )
    if len(str(prompt or "")) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Wan 2.7 Spicy prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    if len(str(negative_prompt or "")) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Wan 2.7 Spicy negative_prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    audio_url_text = str(audio_url or "").strip()
    if audio_url_text:
        parsed = urlsplit(audio_url_text)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise SeedanceLowPriceError("Wan 2.7 Spicy audio_url must be an http(s) URL")
    try:
        seed_value = int(seed)
    except (TypeError, ValueError) as exc:
        raise SeedanceLowPriceError("Wan 2.7 Spicy seed must be an integer") from exc
    if not -1 <= seed_value <= 2147483647:
        raise SeedanceLowPriceError(
            "Wan 2.7 Spicy seed must be between -1 and 2147483647"
        )


def build_wan27_spicy_payload(
    prompt: str,
    seconds: str,
    resolution: str,
    negative_prompt: str,
    audio_url: str,
    prompt_extend: bool,
    seed: int,
    image_url: str,
) -> Dict[str, Any]:
    validate_wan27_spicy_inputs(
        prompt,
        seconds,
        resolution,
        negative_prompt,
        audio_url,
        prompt_extend,
        seed,
    )
    image_url_text = str(image_url or "").strip()
    if not image_url_text:
        raise SeedanceLowPriceError("Wan 2.7 Spicy requires a first image")

    metadata: Dict[str, Any] = {"resolution": resolution}
    negative_prompt_text = str(negative_prompt or "").strip()
    if negative_prompt_text:
        metadata["negative_prompt"] = negative_prompt_text
    audio_url_text = str(audio_url or "").strip()
    if audio_url_text:
        metadata["audio_url"] = audio_url_text
    if bool(prompt_extend):
        metadata["prompt_extend"] = True
    if int(seed) >= 0:
        metadata["seed"] = int(seed)

    payload: Dict[str, Any] = {
        "model": WAN27_SPICY_MODEL,
        "seconds": str(seconds),
        "metadata": metadata,
        "images": [image_url_text],
    }
    prompt_text = str(prompt or "").strip()
    if prompt_text:
        payload["prompt"] = prompt_text
    return payload


class Comfly_wan_2_7_spicy_i2v_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "first_image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (WAN27_SPICY_SECONDS, {"default": "2"}),
                "resolution": (WAN27_SPICY_RESOLUTIONS, {"default": "720p"}),
                "negative_prompt": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
                "audio_url": ("STRING", {"default": ""}),
                "prompt_extend": ("BOOLEAN", {"default": False}),
                "seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 2147483647, "step": 1},
                ),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        prompt="",
        seconds="2",
        resolution="720p",
        negative_prompt="",
        audio_url="",
        prompt_extend=False,
        seed=-1,
        **kwargs,
    ):
        try:
            validate_wan27_spicy_inputs(
                prompt,
                seconds,
                resolution,
                negative_prompt,
                audio_url,
                prompt_extend,
                seed,
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        first_image: Any,
        prompt: str,
        seconds: str,
        resolution: str,
        negative_prompt: str,
        audio_url: str,
        prompt_extend: bool,
        seed: int,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_wan27_spicy_inputs(
                prompt,
                seconds,
                resolution,
                negative_prompt,
                audio_url,
                prompt_extend,
                seed,
            )
            config = resolve_config(api_config)
            image_bytes = image_to_png_bytes(first_image)
            image_url = upload_media(
                image_bytes,
                "wan27_spicy_first_frame.png",
                "image/png",
                config,
            )
            update_progress(20)
            payload = build_wan27_spicy_payload(
                prompt,
                seconds,
                resolution,
                negative_prompt,
                audio_url,
                prompt_extend,
                seed,
                image_url,
            )
            print(
                f"[Wan 2.7 Spicy Low Price] Submitting model={WAN27_SPICY_MODEL}, "
                f"seconds={seconds}, resolution={resolution}"
            )
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": WAN27_SPICY_MODEL,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": WAN27_SPICY_MODEL,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


KLING_T2V_MODELS = [
    "kling-v3.0-std-t2v",
    "kling-v3.0-pro-t2v",
    "kling-v3-turbo-std-t2v",
    "kling-v3-turbo-pro-t2v",
    "kling-v3-4k-t2v",
    "kling-o3-std-t2v",
    "kling-o3-pro-t2v",
    "kling-o3-4k-t2v",
]
KLING_I2V_MODELS = [
    "kling-v3.0-std-i2v",
    "kling-v3.0-pro-i2v",
    "kling-v3-turbo-std-i2v",
    "kling-v3-turbo-pro-i2v",
    "kling-v3-4k-i2v",
    "kling-o3-std-i2v",
    "kling-o3-pro-i2v",
    "kling-o3-4k-i2v",
]
KLING_R2V_MODELS = [
    "kling-o3-std-r2v",
    "kling-o3-pro-r2v",
    "kling-o3-4k-r2v",
]
KLING_VIDEO_MODELS = KLING_T2V_MODELS + KLING_I2V_MODELS + KLING_R2V_MODELS
KLING_EDIT_MODELS = ["kling-o3-std-edit", "kling-o3-pro-edit"]
KLING_SECONDS = ["5", "10"]
KLING_MAX_REFERENCE_IMAGES = 4


def validate_kling_video_inputs(
    model: str,
    prompt: str,
    seconds: str,
    ratio: str,
    negative_prompt: str,
) -> None:
    if model not in KLING_VIDEO_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Kling model: {model}")
    if str(seconds) not in KLING_SECONDS:
        raise SeedanceLowPriceError("Kling seconds must be 5 or 10")
    if ratio not in RATIOS:
        raise SeedanceLowPriceError(f"Unsupported Kling ratio: {ratio}")

    prompt_text = str(prompt or "").strip()
    if len(prompt_text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Kling prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    negative_prompt_text = str(negative_prompt or "").strip()
    if len(negative_prompt_text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Kling negative_prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    if model in KLING_T2V_MODELS + KLING_R2V_MODELS and not prompt_text:
        raise SeedanceLowPriceError(
            "Kling text/reference-to-video requires a prompt"
        )


def build_kling_video_payload(
    model: str,
    prompt: str,
    seconds: str,
    ratio: str,
    negative_prompt: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_kling_video_inputs(model, prompt, seconds, ratio, negative_prompt)
    metadata: Dict[str, Any] = {}
    if ratio != "adaptive":
        metadata["ratio"] = ratio
    negative_prompt_text = str(negative_prompt or "").strip()
    if negative_prompt_text:
        metadata["negative_prompt"] = negative_prompt_text

    payload: Dict[str, Any] = {
        "model": model,
        "seconds": str(seconds),
        "metadata": metadata,
    }
    prompt_text = str(prompt or "").strip()
    if prompt_text:
        payload["prompt"] = prompt_text

    urls = list(image_urls or [])
    if model in KLING_I2V_MODELS:
        if not urls:
            raise SeedanceLowPriceError(
                "Kling image-to-video requires image1"
            )
        payload["images"] = urls[:2]
    elif model in KLING_R2V_MODELS:
        if not urls:
            raise SeedanceLowPriceError(
                "Kling reference-to-video requires at least one image"
            )
        payload["images"] = urls[:KLING_MAX_REFERENCE_IMAGES]
    return payload


class Comfly_kling_video_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {}
        for index in range(1, KLING_MAX_REFERENCE_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (
                    KLING_VIDEO_MODELS,
                    {"default": KLING_T2V_MODELS[0]},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (KLING_SECONDS, {"default": "5"}),
                "ratio": (RATIOS, {"default": "16:9"}),
                "negative_prompt": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="5",
        ratio="16:9",
        negative_prompt="",
        **kwargs,
    ):
        if model is None:
            return True
        try:
            validate_kling_video_inputs(
                model,
                prompt,
                seconds,
                ratio,
                negative_prompt,
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _connected_images(kwargs: Dict[str, Any]) -> List[Tuple[int, Any]]:
        return [
            (index, kwargs[f"image{index}"])
            for index in range(1, KLING_MAX_REFERENCE_IMAGES + 1)
            if kwargs.get(f"image{index}") is not None
        ]

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        ratio: str,
        negative_prompt: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_kling_video_inputs(
                model,
                prompt,
                seconds,
                ratio,
                negative_prompt,
            )
            config = resolve_config(api_config)
            connected = self._connected_images(kwargs)
            selected: List[Tuple[int, Any]] = []
            if model in KLING_I2V_MODELS:
                if kwargs.get("image1") is None:
                    raise SeedanceLowPriceError(
                        "Kling image-to-video requires image1"
                    )
                selected = [(1, kwargs["image1"])]
                if kwargs.get("image2") is not None:
                    selected.append((2, kwargs["image2"]))
            elif model in KLING_R2V_MODELS:
                if not connected:
                    raise SeedanceLowPriceError(
                        "Kling reference-to-video requires at least one image"
                    )
                selected = connected[:KLING_MAX_REFERENCE_IMAGES]
                slots = [slot for slot, _ in selected]
                if slots != list(range(1, len(slots) + 1)):
                    print(
                        f"[Kling Low Price] Image slots {slots} have gaps; "
                        "connected images will be compacted in slot order"
                    )

            image_urls: List[str] = []
            for position, (slot, image) in enumerate(selected, start=1):
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image),
                        f"kling_reference_{slot}.png",
                        "image/png",
                        config,
                    )
                )
                update_progress(int(position / len(selected) * 20))

            payload = build_kling_video_payload(
                model,
                prompt,
                seconds,
                ratio,
                negative_prompt,
                image_urls,
            )
            print(f"[Kling Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


def validate_kling_edit_inputs(
    model: str,
    video_url: str,
    prompt: str,
    seconds: str,
) -> None:
    if model not in KLING_EDIT_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Kling edit model: {model}")
    if str(seconds) not in KLING_SECONDS:
        raise SeedanceLowPriceError("Kling edit seconds must be 5 or 10")
    url_text = str(video_url or "").strip()
    if url_text:
        parsed = urlsplit(url_text)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise SeedanceLowPriceError(
                "Kling edit video_url must be an http(s) URL"
            )
    prompt_text = str(prompt or "").strip()
    if not prompt_text:
        raise SeedanceLowPriceError("Kling edit requires a prompt")
    if len(prompt_text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Kling edit prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )


def build_kling_edit_payload(
    model: str,
    prompt: str,
    seconds: str,
    video_url: str,
) -> Dict[str, Any]:
    validate_kling_edit_inputs(model, video_url, prompt, seconds)
    url_text = str(video_url or "").strip()
    if not url_text:
        raise SeedanceLowPriceError("Kling edit requires a video URL")
    return {
        "model": model,
        "prompt": str(prompt).strip(),
        "seconds": str(seconds),
        "metadata": {
            "content": [
                {
                    "type": "video_url",
                    "video_url": {"url": url_text},
                }
            ],
        },
    }


class Comfly_kling_o3_edit_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (
                    KLING_EDIT_MODELS,
                    {"default": KLING_EDIT_MODELS[0]},
                ),
                "video_url": ("STRING", {"default": ""}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (KLING_SECONDS, {"default": "5"}),
            },
            "optional": {
                "input_video": (VIDEO_TYPE,),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        video_url="",
        prompt="",
        seconds="5",
        **kwargs,
    ):
        if model is None:
            return True
        try:
            validate_kling_edit_inputs(model, video_url, prompt, seconds)
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        video_url: str,
        prompt: str,
        seconds: str,
        input_video: Any = None,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_kling_edit_inputs(model, video_url, prompt, seconds)
            source_url = str(video_url or "").strip()
            if not source_url and input_video is None:
                raise SeedanceLowPriceError(
                    "Kling edit requires input_video or video_url"
                )

            config = resolve_config(api_config)
            if not source_url:
                source_url = upload_media(
                    video_to_mp4_bytes(input_video),
                    "kling_o3_edit_input.mp4",
                    "video/mp4",
                    config,
                )
            update_progress(20)

            payload = build_kling_edit_payload(
                model,
                prompt,
                seconds,
                source_url,
            )
            print(f"[Kling O3 Edit Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            result_url = extract_video_url(final_response)
            video = download_video(result_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                result_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


HAILUO23_T2V_MODELS = [
    "hailuo-2.3-t2v-standard",
    "hailuo-2.3-t2v-pro",
]
HAILUO23_I2V_MODELS = [
    "hailuo-2.3-i2v-standard",
    "hailuo-2.3-i2v-pro",
    "hailuo-2.3-fast-i2v",
    "hailuo-2.3-fast-pro-i2v",
]
HAILUO23_MODELS = HAILUO23_T2V_MODELS + HAILUO23_I2V_MODELS
HAILUO23_SECONDS = ["6", "10"]
HAILUO23_RESOLUTIONS = ["768p", "1080p"]
HAILUO23_PROMPT_MAX_LENGTH = 2000
HAILUO23_MIN_IMAGE_SHORT_EDGE = 301
HAILUO23_MIN_ASPECT_RATIO = 0.4
HAILUO23_MAX_ASPECT_RATIO = 2.5


def validate_hailuo23_inputs(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
) -> None:
    if model not in HAILUO23_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Hailuo 2.3 model: {model}")
    if str(seconds) not in HAILUO23_SECONDS:
        raise SeedanceLowPriceError("Hailuo 2.3 seconds must be 6 or 10")
    if resolution not in HAILUO23_RESOLUTIONS:
        raise SeedanceLowPriceError(
            "Hailuo 2.3 resolution must be 768p or 1080p"
        )
    if str(seconds) == "10" and resolution == "1080p":
        raise SeedanceLowPriceError("Hailuo 2.3 1080p only supports 6 seconds")
    if ratio not in RATIOS:
        raise SeedanceLowPriceError(f"Unsupported Hailuo 2.3 ratio: {ratio}")

    prompt_text = str(prompt or "").strip()
    if len(prompt_text) > HAILUO23_PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Hailuo 2.3 prompt exceeds {HAILUO23_PROMPT_MAX_LENGTH} characters"
        )
    if model in HAILUO23_T2V_MODELS and not prompt_text:
        raise SeedanceLowPriceError("Hailuo 2.3 text-to-video requires a prompt")


def validate_hailuo23_first_image(image: Any) -> None:
    if not isinstance(image, torch.Tensor) or image.ndim not in (3, 4):
        raise SeedanceLowPriceError("Hailuo first_image must be an IMAGE tensor")
    shape = tuple(image.shape)
    height, width = int(shape[-3]), int(shape[-2])
    if height <= 0 or width <= 0:
        raise SeedanceLowPriceError(
            "Hailuo first_image width and height must be positive"
        )
    if min(height, width) < HAILUO23_MIN_IMAGE_SHORT_EDGE:
        raise SeedanceLowPriceError(
            "Hailuo first_image short edge must be greater than 300px"
        )
    aspect_ratio = width / height
    if not HAILUO23_MIN_ASPECT_RATIO <= aspect_ratio <= HAILUO23_MAX_ASPECT_RATIO:
        raise SeedanceLowPriceError(
            "Hailuo first_image aspect ratio must be between 2:5 and 5:2"
        )


def build_hailuo23_payload(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_hailuo23_inputs(model, prompt, seconds, resolution, ratio)
    prompt_text = str(prompt or "").strip()
    metadata: Dict[str, Any] = {"resolution": resolution}
    if model in HAILUO23_T2V_MODELS and ratio != "adaptive":
        metadata["ratio"] = ratio

    payload: Dict[str, Any] = {
        "model": model,
        "seconds": str(seconds),
        "metadata": metadata,
    }
    if prompt_text:
        payload["prompt"] = prompt_text
    if model in HAILUO23_I2V_MODELS:
        urls = list(image_urls or [])
        if not urls:
            raise SeedanceLowPriceError(
                "Hailuo 2.3 image-to-video requires first_image"
            )
        payload["images"] = [urls[0]]
    return payload


class Comfly_hailuo_2_3_video_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (
                    HAILUO23_MODELS,
                    {"default": HAILUO23_T2V_MODELS[0]},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (HAILUO23_SECONDS, {"default": "6"}),
                "resolution": (HAILUO23_RESOLUTIONS, {"default": "768p"}),
                "ratio": (RATIOS, {"default": "16:9"}),
            },
            "optional": {
                "first_image": ("IMAGE",),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="6",
        resolution="768p",
        ratio="16:9",
        **kwargs,
    ):
        if model is None:
            return True
        try:
            validate_hailuo23_inputs(model, prompt, seconds, resolution, ratio)
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        first_image: Any = None,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_hailuo23_inputs(model, prompt, seconds, resolution, ratio)
            config = resolve_config(api_config)
            image_urls: List[str] = []
            if model in HAILUO23_I2V_MODELS:
                if first_image is None:
                    raise SeedanceLowPriceError(
                        "Hailuo 2.3 image-to-video requires first_image"
                    )
                validate_hailuo23_first_image(first_image)
                image_bytes = image_to_png_bytes(first_image)
                image_urls.append(
                    upload_media(
                        image_bytes,
                        "hailuo_2_3_first_image.png",
                        "image/png",
                        config,
                    )
                )
                update_progress(20)

            payload = build_hailuo23_payload(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                image_urls,
            )
            print(f"[Hailuo 2.3 Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


HAILUO_H3_T2V_MODEL = "hailuo-h3-t2v"
HAILUO_H3_I2V_MODEL = "hailuo-h3-i2v"
HAILUO_H3_MULTI_MODEL = "hailuo-h3-multi"
HAILUO_H3_GLOBAL_T2V_MODEL = "hailuo-h3-global-t2v"
HAILUO_H3_GLOBAL_I2V_MODEL = "hailuo-h3-global-i2v"
HAILUO_H3_GLOBAL_MULTI_MODEL = "hailuo-h3-global-multi"
HAILUO_H3_T2V_MODELS = [
    HAILUO_H3_T2V_MODEL,
    HAILUO_H3_GLOBAL_T2V_MODEL,
]
HAILUO_H3_I2V_MODELS = [
    HAILUO_H3_I2V_MODEL,
    HAILUO_H3_GLOBAL_I2V_MODEL,
]
HAILUO_H3_MULTI_MODELS = [
    HAILUO_H3_MULTI_MODEL,
    HAILUO_H3_GLOBAL_MULTI_MODEL,
]
HAILUO_H3_MODELS = [
    HAILUO_H3_T2V_MODEL,
    HAILUO_H3_I2V_MODEL,
    HAILUO_H3_MULTI_MODEL,
    HAILUO_H3_GLOBAL_T2V_MODEL,
    HAILUO_H3_GLOBAL_I2V_MODEL,
    HAILUO_H3_GLOBAL_MULTI_MODEL,
]
HAILUO_H3_SECONDS = [str(seconds) for seconds in range(5, 16)]
HAILUO_H3_RESOLUTIONS = ["768P", "2K"]
HAILUO_H3_PROMPT_MAX_LENGTH = 20480
HAILUO_H3_MAX_IMAGES = 9
HAILUO_H3_MAX_VIDEOS = 3
HAILUO_H3_MAX_AUDIOS = 3


def validate_hailuo_h3_inputs(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
) -> None:
    if model not in HAILUO_H3_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Hailuo H3 model: {model}")
    if str(seconds) not in HAILUO_H3_SECONDS:
        raise SeedanceLowPriceError("Hailuo H3 seconds must be between 5 and 15")
    if resolution not in HAILUO_H3_RESOLUTIONS:
        raise SeedanceLowPriceError("Hailuo H3 resolution must be 768P or 2K")
    if ratio not in RATIOS:
        raise SeedanceLowPriceError(f"Unsupported Hailuo H3 ratio: {ratio}")

    prompt_text = str(prompt or "").strip()
    if len(prompt_text) > HAILUO_H3_PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Hailuo H3 prompt exceeds {HAILUO_H3_PROMPT_MAX_LENGTH} characters"
        )
    if model in (*HAILUO_H3_T2V_MODELS, *HAILUO_H3_MULTI_MODELS) and not prompt_text:
        raise SeedanceLowPriceError(
            "Hailuo H3 text-to-video and multi require a prompt"
        )


def build_hailuo_h3_payload(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
    video_urls: Optional[List[str]] = None,
    audio_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_hailuo_h3_inputs(model, prompt, seconds, resolution, ratio)
    prompt_text = str(prompt or "").strip()
    images = list(image_urls or [])
    videos = list(video_urls or [])
    audios = list(audio_urls or [])

    metadata: Dict[str, Any] = {"resolution": resolution}
    payload: Dict[str, Any] = {
        "model": model,
        "seconds": str(seconds),
        "metadata": metadata,
    }

    if model in (*HAILUO_H3_T2V_MODELS, *HAILUO_H3_MULTI_MODELS):
        metadata["ratio"] = ratio
        payload["prompt"] = prompt_text

    if model in HAILUO_H3_I2V_MODELS:
        if not images:
            raise SeedanceLowPriceError(
                "Hailuo H3 image-to-video requires image1 as the first frame"
            )
        payload["images"] = images[:2]
        if prompt_text:
            payload["prompt"] = prompt_text
        return payload

    if model in HAILUO_H3_MULTI_MODELS:
        if not (images or videos or audios):
            raise SeedanceLowPriceError(
                "Hailuo H3 multi requires at least one image, video, or audio"
            )
        if images:
            payload["images"] = images[:HAILUO_H3_MAX_IMAGES]
        if videos:
            metadata["video_url"] = videos[:HAILUO_H3_MAX_VIDEOS]
        if audios:
            metadata["audio_url"] = audios[:HAILUO_H3_MAX_AUDIOS]
    return payload


class Comfly_hailuo_h3_video_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, Tuple[Any, ...]] = {
            "api_config": (CONFIG_TYPE,),
        }
        for index in range(1, HAILUO_H3_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        for index in range(1, HAILUO_H3_MAX_VIDEOS + 1):
            optional[f"video{index}"] = (VIDEO_TYPE,)
        for index in range(1, HAILUO_H3_MAX_AUDIOS + 1):
            optional[f"audio{index}"] = ("AUDIO",)
        optional["skip_error"] = ("BOOLEAN", {"default": False})

        return {
            "required": {
                "model": (
                    HAILUO_H3_MODELS,
                    {"default": HAILUO_H3_T2V_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (HAILUO_H3_SECONDS, {"default": "5"}),
                "resolution": (HAILUO_H3_RESOLUTIONS, {"default": "768P"}),
                "ratio": (RATIOS, {"default": "16:9"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="5",
        resolution="768P",
        ratio="16:9",
        **kwargs,
    ):
        if model is None:
            return True
        try:
            validate_hailuo_h3_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_hailuo_h3_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
            )
            config = resolve_config(api_config)
            image_slots: List[Tuple[int, Any]] = []
            video_slots: List[Tuple[int, Any]] = []
            audio_slots: List[Tuple[int, Any]] = []

            if model in HAILUO_H3_I2V_MODELS:
                if kwargs.get("image1") is None:
                    raise SeedanceLowPriceError(
                        "Hailuo H3 image-to-video requires image1 as the first frame"
                    )
                image_slots = _connected_slots(
                    kwargs,
                    "image",
                    2,
                    "Hailuo H3 Low Price",
                )
            elif model in HAILUO_H3_MULTI_MODELS:
                image_slots = _connected_slots(
                    kwargs,
                    "image",
                    HAILUO_H3_MAX_IMAGES,
                    "Hailuo H3 Low Price",
                )
                video_slots = _connected_slots(
                    kwargs,
                    "video",
                    HAILUO_H3_MAX_VIDEOS,
                    "Hailuo H3 Low Price",
                )
                audio_slots = _connected_slots(
                    kwargs,
                    "audio",
                    HAILUO_H3_MAX_AUDIOS,
                    "Hailuo H3 Low Price",
                )
                if not (image_slots or video_slots or audio_slots):
                    raise SeedanceLowPriceError(
                        "Hailuo H3 multi requires at least one image, video, or audio"
                    )

            total_uploads = len(image_slots) + len(video_slots) + len(audio_slots)
            completed_uploads = 0
            image_urls: List[str] = []
            video_urls: List[str] = []
            audio_urls: List[str] = []

            def upload_completed() -> None:
                nonlocal completed_uploads
                completed_uploads += 1
                if total_uploads:
                    update_progress(int(completed_uploads / total_uploads * 25))

            for slot, image in image_slots:
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image),
                        f"hailuo_h3_image_{slot}.png",
                        "image/png",
                        config,
                    )
                )
                upload_completed()
            for slot, video in video_slots:
                video_urls.append(
                    upload_media(
                        video_to_mp4_bytes(video),
                        f"hailuo_h3_video_{slot}.mp4",
                        "video/mp4",
                        config,
                    )
                )
                upload_completed()
            for slot, audio in audio_slots:
                audio_urls.append(
                    upload_media(
                        audio_to_wav_bytes(audio),
                        f"hailuo_h3_audio_{slot}.wav",
                        "audio/wav",
                        config,
                    )
                )
                upload_completed()

            payload = build_hailuo_h3_payload(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                image_urls,
                video_urls,
                audio_urls,
            )
            print(f"[Hailuo H3 Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(35)

            def on_poll_progress(progress: int) -> None:
                update_progress(35 + int(progress * 0.55))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


FLUX3_T2V_MODELS = [
    "flux-3-video-t2v",
    "flux-3-video-global-t2v",
]
FLUX3_I2V_MODELS = [
    "flux-3-video-i2v",
    "flux-3-video-global-i2v",
]
FLUX3_V2V_MODELS = [
    "flux-3-video-v2v",
    "flux-3-video-global-v2v",
]
FLUX3_DRAFT_ENHANCE_MODELS = [
    "flux-3-video-draft-enhance",
    "flux-3-video-global-draft-enhance",
]
FLUX3_VIDEO_MODELS = [
    FLUX3_T2V_MODELS[0],
    FLUX3_I2V_MODELS[0],
    FLUX3_V2V_MODELS[0],
    FLUX3_DRAFT_ENHANCE_MODELS[0],
    FLUX3_T2V_MODELS[1],
    FLUX3_I2V_MODELS[1],
    FLUX3_V2V_MODELS[1],
    FLUX3_DRAFT_ENHANCE_MODELS[1],
]
FLUX3_SECONDS = [str(seconds) for seconds in range(5, 21)]
FLUX3_RESOLUTIONS = ["hd", "fhd"]
FLUX3_RATIOS = ["auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"]
FLUX3_AUDIO_MODES = ["api_default", "enabled", "disabled"]
FLUX3_SAFETY_TOLERANCES = ["api_default", "0", "1", "2", "3", "4"]
FLUX3_MAX_IMAGES = 10
FLUX3_PROMPT_MAX_LENGTH = 20480


def validate_flux3_inputs(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    audio_mode: str,
    safety_tolerance: str,
    video_url: str = "",
    draft_cache: str = "",
    has_image: bool = False,
    has_video: bool = False,
    strict: bool = True,
) -> str:
    if model not in FLUX3_VIDEO_MODELS:
        raise SeedanceLowPriceError(f"Unsupported FLUX 3 model: {model}")
    if str(seconds) not in FLUX3_SECONDS:
        raise SeedanceLowPriceError("FLUX 3 seconds must be between 5 and 20")
    if resolution not in FLUX3_RESOLUTIONS:
        raise SeedanceLowPriceError("FLUX 3 resolution must be hd or fhd")
    if ratio not in FLUX3_RATIOS:
        raise SeedanceLowPriceError(f"Unsupported FLUX 3 ratio: {ratio}")
    if audio_mode not in FLUX3_AUDIO_MODES:
        raise SeedanceLowPriceError(f"Unsupported FLUX 3 audio mode: {audio_mode}")
    if str(safety_tolerance) not in FLUX3_SAFETY_TOLERANCES:
        raise SeedanceLowPriceError(
            f"Unsupported FLUX 3 safety tolerance: {safety_tolerance}"
        )

    prompt_text = str(prompt or "").strip()
    if len(prompt_text) > FLUX3_PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"FLUX 3 prompt exceeds {FLUX3_PROMPT_MAX_LENGTH} characters"
        )
    direct_video_url = str(video_url or "").strip()
    if direct_video_url and not direct_video_url.startswith(("http://", "https://")):
        raise SeedanceLowPriceError("FLUX 3 video_url must be an http(s) URL")

    if strict and model not in FLUX3_DRAFT_ENHANCE_MODELS and not prompt_text:
        raise SeedanceLowPriceError("FLUX 3 generation requires a prompt")
    if strict and model in FLUX3_I2V_MODELS and not has_image:
        raise SeedanceLowPriceError("FLUX 3 image-to-video requires image1")
    if strict and model in FLUX3_V2V_MODELS and not (has_video or direct_video_url):
        raise SeedanceLowPriceError(
            "FLUX 3 video-to-video requires input_video or video_url"
        )
    if (
        strict
        and model in FLUX3_DRAFT_ENHANCE_MODELS
        and not str(draft_cache or "").strip()
    ):
        raise SeedanceLowPriceError("FLUX 3 Draft Enhance requires draft_cache")
    return prompt_text


def build_flux3_payload(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    draft: bool = False,
    audio_mode: str = "api_default",
    safety_tolerance: str = "api_default",
    image_urls: Optional[List[str]] = None,
    uploaded_video_url: str = "",
    draft_cache: str = "",
) -> Dict[str, Any]:
    images = list(image_urls or [])
    source_video_url = str(uploaded_video_url or "").strip()
    prompt_text = validate_flux3_inputs(
        model,
        prompt,
        seconds,
        resolution,
        ratio,
        audio_mode,
        safety_tolerance,
        video_url=source_video_url,
        draft_cache=draft_cache,
        has_image=bool(images),
        has_video=bool(source_video_url),
        strict=True,
    )

    metadata: Dict[str, Any] = {
        "resolution": resolution,
        "ratio": ratio,
    }
    payload: Dict[str, Any] = {
        "model": model,
        "seconds": str(seconds),
        "metadata": metadata,
    }

    if model in FLUX3_DRAFT_ENHANCE_MODELS:
        metadata["draft_cache"] = str(draft_cache).strip()
    else:
        payload["prompt"] = prompt_text
        if bool(draft):
            metadata["draft"] = True

    if audio_mode == "enabled":
        metadata["generate_audio"] = True
    elif audio_mode == "disabled":
        metadata["generate_audio"] = False

    if safety_tolerance != "api_default":
        metadata["safety_tolerance"] = int(safety_tolerance)

    if model in FLUX3_I2V_MODELS:
        payload["images"] = images[:FLUX3_MAX_IMAGES]
    elif model in FLUX3_V2V_MODELS:
        metadata["video_url"] = source_video_url
    return payload


def extract_flux3_draft_cache(response: Dict[str, Any]) -> str:
    metadata = response.get("metadata") if isinstance(response, dict) else None
    if isinstance(metadata, dict) and metadata.get("draft_cache"):
        return str(metadata["draft_cache"])
    return ""


class Comfly_flux3_video_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, Tuple[Any, ...]] = {
            "api_config": (CONFIG_TYPE,),
        }
        for index in range(1, FLUX3_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        optional.update(
            {
                "input_video": (VIDEO_TYPE,),
                "video_url": ("STRING", {"default": ""}),
                "draft_cache": ("STRING", {"default": ""}),
                "skip_error": ("BOOLEAN", {"default": False}),
            }
        )
        return {
            "required": {
                "model": (
                    FLUX3_VIDEO_MODELS,
                    {"default": FLUX3_T2V_MODELS[0]},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (FLUX3_SECONDS, {"default": "5"}),
                "resolution": (FLUX3_RESOLUTIONS, {"default": "hd"}),
                "ratio": (FLUX3_RATIOS, {"default": "auto"}),
                "draft": ("BOOLEAN", {"default": False}),
                "audio_mode": (FLUX3_AUDIO_MODES, {"default": "api_default"}),
                "safety_tolerance": (
                    FLUX3_SAFETY_TOLERANCES,
                    {"default": "api_default"},
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "draft_cache", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="5",
        resolution="hd",
        ratio="auto",
        audio_mode="api_default",
        safety_tolerance="api_default",
        video_url="",
        draft_cache="",
        **kwargs,
    ):
        if model is None:
            return True
        try:
            validate_flux3_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                audio_mode,
                safety_tolerance,
                video_url=video_url,
                draft_cache=draft_cache,
                strict=False,
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        draft: bool,
        audio_mode: str,
        safety_tolerance: str,
        api_config: Any = None,
        input_video: Any = None,
        video_url: str = "",
        draft_cache: str = "",
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            image_slots = (
                _connected_slots(
                    kwargs,
                    "image",
                    FLUX3_MAX_IMAGES,
                    "FLUX 3 Low Price",
                )
                if model in FLUX3_I2V_MODELS
                else []
            )
            direct_video_url = str(video_url or "").strip()
            validate_flux3_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                audio_mode,
                safety_tolerance,
                video_url=direct_video_url,
                draft_cache=draft_cache,
                has_image=bool(image_slots and kwargs.get("image1") is not None),
                has_video=input_video is not None,
                strict=True,
            )
            config = resolve_config(api_config)
            image_urls: List[str] = []
            source_video_url = direct_video_url

            if model in FLUX3_I2V_MODELS:
                for position, (slot, image) in enumerate(image_slots, start=1):
                    image_urls.append(
                        upload_media(
                            image_to_png_bytes(image),
                            f"flux3_keyframe_{slot}.png",
                            "image/png",
                            config,
                        )
                    )
                    update_progress(int(position / len(image_slots) * 25))
            elif model in FLUX3_V2V_MODELS:
                if not source_video_url:
                    source_video_url = upload_media(
                        video_to_mp4_bytes(input_video),
                        "flux3_source.mp4",
                        "video/mp4",
                        config,
                    )
                update_progress(25)
            else:
                update_progress(25)

            payload = build_flux3_payload(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                draft=draft,
                audio_mode=audio_mode,
                safety_tolerance=safety_tolerance,
                image_urls=image_urls,
                uploaded_video_url=source_video_url,
                draft_cache=draft_cache,
            )
            print(f"[FLUX 3 Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(35)

            def on_poll_progress(progress: int) -> None:
                update_progress(35 + int(progress * 0.55))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            result_video_url = extract_video_url(final_response)
            video = download_video(result_video_url)
            result_draft_cache = extract_flux3_draft_cache(final_response)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                result_video_url,
                result_draft_cache,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


MINIMAX_H3_OW_T2V_MODEL = "minimax-h3-ow-t2v"
MINIMAX_H3_OW_R2V_MODEL = "minimax-h3-ow-r2v"
MINIMAX_H3_OW_I2V_MODEL = "minimax-h3-ow-i2v"
MINIMAX_H3_OW_MODELS = [
    MINIMAX_H3_OW_T2V_MODEL,
    MINIMAX_H3_OW_R2V_MODEL,
    MINIMAX_H3_OW_I2V_MODEL,
]
MINIMAX_H3_OW_SECONDS = ["5", "10", "15"]
MINIMAX_H3_OW_RESOLUTIONS = ["480p", "720p"]
MINIMAX_H3_OW_RATIOS = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "9:16",
    "16:9",
    "21:9",
]


def validate_minimax_h3_ow_inputs(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    has_image: bool = False,
    strict: bool = True,
) -> str:
    if model not in MINIMAX_H3_OW_MODELS:
        raise SeedanceLowPriceError(f"Unsupported MiniMax H3 OW model: {model}")
    if str(seconds) not in MINIMAX_H3_OW_SECONDS:
        raise SeedanceLowPriceError("MiniMax H3 OW seconds must be 5, 10, or 15")
    if resolution not in MINIMAX_H3_OW_RESOLUTIONS:
        raise SeedanceLowPriceError("MiniMax H3 OW resolution must be 480p or 720p")
    if ratio not in MINIMAX_H3_OW_RATIOS:
        raise SeedanceLowPriceError(f"Unsupported MiniMax H3 OW ratio: {ratio}")

    prompt_text = str(prompt or "").strip()
    if len(prompt_text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"MiniMax H3 OW prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    if (
        strict
        and model in (MINIMAX_H3_OW_T2V_MODEL, MINIMAX_H3_OW_R2V_MODEL)
        and not prompt_text
    ):
        raise SeedanceLowPriceError(
            "MiniMax H3 OW T2V and R2V require a prompt"
        )
    if (
        strict
        and model in (MINIMAX_H3_OW_I2V_MODEL, MINIMAX_H3_OW_R2V_MODEL)
        and not has_image
    ):
        raise SeedanceLowPriceError(
            "MiniMax H3 OW I2V and R2V require image1"
        )
    return prompt_text


def build_minimax_h3_ow_payload(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    images = list(image_urls or [])
    prompt_text = validate_minimax_h3_ow_inputs(
        model,
        prompt,
        seconds,
        resolution,
        ratio,
        has_image=bool(images),
        strict=True,
    )
    if len(images) > 1:
        raise SeedanceLowPriceError("MiniMax H3 OW accepts exactly one reference image")

    payload: Dict[str, Any] = {
        "model": model,
        "seconds": str(seconds),
        "metadata": {
            "resolution": resolution,
            "ratio": ratio,
        },
    }
    if prompt_text:
        payload["prompt"] = prompt_text
    if model in (MINIMAX_H3_OW_I2V_MODEL, MINIMAX_H3_OW_R2V_MODEL):
        payload["images"] = images
    return payload


class Comfly_minimax_h3_ow_video_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (
                    MINIMAX_H3_OW_MODELS,
                    {"default": MINIMAX_H3_OW_T2V_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (MINIMAX_H3_OW_SECONDS, {"default": "5"}),
                "resolution": (MINIMAX_H3_OW_RESOLUTIONS, {"default": "480p"}),
                "ratio": (MINIMAX_H3_OW_RATIOS, {"default": "16:9"}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="5",
        resolution="480p",
        ratio="16:9",
        image1=None,
        strict=False,
        **kwargs,
    ):
        if model is None:
            return True
        try:
            validate_minimax_h3_ow_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                has_image=image1 is not None,
                strict=bool(strict),
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        image1: Any = None,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_minimax_h3_ow_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                has_image=image1 is not None,
                strict=True,
            )
            config = resolve_config(api_config)
            image_urls: List[str] = []
            if model in (MINIMAX_H3_OW_I2V_MODEL, MINIMAX_H3_OW_R2V_MODEL):
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image1),
                        "minimax_h3_ow_reference.png",
                        "image/png",
                        config,
                    )
                )
            update_progress(25)
            payload = build_minimax_h3_ow_payload(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                image_urls,
            )
            print(f"[MiniMax H3 OW Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)
            final_response = poll_task(
                task_id,
                config,
                on_progress=lambda value: update_progress(30 + int(value * 0.6)),
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


MINIMAX_H3_OW_FAST_I2V_MODEL = "minimax-h3-ow-i2v-fast"
MINIMAX_H3_OW_FAST_R2V_MODEL = "minimax-h3-ow-r2v-fast"
MINIMAX_H3_OW_FAST_MODELS = [
    MINIMAX_H3_OW_FAST_I2V_MODEL,
    MINIMAX_H3_OW_FAST_R2V_MODEL,
]
MINIMAX_H3_OW_FAST_MAX_IMAGES = 9


def validate_minimax_h3_ow_fast_inputs(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    connected_image_slots: Optional[List[int]] = None,
    strict: bool = True,
) -> str:
    if model not in MINIMAX_H3_OW_FAST_MODELS:
        raise SeedanceLowPriceError(
            f"Unsupported MiniMax H3 OW Fast model: {model}"
        )
    if str(seconds) not in MINIMAX_H3_OW_SECONDS:
        raise SeedanceLowPriceError(
            "MiniMax H3 OW Fast seconds must be 5, 10, or 15"
        )
    if resolution not in MINIMAX_H3_OW_RESOLUTIONS:
        raise SeedanceLowPriceError(
            "MiniMax H3 OW Fast resolution must be 480p or 720p"
        )
    if ratio not in MINIMAX_H3_OW_RATIOS:
        raise SeedanceLowPriceError(
            f"Unsupported MiniMax H3 OW Fast ratio: {ratio}"
        )

    prompt_text = str(prompt or "").strip()
    if len(prompt_text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"MiniMax H3 OW Fast prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    if strict and model == MINIMAX_H3_OW_FAST_R2V_MODEL and not prompt_text:
        raise SeedanceLowPriceError(
            "MiniMax H3 OW R2V Fast requires a prompt"
        )

    if strict:
        slots = list(connected_image_slots or [])
        if not slots:
            raise SeedanceLowPriceError(
                "MiniMax H3 OW Fast requires at least one image"
            )
        if len(slots) > MINIMAX_H3_OW_FAST_MAX_IMAGES:
            raise SeedanceLowPriceError(
                "MiniMax H3 OW Fast accepts at most 9 images"
            )
        if model == MINIMAX_H3_OW_FAST_I2V_MODEL and slots != [1]:
            raise SeedanceLowPriceError(
                "MiniMax H3 OW I2V Fast requires exactly image1"
            )
    return prompt_text


def build_minimax_h3_ow_fast_payload(
    model: str,
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    images = list(image_urls or [])
    max_images = (
        1
        if model == MINIMAX_H3_OW_FAST_I2V_MODEL
        else MINIMAX_H3_OW_FAST_MAX_IMAGES
    )
    if len(images) > max_images:
        raise SeedanceLowPriceError(
            f"MiniMax H3 OW Fast model {model} accepts at most {max_images} image(s)"
        )
    prompt_text = validate_minimax_h3_ow_fast_inputs(
        model,
        prompt,
        seconds,
        resolution,
        ratio,
        connected_image_slots=list(range(1, len(images) + 1)),
        strict=True,
    )
    payload: Dict[str, Any] = {
        "model": model,
        "seconds": str(seconds),
        "images": images,
        "metadata": {
            "resolution": resolution,
            "ratio": ratio,
        },
    }
    if prompt_text:
        payload["prompt"] = prompt_text
    return payload


class Comfly_minimax_h3_ow_fast_video_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, Tuple[Any, ...]] = {}
        for index in range(1, MINIMAX_H3_OW_FAST_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (
                    MINIMAX_H3_OW_FAST_MODELS,
                    {"default": MINIMAX_H3_OW_FAST_I2V_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (MINIMAX_H3_OW_SECONDS, {"default": "5"}),
                "resolution": (MINIMAX_H3_OW_RESOLUTIONS, {"default": "480p"}),
                "ratio": (MINIMAX_H3_OW_RATIOS, {"default": "16:9"}),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="5",
        resolution="480p",
        ratio="16:9",
        strict=False,
        **kwargs,
    ):
        if model is None:
            return True
        try:
            connected_slots = [
                index
                for index in range(1, MINIMAX_H3_OW_FAST_MAX_IMAGES + 1)
                if kwargs.get(f"image{index}") is not None
            ]
            validate_minimax_h3_ow_fast_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                connected_image_slots=connected_slots,
                strict=bool(strict),
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _connected_images(kwargs: Dict[str, Any]) -> List[Tuple[int, Any]]:
        connected = [
            (index, kwargs[f"image{index}"])
            for index in range(1, MINIMAX_H3_OW_FAST_MAX_IMAGES + 1)
            if kwargs.get(f"image{index}") is not None
        ]
        slots = [slot for slot, _image in connected]
        if slots and slots != list(range(1, len(slots) + 1)):
            print(
                f"[MiniMax H3 OW Fast Low Price] Image slots {slots} have gaps; "
                "connected images will be compacted in slot order"
            )
        return connected

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            connected = self._connected_images(kwargs)
            validate_minimax_h3_ow_fast_inputs(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                connected_image_slots=[slot for slot, _image in connected],
                strict=True,
            )
            config = resolve_config(api_config)
            image_urls: List[str] = []
            for position, (slot, image) in enumerate(connected, start=1):
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image),
                        f"minimax_h3_ow_fast_reference_{slot}.png",
                        "image/png",
                        config,
                    )
                )
                update_progress(int(position / len(connected) * 25))

            payload = build_minimax_h3_ow_fast_payload(
                model,
                prompt,
                seconds,
                resolution,
                ratio,
                image_urls,
            )
            print(f"[MiniMax H3 OW Fast Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)
            final_response = poll_task(
                task_id,
                config,
                on_progress=lambda value: update_progress(30 + int(value * 0.6)),
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


MINMAX_H3_CONTEXT_IR_TEXT_MODEL = "minmax-h3-context-ir-text"
MINMAX_H3_CONTEXT_IR_IMAGE_MODEL = "minmax-h3-context-ir-image"
MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL = "minmax-h3-context-ir-multimodal"
MINMAX_H3_CONTEXT_IR_MODELS = [
    MINMAX_H3_CONTEXT_IR_TEXT_MODEL,
    MINMAX_H3_CONTEXT_IR_IMAGE_MODEL,
    MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL,
]
MINMAX_H3_CONTEXT_IR_SECONDS = [str(value) for value in range(4, 16)]
MINMAX_H3_CONTEXT_IR_TEXT_RATIOS = [
    "21:9",
    "16:9",
    "4:3",
    "1:1",
    "3:4",
    "9:16",
]
MINMAX_H3_CONTEXT_IR_RATIOS = [
    "api_default",
    "adaptive",
    *MINMAX_H3_CONTEXT_IR_TEXT_RATIOS,
]
MINMAX_H3_CONTEXT_IR_PROMPT_MAX_LENGTH = 7000
MINMAX_H3_CONTEXT_IR_MAX_IMAGES = 9
MINMAX_H3_CONTEXT_IR_MAX_VIDEOS = 3
MINMAX_H3_CONTEXT_IR_MAX_AUDIOS = 3
MINMAX_H3_CONTEXT_IR_RUNNING_STATUSES = {
    "NOT_START",
    "SUBMITTED",
    "QUEUED",
    "IN_PROGRESS",
    "PENDING",
    "PROCESSING",
}
MINMAX_H3_CONTEXT_IR_SEED_SPEC = (
    "INT",
    {
        "default": 0,
        "min": 0,
        "max": 0xFFFFFFFFFFFFFFFF,
        "step": 1,
        "control_after_generate": True,
        "tooltip": (
            "ComfyUI cache control only. Fixed reuses a cached result; other modes "
            "request a new run. This value is not sent to the API."
        ),
    },
)


def submit_minmax_h3_context_ir_task(
    payload: Dict[str, Any],
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Tuple[str, Dict[str, Any]]:
    url = f"{config['base_url']}/v1/video/generations"
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            sleep(min(2 ** attempt + 1, 15))
        try:
            response = _get_session().post(
                url,
                headers=_headers(config["api_key"]),
                json=payload,
                timeout=config.get("timeout", 60),
            )
        except requests.RequestException as exc:
            last_error = f"network error: {type(exc).__name__}: {exc}"
            continue

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                "Context IR submit rejected "
                f"(HTTP {response.status_code}): {message}"
            )

        task_id = None
        if isinstance(data, dict):
            task_id = data.get("task_id") or data.get("id")
            nested = data.get("data")
            if not task_id and isinstance(nested, dict):
                task_id = nested.get("task_id") or nested.get("id")
        if not task_id:
            raise SeedanceLowPriceError(
                "Context IR submit response did not contain id/task_id"
            )
        return str(task_id), data
    raise RuntimeError(f"Context IR submit failed after 3 attempts: {last_error}")


def poll_minmax_h3_context_ir_task(
    task_id: str,
    config: Dict[str, Any],
    on_progress: Optional[Callable[[int], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    url = f"{config['base_url']}/v1/video/generations/{task_id}"
    start = clock()
    failures = 0
    while True:
        if clock() - start > config.get("max_poll_time", 1800):
            raise RuntimeError(
                f"Context IR polling timed out [task_id: {task_id}]"
            )
        sleep(config.get("poll_interval", 4))
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
                    "Context IR polling failed after repeated network errors "
                    f"[task_id: {task_id}]"
                )
            sleep(min(failures * 2, 10))
            continue

        data = _response_json(response)
        if response.status_code != 200:
            message = extract_error_message(data, response.text[:300])
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise SeedanceLowPriceError(
                    "Context IR polling rejected "
                    f"(HTTP {response.status_code}): {message} [task_id: {task_id}]"
                )
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    "Context IR polling repeatedly returned "
                    f"HTTP {response.status_code}: {message} [task_id: {task_id}]"
                )
            sleep(min(failures * 2, 10))
            continue

        task_data = data.get("data") if isinstance(data, dict) else None
        if not isinstance(task_data, dict):
            task_data = data if isinstance(data, dict) else None
        if not isinstance(task_data, dict):
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    "Context IR polling response repeatedly had no task object "
                    f"[task_id: {task_id}]"
                )
            continue

        failures = 0
        status = str(task_data.get("status") or "").strip().upper()
        progress = _coerce_progress(task_data.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        if status in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
            return data
        if status in {"FAILURE", "FAILED", "CANCELED", "CANCELLED"}:
            reason = task_data.get("fail_reason") or extract_error_message(
                task_data, "Context IR task failed"
            )
            raise SeedanceLowPriceError(
                f"Context IR task failed: {reason} [task_id: {task_id}]"
            )
        if status and status not in MINMAX_H3_CONTEXT_IR_RUNNING_STATUSES:
            print(
                f"[MiniMax H3 Context IR] Unknown status '{status}', continuing polling"
            )


def extract_minmax_h3_context_ir_text(response: Dict[str, Any]) -> str:
    containers: List[Any] = [response]
    if isinstance(response, dict):
        containers.append(response.get("data"))
    for container in containers:
        if isinstance(container, dict):
            result_text = container.get("result_text")
            if isinstance(result_text, str) and result_text.strip():
                return result_text.strip()
    raise SeedanceLowPriceError(
        "Context IR task completed but response did not contain result_text"
    )


class Comfly_minmax_h3_context_ir_lowprice:
    """Enhance video prompts from text, first/last frames, or mixed media."""

    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, Tuple[Any, ...]] = {}
        for index in range(1, MINMAX_H3_CONTEXT_IR_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        for index in range(1, MINMAX_H3_CONTEXT_IR_MAX_VIDEOS + 1):
            optional[f"video{index}"] = (VIDEO_TYPE,)
        for index in range(1, MINMAX_H3_CONTEXT_IR_MAX_AUDIOS + 1):
            optional[f"audio{index}"] = (AUDIO_TYPE,)
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        optional["seed"] = MINMAX_H3_CONTEXT_IR_SEED_SPEC
        return {
            "required": {
                "model": (
                    MINMAX_H3_CONTEXT_IR_MODELS,
                    {"default": MINMAX_H3_CONTEXT_IR_TEXT_MODEL},
                ),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "Video prompt to enhance, 1 to 7000 characters.",
                    },
                ),
                "seconds": (
                    MINMAX_H3_CONTEXT_IR_SECONDS,
                    {"default": "4"},
                ),
                "ratio": (
                    MINMAX_H3_CONTEXT_IR_RATIOS,
                    {"default": "16:9"},
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("result_text", "task_id", "response")
    FUNCTION = "enhance"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True
    COMFLY_CONCURRENT_DISABLED = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt=None,
        seconds=None,
        ratio=None,
        strict=False,
        **kwargs,
    ):
        if model not in (None, *MINMAX_H3_CONTEXT_IR_MODELS):
            return f"Unsupported MiniMax H3 Context IR model: {model}"
        if seconds is not None and str(seconds) not in MINMAX_H3_CONTEXT_IR_SECONDS:
            return "Context IR seconds must be an integer from 4 to 15"
        if ratio is not None and ratio not in MINMAX_H3_CONTEXT_IR_RATIOS:
            return f"Unsupported Context IR ratio: {ratio}"

        prompt_text = str(prompt or "").strip()
        if len(prompt_text) > MINMAX_H3_CONTEXT_IR_PROMPT_MAX_LENGTH:
            return (
                "Context IR prompt exceeds "
                f"{MINMAX_H3_CONTEXT_IR_PROMPT_MAX_LENGTH} characters"
            )
        if strict and not prompt_text:
            return "Context IR prompt is required"
        if (
            model == MINMAX_H3_CONTEXT_IR_TEXT_MODEL
            and ratio is not None
            and ratio not in MINMAX_H3_CONTEXT_IR_TEXT_RATIOS
        ):
            return "Context IR Text requires a fixed documented ratio"

        if strict and model == MINMAX_H3_CONTEXT_IR_IMAGE_MODEL:
            connected = [
                index
                for index in range(1, MINMAX_H3_CONTEXT_IR_MAX_IMAGES + 1)
                if kwargs.get(f"image{index}") is not None
            ]
            if not connected or connected[0] != 1:
                return "Context IR Image requires image1"
            if any(index > 2 for index in connected):
                return "Context IR Image accepts only image1 and image2"

        if strict and model == MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL:
            has_media = any(
                kwargs.get(f"{family}{index}") is not None
                for family, count in (
                    ("image", MINMAX_H3_CONTEXT_IR_MAX_IMAGES),
                    ("video", MINMAX_H3_CONTEXT_IR_MAX_VIDEOS),
                    ("audio", MINMAX_H3_CONTEXT_IR_MAX_AUDIOS),
                )
                for index in range(1, count + 1)
            )
            if not has_media:
                return (
                    "Context IR Multimodal requires at least one image, video, "
                    "or audio"
                )
        return True

    @staticmethod
    def _gather_slots(
        kwargs: Dict[str, Any],
        family: str,
        count: int,
    ) -> List[Tuple[int, Any]]:
        slots = [
            (index, kwargs.get(f"{family}{index}"))
            for index in range(1, count + 1)
            if kwargs.get(f"{family}{index}") is not None
        ]
        connected = [index for index, _value in slots]
        if connected and connected != list(range(1, len(connected) + 1)):
            print(
                f"[MiniMax H3 Context IR] {family} slots {connected} have gaps; "
                "connected media will be compacted in slot order"
            )
        return slots

    def _collect_media(
        self,
        model: str,
        config: Dict[str, Any],
        kwargs: Dict[str, Any],
        on_progress: Callable[[int], None],
    ) -> Dict[str, List[str]]:
        if model == MINMAX_H3_CONTEXT_IR_TEXT_MODEL:
            on_progress(15)
            return {}

        image_count = (
            2
            if model == MINMAX_H3_CONTEXT_IR_IMAGE_MODEL
            else MINMAX_H3_CONTEXT_IR_MAX_IMAGES
        )
        image_slots = self._gather_slots(kwargs, "image", image_count)
        video_slots = (
            self._gather_slots(
                kwargs, "video", MINMAX_H3_CONTEXT_IR_MAX_VIDEOS
            )
            if model == MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL
            else []
        )
        audio_slots = (
            self._gather_slots(
                kwargs, "audio", MINMAX_H3_CONTEXT_IR_MAX_AUDIOS
            )
            if model == MINMAX_H3_CONTEXT_IR_MULTIMODAL_MODEL
            else []
        )
        total = len(image_slots) + len(video_slots) + len(audio_slots)
        completed = 0
        images: List[str] = []
        video_urls: List[str] = []
        audio_urls: List[str] = []

        for slot, image in image_slots:
            images.append(
                upload_media(
                    image_to_png_bytes(image),
                    f"minmax_h3_context_ir_image_{slot}.png",
                    "image/png",
                    config,
                )
            )
            completed += 1
            on_progress(int(completed / max(1, total) * 15))
        for slot, video in video_slots:
            video_urls.append(
                upload_media(
                    video_to_mp4_bytes(video),
                    f"minmax_h3_context_ir_video_{slot}.mp4",
                    "video/mp4",
                    config,
                )
            )
            completed += 1
            on_progress(int(completed / max(1, total) * 15))
        for slot, audio in audio_slots:
            audio_urls.append(
                upload_media(
                    audio_to_wav_bytes(audio),
                    f"minmax_h3_context_ir_audio_{slot}.wav",
                    "audio/wav",
                    config,
                )
            )
            completed += 1
            on_progress(int(completed / max(1, total) * 15))
        return {
            "images": images,
            "video_urls": video_urls,
            "audio_urls": audio_urls,
        }

    def _build_payload(
        self,
        model: str,
        prompt: str,
        seconds: str,
        ratio: str,
        media: Dict[str, List[str]],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        validation = self.VALIDATE_INPUTS(
            model=model,
            prompt=prompt,
            seconds=seconds,
            ratio=ratio,
            strict=True,
            **kwargs,
        )
        if validation is not True:
            raise SeedanceLowPriceError(str(validation))

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": str(prompt or "").strip(),
            "seconds": str(seconds),
        }
        metadata: Dict[str, Any] = {}
        if model == MINMAX_H3_CONTEXT_IR_TEXT_MODEL:
            metadata["ratio"] = ratio
        elif model == MINMAX_H3_CONTEXT_IR_IMAGE_MODEL:
            images = media.get("images") or []
            if not images:
                raise SeedanceLowPriceError("Context IR Image requires image1")
            payload["images"] = images[:2]
        else:
            images = media.get("images") or []
            video_urls = media.get("video_urls") or []
            audio_urls = media.get("audio_urls") or []
            if not (images or video_urls or audio_urls):
                raise SeedanceLowPriceError(
                    "Context IR Multimodal requires at least one image, video, or audio"
                )
            if ratio != "api_default":
                metadata["ratio"] = ratio
            if images:
                payload["images"] = images[:MINMAX_H3_CONTEXT_IR_MAX_IMAGES]
            if video_urls:
                metadata["video_urls"] = video_urls[
                    :MINMAX_H3_CONTEXT_IR_MAX_VIDEOS
                ]
            if audio_urls:
                metadata["audio_url"] = audio_urls[
                    :MINMAX_H3_CONTEXT_IR_MAX_AUDIOS
                ]
        if metadata:
            payload["metadata"] = metadata
        return payload

    def enhance(
        self,
        model: str,
        prompt: str,
        seconds: str,
        ratio: str,
        api_config: Any = None,
        skip_error: bool = False,
        seed: int = 0,
        **kwargs,
    ):
        del seed
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validation = self.VALIDATE_INPUTS(
                model=model,
                prompt=prompt,
                seconds=seconds,
                ratio=ratio,
                strict=True,
                **kwargs,
            )
            if validation is not True:
                raise SeedanceLowPriceError(str(validation))
            config = resolve_config(api_config)
            media = self._collect_media(model, config, kwargs, update_progress)
            payload = self._build_payload(
                model, prompt, seconds, ratio, media, kwargs
            )
            print(f"[MiniMax H3 Context IR] Submitting model={model}")
            task_id, submit_response = submit_minmax_h3_context_ir_task(
                payload, config
            )
            update_progress(20)
            final_response = poll_minmax_h3_context_ir_task(
                task_id,
                config,
                on_progress=lambda value: update_progress(20 + int(value * 0.8)),
            )
            result_text = extract_minmax_h3_context_ir_text(final_response)
            update_progress(100)
            response = json.dumps(
                {
                    "status": "completed",
                    "model": model,
                    "task_id": task_id,
                    "submit": submit_response,
                    "result": final_response,
                },
                ensure_ascii=False,
                indent=2,
            )
            return {
                "ui": {"text": [result_text, response]},
                "result": (result_text, task_id, response),
            }
        except Exception as exc:
            if not skip_error:
                raise
            response = json.dumps(
                {
                    "status": "error",
                    "model": model,
                    "task_id": task_id,
                    "message": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                indent=2,
            )
            return {
                "ui": {"text": ["", response]},
                "result": ("", task_id, response),
            }


VIDU_Q3_T2V_MODELS = [
    "vidu-q3-pro-t2v",
    "vidu-q3-turbo-t2v",
    "vidu-q3-pro-fast-t2v",
]
VIDU_Q3_I2V_MODELS = [
    "vidu-q3-pro-i2v",
    "vidu-q3-turbo-i2v",
    "vidu-q3-pro-fast-i2v",
]
VIDU_Q3_START_END_MODELS = [
    "vidu-q3-pro-start-end",
    "vidu-q3-turbo-start-end",
    "vidu-q3-pro-fast-start-end",
]
VIDU_Q3_R2V_MODELS = [
    "vidu-q3-r2v",
    "vidu-q3-mix-r2v",
    "vidu-q3-ad-r2v",
    "vidu-q3-drama-r2v",
]
VIDU_Q3_VIDEO_MODELS = (
    VIDU_Q3_T2V_MODELS
    + VIDU_Q3_I2V_MODELS
    + VIDU_Q3_START_END_MODELS
    + VIDU_Q3_R2V_MODELS
)
VIDU_Q3_SHORT_PLAY_MODELS = [
    "vidu-q3-drama-short-play",
    "vidu-q3-ad-short-play",
]
VIDU_Q3_SECONDS = [str(value) for value in range(4, 16)]
VIDU_Q3_RESOLUTIONS = ["default", "720p", "1080p"]
VIDU_Q3_MAX_IMAGES = 9
VIDU_Q3_SHORT_PLAY_DURATIONS = [str(value) for value in range(8, 13)]
VIDU_Q3_SHORT_PLAY_RATIOS = ["9:16", "16:9"]
VIDU_Q3_SHORT_PLAY_ASSET_TYPES = ["character", "scene", "prop"]
VIDU_Q3_MAX_SHORT_PLAY_ASSETS = 14


def validate_vidu_q3_inputs(
    model: str,
    prompt: str,
    seconds: str,
    ratio: str,
    resolution: str,
    seed: int,
) -> None:
    if model not in VIDU_Q3_VIDEO_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Vidu Q3 model: {model}")
    if str(seconds) not in VIDU_Q3_SECONDS:
        raise SeedanceLowPriceError(
            "Vidu Q3 seconds must be an integer from 4 to 15"
        )
    if ratio not in RATIOS:
        raise SeedanceLowPriceError(f"Unsupported Vidu Q3 ratio: {ratio}")
    if resolution not in VIDU_Q3_RESOLUTIONS:
        raise SeedanceLowPriceError(
            "Vidu Q3 resolution must be default, 720p, or 1080p"
        )
    prompt_text = str(prompt or "").strip()
    if len(prompt_text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Vidu Q3 prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    if model in VIDU_Q3_T2V_MODELS and not prompt_text:
        raise SeedanceLowPriceError("Vidu Q3 text-to-video requires a prompt")
    try:
        seed_value = int(seed)
    except (TypeError, ValueError) as exc:
        raise SeedanceLowPriceError("Vidu Q3 seed must be an integer") from exc
    if not -1 <= seed_value <= 2147483647:
        raise SeedanceLowPriceError(
            "Vidu Q3 seed must be -1 to 2147483647"
        )


def build_vidu_q3_payload(
    model: str,
    prompt: str,
    seconds: str,
    ratio: str,
    resolution: str,
    seed: int,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_vidu_q3_inputs(model, prompt, seconds, ratio, resolution, seed)
    urls = list(image_urls or [])
    metadata: Dict[str, Any] = {}
    if ratio != "adaptive":
        metadata["ratio"] = ratio
    if resolution != "default":
        metadata["resolution"] = resolution
    if int(seed) >= 0:
        metadata["seed"] = int(seed)

    payload: Dict[str, Any] = {
        "model": model,
        "seconds": str(seconds),
        "metadata": metadata,
    }
    prompt_text = str(prompt or "").strip()
    if prompt_text:
        payload["prompt"] = prompt_text

    if model in VIDU_Q3_I2V_MODELS:
        if not urls:
            raise SeedanceLowPriceError("Vidu Q3 image-to-video requires image1")
        payload["images"] = urls[:1]
    elif model in VIDU_Q3_START_END_MODELS:
        if len(urls) < 2:
            raise SeedanceLowPriceError(
                "Vidu Q3 start-end requires image1 and image2"
            )
        payload["images"] = urls[:2]
    elif model in VIDU_Q3_R2V_MODELS:
        if not urls:
            raise SeedanceLowPriceError(
                "Vidu Q3 reference-to-video requires at least one image"
            )
        payload["images"] = urls[:VIDU_Q3_MAX_IMAGES]
    return payload


class Comfly_vidu_q3_video_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {}
        for index in range(1, VIDU_Q3_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (
                    VIDU_Q3_VIDEO_MODELS,
                    {"default": "vidu-q3-turbo-t2v"},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (VIDU_Q3_SECONDS, {"default": "4"}),
                "ratio": (RATIOS, {"default": "16:9"}),
                "resolution": (VIDU_Q3_RESOLUTIONS, {"default": "default"}),
                "seed": (
                    "INT",
                    {"default": -1, "min": -1, "max": 2147483647, "step": 1},
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="4",
        ratio="16:9",
        resolution="default",
        seed=-1,
        **kwargs,
    ):
        if model is None:
            return True
        try:
            validate_vidu_q3_inputs(
                model,
                prompt,
                seconds,
                ratio,
                resolution,
                seed,
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _connected_images(kwargs: Dict[str, Any]) -> List[Tuple[int, Any]]:
        return [
            (index, kwargs[f"image{index}"])
            for index in range(1, VIDU_Q3_MAX_IMAGES + 1)
            if kwargs.get(f"image{index}") is not None
        ]

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        ratio: str,
        resolution: str,
        seed: int,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_vidu_q3_inputs(
                model,
                prompt,
                seconds,
                ratio,
                resolution,
                seed,
            )
            config = resolve_config(api_config)
            connected = self._connected_images(kwargs)
            selected: List[Tuple[int, Any]] = []
            if model in VIDU_Q3_I2V_MODELS:
                if kwargs.get("image1") is None:
                    raise SeedanceLowPriceError(
                        "Vidu Q3 image-to-video requires image1"
                    )
                selected = [(1, kwargs["image1"])]
            elif model in VIDU_Q3_START_END_MODELS:
                if kwargs.get("image1") is None or kwargs.get("image2") is None:
                    raise SeedanceLowPriceError(
                        "Vidu Q3 start-end requires image1 and image2"
                    )
                selected = [(1, kwargs["image1"]), (2, kwargs["image2"])]
            elif model in VIDU_Q3_R2V_MODELS:
                if not connected:
                    raise SeedanceLowPriceError(
                        "Vidu Q3 reference-to-video requires at least one image"
                    )
                selected = connected[:VIDU_Q3_MAX_IMAGES]
                slots = [slot for slot, _ in selected]
                if slots != list(range(1, len(slots) + 1)):
                    print(
                        f"[Vidu Q3 Low Price] Image slots {slots} have gaps; "
                        "connected images will be compacted in slot order"
                    )

            image_urls: List[str] = []
            for position, (slot, image) in enumerate(selected, start=1):
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image),
                        f"vidu_q3_reference_{slot}.png",
                        "image/png",
                        config,
                    )
                )
                update_progress(int(position / len(selected) * 20))

            payload = build_vidu_q3_payload(
                model,
                prompt,
                seconds,
                ratio,
                resolution,
                seed,
                image_urls,
            )
            print(f"[Vidu Q3 Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


def validate_vidu_q3_short_play_inputs(
    model: str,
    prompt: str,
    script_name: str,
    resolution: str,
    duration: str,
    aspect_ratio: str,
    style: str,
    asset_type: str,
    asset_name_prefix: str,
    asset_description: str,
) -> None:
    if model not in VIDU_Q3_SHORT_PLAY_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Vidu short-play model: {model}")
    prompt_text = str(prompt or "").strip()
    if not prompt_text:
        raise SeedanceLowPriceError("Vidu short-play requires script content")
    if len(prompt_text) > PROMPT_MAX_LENGTH:
        raise SeedanceLowPriceError(
            f"Vidu short-play prompt exceeds {PROMPT_MAX_LENGTH} characters"
        )
    script_name_text = str(script_name or "").strip()
    if not script_name_text:
        raise SeedanceLowPriceError("Vidu short-play requires script_name")
    if len(script_name_text) > 20:
        raise SeedanceLowPriceError(
            "Vidu short-play script_name must be 20 characters or fewer"
        )
    if resolution != "1080p":
        raise SeedanceLowPriceError("Vidu short-play resolution must be 1080p")
    if str(duration) not in VIDU_Q3_SHORT_PLAY_DURATIONS:
        raise SeedanceLowPriceError(
            "Vidu short-play duration must be 8 to 12 seconds"
        )
    if aspect_ratio not in VIDU_Q3_SHORT_PLAY_RATIOS:
        raise SeedanceLowPriceError(
            "Vidu short-play aspect_ratio must be 9:16 or 16:9"
        )
    if len(str(style or "")) > 30:
        raise SeedanceLowPriceError(
            "Vidu short-play style must be 30 characters or fewer"
        )
    if asset_type not in VIDU_Q3_SHORT_PLAY_ASSET_TYPES:
        raise SeedanceLowPriceError(f"Unsupported Vidu asset_type: {asset_type}")
    if not str(asset_name_prefix or "").strip():
        raise SeedanceLowPriceError(
            "Vidu short-play asset_name_prefix is required"
        )
    if not str(asset_description or "").strip():
        raise SeedanceLowPriceError(
            "Vidu short-play asset_description is required"
        )


def build_vidu_q3_short_play_payload(
    model: str,
    prompt: str,
    script_name: str,
    resolution: str,
    duration: str,
    aspect_ratio: str,
    style: str,
    asset_type: str,
    asset_name_prefix: str,
    asset_description: str,
    asset_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_vidu_q3_short_play_inputs(
        model,
        prompt,
        script_name,
        resolution,
        duration,
        aspect_ratio,
        style,
        asset_type,
        asset_name_prefix,
        asset_description,
    )
    urls = list(asset_urls or [])[:VIDU_Q3_MAX_SHORT_PLAY_ASSETS]
    if not urls:
        raise SeedanceLowPriceError(
            "Vidu short-play requires at least one reference asset"
        )
    prefix = str(asset_name_prefix).strip()
    description = str(asset_description).strip()
    assets = [
        {
            "id": str(index),
            "type": asset_type,
            "name": f"{prefix} {index}",
            "image_uri": url,
            "description": description,
        }
        for index, url in enumerate(urls, start=1)
    ]
    return {
        "model": model,
        "prompt": str(prompt).strip(),
        "metadata": {
            "script_name": str(script_name).strip(),
            "resolution": resolution,
            "duration": int(duration),
            "aspect_ratio": aspect_ratio,
            "style": str(style or "").strip(),
            "assets": assets,
        },
    }


class Comfly_vidu_q3_short_play_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {}
        for index in range(1, VIDU_Q3_MAX_SHORT_PLAY_ASSETS + 1):
            optional[f"asset_image{index}"] = ("IMAGE",)
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (
                    VIDU_Q3_SHORT_PLAY_MODELS,
                    {"default": VIDU_Q3_SHORT_PLAY_MODELS[0]},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "script_name": ("STRING", {"default": "Vidu short play"}),
                "resolution": (["1080p"], {"default": "1080p"}),
                "duration": (VIDU_Q3_SHORT_PLAY_DURATIONS, {"default": "8"}),
                "aspect_ratio": (
                    VIDU_Q3_SHORT_PLAY_RATIOS,
                    {"default": "9:16"},
                ),
                "style": ("STRING", {"default": "realistic"}),
                "asset_type": (
                    VIDU_Q3_SHORT_PLAY_ASSET_TYPES,
                    {"default": "character"},
                ),
                "asset_name_prefix": ("STRING", {"default": "Asset"}),
                "asset_description": (
                    "STRING",
                    {"default": "Reference asset"},
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        try:
            validate_vidu_q3_short_play_inputs(
                kwargs.get("model"),
                kwargs.get("prompt", ""),
                kwargs.get("script_name", ""),
                kwargs.get("resolution", "1080p"),
                kwargs.get("duration", "8"),
                kwargs.get("aspect_ratio", "9:16"),
                kwargs.get("style", "realistic"),
                kwargs.get("asset_type", "character"),
                kwargs.get("asset_name_prefix", "Asset"),
                kwargs.get("asset_description", "Reference asset"),
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _connected_assets(kwargs: Dict[str, Any]) -> List[Tuple[int, Any]]:
        return [
            (index, kwargs[f"asset_image{index}"])
            for index in range(1, VIDU_Q3_MAX_SHORT_PLAY_ASSETS + 1)
            if kwargs.get(f"asset_image{index}") is not None
        ]

    def generate(
        self,
        model: str,
        prompt: str,
        script_name: str,
        resolution: str,
        duration: str,
        aspect_ratio: str,
        style: str,
        asset_type: str,
        asset_name_prefix: str,
        asset_description: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_vidu_q3_short_play_inputs(
                model,
                prompt,
                script_name,
                resolution,
                duration,
                aspect_ratio,
                style,
                asset_type,
                asset_name_prefix,
                asset_description,
            )
            connected = self._connected_assets(kwargs)
            if not connected:
                raise SeedanceLowPriceError(
                    "Vidu short-play requires at least one reference asset"
                )
            slots = [slot for slot, _ in connected]
            if slots != list(range(1, len(slots) + 1)):
                print(
                    f"[Vidu Q3 Short Play Low Price] Asset slots {slots} have gaps; "
                    "connected assets will be compacted in slot order"
                )

            config = resolve_config(api_config)
            asset_urls: List[str] = []
            for position, (slot, image) in enumerate(connected, start=1):
                asset_urls.append(
                    upload_media(
                        image_to_png_bytes(image),
                        f"vidu_short_play_asset_{slot}.png",
                        "image/png",
                        config,
                    )
                )
                update_progress(int(position / len(connected) * 20))

            payload = build_vidu_q3_short_play_payload(
                model,
                prompt,
                script_name,
                resolution,
                duration,
                aspect_ratio,
                style,
                asset_type,
                asset_name_prefix,
                asset_description,
                asset_urls,
            )
            print(f"[Vidu Q3 Short Play Low Price] Submitting model={model}")
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            video_url = extract_video_url(final_response)
            video = download_video(video_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                video_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


ZHENZHEN_UPSCALER_MODEL = "zhenzhen-upscaler"
ZHENZHEN_UPSCALER_RESOLUTIONS = ["720p", "1080p", "2k", "4k"]


def validate_zhenzhen_upscaler_inputs(video_url: str, resolution: str) -> None:
    if resolution not in ZHENZHEN_UPSCALER_RESOLUTIONS:
        raise SeedanceLowPriceError(
            "Zhenzhen Upscaler resolution must be 720p, 1080p, 2k, or 4k"
        )
    url = str(video_url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise SeedanceLowPriceError(
            "Zhenzhen Upscaler video_url must be an http(s) URL"
        )


def build_zhenzhen_upscaler_payload(
    video_url: str,
    resolution: str,
) -> Dict[str, Any]:
    validate_zhenzhen_upscaler_inputs(video_url, resolution)
    url = str(video_url or "").strip()
    if not url:
        raise SeedanceLowPriceError(
            "Zhenzhen Upscaler requires a non-empty video URL"
        )
    return {
        "model": ZHENZHEN_UPSCALER_MODEL,
        "prompt": "upscale",
        "metadata": {
            "resolution": resolution,
            "content": [
                {
                    "type": "video_url",
                    "video_url": {"url": url},
                }
            ],
        },
    }


class Comfly_zhenzhen_upscaler_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_url": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Optional public MP4 URL; leave empty when input_video is connected.",
                    },
                ),
                "resolution": (
                    ZHENZHEN_UPSCALER_RESOLUTIONS,
                    {"default": "1080p"},
                ),
            },
            "optional": {
                "input_video": (VIDEO_TYPE,),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        video_url="",
        resolution="1080p",
        **kwargs,
    ):
        try:
            validate_zhenzhen_upscaler_inputs(video_url, resolution)
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        video_url: str,
        resolution: str,
        input_video: Any = None,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_zhenzhen_upscaler_inputs(video_url, resolution)
            source_url = str(video_url or "").strip()
            if not source_url and input_video is None:
                raise SeedanceLowPriceError(
                    "Connect input_video or provide video_url for zhenzhen-upscaler"
                )

            config = resolve_config(api_config)
            if not source_url:
                video_bytes = video_to_mp4_bytes(input_video)
                source_url = upload_media(
                    video_bytes,
                    "zhenzhen_upscaler_input.mp4",
                    "video/mp4",
                    config,
                )
            update_progress(20)

            payload = build_zhenzhen_upscaler_payload(source_url, resolution)
            print(
                f"[Zhenzhen Upscaler Low Price] Submitting "
                f"model={ZHENZHEN_UPSCALER_MODEL}, resolution={resolution}"
            )
            task_id, submit_response = submit_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_task(
                task_id,
                config,
                on_progress=on_poll_progress,
            )
            result_url = extract_video_url(final_response)
            video = download_video(result_url)
            update_progress(100)
            response = {
                "status": "completed",
                "model": ZHENZHEN_UPSCALER_MODEL,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                video,
                result_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": ZHENZHEN_UPSCALER_MODEL,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_video(message),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


SEED_AUDIO_MODEL = "doubao-seed-audio-1.0"
SEED_AUDIO_REFERENCE_MODES = [
    "none",
    "speaker",
    "reference_audio",
    "reference_image",
]
SEED_AUDIO_FORMATS = ["wav", "mp3", "ogg_opus"]
SEED_AUDIO_SAMPLE_RATES = ["8000", "16000", "24000", "32000", "44100"]


def _parse_http_urls(value: str, label: str) -> List[str]:
    urls = []
    for line in str(value or "").replace(",", "\n").splitlines():
        url = line.strip()
        if not url:
            continue
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise SeedanceLowPriceError(f"{label} must contain http(s) direct URLs")
        urls.append(url)
    return urls


def validate_seed_audio_settings(
    reference_mode: str,
    prompt: str,
    speaker: str,
    output_format: str,
    sample_rate: str,
    speech_rate: int,
    loudness_rate: int,
    pitch_rate: int,
) -> None:
    if reference_mode not in SEED_AUDIO_REFERENCE_MODES:
        raise SeedanceLowPriceError(
            f"Unsupported Seed Audio reference_mode: {reference_mode}"
        )
    prompt_length = len(str(prompt or "").strip())
    if not 5 <= prompt_length <= 2048:
        raise SeedanceLowPriceError("Seed Audio prompt length must be 5-2048 characters")
    if output_format not in SEED_AUDIO_FORMATS:
        raise SeedanceLowPriceError(
            "Seed Audio output_format must be wav, mp3, or ogg_opus"
        )
    if str(sample_rate) not in SEED_AUDIO_SAMPLE_RATES:
        raise SeedanceLowPriceError(f"Unsupported Seed Audio sample_rate: {sample_rate}")
    if not -50 <= int(speech_rate) <= 100:
        raise SeedanceLowPriceError("Seed Audio speech_rate must be -50 to 100")
    if not -50 <= int(loudness_rate) <= 100:
        raise SeedanceLowPriceError("Seed Audio loudness_rate must be -50 to 100")
    if not -12 <= int(pitch_rate) <= 12:
        raise SeedanceLowPriceError("Seed Audio pitch_rate must be -12 to 12")
    if reference_mode == "speaker" and not str(speaker or "").strip():
        raise SeedanceLowPriceError("Seed Audio speaker mode requires a speaker ID")


def build_seed_audio_payload(
    reference_mode: str,
    prompt: str,
    speaker: str,
    output_format: str,
    sample_rate: str,
    speech_rate: int,
    loudness_rate: int,
    pitch_rate: int,
    audio_urls: Optional[List[str]] = None,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    validate_seed_audio_settings(
        reference_mode,
        prompt,
        speaker,
        output_format,
        sample_rate,
        speech_rate,
        loudness_rate,
        pitch_rate,
    )
    audios = list(audio_urls or [])
    images = list(image_urls or [])
    if reference_mode in ("none", "speaker") and (audios or images):
        raise SeedanceLowPriceError(
            f"Seed Audio {reference_mode} mode does not accept reference media"
        )
    if reference_mode == "reference_audio":
        if not 1 <= len(audios) <= 3 or images:
            raise SeedanceLowPriceError(
                "Seed Audio reference_audio mode requires 1-3 audios and no image"
            )
    if reference_mode == "reference_image":
        if len(images) != 1 or audios:
            raise SeedanceLowPriceError(
                "Seed Audio reference_image mode requires exactly one image and no audio"
            )

    metadata: Dict[str, Any] = {
        "format": output_format,
        "sample_rate": str(sample_rate),
        "speech_rate": int(speech_rate),
        "loudness_rate": int(loudness_rate),
        "pitch_rate": int(pitch_rate),
    }
    if reference_mode == "speaker":
        metadata["speaker"] = str(speaker).strip()
    elif reference_mode == "reference_audio":
        metadata["audio_urls"] = audios

    payload: Dict[str, Any] = {
        "model": SEED_AUDIO_MODEL,
        "prompt": str(prompt).strip(),
        "metadata": metadata,
    }
    if reference_mode == "reference_image":
        payload["images"] = images
    return payload


def submit_audio_task(
    payload: Dict[str, Any],
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Tuple[str, Dict[str, Any]]:
    url = f"{config['base_url']}/v1/audio/generations"
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            sleep(min(2 ** attempt + 1, 15))
        try:
            response = _get_session().post(
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
                "Seed Audio submit transport failed after the request may have reached "
                "the server; it was not retried to avoid a duplicate paid task. "
                f"Check the provider console before retrying manually: {type(exc).__name__}: {exc}"
            ) from exc

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            if response.status_code == 404 and "invalid url" in message.lower():
                raise SeedanceLowPriceError(
                    "Seed Audio provider route is not enabled yet: the documented "
                    f"POST /v1/audio/generations returned HTTP 404 ({message})"
                )
            raise SeedanceLowPriceError(
                f"Seed Audio submit rejected (HTTP {response.status_code}): {message}"
            )
        task_id = None
        if isinstance(data, dict):
            task_id = data.get("task_id") or data.get("id")
            if not task_id and isinstance(data.get("data"), dict):
                task_id = data["data"].get("task_id") or data["data"].get("id")
        if not task_id:
            raise SeedanceLowPriceError(
                "Seed Audio submit response did not contain task_id/id"
            )
        return str(task_id), data
    raise RuntimeError(f"Seed Audio submit failed after 3 attempts: {last_error}")


def poll_audio_task(
    task_id: str,
    config: Dict[str, Any],
    on_progress: Optional[Callable[[int], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    url = f"{config['base_url']}/v1/audio/generations/{task_id}"
    start = clock()
    failures = 0
    while True:
        if clock() - start > config.get("max_poll_time", 1800):
            raise RuntimeError(f"Seed Audio polling timed out [task_id: {task_id}]")
        sleep(config.get("poll_interval", 4))
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
                    f"Seed Audio polling failed after repeated network errors [task_id: {task_id}]"
                )
            sleep(min(failures * 2, 10))
            continue

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code != 200:
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise SeedanceLowPriceError(
                    f"Seed Audio polling rejected (HTTP {response.status_code}): {message} "
                    f"[task_id: {task_id}]"
                )
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"Seed Audio polling repeatedly returned HTTP {response.status_code}: "
                    f"{message} [task_id: {task_id}]"
                )
            sleep(min(failures * 2, 10))
            continue

        failures = 0
        record = data.get("data") if isinstance(data, dict) else None
        if not isinstance(record, dict):
            record = data if isinstance(data, dict) else {}
        status = str(record.get("status") or "").strip().upper()
        progress = _coerce_progress(record.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        if status == "SUCCESS":
            return data
        if status == "FAILURE":
            reason = record.get("fail_reason") or message or "audio generation failed"
            raise SeedanceLowPriceError(
                f"Seed Audio task failed: {reason} [task_id: {task_id}]"
            )


def extract_audio_urls(response: Dict[str, Any]) -> List[str]:
    """Extract every documented audio URL without reordering or deduplicating."""
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, dict):
                content = nested.get("content")
                if isinstance(content, dict):
                    values = content.get("audio_urls")
                    if isinstance(values, (list, tuple)):
                        urls = [
                            str(value or "").strip()
                            for value in values
                            if str(value or "").strip()
                        ]
                        if urls:
                            return urls
                    for key in ("audio_url", "url"):
                        value = content.get(key)
                        if isinstance(value, str) and value.strip():
                            return [value.strip()]
            for key in ("result_url", "audio_url", "url"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return [value.strip()]
        for key in ("result_url", "audio_url", "url"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return [value.strip()]
    raise SeedanceLowPriceError(
        "Seed Audio completed response did not contain an audio URL"
    )


def extract_audio_url(response: Dict[str, Any]) -> str:
    return extract_audio_urls(response)[0]


def audio_bytes_to_comfy(
    data: bytes, output_format: str, expected_sample_rate: int
) -> Dict[str, Any]:
    if not data:
        raise SeedanceLowPriceError("Downloaded Seed Audio result is empty")

    if output_format == "wav":
        try:
            with wave.open(io.BytesIO(data), "rb") as handle:
                channels = handle.getnchannels()
                sample_width = handle.getsampwidth()
                sample_rate = handle.getframerate() or int(expected_sample_rate)
                frame_count = handle.getnframes()
                frames = handle.readframes(frame_count)
        except (EOFError, wave.Error) as exc:
            raise SeedanceLowPriceError(f"Invalid WAV result: {exc}") from exc

        if channels <= 0 or sample_width not in (1, 2, 3, 4):
            raise SeedanceLowPriceError(
                f"Unsupported WAV layout: channels={channels}, sample_width={sample_width}"
            )
        if sample_width == 1:
            samples = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sample_width == 2:
            samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        elif sample_width == 3:
            raw = np.frombuffer(frames, dtype=np.uint8).reshape(-1, 3)
            samples_24 = (
                raw[:, 0].astype(np.int32)
                | (raw[:, 1].astype(np.int32) << 8)
                | (raw[:, 2].astype(np.int32) << 16)
            )
            samples_24 = (samples_24 ^ 0x800000) - 0x800000
            samples = samples_24.astype(np.float32) / 8388608.0
        else:
            samples = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0

        if samples.size % channels:
            raise SeedanceLowPriceError("WAV sample count is not divisible by channel count")
        waveform = torch.from_numpy(samples.reshape(-1, channels).T.copy()).unsqueeze(0)
        return {"waveform": waveform, "sample_rate": int(sample_rate)}

    format_hint = "ogg" if output_format == "ogg_opus" else output_format
    torchaudio_error: Optional[Exception] = None
    try:
        import torchaudio

        try:
            waveform, sample_rate = torchaudio.load(
                io.BytesIO(data), format=format_hint
            )
        except Exception:
            waveform, sample_rate = torchaudio.load(io.BytesIO(data))
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        if waveform.ndim != 2:
            raise SeedanceLowPriceError(
                f"Unexpected downloaded audio shape: {tuple(waveform.shape)}"
            )
        if int(sample_rate) <= 0:
            sample_rate = int(expected_sample_rate)
        return {
            "waveform": waveform.float().unsqueeze(0),
            "sample_rate": int(sample_rate),
        }
    except Exception as exc:
        torchaudio_error = exc

    suffix = f".{format_hint or 'audio'}"
    handle, path = tempfile.mkstemp(prefix="zhenzhen_audio_", suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as output:
            output.write(data)
        return _decode_suno_audio(path)
    except Exception as ffmpeg_error:
        raise SeedanceLowPriceError(
            "Compressed audio could not be decoded by torchaudio or the bundled "
            f"FFmpeg fallback ({type(torchaudio_error).__name__}; "
            f"{type(ffmpeg_error).__name__})"
        ) from ffmpeg_error
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def download_audio(
    url: str,
    output_format: str,
    expected_sample_rate: int,
    max_retries: int = 3,
) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        if attempt:
            time.sleep(2 ** attempt)
        response = None
        try:
            response = get_media_response(
                url,
                request_get=_get_session().get,
                direct_get=direct_media_get,
                timeout=media_download_timeout(300),
            )
            response.raise_for_status()
            return audio_bytes_to_comfy(
                response.content, output_format, expected_sample_rate
            )
        except Exception as exc:
            last_error = exc
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
    raise RuntimeError(
        f"Seed Audio download failed after {max_retries} attempts: {last_error}"
    )


def make_error_audio(sample_rate: int = 24000) -> Dict[str, Any]:
    return {
        "waveform": torch.zeros((1, 1, int(sample_rate)), dtype=torch.float32),
        "sample_rate": int(sample_rate),
    }


class Comfly_doubao_seed_audio_1_0_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "reference_mode": (
                    SEED_AUDIO_REFERENCE_MODES,
                    {"default": "none"},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "speaker": ("STRING", {"default": ""}),
                "output_format": (SEED_AUDIO_FORMATS, {"default": "wav"}),
                "sample_rate": (SEED_AUDIO_SAMPLE_RATES, {"default": "24000"}),
                "speech_rate": (
                    "INT",
                    {"default": 0, "min": -50, "max": 100, "step": 1},
                ),
                "loudness_rate": (
                    "INT",
                    {"default": 0, "min": -50, "max": 100, "step": 1},
                ),
                "pitch_rate": (
                    "INT",
                    {"default": 0, "min": -12, "max": 12, "step": 1},
                ),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "reference_image": ("IMAGE",),
                "reference_image_url": ("STRING", {"default": ""}),
                "audio1": ("AUDIO",),
                "audio2": ("AUDIO",),
                "audio3": ("AUDIO",),
                "reference_audio_urls": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = (AUDIO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio", "audio_url", "task_id", "response")
    FUNCTION = "generate"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        reference_mode=None,
        prompt="",
        speaker="",
        output_format="wav",
        sample_rate="24000",
        speech_rate=0,
        loudness_rate=0,
        pitch_rate=0,
        **kwargs,
    ):
        if reference_mode is None:
            return True
        try:
            validate_seed_audio_settings(
                reference_mode,
                prompt,
                speaker,
                output_format,
                sample_rate,
                speech_rate,
                loudness_rate,
                pitch_rate,
            )
        except Exception as exc:
            return str(exc)
        return True

    @staticmethod
    def _collect_references(
        reference_mode: str,
        config: Dict[str, Any],
        reference_image: Any,
        reference_image_url: str,
        reference_audio_urls: str,
        audios: List[Any],
    ) -> Tuple[List[str], List[str]]:
        external_audios = _parse_http_urls(
            reference_audio_urls, "reference_audio_urls"
        )
        external_images = _parse_http_urls(
            reference_image_url, "reference_image_url"
        )
        connected_audios = [audio for audio in audios if audio is not None]

        if reference_mode in ("none", "speaker"):
            if reference_image is not None or external_images or connected_audios or external_audios:
                raise SeedanceLowPriceError(
                    f"Seed Audio {reference_mode} mode does not accept reference media"
                )
            return [], []

        if reference_mode == "reference_image":
            if connected_audios or external_audios:
                raise SeedanceLowPriceError(
                    "Seed Audio reference_image mode cannot use reference audio"
                )
            image_urls = list(external_images)
            if reference_image is not None:
                image_urls.insert(
                    0,
                    upload_media(
                        image_to_png_bytes(reference_image),
                        "reference_image.png",
                        "image/png",
                        config,
                    ),
                )
            if len(image_urls) != 1:
                raise SeedanceLowPriceError(
                    "Seed Audio reference_image mode requires exactly one image or image URL"
                )
            return [], image_urls

        if reference_image is not None or external_images:
            raise SeedanceLowPriceError(
                "Seed Audio reference_audio mode cannot use a reference image"
            )
        audio_urls = []
        for index, audio in enumerate(connected_audios, start=1):
            audio_urls.append(
                upload_media(
                    audio_to_wav_bytes(audio),
                    f"reference_audio{index}.wav",
                    "audio/wav",
                    config,
                )
            )
        audio_urls.extend(external_audios)
        if not 1 <= len(audio_urls) <= 3:
            raise SeedanceLowPriceError(
                "Seed Audio reference_audio mode requires 1-3 audios or audio URLs"
            )
        return audio_urls, []

    def generate(
        self,
        reference_mode: str,
        prompt: str,
        speaker: str,
        output_format: str,
        sample_rate: str,
        speech_rate: int,
        loudness_rate: int,
        pitch_rate: int,
        api_config: Any = None,
        reference_image: Any = None,
        reference_image_url: str = "",
        audio1: Any = None,
        audio2: Any = None,
        audio3: Any = None,
        reference_audio_urls: str = "",
        skip_error: bool = False,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_seed_audio_settings(
                reference_mode,
                prompt,
                speaker,
                output_format,
                sample_rate,
                speech_rate,
                loudness_rate,
                pitch_rate,
            )
            config = resolve_config(api_config)
            audio_urls, image_urls = self._collect_references(
                reference_mode,
                config,
                reference_image,
                reference_image_url,
                reference_audio_urls,
                [audio1, audio2, audio3],
            )
            payload = build_seed_audio_payload(
                reference_mode,
                prompt,
                speaker,
                output_format,
                sample_rate,
                speech_rate,
                loudness_rate,
                pitch_rate,
                audio_urls,
                image_urls,
            )
            update_progress(25)
            print(
                f"[Seed Audio Low Price] Submitting model={SEED_AUDIO_MODEL}, "
                f"reference_mode={reference_mode}"
            )
            task_id, submit_response = submit_audio_task(payload, config)
            update_progress(30)

            def on_poll_progress(progress: int) -> None:
                update_progress(30 + int(progress * 0.6))

            final_response = poll_audio_task(
                task_id, config, on_progress=on_poll_progress
            )
            audio_url = extract_audio_url(final_response)
            audio = download_audio(audio_url, output_format, int(sample_rate))
            update_progress(100)
            response = {
                "status": "SUCCESS",
                "model": SEED_AUDIO_MODEL,
                "reference_mode": reference_mode,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                audio,
                audio_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            message = f"{type(exc).__name__}: {exc}"
            response = {
                "status": "error",
                "model": SEED_AUDIO_MODEL,
                "reference_mode": reference_mode,
                "task_id": task_id,
                "message": message,
            }
            return (
                make_error_audio(int(sample_rate)),
                "",
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )


QWEN_IMAGE_30_T2I_MODEL = "qwen-image-3.0-t2i"
QWEN_IMAGE_30_I2I_MODEL = "qwen-image-3.0-i2i"
QWEN_IMAGE_30_PRO_T2I_MODEL = "qwen-image-3.0-pro-t2i"
QWEN_IMAGE_30_PRO_I2I_MODEL = "qwen-image-3.0-pro-i2i"
QWEN_IMAGE_30_GLOBAL_T2I_MODEL = "qwen-image-3.0-global-t2i"
QWEN_IMAGE_30_GLOBAL_I2I_MODEL = "qwen-image-3.0-global-i2i"
QWEN_IMAGE_30_GLOBAL_PRO_T2I_MODEL = "qwen-image-3.0-global-pro-t2i"
QWEN_IMAGE_30_GLOBAL_PRO_I2I_MODEL = "qwen-image-3.0-global-pro-i2i"
QWEN_IMAGE_30_T2I_MODELS = [
    QWEN_IMAGE_30_T2I_MODEL,
    QWEN_IMAGE_30_PRO_T2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_T2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_PRO_T2I_MODEL,
]
QWEN_IMAGE_30_I2I_MODELS = [
    QWEN_IMAGE_30_I2I_MODEL,
    QWEN_IMAGE_30_PRO_I2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_I2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_PRO_I2I_MODEL,
]
QWEN_IMAGE_30_MODELS = [
    QWEN_IMAGE_30_T2I_MODEL,
    QWEN_IMAGE_30_I2I_MODEL,
    QWEN_IMAGE_30_PRO_T2I_MODEL,
    QWEN_IMAGE_30_PRO_I2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_T2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_I2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_PRO_T2I_MODEL,
    QWEN_IMAGE_30_GLOBAL_PRO_I2I_MODEL,
]
QWEN_IMAGE_30_SIZING_MODES = ["auto", "ratio", "custom_size"]
QWEN_IMAGE_30_RESOLUTIONS = ["1k", "2k"]
QWEN_IMAGE_30_RATIOS = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
]
QWEN_IMAGE_30_PROMPT_MIN_LENGTH = 5
QWEN_IMAGE_30_PROMPT_MAX_LENGTH = 2000
QWEN_IMAGE_30_MAX_IMAGES = 3


def normalize_qwen_image_30_custom_size(value: Any) -> str:
    return str(value or "").strip().replace("X", "*").replace("x", "*")


def is_valid_qwen_image_30_custom_size(value: Any) -> bool:
    parts = [part.strip() for part in normalize_qwen_image_30_custom_size(value).split("*")]
    return len(parts) == 2 and all(part.isdigit() and int(part) > 0 for part in parts)


def validate_qwen_image_30_inputs(
    model: str,
    prompt: str,
    sizing_mode: str,
    resolution: str,
    ratio: str,
    custom_size: str,
    n: int,
    seed: int,
    image_count: int = 0,
    strict: bool = True,
) -> str:
    if model not in QWEN_IMAGE_30_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Qwen Image 3.0 model: {model}")
    prompt_text = str(prompt or "").strip()
    if strict and not prompt_text:
        raise SeedanceLowPriceError("Qwen Image 3.0 prompt is required")
    if prompt_text and not (
        QWEN_IMAGE_30_PROMPT_MIN_LENGTH
        <= len(prompt_text)
        <= QWEN_IMAGE_30_PROMPT_MAX_LENGTH
    ):
        raise SeedanceLowPriceError(
            "Qwen Image 3.0 prompt must contain 5 to 2000 characters"
        )
    if sizing_mode not in QWEN_IMAGE_30_SIZING_MODES:
        raise SeedanceLowPriceError(
            f"Unsupported Qwen Image 3.0 sizing_mode: {sizing_mode}"
        )
    if resolution not in QWEN_IMAGE_30_RESOLUTIONS:
        raise SeedanceLowPriceError("Qwen Image 3.0 resolution must be 1k or 2k")
    if ratio not in QWEN_IMAGE_30_RATIOS:
        raise SeedanceLowPriceError(f"Unsupported Qwen Image 3.0 ratio: {ratio}")
    if sizing_mode == "custom_size" and not is_valid_qwen_image_30_custom_size(custom_size):
        raise SeedanceLowPriceError(
            "Qwen Image 3.0 custom_size must use positive WxH, for example 1024*1024"
        )
    if not 1 <= int(n) <= 6:
        raise SeedanceLowPriceError("Qwen Image 3.0 n must be between 1 and 6")
    if int(seed) < -1:
        raise SeedanceLowPriceError("Qwen Image 3.0 seed must be -1 or non-negative")
    if not 0 <= int(image_count) <= QWEN_IMAGE_30_MAX_IMAGES:
        raise SeedanceLowPriceError("Qwen Image 3.0 accepts at most 3 images")
    if strict and model in QWEN_IMAGE_30_I2I_MODELS and image_count == 0:
        raise SeedanceLowPriceError("Qwen Image 3.0 I2I requires 1 to 3 images")
    return prompt_text


def build_qwen_image_30_payload(
    model: str,
    prompt: str,
    negative_prompt: str,
    prompt_extend: bool,
    sizing_mode: str,
    resolution: str,
    ratio: str,
    custom_size: str,
    n: int,
    seed: int,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    images = list(image_urls or [])
    prompt_text = validate_qwen_image_30_inputs(
        model,
        prompt,
        sizing_mode,
        resolution,
        ratio,
        custom_size,
        n,
        seed,
        image_count=len(images),
        strict=True,
    )
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt_text,
        "n": int(n),
        "prompt_extend": bool(prompt_extend),
    }
    negative_text = str(negative_prompt or "").strip()
    if negative_text:
        payload["negative_prompt"] = negative_text

    metadata: Dict[str, Any] = {}
    if int(seed) >= 0:
        metadata["seed"] = int(seed)
    if sizing_mode == "ratio":
        metadata["ratio"] = ratio
        metadata["resolution"] = resolution
    elif sizing_mode == "custom_size":
        payload["size"] = normalize_qwen_image_30_custom_size(custom_size)
    if metadata:
        payload["metadata"] = metadata
    if model in QWEN_IMAGE_30_I2I_MODELS:
        payload["images"] = images
    return payload


class Comfly_qwen_image_3_0_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {"api_config": (CONFIG_TYPE,)}
        for index in range(1, QWEN_IMAGE_30_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (
                    QWEN_IMAGE_30_MODELS,
                    {"default": QWEN_IMAGE_30_T2I_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "prompt_extend": ("BOOLEAN", {"default": True}),
                "sizing_mode": (
                    QWEN_IMAGE_30_SIZING_MODES,
                    {"default": "auto"},
                ),
                "resolution": (QWEN_IMAGE_30_RESOLUTIONS, {"default": "1k"}),
                "ratio": (QWEN_IMAGE_30_RATIOS, {"default": "1:1"}),
                "custom_size": ("STRING", {"default": "1024*1024"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 6, "step": 1}),
                "seed": (
                    "INT",
                    {
                        "default": -1,
                        "min": -1,
                        "max": 2147483647,
                        "step": 1,
                        "control_after_generate": True,
                    },
                ),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate_image"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        sizing_mode="auto",
        resolution="1k",
        ratio="1:1",
        custom_size="1024*1024",
        n=1,
        seed=-1,
        strict=False,
        **kwargs,
    ):
        if model is None:
            return True
        image_count = sum(
            kwargs.get(f"image{index}") is not None
            for index in range(1, QWEN_IMAGE_30_MAX_IMAGES + 1)
        )
        try:
            validate_qwen_image_30_inputs(
                model,
                prompt,
                sizing_mode,
                resolution,
                ratio,
                custom_size,
                n,
                seed,
                image_count=image_count,
                strict=bool(strict),
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate_image(
        self,
        model: str,
        prompt: str,
        negative_prompt: str,
        prompt_extend: bool,
        sizing_mode: str,
        resolution: str,
        ratio: str,
        custom_size: str,
        n: int,
        seed: int,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            slots = _connected_slots(
                kwargs,
                "image",
                QWEN_IMAGE_30_MAX_IMAGES,
                "Qwen Image 3.0 Low Price",
            )
            validate_qwen_image_30_inputs(
                model,
                prompt,
                sizing_mode,
                resolution,
                ratio,
                custom_size,
                n,
                seed,
                image_count=len(slots),
                strict=True,
            )
            config = resolve_config(api_config)
            image_urls: List[str] = []
            if model in QWEN_IMAGE_30_I2I_MODELS:
                image_urls = _upload_image_slots(
                    slots,
                    config,
                    "qwen_image_3_reference",
                    on_progress=update_progress,
                )
            payload = build_qwen_image_30_payload(
                model,
                prompt,
                negative_prompt,
                prompt_extend,
                sizing_mode,
                resolution,
                ratio,
                custom_size,
                n,
                seed,
                image_urls,
            )
            update_progress(25)
            print(f"[Qwen Image 3.0 Low Price] Submitting model={model}")
            task_id, submit_response = submit_image_task(payload, config)
            update_progress(30)
            final_response = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: update_progress(30 + int(value * 0.6)),
            )
            image_url = extract_image_url(final_response)
            image = download_image(image_url)
            update_progress(100)
            response = {
                "status": "SUCCESS",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                image,
                image_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": f"{type(exc).__name__}: {exc}",
            }
            blank = torch.ones((1, 512, 512, 3), dtype=torch.float32)
            return (blank, "", task_id, json.dumps(response, ensure_ascii=False, indent=2))


class Comfly_seedream_v5_pro_layer_decomposition_lowprice:
    """Split one source image with domestic Seedream or overseas Dola."""

    COMFLY_CONCURRENT_DISABLED = True
    SEEDANCE_EXPLICIT_CACHE_ONLY_SEED = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (SEEDREAM_LAYER_RESOLUTIONS, {"default": "auto"}),
                "output_format": (SEEDREAM_OUTPUT_FORMATS, {"default": "png"}),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "step": 1,
                        "control_after_generate": True,
                        "tooltip": (
                            "ComfyUI cache seed only; this value is not sent to "
                            "Seedream. Fixed reuses the cached result."
                        ),
                    },
                ),
                # Keep model after the pre-existing seed and its linked control so
                # workflows serialized before this update retain their widget indexes.
                "model": (
                    SEEDREAM_LAYER_DECOMPOSITION_MODELS,
                    {"default": SEEDREAM_LAYER_DECOMPOSITION_MODEL},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "INT", "STRING", "STRING")
    RETURN_NAMES = (
        "images",
        "masks",
        "image_urls",
        "image_count",
        "task_id",
        "response",
    )
    OUTPUT_IS_LIST = (True, True, False, False, False, False)
    FUNCTION = "decompose_layers"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        image=None,
        prompt="",
        resolution="auto",
        output_format="png",
        model=SEEDREAM_LAYER_DECOMPOSITION_MODEL,
        strict=False,
        **kwargs,
    ):
        prompt_text = str(prompt or "").strip()
        if len(prompt_text) > SEEDREAM_PROMPT_MAX_LENGTH:
            return f"Layer decomposition prompt cannot exceed {SEEDREAM_PROMPT_MAX_LENGTH} characters"
        if resolution not in SEEDREAM_LAYER_RESOLUTIONS:
            return f"Unsupported layer decomposition resolution: {resolution}"
        if output_format not in SEEDREAM_OUTPUT_FORMATS:
            return f"Unsupported layer decomposition output_format: {output_format}"
        if model not in SEEDREAM_LAYER_DECOMPOSITION_MODELS:
            return f"Unsupported layer decomposition model: {model}"
        if strict and image is None:
            return "Layer decomposition requires exactly one source image"
        shape = getattr(image, "shape", None)
        if strict and shape is not None and len(shape) == 4 and int(shape[0]) != 1:
            return "Layer decomposition accepts one source image, not an IMAGE batch"
        return True

    @staticmethod
    def _build_payload(
        source_url: str,
        prompt: str,
        resolution: str,
        output_format: str,
        model: str = SEEDREAM_LAYER_DECOMPOSITION_MODEL,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "images": [source_url],
            "metadata": {
                "resolution": resolution,
                "output_format": output_format,
            },
        }
        if prompt:
            payload["prompt"] = prompt
        return payload

    @staticmethod
    def _error_result(
        message: str,
        task_id: str = "",
        model: str = SEEDREAM_LAYER_DECOMPOSITION_MODEL,
    ):
        image = torch.ones((1, 512, 512, 3), dtype=torch.float32)
        mask = torch.zeros((1, 512, 512), dtype=torch.float32)
        response = json.dumps(
            {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": message,
            },
            ensure_ascii=False,
            indent=2,
        )
        return ([image], [mask], "[]", 0, task_id, response)

    def decompose_layers(
        self,
        image,
        prompt: str,
        resolution: str,
        output_format: str,
        api_config: Any = None,
        skip_error: bool = False,
        seed: int = 0,
        model: str = SEEDREAM_LAYER_DECOMPOSITION_MODEL,
    ):
        del seed
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: float) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(int(value), 100)
                except Exception:
                    pass

        try:
            validation = self.VALIDATE_INPUTS(
                image=image,
                prompt=prompt,
                resolution=resolution,
                output_format=output_format,
                model=model,
                strict=True,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)

            prompt_text = str(prompt or "").strip()
            config = resolve_config(api_config)
            source_bytes = image_to_png_bytes(image)
            if len(source_bytes) > SEEDREAM_LAYER_SOURCE_MAX_BYTES:
                raise SeedanceLowPriceError(
                    "Layer decomposition source image exceeds the 30MB upload limit"
                )
            source_url = upload_media(
                source_bytes,
                "seedream_layer_source.png",
                "image/png",
                config,
            )
            update_progress(15)

            payload = self._build_payload(
                source_url,
                prompt_text,
                resolution,
                output_format,
                model,
            )
            task_id, submit_response = submit_image_task(payload, config)
            update_progress(20)

            final_response = poll_image_task(
                task_id,
                config,
                on_progress=lambda progress: update_progress(20 + progress * 0.7),
            )
            image_urls = extract_image_urls(final_response)
            images: List[torch.Tensor] = []
            masks: List[torch.Tensor] = []
            for index, image_url in enumerate(image_urls, start=1):
                layer_image, layer_mask = download_image_with_mask(image_url)
                images.append(layer_image)
                masks.append(layer_mask)
                update_progress(90 + index / len(image_urls) * 10)

            urls_json = json.dumps(image_urls, ensure_ascii=False)
            response = json.dumps(
                {
                    "status": "SUCCESS",
                    "model": model,
                    "task_id": task_id,
                    "submit": submit_response,
                    "result": final_response,
                },
                ensure_ascii=False,
                indent=2,
            )
            return (
                images,
                masks,
                urls_json,
                len(image_urls),
                task_id,
                response,
            )
        except Exception as exc:
            if not skip_error:
                raise
            return self._error_result(
                f"{type(exc).__name__}: {exc}", task_id, model
            )


ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL = "zhenzhen-image-g-v2-lowprice"
ZHENZHEN_IMAGE_G_V2_RESOLUTIONS = ["1k", "2k", "4k"]
ZHENZHEN_IMAGE_G_V2_SIZES = [
    "1:1",
    "16:9",
    "9:16",
    "21:9",
    "9:21",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "4:5",
    "5:4",
]
ZHENZHEN_IMAGE_G_V2_SIZE_OPTIONS = [*ZHENZHEN_IMAGE_G_V2_SIZES, "custom"]
ZHENZHEN_IMAGE_G_V2_MAX_IMAGES = 16
ZHENZHEN_IMAGE_GK_V15_MODEL = "zhenzhen-image-gk-v15"
ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL = "zhenzhen-image-gk-v15-edit"
ZHENZHEN_IMAGE_GK_V15_MODELS = [
    ZHENZHEN_IMAGE_GK_V15_MODEL,
    ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL,
]
ZHENZHEN_IMAGE_GK_V15_SIZES = ["1:1", "16:9", "9:16", "3:2", "2:3"]
ZHENZHEN_IMAGE_NB_FLASH_MODEL = "zhenzhen-image-nb-flash"
ZHENZHEN_IMAGE_NB_2_MODEL = "zhenzhen-image-nb-2"
ZHENZHEN_IMAGE_NB_2_LITE_MODEL = "zhenzhen-image-nb-2-lite"
ZHENZHEN_IMAGE_NB_PRO_MODEL = "zhenzhen-image-nb-pro"
ZHENZHEN_IMAGE_NB_MODELS = [
    ZHENZHEN_IMAGE_NB_FLASH_MODEL,
    ZHENZHEN_IMAGE_NB_2_MODEL,
    ZHENZHEN_IMAGE_NB_2_LITE_MODEL,
    ZHENZHEN_IMAGE_NB_PRO_MODEL,
]
ZHENZHEN_IMAGE_NB_STANDARD_SIZES = [
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
]
ZHENZHEN_IMAGE_NB_EXTREME_SIZES = [
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:1",
    "4:3",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
]
ZHENZHEN_IMAGE_NB_SIZES = ["auto", *ZHENZHEN_IMAGE_NB_EXTREME_SIZES]
ZHENZHEN_IMAGE_NB_RESOLUTIONS = ["0.5k", "1k", "2k", "4k"]
ZHENZHEN_IMAGE_NB_MODEL_RESOLUTIONS = {
    ZHENZHEN_IMAGE_NB_FLASH_MODEL: ("1k",),
    ZHENZHEN_IMAGE_NB_2_MODEL: ("0.5k", "1k", "2k", "4k"),
    ZHENZHEN_IMAGE_NB_2_LITE_MODEL: ("1k",),
    ZHENZHEN_IMAGE_NB_PRO_MODEL: ("1k", "2k", "4k"),
}
ZHENZHEN_IMAGE_NB_MODEL_SIZES = {
    ZHENZHEN_IMAGE_NB_FLASH_MODEL: ("auto", *ZHENZHEN_IMAGE_NB_STANDARD_SIZES),
    ZHENZHEN_IMAGE_NB_2_MODEL: tuple(ZHENZHEN_IMAGE_NB_EXTREME_SIZES),
    ZHENZHEN_IMAGE_NB_2_LITE_MODEL: tuple(ZHENZHEN_IMAGE_NB_EXTREME_SIZES),
    ZHENZHEN_IMAGE_NB_PRO_MODEL: tuple(ZHENZHEN_IMAGE_NB_STANDARD_SIZES),
}
ZHENZHEN_IMAGE_NB_MODEL_N_RANGE = {
    ZHENZHEN_IMAGE_NB_FLASH_MODEL: (1, 1),
    ZHENZHEN_IMAGE_NB_2_MODEL: (1, 1),
    ZHENZHEN_IMAGE_NB_2_LITE_MODEL: (1, 4),
    ZHENZHEN_IMAGE_NB_PRO_MODEL: (1, 1),
}
ZHENZHEN_IMAGE_NB_MAX_IMAGES = 14
ZHENZHEN_IMAGE_NB_FLASH_PROMPT_MAX_LENGTH = 1000
APIMART_IMAGE_PROMPT_MAX_LENGTH = 20000

ZHENZHEN_VIDEO_G_OMNI_FLASH_MODEL = "zhenzhen-video-g-omni-flash"
ZHENZHEN_VIDEO_GK_V15_MODEL = "zhenzhen-video-gk-v15"
ZHENZHEN_VIDEO_GK_SECONDS = [str(value) for value in range(6, 31)]
ZHENZHEN_VIDEO_GK_RESOLUTIONS = ["480p", "720p"]
ZHENZHEN_VIDEO_GK_RATIOS = ["16:9", "9:16", "1:1", "3:2", "2:3"]
ZHENZHEN_VIDEO_V31_FAST_MODEL = "zhenzhen-video-v31-fast"
ZHENZHEN_VIDEO_V31_QUALITY_MODEL = "zhenzhen-video-v31-quality"
ZHENZHEN_VIDEO_V31_LITE_MODEL = "zhenzhen-video-v31-lite"
ZHENZHEN_VIDEO_V31_MODELS = [
    ZHENZHEN_VIDEO_V31_FAST_MODEL,
    ZHENZHEN_VIDEO_V31_QUALITY_MODEL,
    ZHENZHEN_VIDEO_V31_LITE_MODEL,
]
ZHENZHEN_VIDEO_V31_RESOLUTIONS = ["720p", "1080p", "4k"]
ZHENZHEN_VIDEO_V31_RATIOS = ["16:9", "9:16"]
WHISPER_TRANSCRIPTION_MODEL = "whisper-1"
WHISPER_RESPONSE_FORMATS = ["json", "verbose_json", "srt", "text", "vtt"]


def _validate_prompt(
    prompt: str,
    label: str,
    required: bool = True,
    max_length: int = PROMPT_MAX_LENGTH,
) -> str:
    text = str(prompt or "").strip()
    if required and not text:
        raise SeedanceLowPriceError(f"{label} prompt is required")
    if len(text) > max_length:
        raise SeedanceLowPriceError(
            f"{label} prompt cannot exceed {max_length} characters"
        )
    return text


def _is_width_height_size(size: str) -> bool:
    parts = str(size or "").strip().lower().split("x")
    return (
        len(parts) == 2
        and all(part.isdigit() for part in parts)
        and all(int(part) > 0 for part in parts)
    )


def _connected_slots(
    kwargs: Dict[str, Any],
    prefix: str,
    count: int,
    label: str,
) -> List[Tuple[int, Any]]:
    slots = [
        (index, kwargs[f"{prefix}{index}"])
        for index in range(1, count + 1)
        if kwargs.get(f"{prefix}{index}") is not None
    ]
    indexes = [index for index, _ in slots]
    if indexes and indexes != list(range(1, len(indexes) + 1)):
        print(f"[{label}] {prefix} slots {indexes} contain gaps; compacting in slot order.")
    return slots


def _upload_image_slots(
    slots: List[Tuple[int, Any]],
    config: Dict[str, Any],
    filename_prefix: str,
    on_progress: Optional[Callable[[int], None]] = None,
) -> List[str]:
    urls: List[str] = []
    total = len(slots)
    for position, (slot, image) in enumerate(slots, start=1):
        image_bytes = image_to_png_bytes(image)
        urls.append(
            upload_media(
                image_bytes,
                f"{filename_prefix}_{slot}.png",
                "image/png",
                config,
            )
        )
        if on_progress and total:
            on_progress(int(position / total * 20))
    return urls


def resolve_zhenzhen_image_g_v2_size(
    size: str,
    custom_size: str = "",
) -> str:
    normalized_size = str(size or "").strip().lower()
    if normalized_size == "custom":
        normalized_custom_size = str(custom_size or "").strip().lower()
        if not _is_width_height_size(normalized_custom_size):
            raise SeedanceLowPriceError(
                "Image G V2 custom_size must use WxH, for example 1280x720"
            )
        return normalized_custom_size
    if (
        normalized_size in ZHENZHEN_IMAGE_G_V2_SIZES
        or _is_width_height_size(normalized_size)
    ):
        return normalized_size
    supported_sizes = ", ".join(ZHENZHEN_IMAGE_G_V2_SIZES)
    raise SeedanceLowPriceError(
        f"Image G V2 size must be {supported_sizes}, custom, or WxH"
    )


def validate_zhenzhen_image_g_v2_inputs(
    model: str,
    prompt: str,
    resolution: str,
    size: str,
    n: int,
    strict: bool = True,
    custom_size: str = "",
) -> None:
    if model != ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL:
        raise SeedanceLowPriceError(f"Unsupported Zhenzhen Image G V2 model: {model}")
    _validate_prompt(
        prompt,
        "Zhenzhen Image G V2",
        required=strict,
        max_length=APIMART_IMAGE_PROMPT_MAX_LENGTH,
    )
    if resolution not in ZHENZHEN_IMAGE_G_V2_RESOLUTIONS:
        raise SeedanceLowPriceError("Image G V2 resolution must be 1k, 2k, or 4k")
    resolve_zhenzhen_image_g_v2_size(size, custom_size)
    if not 1 <= int(n) <= 10:
        raise SeedanceLowPriceError("Image G V2 n must be between 1 and 10")


def build_zhenzhen_image_g_v2_payload(
    model: str,
    prompt: str,
    resolution: str,
    size: str,
    n: int,
    image_urls: Optional[List[str]] = None,
    custom_size: str = "",
) -> Dict[str, Any]:
    validate_zhenzhen_image_g_v2_inputs(
        model,
        prompt,
        resolution,
        size,
        n,
        strict=True,
        custom_size=custom_size,
    )
    effective_size = resolve_zhenzhen_image_g_v2_size(size, custom_size)
    urls = list(image_urls or [])
    if len(urls) > ZHENZHEN_IMAGE_G_V2_MAX_IMAGES:
        raise SeedanceLowPriceError("Image G V2 accepts at most 16 reference images")
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": str(prompt).strip(),
        "n": int(n),
        "size": effective_size,
        "metadata": {"resolution": resolution},
    }
    if urls:
        payload["images"] = urls
    return payload


class Comfly_zhenzhen_image_g_v2_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {"api_config": (CONFIG_TYPE,)}
        for index in range(1, ZHENZHEN_IMAGE_G_V2_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        optional["custom_size"] = ("STRING", {"default": "1024x1024"})
        return {
            "required": {
                "model": (
                    [ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL],
                    {"default": ZHENZHEN_IMAGE_G_V2_LOWPRICE_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (
                    ZHENZHEN_IMAGE_G_V2_RESOLUTIONS,
                    {"default": "1k"},
                ),
                "size": (
                    ZHENZHEN_IMAGE_G_V2_SIZE_OPTIONS,
                    {"default": "1:1"},
                ),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate_image"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        resolution=None,
        size="1:1",
        n=1,
        custom_size="1024x1024",
        strict=False,
        **kwargs,
    ):
        if None in (model, resolution):
            return True
        try:
            validate_zhenzhen_image_g_v2_inputs(
                model,
                prompt,
                resolution,
                size,
                n,
                strict=bool(strict),
                custom_size=custom_size,
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate_image(
        self,
        model: str,
        prompt: str,
        resolution: str,
        size: str,
        n: int,
        api_config: Any = None,
        skip_error: bool = False,
        custom_size: str = "1024x1024",
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_zhenzhen_image_g_v2_inputs(
                model,
                prompt,
                resolution,
                size,
                n,
                strict=True,
                custom_size=custom_size,
            )
            config = resolve_config(api_config)
            slots = _connected_slots(
                kwargs,
                "image",
                ZHENZHEN_IMAGE_G_V2_MAX_IMAGES,
                "Zhenzhen Image G V2 Low Price",
            )
            image_urls = _upload_image_slots(
                slots,
                config,
                "zhenzhen_image_g_v2_reference",
                on_progress=update_progress,
            )
            payload = build_zhenzhen_image_g_v2_payload(
                model,
                prompt,
                resolution,
                size,
                n,
                image_urls,
                custom_size=custom_size,
            )
            update_progress(25)
            task_id, submit_response = submit_image_task(payload, config)
            update_progress(30)
            final_response = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: update_progress(30 + int(value * 0.6)),
            )
            image_url = extract_image_url(final_response)
            image = download_image(image_url)
            update_progress(100)
            response = {
                "status": "SUCCESS",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                image,
                image_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": f"{type(exc).__name__}: {exc}",
            }
            blank = torch.ones((1, 512, 512, 3), dtype=torch.float32)
            return (blank, "", task_id, json.dumps(response, ensure_ascii=False, indent=2))


def validate_zhenzhen_image_nb_inputs(
    model: str,
    prompt: str,
    resolution: str,
    size: str,
    n: int,
    image_count: int = 0,
    strict: bool = True,
) -> str:
    if model not in ZHENZHEN_IMAGE_NB_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Zhenzhen Image NB model: {model}")
    text = str(prompt or "").strip()
    if strict and not text:
        raise SeedanceLowPriceError("Zhenzhen Image NB prompt is required")
    if (
        model == ZHENZHEN_IMAGE_NB_FLASH_MODEL
        and len(text) > ZHENZHEN_IMAGE_NB_FLASH_PROMPT_MAX_LENGTH
    ):
        raise SeedanceLowPriceError(
            "zhenzhen-image-nb-flash prompt cannot exceed "
            f"{ZHENZHEN_IMAGE_NB_FLASH_PROMPT_MAX_LENGTH} characters"
        )
    allowed_resolutions = ZHENZHEN_IMAGE_NB_MODEL_RESOLUTIONS[model]
    if resolution not in allowed_resolutions:
        raise SeedanceLowPriceError(
            f"{model} resolution must be one of {', '.join(allowed_resolutions)}"
        )
    allowed_sizes = ZHENZHEN_IMAGE_NB_MODEL_SIZES[model]
    if size not in allowed_sizes:
        raise SeedanceLowPriceError(
            f"{model} size must be one of {', '.join(allowed_sizes)}"
        )
    try:
        image_count_value = int(image_count)
        n_value = int(n)
    except (TypeError, ValueError) as exc:
        raise SeedanceLowPriceError("Zhenzhen Image NB n and image count must be integers") from exc
    minimum_n, maximum_n = ZHENZHEN_IMAGE_NB_MODEL_N_RANGE[model]
    if not minimum_n <= n_value <= maximum_n:
        raise SeedanceLowPriceError(
            f"{model} n must be between {minimum_n} and {maximum_n}"
        )
    if not 0 <= image_count_value <= ZHENZHEN_IMAGE_NB_MAX_IMAGES:
        raise SeedanceLowPriceError(
            f"Zhenzhen Image NB accepts at most {ZHENZHEN_IMAGE_NB_MAX_IMAGES} images"
        )
    return text


def build_zhenzhen_image_nb_payload(
    model: str,
    prompt: str,
    resolution: str,
    size: str,
    n: int,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    urls = list(image_urls or [])
    text = validate_zhenzhen_image_nb_inputs(
        model,
        prompt,
        resolution,
        size,
        n,
        image_count=len(urls),
        strict=True,
    )
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": text,
        "n": int(n),
        "size": size,
        "metadata": {"resolution": resolution},
    }
    if urls:
        payload["images"] = urls
    return payload


class Comfly_zhenzhen_image_nb_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {"api_config": (CONFIG_TYPE,)}
        for index in range(1, ZHENZHEN_IMAGE_NB_MAX_IMAGES + 1):
            optional[f"image{index}"] = ("IMAGE",)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "model": (
                    ZHENZHEN_IMAGE_NB_MODELS,
                    {"default": ZHENZHEN_IMAGE_NB_FLASH_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (ZHENZHEN_IMAGE_NB_RESOLUTIONS, {"default": "1k"}),
                "size": (ZHENZHEN_IMAGE_NB_SIZES, {"default": "1:1"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate_image"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        resolution=None,
        size=None,
        n=1,
        strict=False,
        **kwargs,
    ):
        if None in (model, resolution, size):
            return True
        try:
            validate_zhenzhen_image_nb_inputs(
                model,
                prompt,
                resolution,
                size,
                n,
                image_count=0,
                strict=bool(strict),
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate_image(
        self,
        model: str,
        prompt: str,
        resolution: str,
        size: str,
        n: int,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            config = resolve_config(api_config)
            slots = _connected_slots(
                kwargs,
                "image",
                ZHENZHEN_IMAGE_NB_MAX_IMAGES,
                "Zhenzhen Image NB Low Price",
            )
            validate_zhenzhen_image_nb_inputs(
                model,
                prompt,
                resolution,
                size,
                n,
                image_count=len(slots),
                strict=True,
            )
            image_urls = _upload_image_slots(
                slots,
                config,
                "zhenzhen_image_nb_reference",
                on_progress=update_progress,
            )
            payload = build_zhenzhen_image_nb_payload(
                model,
                prompt,
                resolution,
                size,
                n,
                image_urls,
            )
            update_progress(25)
            task_id, submit_response = submit_image_task(payload, config)
            update_progress(30)
            final_response = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: update_progress(30 + int(value * 0.6)),
            )
            image_url = extract_image_url(final_response)
            image = download_image(image_url)
            update_progress(100)
            response = {
                "status": "SUCCESS",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                image,
                image_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": f"{type(exc).__name__}: {exc}",
            }
            blank = torch.ones((1, 512, 512, 3), dtype=torch.float32)
            return (blank, "", task_id, json.dumps(response, ensure_ascii=False, indent=2))


def validate_zhenzhen_image_gk_v15_inputs(
    model: str,
    prompt: str,
    size: str,
    n: int,
    has_image: bool = False,
    strict: bool = True,
) -> None:
    if model not in ZHENZHEN_IMAGE_GK_V15_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Zhenzhen Image GK V1.5 model: {model}")
    _validate_prompt(
        prompt,
        "Zhenzhen Image GK V1.5",
        required=strict,
        max_length=APIMART_IMAGE_PROMPT_MAX_LENGTH,
    )
    if size not in ZHENZHEN_IMAGE_GK_V15_SIZES:
        raise SeedanceLowPriceError(f"Unsupported Zhenzhen Image GK V1.5 size: {size}")
    if not 1 <= int(n) <= 10:
        raise SeedanceLowPriceError("Zhenzhen Image GK V1.5 n must be between 1 and 10")
    if strict and model == ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL and not has_image:
        raise SeedanceLowPriceError(
            "zhenzhen-image-gk-v15-edit requires image1"
        )
    if model == ZHENZHEN_IMAGE_GK_V15_MODEL and has_image:
        raise SeedanceLowPriceError(
            "zhenzhen-image-gk-v15 is text-to-image and does not accept image1"
        )


def build_zhenzhen_image_gk_v15_payload(
    model: str,
    prompt: str,
    size: str,
    n: int,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    urls = list(image_urls or [])
    validate_zhenzhen_image_gk_v15_inputs(
        model, prompt, size, n, has_image=bool(urls), strict=True
    )
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": str(prompt).strip(),
        "n": int(n),
        "size": size,
    }
    if model == ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL:
        payload["images"] = urls[:1]
    return payload


class Comfly_zhenzhen_image_gk_v15_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (
                    ZHENZHEN_IMAGE_GK_V15_MODELS,
                    {"default": ZHENZHEN_IMAGE_GK_V15_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "size": (ZHENZHEN_IMAGE_GK_V15_SIZES, {"default": "1:1"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
            },
            "optional": {
                "image1": ("IMAGE",),
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("image", "image_url", "task_id", "response")
    FUNCTION = "generate_image"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        size=None,
        n=1,
        image1=None,
        strict=False,
        **kwargs,
    ):
        if None in (model, size):
            return True
        try:
            validate_zhenzhen_image_gk_v15_inputs(
                model,
                prompt,
                size,
                n,
                has_image=image1 is not None,
                strict=bool(strict),
            )
        except Exception as exc:
            return str(exc)
        return True

    def generate_image(
        self,
        model: str,
        prompt: str,
        size: str,
        n: int,
        image1: Any = None,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_zhenzhen_image_gk_v15_inputs(
                model,
                prompt,
                size,
                n,
                has_image=image1 is not None,
                strict=True,
            )
            config = resolve_config(api_config)
            image_urls: List[str] = []
            if model == ZHENZHEN_IMAGE_GK_V15_EDIT_MODEL:
                image_urls.append(
                    upload_media(
                        image_to_png_bytes(image1),
                        "zhenzhen_image_gk_v15_reference.png",
                        "image/png",
                        config,
                    )
                )
            update_progress(20)
            payload = build_zhenzhen_image_gk_v15_payload(
                model, prompt, size, n, image_urls
            )
            task_id, submit_response = submit_image_task(payload, config)
            update_progress(30)
            final_response = poll_image_task(
                task_id,
                config,
                on_progress=lambda value: update_progress(30 + int(value * 0.6)),
            )
            image_url = extract_image_url(final_response)
            image = download_image(image_url)
            update_progress(100)
            response = {
                "status": "SUCCESS",
                "model": model,
                "task_id": task_id,
                "submit": submit_response,
                "result": final_response,
            }
            return (
                image,
                image_url,
                task_id,
                json.dumps(response, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            if not skip_error:
                raise
            response = {
                "status": "error",
                "model": model,
                "task_id": task_id,
                "message": f"{type(exc).__name__}: {exc}",
            }
            blank = torch.ones((1, 512, 512, 3), dtype=torch.float32)
            return (blank, "", task_id, json.dumps(response, ensure_ascii=False, indent=2))


def _validate_ratio(ratio: str, supported: List[str], label: str) -> None:
    if ratio not in supported:
        raise SeedanceLowPriceError(
            f"{label} ratio must be one of {', '.join(supported)}"
        )


def build_zhenzhen_video_gk_v15_payload(
    prompt: str,
    seconds: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    text = _validate_prompt(prompt, "Zhenzhen Video GK V1.5")
    urls = list(image_urls or [])
    if str(seconds) not in ZHENZHEN_VIDEO_GK_SECONDS:
        raise SeedanceLowPriceError("Video GK V1.5 seconds must be 6 through 30")
    if resolution not in ZHENZHEN_VIDEO_GK_RESOLUTIONS:
        raise SeedanceLowPriceError("Video GK V1.5 resolution must be 480p or 720p")
    _validate_ratio(ratio, ZHENZHEN_VIDEO_GK_RATIOS, "Video GK V1.5")
    if len(urls) > 7:
        raise SeedanceLowPriceError("Video GK V1.5 accepts at most 7 images")
    payload: Dict[str, Any] = {
        "model": ZHENZHEN_VIDEO_GK_V15_MODEL,
        "prompt": text,
        "seconds": str(seconds),
        "metadata": {"resolution": resolution, "ratio": ratio},
    }
    if urls:
        payload["images"] = urls
    return payload


def build_zhenzhen_video_v31_payload(
    model: str,
    prompt: str,
    resolution: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if model not in ZHENZHEN_VIDEO_V31_MODELS:
        raise SeedanceLowPriceError(f"Unsupported Video V3.1 model: {model}")
    text = _validate_prompt(prompt, "Zhenzhen Video V3.1")
    urls = list(image_urls or [])
    if resolution not in ZHENZHEN_VIDEO_V31_RESOLUTIONS:
        raise SeedanceLowPriceError("Video V3.1 resolution must be 720p, 1080p, or 4k")
    _validate_ratio(ratio, ZHENZHEN_VIDEO_V31_RATIOS, "Video V3.1")
    if model == ZHENZHEN_VIDEO_V31_LITE_MODEL and urls:
        raise SeedanceLowPriceError(
            "zhenzhen-video-v31-lite is text-to-video only and does not accept images"
        )
    if len(urls) > 3:
        raise SeedanceLowPriceError("Video V3.1 accepts at most 3 images")
    if model == ZHENZHEN_VIDEO_V31_QUALITY_MODEL and len(urls) == 3:
        raise SeedanceLowPriceError(
            "Video V3.1 Quality does not support the 3-image reference mode"
        )
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": text,
        "seconds": "8",
        "metadata": {"resolution": resolution, "ratio": ratio},
    }
    if urls:
        payload["images"] = urls
    return payload


def _validate_remote_video_url(video_url: str) -> str:
    value = str(video_url or "").strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SeedanceLowPriceError("Omni video_url must be an http(s) URL")
    return value


def build_zhenzhen_video_g_omni_flash_payload(
    prompt: str,
    ratio: str,
    image_urls: Optional[List[str]] = None,
    video_url: str = "",
    extend_from_task_id: str = "",
) -> Dict[str, Any]:
    text = _validate_prompt(
        prompt, "Zhenzhen Video G Omni Flash", required=False
    )
    urls = list(image_urls or [])
    if len(urls) > 16:
        raise SeedanceLowPriceError("Video G Omni Flash accepts at most 16 images")
    _validate_ratio(ratio, RATIOS, "Video G Omni Flash")
    normalized_video_url = _validate_remote_video_url(video_url)
    extend_id = str(extend_from_task_id or "").strip()
    if normalized_video_url and extend_id:
        raise SeedanceLowPriceError(
            "Omni video_url and extend_from_task_id are mutually exclusive"
        )
    if not (text or urls or normalized_video_url or extend_id):
        raise SeedanceLowPriceError(
            "Omni requires a prompt, image, video, or extend_from_task_id"
        )
    metadata: Dict[str, Any] = {"resolution": "720p"}
    if ratio != "adaptive":
        metadata["ratio"] = ratio
    if normalized_video_url:
        metadata["video_url"] = normalized_video_url
    if extend_id:
        metadata["extend_from_task_id"] = extend_id
    payload: Dict[str, Any] = {
        "model": ZHENZHEN_VIDEO_G_OMNI_FLASH_MODEL,
        "metadata": metadata,
    }
    if text:
        payload["prompt"] = text
    if urls:
        payload["images"] = urls
    return payload


class _Comfly_apimart_video_base:
    RETURN_TYPES = (VIDEO_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_url", "task_id", "response")
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @staticmethod
    def _update_progress(pbar: Any, value: int) -> None:
        if pbar is not None:
            try:
                pbar.update_absolute(value, 100)
            except Exception:
                pass

    def _finish_video(
        self,
        payload: Dict[str, Any],
        config: Dict[str, Any],
        task_id: str,
        pbar: Any,
    ):
        task_id, submit_response = submit_task(payload, config)
        self._update_progress(pbar, 25)
        final_response = poll_task(
            task_id,
            config,
            on_progress=lambda value: self._update_progress(
                pbar, 25 + int(value * 0.7)
            ),
        )
        video_url = extract_video_url(final_response)
        video = download_video(video_url)
        self._update_progress(pbar, 100)
        response = {
            "status": "completed",
            "model": payload["model"],
            "task_id": task_id,
            "submit": submit_response,
            "result": final_response,
        }
        return (
            video,
            video_url,
            task_id,
            json.dumps(response, ensure_ascii=False, indent=2),
        )

    @staticmethod
    def _error_result(model: str, task_id: str, exc: Exception):
        message = f"{type(exc).__name__}: {exc}"
        response = {
            "status": "error",
            "model": model,
            "task_id": task_id,
            "message": message,
        }
        return (
            make_error_video(message),
            "",
            task_id,
            json.dumps(response, ensure_ascii=False, indent=2),
        )


class Comfly_zhenzhen_video_gk_v15_lowprice(_Comfly_apimart_video_base):
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {"api_config": (CONFIG_TYPE,)}
        for index in range(1, 8):
            optional[f"image{index}"] = ("IMAGE",)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (ZHENZHEN_VIDEO_GK_SECONDS, {"default": "6"}),
                "resolution": (
                    ZHENZHEN_VIDEO_GK_RESOLUTIONS,
                    {"default": "480p"},
                ),
                "ratio": (ZHENZHEN_VIDEO_GK_RATIOS, {"default": "16:9"}),
            },
            "optional": optional,
        }

    FUNCTION = "generate"

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        prompt="",
        seconds="6",
        resolution="480p",
        ratio="16:9",
        strict=False,
        **kwargs,
    ):
        try:
            if strict:
                build_zhenzhen_video_gk_v15_payload(
                    prompt, seconds, resolution, ratio
                )
            else:
                _validate_prompt(
                    prompt,
                    "Zhenzhen Video GK V1.5",
                    required=False,
                )
                if str(seconds) not in ZHENZHEN_VIDEO_GK_SECONDS:
                    raise SeedanceLowPriceError(
                        "Video GK V1.5 seconds must be 6 through 30"
                    )
                if resolution not in ZHENZHEN_VIDEO_GK_RESOLUTIONS:
                    raise SeedanceLowPriceError(
                        "Video GK V1.5 resolution must be 480p or 720p"
                    )
                _validate_ratio(ratio, ZHENZHEN_VIDEO_GK_RATIOS, "Video GK V1.5")
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None
        try:
            config = resolve_config(api_config)
            slots = _connected_slots(
                kwargs, "image", 7, "Zhenzhen Video GK V1.5 Low Price"
            )
            image_urls = _upload_image_slots(
                slots,
                config,
                "zhenzhen_video_gk_v15_reference",
                on_progress=lambda value: self._update_progress(pbar, value),
            )
            payload = build_zhenzhen_video_gk_v15_payload(
                prompt, seconds, resolution, ratio, image_urls
            )
            return self._finish_video(payload, config, task_id, pbar)
        except Exception as exc:
            if not skip_error:
                raise
            return self._error_result(ZHENZHEN_VIDEO_GK_V15_MODEL, task_id, exc)


class Comfly_zhenzhen_video_v31_lowprice(_Comfly_apimart_video_base):
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            "api_config": (CONFIG_TYPE,),
            "image1": ("IMAGE",),
            "image2": ("IMAGE",),
            "image3": ("IMAGE",),
            "skip_error": ("BOOLEAN", {"default": False}),
        }
        return {
            "required": {
                "model": (
                    ZHENZHEN_VIDEO_V31_MODELS,
                    {"default": ZHENZHEN_VIDEO_V31_FAST_MODEL},
                ),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (["8"], {"default": "8"}),
                "resolution": (
                    ZHENZHEN_VIDEO_V31_RESOLUTIONS,
                    {"default": "720p"},
                ),
                "ratio": (ZHENZHEN_VIDEO_V31_RATIOS, {"default": "16:9"}),
            },
            "optional": optional,
        }

    FUNCTION = "generate"

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model=None,
        prompt="",
        seconds="8",
        resolution="720p",
        ratio="16:9",
        strict=False,
        **kwargs,
    ):
        if model is None:
            return True
        try:
            if str(seconds) != "8":
                raise SeedanceLowPriceError("Video V3.1 duration is fixed at 8 seconds")
            if strict:
                build_zhenzhen_video_v31_payload(
                    model, prompt, resolution, ratio
                )
            else:
                if model not in ZHENZHEN_VIDEO_V31_MODELS:
                    raise SeedanceLowPriceError(
                        f"Unsupported Video V3.1 model: {model}"
                    )
                _validate_prompt(
                    prompt, "Zhenzhen Video V3.1", required=False
                )
                if resolution not in ZHENZHEN_VIDEO_V31_RESOLUTIONS:
                    raise SeedanceLowPriceError(
                        "Video V3.1 resolution must be 720p, 1080p, or 4k"
                    )
                _validate_ratio(ratio, ZHENZHEN_VIDEO_V31_RATIOS, "Video V3.1")
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        model: str,
        prompt: str,
        seconds: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None
        try:
            if str(seconds) != "8":
                raise SeedanceLowPriceError("Video V3.1 duration is fixed at 8 seconds")
            config = resolve_config(api_config)
            slots = _connected_slots(
                kwargs, "image", 3, "Zhenzhen Video V3.1 Low Price"
            )
            if model == ZHENZHEN_VIDEO_V31_LITE_MODEL and slots:
                raise SeedanceLowPriceError(
                    "zhenzhen-video-v31-lite is text-to-video only and does not accept images"
                )
            image_urls = _upload_image_slots(
                slots,
                config,
                "zhenzhen_video_v31_reference",
                on_progress=lambda value: self._update_progress(pbar, value),
            )
            payload = build_zhenzhen_video_v31_payload(
                model, prompt, resolution, ratio, image_urls
            )
            return self._finish_video(payload, config, task_id, pbar)
        except Exception as exc:
            if not skip_error:
                raise
            return self._error_result(model, task_id, exc)


class Comfly_zhenzhen_video_g_omni_flash_lowprice(_Comfly_apimart_video_base):
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            "api_config": (CONFIG_TYPE,),
            "input_video": (VIDEO_TYPE,),
            "video_url": ("STRING", {"default": ""}),
            "extend_from_task_id": ("STRING", {"default": ""}),
        }
        for index in range(1, 17):
            optional[f"image{index}"] = ("IMAGE",)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "resolution": (["720p"], {"default": "720p"}),
                "ratio": (RATIOS, {"default": "16:9"}),
            },
            "optional": optional,
        }

    FUNCTION = "generate"

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        prompt="",
        resolution="720p",
        ratio="16:9",
        video_url="",
        extend_from_task_id="",
        strict=False,
        **kwargs,
    ):
        try:
            if resolution != "720p":
                raise SeedanceLowPriceError(
                    "Video G Omni Flash resolution is fixed at 720p"
                )
            _validate_ratio(ratio, RATIOS, "Video G Omni Flash")
            normalized_url = _validate_remote_video_url(video_url)
            if normalized_url and str(extend_from_task_id or "").strip():
                raise SeedanceLowPriceError(
                    "Omni video_url and extend_from_task_id are mutually exclusive"
                )
            if strict:
                build_zhenzhen_video_g_omni_flash_payload(
                    prompt,
                    ratio,
                    video_url=normalized_url,
                    extend_from_task_id=extend_from_task_id,
                )
            else:
                _validate_prompt(
                    prompt,
                    "Zhenzhen Video G Omni Flash",
                    required=False,
                )
        except Exception as exc:
            return str(exc)
        return True

    def generate(
        self,
        prompt: str,
        resolution: str,
        ratio: str,
        api_config: Any = None,
        input_video: Any = None,
        video_url: str = "",
        extend_from_task_id: str = "",
        skip_error: bool = False,
        **kwargs,
    ):
        task_id = ""
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None
        try:
            if resolution != "720p":
                raise SeedanceLowPriceError(
                    "Video G Omni Flash resolution is fixed at 720p"
                )
            normalized_video_url = _validate_remote_video_url(video_url)
            if input_video is not None and normalized_video_url:
                raise SeedanceLowPriceError(
                    "Connect input_video or set video_url, not both"
                )
            if input_video is not None and str(extend_from_task_id or "").strip():
                raise SeedanceLowPriceError(
                    "Omni input_video and extend_from_task_id are mutually exclusive"
                )
            config = resolve_config(api_config)
            slots = _connected_slots(
                kwargs, "image", 16, "Zhenzhen Video G Omni Flash Low Price"
            )
            image_urls = _upload_image_slots(
                slots,
                config,
                "zhenzhen_video_g_omni_reference",
                on_progress=lambda value: self._update_progress(pbar, value),
            )
            if input_video is not None:
                normalized_video_url = upload_media(
                    video_to_mp4_bytes(input_video),
                    "zhenzhen_video_g_omni_input.mp4",
                    "video/mp4",
                    config,
                )
                self._update_progress(pbar, 20)
            payload = build_zhenzhen_video_g_omni_flash_payload(
                prompt,
                ratio,
                image_urls=image_urls,
                video_url=normalized_video_url,
                extend_from_task_id=extend_from_task_id,
            )
            return self._finish_video(payload, config, task_id, pbar)
        except Exception as exc:
            if not skip_error:
                raise
            return self._error_result(
                ZHENZHEN_VIDEO_G_OMNI_FLASH_MODEL, task_id, exc
            )


def _extract_transcription_text(data: Any) -> str:
    if isinstance(data, dict):
        for key in ("text", "transcript", "transcription"):
            value = data.get(key)
            if value is not None:
                return str(value)
        if isinstance(data.get("data"), dict):
            return _extract_transcription_text(data["data"])
    return ""


def transcribe_audio(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    model: str,
    response_format: str,
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Tuple[str, str]:
    if model != WHISPER_TRANSCRIPTION_MODEL:
        raise SeedanceLowPriceError(f"Unsupported Whisper model: {model}")
    if response_format not in WHISPER_RESPONSE_FORMATS:
        raise SeedanceLowPriceError(
            f"Unsupported Whisper response_format: {response_format}"
        )
    url = f"{config['base_url']}/v1/audio/transcriptions"
    form = {"model": model, "response_format": response_format}
    files = {"file": (filename, file_bytes, mime_type)}
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            sleep(min(2 ** attempt + 1, 15))
        try:
            response = _get_session().post(
                url,
                headers=_headers(config["api_key"], json_content=False),
                data=form,
                files=files,
                timeout=config.get("timeout", 60),
            )
        except requests.RequestException as exc:
            last_error = f"network error: {type(exc).__name__}: {exc}"
            continue

        try:
            parsed = response.json() if response.text else None
        except ValueError:
            parsed = None
        if response.status_code == 429 or response.status_code >= 500:
            last_error = (
                f"HTTP {response.status_code}: "
                f"{extract_error_message(parsed, response.text[:300])}"
            )
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                f"Transcription rejected (HTTP {response.status_code}): "
                f"{extract_error_message(parsed, response.text[:300])}"
            )
        if response_format in ("json", "verbose_json"):
            if not isinstance(parsed, dict):
                raise SeedanceLowPriceError(
                    f"Transcription returned invalid JSON: {response.text[:300]}"
                )
            return (
                _extract_transcription_text(parsed),
                json.dumps(parsed, ensure_ascii=False, indent=2),
            )
        return (response.text, response.text)
    raise RuntimeError(f"Transcription failed after 3 attempts: {last_error}")


class Comfly_whisper_1_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": (AUDIO_TYPE,),
                "model": (
                    [WHISPER_TRANSCRIPTION_MODEL],
                    {"default": WHISPER_TRANSCRIPTION_MODEL},
                ),
                "response_format": (
                    WHISPER_RESPONSE_FORMATS,
                    {"default": "json"},
                ),
            },
            "optional": {
                "api_config": (CONFIG_TYPE,),
                "skip_error": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "response")
    FUNCTION = "transcribe"
    CATEGORY = "zhenzhen/Seedance2 Low Price"
    OUTPUT_NODE = True

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        audio=None,
        model=None,
        response_format=None,
        strict=False,
        **kwargs,
    ):
        if model not in (None, WHISPER_TRANSCRIPTION_MODEL):
            return f"Unsupported Whisper model: {model}"
        if response_format not in (None, *WHISPER_RESPONSE_FORMATS):
            return f"Unsupported Whisper response_format: {response_format}"
        if strict and audio is None:
            return "Whisper transcription requires an audio input"
        return True

    def transcribe(
        self,
        audio: Any,
        model: str,
        response_format: str,
        api_config: Any = None,
        skip_error: bool = False,
    ):
        try:
            validation = self.VALIDATE_INPUTS(
                audio=audio,
                model=model,
                response_format=response_format,
                strict=True,
            )
            if validation is not True:
                raise SeedanceLowPriceError(validation)
            config = resolve_config(api_config)
            wav_bytes = audio_to_wav_bytes(audio)
            return transcribe_audio(
                wav_bytes,
                "whisper_input.wav",
                "audio/wav",
                model,
                response_format,
                config,
            )
        except Exception as exc:
            if not skip_error:
                raise
            response = {
                "status": "error",
                "model": model,
                "message": f"{type(exc).__name__}: {exc}",
            }
            return ("", json.dumps(response, ensure_ascii=False, indent=2))


SUNO_VERSIONS = ["v3.5", "v4", "v4.5", "v4.5+", "v4.5-all", "v5", "v5.5"]
SUNO_INSPO_VERSIONS = ["v4", "v4.5", "v4.5+", "v4.5-all", "v5", "v5.5"]
SUNO_REPLACE_VERSIONS = ["v4", "v4.5+", "v5", "v5.5"]
SUNO_REMASTER_VERSIONS = ["v4.5+", "v5", "v5.5"]
SUNO_V5_VERSIONS = ["v5", "v5.5"]
MAX_SUNO_REFERENCE_AUDIOS = 4
SUNO_UPLOAD_MIN_SECONDS = 6.0
SUNO_CREATE_VOICE_MIN_SECONDS = 10.0
SUNO_CREATE_VOICE_MAX_SECONDS = 240.0

SUNO_ACTION_SPECS: Dict[str, Dict[str, Any]] = {
    "suno-generation": {
        "action": "",
        "sync": False,
        "reference_type": "none",
        "required_fields": ("version", "prompt"),
        "allowed_fields": (
            "version",
            "prompt",
            "custom",
            "instrumental",
            "title",
            "style",
            "vocal_gender",
        ),
        "allowed_versions": tuple(SUNO_VERSIONS),
        "result_family": "audio",
    },
    "suno-lyrics": {
        "action": "lyrics",
        "sync": False,
        "reference_type": "none",
        "required_fields": ("prompt",),
        "allowed_fields": ("prompt",),
        "allowed_versions": (),
        "result_family": "text",
    },
    "suno-upload": {
        "action": "upload",
        "sync": False,
        "reference_type": "url",
        "required_fields": ("audioFilePath",),
        "allowed_fields": ("audioFilePath",),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-extend": {
        "action": "extend",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "continue_at"),
        "allowed_fields": ("task_id", "audio_index", "continue_at", "version"),
        "allowed_versions": tuple(SUNO_VERSIONS),
        "result_family": "audio",
    },
    "suno-cover-song": {
        "action": "cover-song",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "prompt"),
        "allowed_fields": ("task_id", "audio_index", "prompt", "version"),
        "allowed_versions": tuple(SUNO_VERSIONS),
        "result_family": "audio",
    },
    "suno-inspo": {
        "action": "inspo",
        "sync": False,
        "reference_type": "url",
        "required_fields": ("audio_urls",),
        "allowed_fields": ("audio_urls", "version"),
        "allowed_versions": tuple(SUNO_INSPO_VERSIONS),
        "result_family": "audio",
    },
    "suno-mashup": {
        "action": "mashup",
        "sync": False,
        "reference_type": "mashup",
        "required_fields": ("task_ids", "prompt"),
        "allowed_fields": ("task_ids", "prompt", "version"),
        "allowed_versions": tuple(SUNO_VERSIONS),
        "result_family": "audio",
    },
    "suno-upsample-tags": {
        "action": "upsample-tags",
        "sync": True,
        "reference_type": "none",
        "required_fields": ("tags",),
        "allowed_fields": ("tags",),
        "allowed_versions": (),
        "result_family": "text",
    },
    "suno-sounds": {
        "action": "sounds",
        "sync": False,
        "reference_type": "none",
        "required_fields": ("prompt",),
        "allowed_fields": ("prompt", "version"),
        "allowed_versions": tuple(SUNO_V5_VERSIONS),
        "result_family": "audio",
    },
    "suno-create-voice": {
        "action": "create-voice",
        "sync": False,
        "reference_type": "url",
        "required_fields": ("audio_url",),
        "allowed_fields": ("audio_url",),
        "allowed_versions": (),
        "result_family": "text",
    },
    "suno-stems": {
        "action": "stems",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-stems-all": {
        "action": "stems-all",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-wav": {
        "action": "wav",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-generate-mp4": {
        "action": "generate-mp4",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "video",
    },
    "suno-concat": {
        "action": "concat",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-crop": {
        "action": "crop",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "start_s", "end_s"),
        "allowed_fields": ("task_id", "audio_index", "start_s", "end_s"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-fade-in": {
        "action": "fade-in",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "duration_s"),
        "allowed_fields": ("task_id", "audio_index", "duration_s"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-fade-out": {
        "action": "fade-out",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "duration_s"),
        "allowed_fields": ("task_id", "audio_index", "duration_s"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-remove-section": {
        "action": "remove-section",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "start_s", "end_s"),
        "allowed_fields": ("task_id", "audio_index", "start_s", "end_s"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-replace-music": {
        "action": "replace-music",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "start_s", "end_s"),
        "allowed_fields": (
            "task_id",
            "audio_index",
            "start_s",
            "end_s",
            "version",
        ),
        "allowed_versions": tuple(SUNO_REPLACE_VERSIONS),
        "result_family": "audio",
    },
    "suno-adjust-speed": {
        "action": "adjust-speed",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "speed"),
        "allowed_fields": ("task_id", "audio_index", "speed"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-remaster": {
        "action": "remaster",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index", "version"),
        "allowed_versions": tuple(SUNO_REMASTER_VERSIONS),
        "result_family": "audio",
    },
    "suno-midi": {
        "action": "midi",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "file",
    },
    "suno-bpm": {
        "action": "bpm",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "text",
    },
    "suno-aligned-lyrics": {
        "action": "aligned-lyrics",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "text",
    },
    "suno-persona": {
        "action": "persona",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "name"),
        "allowed_fields": ("task_id", "audio_index", "name"),
        "allowed_versions": (),
        "result_family": "text",
    },
    "suno-vox": {
        "action": "vox",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id",),
        "allowed_fields": ("task_id", "audio_index"),
        "allowed_versions": (),
        "result_family": "audio",
    },
    "suno-sample": {
        "action": "sample",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "start_s", "end_s", "prompt"),
        "allowed_fields": (
            "task_id",
            "audio_index",
            "prompt",
            "start_s",
            "end_s",
            "version",
        ),
        "allowed_versions": tuple(SUNO_VERSIONS),
        "result_family": "audio",
    },
    "suno-add-vocals": {
        "action": "add-vocals",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "prompt"),
        "allowed_fields": ("task_id", "audio_index", "prompt", "version"),
        "allowed_versions": tuple(SUNO_V5_VERSIONS),
        "result_family": "audio",
    },
    "suno-add-instrumental": {
        "action": "add-instrumental",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "prompt"),
        "allowed_fields": ("task_id", "audio_index", "prompt", "version"),
        "allowed_versions": tuple(SUNO_V5_VERSIONS),
        "result_family": "audio",
    },
    "suno-add-stem": {
        "action": "add-stem",
        "sync": False,
        "reference_type": "task_audio",
        "required_fields": ("task_id", "prompt"),
        "allowed_fields": ("task_id", "audio_index", "prompt", "version"),
        "allowed_versions": ("v5.5",),
        "result_family": "audio",
    },
}
SUNO_OPERATIONS = list(SUNO_ACTION_SPECS)


_SUNO_RUNNING_STATUSES = {
    "created",
    "submitted",
    "queued",
    "pending",
    "processing",
    "in_progress",
    "running",
}
_SUNO_COMPLETED_STATUSES = {"completed", "complete", "success", "succeeded"}
_SUNO_FAILED_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}


def _extract_suno_task_id(value: Any) -> Optional[str]:
    if isinstance(value, list):
        for item in value:
            task_id = _extract_suno_task_id(item)
            if task_id:
                return task_id
        return None
    if not isinstance(value, dict):
        return None
    for key in ("task_id", "id"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    nested = value.get("data")
    if isinstance(nested, (dict, list)):
        return _extract_suno_task_id(nested)
    return None


def submit_suno_action(
    action: str,
    payload: Dict[str, Any],
    config: Dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> Tuple[Optional[str], Dict[str, Any]]:
    action_text = str(action or "").strip().strip("/")
    suffix = f"/{action_text}" if action_text else ""
    url = f"{config['base_url']}/v1/music/generations{suffix}"
    last_error = "unknown error"
    for attempt in range(3):
        if attempt:
            sleep(min(2 ** attempt + 1, 15))
        try:
            response = _get_session().post(
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
                "Suno submit transport failed after the request may have reached "
                "the server; it was not retried to avoid a duplicate paid task. "
                f"Check the provider console before retrying: {type(exc).__name__}: {exc}"
            ) from exc

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {message}"
            continue
        if not 200 <= response.status_code < 300:
            raise SeedanceLowPriceError(
                f"Suno submit rejected (HTTP {response.status_code}): {message}"
            )
        if not isinstance(data, dict):
            raise SeedanceLowPriceError("Suno submit returned a non-object JSON response")
        return _extract_suno_task_id(data), data
    raise RuntimeError(f"Suno submit failed after 3 attempts: {last_error}")


def poll_suno_task(
    task_id: str,
    config: Dict[str, Any],
    on_progress: Optional[Callable[[int], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    task_id_text = str(task_id or "").strip()
    if not task_id_text:
        raise SeedanceLowPriceError("Suno task_id is required for polling")
    url = f"{config['base_url']}/v1/music/tasks/{task_id_text}"
    start = clock()
    failures = 0
    while True:
        if clock() - start > config.get("max_poll_time", 1800):
            raise RuntimeError("Suno polling timed out")
        sleep(config.get("poll_interval", 4))
        try:
            response = _get_session().get(
                url,
                headers=_headers(config["api_key"], json_content=False),
                timeout=30,
            )
        except requests.RequestException:
            failures += 1
            if failures >= 6:
                raise RuntimeError("Suno polling failed after repeated network errors")
            sleep(min(failures * 2, 10))
            continue

        data = _response_json(response)
        message = extract_error_message(data, response.text[:300])
        if response.status_code != 200:
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise SeedanceLowPriceError(
                    f"Suno polling rejected (HTTP {response.status_code}): {message}"
                )
            failures += 1
            if failures >= 6:
                raise RuntimeError(
                    f"Suno polling repeatedly returned HTTP {response.status_code}: {message}"
                )
            sleep(min(failures * 2, 10))
            continue
        if not isinstance(data, dict):
            failures += 1
            if failures >= 6:
                raise RuntimeError("Suno polling repeatedly returned invalid JSON")
            continue

        task_data: Any = data.get("data")
        if isinstance(task_data, list) and task_data and isinstance(task_data[0], dict):
            task_data = task_data[0]
        elif not isinstance(task_data, dict) and data.get("status"):
            task_data = data
        if not isinstance(task_data, dict):
            failures += 1
            if failures >= 6:
                raise RuntimeError("Suno polling response did not contain a data object")
            continue

        failures = 0
        status = str(task_data.get("status") or "").strip().lower()
        progress = _coerce_progress(task_data.get("progress"))
        if on_progress and progress is not None:
            on_progress(progress)
        if status in _SUNO_COMPLETED_STATUSES:
            return data
        if status in _SUNO_FAILED_STATUSES:
            reason = (
                task_data.get("fail_reason")
                or task_data.get("error")
                or extract_error_message(task_data, "music task failed")
            )
            raise SeedanceLowPriceError(f"Suno task failed: {reason}")
        if status and status not in _SUNO_RUNNING_STATUSES:
            print(f"[Suno Low Price] Unknown task status '{status}', continuing to poll")


def _suno_url_kind(key: str, url: str) -> str:
    key_text = str(key or "").lower()
    path = urlsplit(url).path.lower()
    extension = os.path.splitext(path)[1]
    if "image" in key_text or extension in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return "image"
    if (
        "video" in key_text
        or "mp4" in key_text
        or extension in {".mp4", ".mov", ".mkv", ".avi", ".webm"}
    ):
        return "video"
    if (
        "audio" in key_text
        or "wav" in key_text
        or extension in {".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac"}
    ):
        return "audio"
    return "file"


def _collect_suno_urls(
    value: Any,
    key: str,
    buckets: Dict[str, List[str]],
    seen: Set[str],
    artifacts: List[Dict[str, str]],
) -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _collect_suno_urls(child_value, str(child_key), buckets, seen, artifacts)
        return
    if isinstance(value, list):
        for item in value:
            _collect_suno_urls(item, key, buckets, seen, artifacts)
        return
    if not isinstance(value, str):
        return
    url = value.strip()
    if not url.startswith(("http://", "https://")) or url in seen:
        return
    seen.add(url)
    kind = _suno_url_kind(key, url)
    buckets[kind].append(url)
    buckets["all"].append(url)
    artifacts.append({"url": url, "kind": kind})


def _extract_suno_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        simple = [item for item in value if isinstance(item, (str, int, float, bool))]
        if simple and len(simple) == len(value):
            return json.dumps(simple, ensure_ascii=False)
    if not isinstance(value, dict):
        return ""
    for key in (
        "text",
        "lyrics",
        "tags",
        "aligned_lyrics",
        "bpm",
        "persona_id",
        "voice_id",
        "audio_id",
        "content",
        "message",
    ):
        if key in value:
            text = _extract_suno_text(value.get(key))
            if text:
                return text
    music = value.get("music")
    if isinstance(music, list):
        for item in music:
            if isinstance(item, dict):
                for key in ("lyrics", "title", "audio_id"):
                    text = _extract_suno_text(item.get(key))
                    if text:
                        return text
    for key, child in value.items():
        if key in {"id", "task_id", "status", "progress"}:
            continue
        text = _extract_suno_text(child)
        if text:
            return text
    return ""


def extract_suno_results(final_response: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(final_response, dict):
        raise SeedanceLowPriceError("Suno response must be a JSON object")
    data = final_response.get("data")
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        task_data: Any = data[0]
    else:
        task_data = data if isinstance(data, dict) else final_response
    result = task_data.get("result") if isinstance(task_data, dict) else None
    result_data = result if result is not None else task_data
    buckets: Dict[str, List[str]] = {
        "audio": [],
        "video": [],
        "image": [],
        "file": [],
        "all": [],
    }
    artifacts: List[Dict[str, str]] = []
    _collect_suno_urls(result_data, "", buckets, set(), artifacts)
    return {
        "task_id": _extract_suno_task_id(final_response) or "",
        "status": (
            str(task_data.get("status") or "").strip()
            if isinstance(task_data, dict)
            else ""
        ),
        "result": result_data,
        "artifacts": artifacts,
        "all_urls": buckets["all"],
        "text": _extract_suno_text(result_data),
    }


def _suno_output_directory() -> str:
    try:
        import folder_paths

        output_dir = folder_paths.get_output_directory()
    except ImportError:
        output_dir = os.environ.get("SEEDANCE_OUTPUT_DIR") or tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _guess_suno_extension(url: str, content_type: str, fallback: str) -> str:
    extension = os.path.splitext(urlsplit(url).path)[1].lower()
    if 1 < len(extension) <= 10 and extension[1:].replace("_", "").isalnum():
        return extension
    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_extension(media_type) if media_type else None
    if guessed:
        return guessed
    return f".{str(fallback or 'bin').strip().lower().lstrip('.') or 'bin'}"


def download_suno_file(
    url: str,
    filename_prefix: str,
    fallback_extension: str,
    max_retries: int = 3,
) -> str:
    output_dir = _suno_output_directory()
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        if attempt:
            time.sleep(2 ** attempt)
        path = ""
        response = None
        try:
            response = get_media_response(
                url,
                request_get=_get_session().get,
                direct_get=direct_media_get,
                stream=True,
                timeout=media_download_timeout(300),
            )
            response.raise_for_status()
            content_type = (getattr(response, "headers", {}) or {}).get(
                "Content-Type", ""
            )
            extension = _guess_suno_extension(
                url, content_type, fallback_extension
            )
            path = os.path.join(
                output_dir,
                f"{filename_prefix}_{uuid.uuid4().hex[:12]}{extension}",
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
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
    raise RuntimeError(
        f"Suno result download failed after {max_retries} attempts: {last_error}"
    )


def _load_suno_wav(path: str) -> Dict[str, Any]:
    with open(path, "rb") as handle:
        return audio_bytes_to_comfy(handle.read(), "wav", 44100)


def _find_suno_ffmpeg() -> Optional[str]:
    configured = str(
        os.environ.get("SEEDANCE_FFMPEG")
        or os.environ.get("FFMPEG_BINARY")
        or ""
    ).strip()
    if configured and os.path.isfile(configured):
        return configured
    path_binary = shutil.which("ffmpeg")
    if path_binary:
        return path_binary
    bundle_candidate = Path(__file__).resolve().parents[3] / "ffmpeg" / "bin" / "ffmpeg.exe"
    return str(bundle_candidate) if bundle_candidate.is_file() else None


def _decode_suno_audio(path: str) -> Dict[str, Any]:
    try:
        import torchaudio

        waveform, sample_rate = torchaudio.load(path)
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0)
        return {
            "waveform": waveform.float().unsqueeze(0),
            "sample_rate": int(sample_rate),
        }
    except Exception:
        pass
    if Path(path).suffix.lower() == ".wav":
        return _load_suno_wav(path)
    ffmpeg = _find_suno_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "Suno audio was downloaded but cannot be decoded; torchaudio failed "
            "and FFmpeg was not found"
        )
    wav_path = f"{path}.decoded.wav"
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                path,
                "-acodec",
                "pcm_s16le",
                wav_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180,
            creationflags=creation_flags,
        )
        if completed.returncode != 0:
            error = completed.stderr.decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"FFmpeg decode failed: {error}")
        return _load_suno_wav(wav_path)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


def download_suno_audio(url: str) -> Tuple[Dict[str, Any], str]:
    path = download_suno_file(url, "suno_audio", "mp3")
    try:
        return _decode_suno_audio(path), path
    except Exception:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


def download_suno_video(url: str) -> Tuple[Any, str]:
    path = download_suno_file(url, "suno_video", "mp4")
    return _video_from_path(path), path


def make_silent_audio(
    sample_rate: int = 44100, duration_seconds: float = 1.0
) -> Dict[str, Any]:
    samples = max(1, int(sample_rate * duration_seconds))
    return {
        "waveform": torch.zeros((1, 1, samples), dtype=torch.float32),
        "sample_rate": int(sample_rate),
    }


class Comfly_suno_music_lowprice:
    """All documented Suno music actions through the domestic low-price API."""

    CATEGORY = "zhenzhen/Seedance2 Low Price"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (
        AUDIO_TYPE,
        AUDIO_TYPE,
        VIDEO_TYPE,
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "audio1",
        "audio2",
        "video",
        "text",
        "primary_url",
        "result_urls",
        "primary_path",
        "result_paths",
        "task_id",
        "response",
    )

    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {}
        for index in range(1, MAX_SUNO_REFERENCE_AUDIOS + 1):
            optional[f"audio{index}"] = (
                AUDIO_TYPE,
                {
                    "tooltip": (
                        f"本地音频素材 {index}，用于 upload、create-voice 或 inspo；"
                        "upload 至少 6 秒，create-voice 需要 10-240 秒。"
                    )
                },
            )
            optional[f"audio_url{index}"] = (
                "STRING",
                {
                    "default": "",
                    "tooltip": (
                        f"公网音频 URL {index}，不能与同槽本地音频同时使用。"
                    ),
                },
            )
        optional["api_config"] = (CONFIG_TYPE,)
        optional["skip_error"] = ("BOOLEAN", {"default": False})
        return {
            "required": {
                "operation": (
                    SUNO_OPERATIONS,
                    {"default": "suno-generation"},
                ),
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "当前操作使用的提示词、歌词或编辑说明。",
                    },
                ),
                "version": (
                    SUNO_VERSIONS,
                    {
                        "default": "v5.5",
                        "tooltip": "仅在当前操作支持版本参数时发送。",
                    },
                ),
                "custom": ("BOOLEAN", {"default": False}),
                "instrumental": ("BOOLEAN", {"default": False}),
                "title": ("STRING", {"default": ""}),
                "style": ("STRING", {"default": ""}),
                "vocal_gender": (
                    ["unspecified", "Male", "Female"],
                    {"default": "unspecified"},
                ),
                "tags": (
                    "STRING",
                    {"multiline": True, "default": ""},
                ),
                "name": ("STRING", {"default": ""}),
                "task_id": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "源 Suno 任务 ID，可连接前一个节点的 task_id 输出。",
                    },
                ),
                "task_id_2": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "mashup 使用的第二个源任务 ID。",
                    },
                ),
                "audio_index": (
                    "INT",
                    {"default": 1, "min": 1, "max": 2147483647, "step": 1},
                ),
                "continue_at": (
                    "FLOAT",
                    {"default": 30.0, "min": 0.0, "step": 0.1},
                ),
                "start_s": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "step": 0.1},
                ),
                "end_s": (
                    "FLOAT",
                    {"default": 30.0, "min": 0.0, "step": 0.1},
                ),
                "duration_s": (
                    "FLOAT",
                    {"default": 5.0, "min": 0.1, "step": 0.1},
                ),
                "speed": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.1, "step": 0.05},
                ),
            },
            "optional": optional,
        }

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        operation=None,
        version=None,
        audio_index=None,
        **kwargs,
    ):
        if operation not in SUNO_ACTION_SPECS:
            return f"Unsupported Suno operation: {operation}"
        allowed_versions = SUNO_ACTION_SPECS[operation]["allowed_versions"]
        if allowed_versions and version not in allowed_versions:
            return (
                f"{operation} does not support version '{version}'; "
                f"allowed: {', '.join(allowed_versions)}"
            )
        if audio_index is not None and int(audio_index) < 1:
            return "audio_index must be at least 1"
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
    def _audio_duration_seconds(audio: Any) -> Optional[float]:
        if not isinstance(audio, dict):
            return None
        waveform = audio.get("waveform")
        sample_rate = int(audio.get("sample_rate") or 0)
        shape = getattr(waveform, "shape", None)
        if not shape or sample_rate <= 0:
            return None
        try:
            return float(shape[-1]) / float(sample_rate)
        except (TypeError, ValueError, IndexError):
            return None

    def _collect_audio_inputs(
        self,
        operation: str,
        values: Dict[str, Any],
        config: Dict[str, Any],
        progress_cb: Callable[[float], None],
    ) -> List[str]:
        if operation not in {"suno-upload", "suno-create-voice", "suno-inspo"}:
            return []
        slots: List[Tuple[int, Any, str]] = []
        for index in range(1, MAX_SUNO_REFERENCE_AUDIOS + 1):
            audio = values.get(f"audio{index}")
            url = self._text(values.get(f"audio_url{index}"))
            if audio is not None and url:
                raise SeedanceLowPriceError(
                    f"audio{index} and audio_url{index} cannot both be used"
                )
            if url:
                parsed = urlsplit(url)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    raise SeedanceLowPriceError(
                        f"audio_url{index} must be an http(s) URL"
                    )
            if audio is not None or url:
                slots.append((index, audio, url))

        if operation in {"suno-upload", "suno-create-voice"}:
            if any(index != 1 for index, _audio, _url in slots):
                raise SeedanceLowPriceError(
                    f"{operation} only accepts audio slot 1"
                )
            if len(slots) != 1:
                raise SeedanceLowPriceError(
                    f"{operation} requires exactly one local audio or URL"
                )
        elif not 1 <= len(slots) <= MAX_SUNO_REFERENCE_AUDIOS:
            raise SeedanceLowPriceError(
                "suno-inspo requires 1-4 local audios or URLs"
            )

        resolved: List[str] = []
        total_uploads = sum(1 for _index, audio, _url in slots if audio is not None)
        uploaded = 0
        for index, audio, url in slots:
            if audio is not None:
                duration = self._audio_duration_seconds(audio)
                if (
                    operation == "suno-upload"
                    and duration is not None
                    and duration < SUNO_UPLOAD_MIN_SECONDS
                ):
                    raise SeedanceLowPriceError(
                        "suno-upload local audio must be at least 6 seconds"
                    )
                if (
                    operation == "suno-create-voice"
                    and duration is not None
                    and not (
                        SUNO_CREATE_VOICE_MIN_SECONDS
                        <= duration
                        <= SUNO_CREATE_VOICE_MAX_SECONDS
                    )
                ):
                    raise SeedanceLowPriceError(
                        "suno-create-voice local audio must be 10-240 seconds"
                    )
                url = upload_media(
                    audio_to_wav_bytes(audio),
                    f"suno_reference_{index}.wav",
                    "audio/wav",
                    config,
                )
                uploaded += 1
                progress_cb(uploaded / max(total_uploads, 1))
            resolved.append(url)
        if total_uploads == 0:
            progress_cb(1.0)
        return resolved

    def _build_payload(
        self,
        operation: str,
        audio_urls: List[str],
        **values,
    ) -> Dict[str, Any]:
        if operation not in SUNO_ACTION_SPECS:
            raise SeedanceLowPriceError(f"Unsupported Suno operation: {operation}")
        spec = SUNO_ACTION_SPECS[operation]
        allowed_fields = set(spec["allowed_fields"])
        payload: Dict[str, Any] = {"model": "suno"}

        version = self._text(values.get("version"))
        allowed_versions = spec["allowed_versions"]
        if allowed_versions:
            if version not in allowed_versions:
                raise SeedanceLowPriceError(
                    f"{operation} does not support version '{version}'; "
                    f"allowed: {', '.join(allowed_versions)}"
                )
            payload["version"] = version

        if "prompt" in allowed_fields:
            prompt = self._text(values.get("prompt"))
            if prompt:
                payload["prompt"] = prompt
        if "tags" in allowed_fields:
            tags = self._text(values.get("tags"))
            if tags:
                payload["tags"] = tags
        if "name" in allowed_fields:
            name = self._text(values.get("name"))
            if name:
                payload["name"] = name

        if operation == "suno-generation":
            payload["custom"] = bool(values.get("custom", False))
            payload["instrumental"] = bool(values.get("instrumental", False))
            for field in ("title", "style"):
                text = self._text(values.get(field))
                if text:
                    payload[field] = text
            vocal_gender = self._text(values.get("vocal_gender"))
            if vocal_gender in {"Male", "Female"}:
                payload["vocal_gender"] = vocal_gender

        if spec["reference_type"] == "task_audio":
            task_id = self._text(values.get("task_id"))
            if task_id:
                payload["task_id"] = task_id
            payload["audio_index"] = int(values.get("audio_index") or 1)
        elif spec["reference_type"] == "mashup":
            task_ids = [
                self._text(values.get("task_id")),
                self._text(values.get("task_id_2")),
            ]
            if all(task_ids):
                payload["task_ids"] = task_ids

        if operation == "suno-upload" and audio_urls:
            payload["audioFilePath"] = audio_urls[0]
        elif operation == "suno-create-voice" and audio_urls:
            payload["audio_url"] = audio_urls[0]
        elif operation == "suno-inspo" and audio_urls:
            payload["audio_urls"] = audio_urls

        for field in ("continue_at", "start_s", "end_s", "duration_s", "speed"):
            if field in allowed_fields:
                raw_value = values.get(field)
                if raw_value not in (None, ""):
                    payload[field] = float(raw_value)

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
        if "task_ids" in payload and len(payload["task_ids"]) != 2:
            raise SeedanceLowPriceError(
                "suno-mashup requires exactly two task IDs"
            )
        if "audio_urls" in payload and not 1 <= len(payload["audio_urls"]) <= 4:
            raise SeedanceLowPriceError("suno-inspo requires 1-4 audio URLs")
        if payload.get("audio_index", 1) < 1:
            raise SeedanceLowPriceError("audio_index must be at least 1")
        if "start_s" in payload and "end_s" in payload:
            if payload["end_s"] <= payload["start_s"]:
                raise SeedanceLowPriceError(
                    "end_s must be greater than start_s"
                )
        return {
            key: value
            for key, value in payload.items()
            if key == "model" or key in allowed_fields
        }

    def _make_error_result(self, message: str) -> Dict[str, Any]:
        response = json.dumps({"error": message}, ensure_ascii=False, indent=2)
        silence = make_silent_audio()
        return {
            "ui": {"text": ["", "", "", "", response]},
            "result": (
                silence,
                silence,
                make_error_video(message),
                "",
                "",
                "[]",
                "",
                "[]",
                "",
                response,
            ),
        }

    def execute(
        self,
        operation: str,
        prompt: str,
        version: str,
        custom: bool,
        instrumental: bool,
        title: str,
        style: str,
        vocal_gender: str,
        tags: str,
        name: str,
        task_id: str,
        task_id_2: str,
        audio_index: int,
        continue_at: float,
        start_s: float,
        end_s: float,
        duration_s: float,
        speed: float,
        api_config: Any = None,
        skip_error: bool = False,
        **kwargs,
    ):
        values = {
            **kwargs,
            "prompt": prompt,
            "version": version,
            "custom": custom,
            "instrumental": instrumental,
            "title": title,
            "style": style,
            "vocal_gender": vocal_gender,
            "tags": tags,
            "name": name,
            "task_id": task_id,
            "task_id_2": task_id_2,
            "audio_index": audio_index,
            "continue_at": continue_at,
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": duration_s,
            "speed": speed,
        }
        try:
            return self._execute_inner(operation, api_config, values)
        except Exception as exc:
            if not skip_error:
                raise
            return self._make_error_result(
                f"Suno Low Price: {type(exc).__name__}: {exc}"
            )

    def _execute_inner(
        self,
        operation: str,
        api_config: Any,
        values: Dict[str, Any],
    ):
        validation = self.VALIDATE_INPUTS(
            operation=operation,
            version=values.get("version"),
            audio_index=values.get("audio_index"),
        )
        if validation is not True:
            raise SeedanceLowPriceError(validation)
        spec = SUNO_ACTION_SPECS[operation]
        config = resolve_config(api_config)
        progress_bar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None
        self._update_progress(progress_bar, 0)

        audio_urls = self._collect_audio_inputs(
            operation,
            values,
            config,
            lambda fraction: self._update_progress(progress_bar, fraction * 15),
        )
        payload = self._build_payload(operation, audio_urls, **values)
        self._update_progress(progress_bar, 15)
        submitted_task_id, submit_response = submit_suno_action(
            spec["action"], payload, config
        )
        self._update_progress(progress_bar, 20)

        final_response = submit_response
        if submitted_task_id:
            final_response = poll_suno_task(
                submitted_task_id,
                config,
                on_progress=lambda progress: self._update_progress(
                    progress_bar, 20 + progress / 100.0 * 65
                ),
            )
        elif not spec["sync"]:
            raise SeedanceLowPriceError(
                f"{operation} returned no task id in its asynchronous response"
            )
        self._update_progress(progress_bar, 85)

        extracted = extract_suno_results(final_response)
        result_task_id = submitted_task_id or extracted["task_id"]
        artifacts = extracted["artifacts"]
        result_paths: List[str] = []
        audio_objects: List[Dict[str, Any]] = []
        video: Any = None
        warnings: List[Dict[str, Any]] = []
        successful_downloads = 0
        artifact_count = max(1, len(artifacts))

        for index, artifact in enumerate(artifacts, start=1):
            url = artifact["url"]
            kind = artifact["kind"]
            path = ""
            try:
                if kind == "audio":
                    audio, path = download_suno_audio(url)
                    audio_objects.append(audio)
                elif kind == "video" and video is None:
                    video, path = download_suno_video(url)
                else:
                    prefix = {
                        "video": "suno_video",
                        "image": "suno_image",
                        "file": "suno_file",
                    }.get(kind, "suno_file")
                    extension = {
                        "video": "mp4",
                        "image": "jpg",
                        "file": "bin",
                    }.get(kind, "bin")
                    path = download_suno_file(url, prefix, extension)
                successful_downloads += 1
            except Exception as exc:
                warnings.append(
                    {
                        "artifact_index": index,
                        "kind": kind,
                        "error": type(exc).__name__,
                    }
                )
                print(
                    f"[Suno Low Price] Artifact {index}/{artifact_count} "
                    f"({kind}) download failed: {type(exc).__name__}"
                )
            result_paths.append(path)
            self._update_progress(
                progress_bar,
                85 + min(10, index / artifact_count * 10),
            )

        if artifacts and successful_downloads == 0:
            raise SeedanceLowPriceError(
                "All Suno result artifacts failed to download"
            )

        all_urls = [artifact["url"] for artifact in artifacts]
        text = extracted["text"]
        if not text and spec["result_family"] in {"text", "file"}:
            text = json.dumps(extracted["result"], ensure_ascii=False, indent=2)
        response_payload: Dict[str, Any] = final_response
        if warnings:
            response_payload = dict(final_response)
            response_payload["_zhenzhen_local"] = {"download_warnings": warnings}
        response = json.dumps(response_payload, ensure_ascii=False, indent=2)
        primary_url = all_urls[0] if all_urls else ""
        primary_path = result_paths[0] if result_paths else ""
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
                audio_objects[0] if audio_objects else None,
                audio_objects[1] if len(audio_objects) > 1 else None,
                video,
                text,
                primary_url,
                json.dumps(all_urls, ensure_ascii=False),
                primary_path,
                json.dumps(result_paths, ensure_ascii=False),
                result_task_id,
                response,
            ),
        }


__all__ = [
    "Comfly_seedance2_low_price_settings",
    "Comfly_seedance2_low_price",
    "Comfly_seedance25_standard_low_price",
    "Comfly_sd2_seedream_v5_pro_lowprice",
    "Comfly_seedream_v5_pro_layer_decomposition_lowprice",
    "Comfly_zhenzhen_image_g2_lowprice",
    "Comfly_zhenzhen_image_g_v2_lowprice",
    "Comfly_zhenzhen_image_nb_lowprice",
    "Comfly_zhenzhen_video_g_omni_flash_lowprice",
    "Comfly_zhenzhen_video_gk_v15_lowprice",
    "Comfly_zhenzhen_video_v31_lowprice",
    "Comfly_whisper_1_lowprice",
    "Comfly_zhenzhen_image_gk_v15_lowprice",
    "Comfly_happyhorse_1_1_lowprice",
    "Comfly_wan_2_7_spicy_i2v_lowprice",
    "Comfly_kling_video_lowprice",
    "Comfly_kling_o3_edit_lowprice",
    "Comfly_hailuo_2_3_video_lowprice",
    "Comfly_hailuo_h3_video_lowprice",
    "Comfly_minimax_h3_ow_video_lowprice",
    "Comfly_minimax_h3_ow_fast_video_lowprice",
    "Comfly_vidu_q3_video_lowprice",
    "Comfly_vidu_q3_short_play_lowprice",
    "Comfly_zhenzhen_upscaler_lowprice",
    "Comfly_doubao_seed_audio_1_0_lowprice",
    "Comfly_qwen_image_3_0_lowprice",
    "Comfly_suno_music_lowprice",
]

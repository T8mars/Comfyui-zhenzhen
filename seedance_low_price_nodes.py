"""Seedance 2.0 low-price settings and unified video node."""

from __future__ import annotations

import io
import json
import os
import ssl
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import requests
import torch
from PIL import Image

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


class SeedanceLowPriceError(RuntimeError):
    """Non-retryable Seedance API or input error."""


_CONFIG_LOCK = threading.RLock()


def _config_path() -> Path:
    return Path(__file__).resolve().parent / "Comflyapi.json"


def _read_project_config(strict: bool = False) -> Dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        with _CONFIG_LOCK:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        if strict:
            raise SeedanceLowPriceError(
                f"Cannot safely update invalid config file {path.name}: {exc}"
            ) from exc
        return {}


def _write_project_config(config: Dict[str, Any]) -> None:
    path = _config_path()
    with _CONFIG_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=4)
        os.replace(temp_path, path)


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
    """Resolve settings node, independent project config, then environment."""
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
        stored = _read_project_config()
        api_key = str(stored.get("seedance2_low_price_api_key") or "").strip()
        if api_key:
            base_url = str(stored.get("seedance2_low_price_base_url") or "").strip()
            source = "Comflyapi.json"

    if not api_key:
        api_key = str(os.environ.get("SEEDANCE_API_KEY") or "").strip()
        base_url = str(os.environ.get("SEEDANCE_BASE_URL") or "").strip()
        if api_key:
            source = "environment"

    if not api_key:
        raise SeedanceLowPriceError(
            "Seedance API key is required. Connect the Low Price Settings node, "
            "save its independent key, or set SEEDANCE_API_KEY."
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
        with _CONFIG_LOCK:
            config = _read_project_config(strict=True)
            normalized_key = str(api_key or "").strip()
            if not normalized_key:
                normalized_key = str(config.get("seedance2_low_price_api_key") or "").strip()
            if not normalized_key:
                raise SeedanceLowPriceError(
                    "api_key cannot be empty until a key has been saved locally once"
                )

            config["seedance2_low_price_base_url"] = normalized_base
            config["seedance2_low_price_api_key"] = normalized_key
            _write_project_config(config)
        print(f"[Seedance Low Price Settings] Saved independent config for {normalized_base}")
        return ({"base_url": normalized_base, "api_key": normalized_key},)


class _TruststoreAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, context: ssl.SSLContext):
        self._context = context
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs["ssl_context"] = self._context
        return super().proxy_manager_for(*args, **kwargs)


_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    session = requests.Session()
    verify_value = os.environ.get("SEEDANCE_SSL_VERIFY", "1").strip().lower()
    if verify_value in ("0", "false", "no"):
        session.verify = False
        print("[Seedance Low Price] WARNING: SSL verification is disabled")
    else:
        try:
            import truststore

            context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            session.mount("https://", _TruststoreAdapter(context))
        except ImportError:
            pass
        except Exception as exc:
            print(f"[Seedance Low Price] truststore unavailable, using requests CA: {exc}")
    _SESSION = session
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


def download_video(url: str, max_retries: int = 3) -> Any:
    try:
        import folder_paths

        output_dir = folder_paths.get_output_directory()
    except ImportError:
        output_dir = os.environ.get("SEEDANCE_OUTPUT_DIR") or tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"seedance_low_price_{uuid.uuid4().hex[:12]}.mp4")
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            response = _get_session().get(url, stream=True, timeout=300)
            response.raise_for_status()
            with open(path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)
            if os.path.getsize(path) == 0:
                raise RuntimeError("downloaded video is empty")
            return _video_from_path(path)
        except Exception as exc:
            last_error = exc
    try:
        os.remove(path)
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


SEEDREAM_MODES = ["text_to_image", "image_edit"]
SEEDREAM_MODELS = {
    "text_to_image": "seedream-v5-pro-t2i",
    "image_edit": "seedream-v5-pro-i2i",
}
SEEDREAM_RESOLUTIONS = ["1k", "2k", "custom"]
SEEDREAM_OUTPUT_FORMATS = ["png", "jpeg"]
SEEDREAM_PROMPT_MIN_LENGTH = 5
SEEDREAM_PROMPT_MAX_LENGTH = 2000
SEEDREAM_IMAGE_MAX_BYTES = 10 * 1024 * 1024


def validate_seedream_inputs(
    mode: str,
    prompt: str,
    resolution: str,
    width: int,
    height: int,
    output_format: str,
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
) -> Dict[str, Any]:
    validate_seedream_inputs(mode, prompt, resolution, width, height, output_format)
    metadata: Dict[str, Any] = {"output_format": output_format}
    if resolution == "custom":
        metadata["width"] = int(width)
        metadata["height"] = int(height)
    else:
        metadata["resolution"] = resolution
    payload: Dict[str, Any] = {
        "model": SEEDREAM_MODELS[mode],
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


def _pil_to_image_tensor(image: Image.Image) -> torch.Tensor:
    array = np.asarray(image.convert("RGB"), dtype=np.float32).copy() / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def download_image(url: str, max_retries: int = 3) -> torch.Tensor:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            response = _get_session().get(url, timeout=300)
            response.raise_for_status()
            with Image.open(io.BytesIO(response.content)) as image:
                return _pil_to_image_tensor(image)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Seedream image download failed after {max_retries} attempts: {last_error}")


class Comfly_sd2_seedream_v5_pro_lowprice:
    @classmethod
    def INPUT_TYPES(cls):
        optional: Dict[str, tuple] = {
            "api_config": (CONFIG_TYPE,),
            "skip_error": ("BOOLEAN", {"default": False}),
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
        **kwargs,
    ):
        if None in (mode, resolution):
            return True
        try:
            validate_seedream_inputs(
                mode, prompt or "", resolution, width, height, output_format
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
        **kwargs,
    ):
        task_id = ""
        model = SEEDREAM_MODELS.get(mode, "")
        pbar = comfy.utils.ProgressBar(100) if COMFYUI_AVAILABLE else None

        def update_progress(value: int) -> None:
            if pbar is not None:
                try:
                    pbar.update_absolute(value, 100)
                except Exception:
                    pass

        try:
            validate_seedream_inputs(mode, prompt, resolution, width, height, output_format)
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


__all__ = [
    "Comfly_seedance2_low_price_settings",
    "Comfly_seedance2_low_price",
    "Comfly_sd2_seedream_v5_pro_lowprice",
]

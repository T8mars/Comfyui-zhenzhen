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


class _SSLContextAdapter(requests.adapters.HTTPAdapter):
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

    if not BUNDLED_ROOT_YR_CERT.is_file():
        raise RuntimeError(
            f"Bundled TLS certificate is missing: {BUNDLED_ROOT_YR_CERT.name}"
        )

    context = ssl.create_default_context(cafile=requests.certs.where())
    context.load_verify_locations(cafile=str(BUNDLED_ROOT_YR_CERT))

    session = requests.Session()
    session.mount(
        f"{DEFAULT_BASE_URL}/",
        _SSLContextAdapter(context),
    )
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


def extract_audio_url(response: Dict[str, Any]) -> str:
    candidates: List[Any] = []
    if isinstance(response, dict):
        candidates.extend(
            [response.get("result_url"), response.get("audio_url"), response.get("url")]
        )
        data = response.get("data")
        if isinstance(data, dict):
            candidates.extend(
                [data.get("result_url"), data.get("audio_url"), data.get("url")]
            )
            nested = data.get("data")
            if isinstance(nested, dict):
                candidates.extend(
                    [nested.get("result_url"), nested.get("audio_url"), nested.get("url")]
                )
                content = nested.get("content")
                if isinstance(content, dict):
                    candidates.extend([content.get("audio_url"), content.get("url")])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    raise SeedanceLowPriceError(
        "Seed Audio completed response did not contain an audio URL"
    )


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

    try:
        import torchaudio
    except ImportError as exc:
        raise SeedanceLowPriceError(
            "MP3/Opus decoding requires ComfyUI's built-in torchaudio; use wav output "
            "or repair the ComfyUI Python environment"
        ) from exc

    format_hint = "ogg" if output_format == "ogg_opus" else output_format
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
        try:
            response = _get_session().get(url, timeout=300)
            response.raise_for_status()
            return audio_bytes_to_comfy(
                response.content, output_format, expected_sample_rate
            )
        except Exception as exc:
            last_error = exc
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


__all__ = [
    "Comfly_seedance2_low_price_settings",
    "Comfly_seedance2_low_price",
    "Comfly_sd2_seedream_v5_pro_lowprice",
    "Comfly_happyhorse_1_1_lowprice",
    "Comfly_wan_2_7_spicy_i2v_lowprice",
    "Comfly_kling_video_lowprice",
    "Comfly_kling_o3_edit_lowprice",
    "Comfly_hailuo_2_3_video_lowprice",
    "Comfly_vidu_q3_video_lowprice",
    "Comfly_vidu_q3_short_play_lowprice",
    "Comfly_zhenzhen_upscaler_lowprice",
    "Comfly_doubao_seed_audio_1_0_lowprice",
]
